# 微信视频号发布流程代码链路

> 行号基于 2026-08-04 代码状态。代码改动后行号会偏移,函数名为主索引。

## 概述

微信视频号(tencent)的发布流程从 `publish_all.py` 入口开始,经过登录校验、进入发布页、上传视频、填写元数据、触发发布 5 个阶段。本文档梳理每个阶段的代码调用链,标注文件:行号,并说明微信视频号的特殊性( sessionid 快速失效、不暴露发布内容 URL、QR 在 iframe 内)。

## 阶段 0:入口

```
publish_all.py:73  main()
  └─ publish/orchestrator.py:282  main()
       └─ publish/orchestrator.py:204  run_publish()
            └─ publish/orchestrator.py:96  run_publish_with_params()
                 └─ publish/orchestrator.py:172  for video_file in video_files:
                      └─ publish/orchestrator.py:31  publish_one_item(video_params)
```

## 阶段 1:登录校验

`publish_one_item` 对每个启用平台先调 `ensure_account_login`,确保已登录。

```
publish/orchestrator.py:64-67  if platform_requires_account_login(platform):
  └─ publish/orchestrator.py:67  login_ok = await ensure_account_login(platform, account_file)
       └─ publish/dispatch.py:40  ensure_account_login()
            └─ publish/dispatch.py:22  ensure_login(platform, account_file)
                 │
                 ├─ publish/dispatch.py:31-33  if os.path.exists(account_file):
                 │    └─ cookie_auth(account_file)              [uploader/tencent_uploader/main.py:264]
                 │         └─ TencentBaseUploader.cookie_auth() [uploader/tencent_uploader/main.py:409]
                 │              🔧 2026-08-04 修复:只检查文件存在性,不开浏览器
                 │              (原版开浏览器 #1 让 sessionid 失效,是卡死根因)
                 │         ✅ 文件存在 -> return True(跳过重新登录,直接进 upload)
                 │         ❌ 文件不存在 -> 走重新登录 ↓
                 │
                 └─ publish/dispatch.py:36-37  setup_func(account_file, handle=True)
                      └─ tencent_setup(handle=True)              [uploader/tencent_uploader/main.py:338]
                           ├─ 🔧 2026-08-04 修复:handle=True 总是扫码(不 return True)
                           └─ main.py:353  tencent_cookie_gen()  [uploader/tencent_uploader/main.py:270]
                                ├─ 开浏览器 #1,page.goto(LOGIN_URL) [main.py:287]
                                ├─ _save_tencent_qrcode()        [main.py:87]
                                │    └─ _extract_tencent_qrcode_src()  [main.py:55]
                                │         ❌ 抛 RuntimeError(选择器 login-for-iframe 失效)
                                │         🔧 2026-08-04 修复:try/except 包裹,失败只 warning
                                │            继续走 _wait_for_tencent_login,不 abort
                                ├─ _wait_for_tencent_login()     [main.py:225]
                                │    └─ 轮询 _is_tencent_login_completed()  [main.py:118]
                                │         ├─ 检查 publish marker(发表视频/发表/保存草稿)
                                │         └─ 检查 login marker(qrcode-wrap 等)
                                ├─ 登录成功后:
                                │    └─ context.storage_state(path=account_file)  [main.py:311]
                                │       ★ 这里保存 cookie(扫码后只有 sessionid/wxuin 2 个)
                                │       ★ cookie_auth() 调用变成 no-op(只检查文件存在性)
                                └─ 关浏览器 #1
```

## 阶段 2:进入发布页 + 上传 + 填写

登录校验通过后,`publish_one_item` 调 `publish_to_platform`。

```
publish/orchestrator.py:84  result = await publish_to_platform(platform, platform_params)
  └─ publish/dispatch.py:326  publish_to_platform()
       └─ publish/dispatch.py:151  publish_to_tencent(params)
            ├─ publish/dispatch.py:163  TencentVideo.validate_base_args(params)  [uploader/base_video.py:88]
            ├─ publish/dispatch.py:168  uploader = TencentVideo(...)
            └─ publish/dispatch.py:173  return await uploader.upload()
                 │
                 │  ── TencentVideo.upload()  [uploader/tencent_uploader/main.py:748] ──
                 │
                 ├─ main.py:752  validate_upload_args()      [main.py:652]
                 │    └─ validate_login_and_strategy()       [main.py:448]
                 │         ├─ 检查 cookie 文件存在           [main.py:452]
                 │         │   (🔧 2026-08-04 修复:去掉冗余 cookie_auth,不再开浏览器 #2)
                 │         ├─ 检查 publish_strategy         [main.py:456]
                 │         └─ 检查 publish_date(定时发布)   [main.py:459]
                 │
                 ├─ main.py:758  async with self._browser_session(save_on_success_only=True, save_state=False):
                 │    │   [uploader/base_video.py:297]
                 │    │   ├─ 开浏览器 #3,加载 storage_state
                 │    │   ├─ yield page
                 │    │   ├─ (退出时 save_state=False -> 不覆盖 cookie 文件)
                 │    │   │   🔧 2026-08-04 修复:之前 publish 成功后 storage_state 覆盖
                 │    │   │   cookie 文件,只剩 sessionid/wxuin 2 个,下次 cookie_auth 必失败
                 │    │   └─ 关浏览器 #3
                 │    │
                 │    └─ upload_video_content(page)          [main.py:732]
                 │         │
                 │         ├─ open_upload_page(page)         [main.py:488]
                 │         │    └─ page.goto(UPLOAD_URL)
                 │         │
                 │         ├─ upload_video_file(page, file_path)  [main.py:492]
                 │         │    └─ file_input.set_input_files(file_path)
                 │         │
                 │         ├─ prepare_video_for_publish(page)     [main.py:726]
                 │         │    ├─ fill_title_and_tags()          [main.py:506]
                 │         │    │    └─ div.input-editor click + keyboard.type(title)
                 │         │    ├─ fill_description()             [main.py:511]
                 │         │    │    └─ Enter + keyboard.type(desc)
                 │         │    │    └─ for tag: keyboard.type(" #" + tag)
                 │         │    ├─ apply_collection()              [main.py:520]
                 │         │    └─ apply_original_statement()     [main.py:530]
                 │         │
                 │         ├─ wait_for_upload_complete(page)      [main.py:567]
                 │         │    └─ while True:
                 │         │         ├─ 检查 "发表" 按钮 class 是否还 disabled
                 │         │         ├─ 检查 div.status-msg.error(上传出错)
                 │         │         └─ asyncio.sleep(2)
                 │         │
                 │         ├─ set_thumbnail(page)  [可选]         [main.py:666]
                 │         │
                 │         ├─ if 定时发布: set_schedule_time_tencent()  [main.py:464]
                 │         │
                 │         ├─ set_short_title(page, title)        [main.py:496]
                 │         │
                 │         └─ submit_publish(page)                [main.py:588]
                 │              └─ while True:
                 │                   ├─ if is_draft: 点 "保存草稿"
                 │                   │   else: 点 "发表"           [main.py:598]
                 │                   ├─ wait_for_url(MANAGE_URL, 5s) [main.py:601]
                 │                   │   ★ 跳到管理页 = 发布成功
                 │                   └─ 异常时检查 URL 是否已跳转
                 │
                 └─ main.py:760  result["success"] = True
                                 result["message"] = "发布成功"
                    main.py:749  ★ result 不含 result_url
                                 (微信视频号不暴露已发布视频 URL)
```

## 阶段 3:拿发布内容链接

```
upload() 返回 result = {"success": True, "message": "发布成功", "result_url": "https://weixin.qq.com/sph/XXX"}
                          ↑ result_url 通过 API 抓取(不走 UI 分享弹框)

tencent: publish/dispatch.py:151-176  publish_to_tencent() 有 write_video_link 调用
        uploader/tencent_uploader/main.py  upload_video_content() 在 submit_publish 后调:
          └─ _fetch_published_video_short_url(page)   [TencentBaseUploader]
               ├─ page.goto(MANAGE_URL) 重新加载管理页
               ├─ 拦截 post_list 响应 -> 取第一个视频的 exportId + objectNonce
               ├─ 拦截 auth_data 响应 -> 取 finderUsername (_log_finder_id)
               ├─ 从 post_list 请求 URL 提取 _aid
               └─ page.evaluate(fetch(get_object_short_link)) -> data.shortUrl
                  POST /micro/content/cgi-bin/mmfinderassistant-bin/post/get_object_short_link
                  body: {exportId, nonceId, scene:40, timestamp, _log_finder_id, reqScene:7, ...}
                  resp: {"errCode":0,"data":{"shortUrl":"https://weixin.qq.com/sph/XXX"}}
```

**为什么走 API 而不是 UI**:管理页的"分享"按钮在 Shadow DOM 里,Vue @click 处理器
不在祖先链上(cursor=auto),Playwright click + JS el.click() + dispatchEvent 都触发不了。
直接调 `get_object_short_link` API 绕过 UI,更稳定。

## 关键节点速查

| 节点 | 文件:行号 | 干什么 | 浏览器上下文 |
|---|---|---|---|
| cookie 预检 | `tencent/main.py:409` | `cookie_auth` 只检查文件存在性,**不开浏览器** | - |
| QR 登录 | `tencent/main.py:270` | `tencent_setup(handle=True)` 总是扫码 | #1 扫码浏览器 |
| ~~cookie 二次校验~~ | ~~`tencent/main.py:454`~~ | 🔧 2026-08-04 已删除:`validate_login_and_strategy` 不调 cookie_auth | - |
| 上传+发布 | `base_video.py:297` | `_browser_session(save_state=False)` 加载 cookie 发布 | #2 |
| 成功判定 | `tencent/main.py:601` | URL 跳到 `post/list` 即成功 | - |
| 内容链接 | `tencent/main.py` `_fetch_published_video_short_url` | 调 `get_object_short_link` API 拿 sph 短链 | 复用 #2 |

## 微信视频号的特殊性

1. **sessionid 在新浏览器上下文里快速失效**
   - 实测 22 秒即失效(memory 里记 2-5 分钟,已过时)
   - 每次开新浏览器上下文都重新挑战
   - cookie 文件本身 expires 是 2027 年,是服务端 session 失效,不是 cookie 过期

2. **分享链接通过 API 抓取,不走 UI**
   - 管理页"分享"按钮在 Shadow DOM 里,Vue @click 不在祖先链上,click 触发不了
   - 直接调 `get_object_short_link` API:`post_list` 取 `exportId`+`objectNonce`,`auth_data` 取 `finderUsername`,POST 拿 `shortUrl`
   - 短链格式:`https://weixin.qq.com/sph/XXXXXXXX`
   - 复用发布时的浏览器 session(cookie 有效),不需要重新登录

3. **QR 在 qrconnect iframe 里**
   - 登录页 DOM 结构:1 个 iframe,src 是 `https://open.weixin.qq.com/connect/qrconnect?appid=...`
   - 二维码 img 在 iframe 内部,class 是 `qrcode lightBorder js_qrcode_img`
   - img 的 src 是相对 URL `/connect/qrcode/...`,不是 `data:image/`
   - 旧选择器 `iframe[src*="login-for-iframe"]` 已失效
   - headless=False 时用户能直接在浏览器窗口扫码(不依赖终端 QR 提取)

## 当前已知问题(2026-08-04 实测状态)

### 已修复(2026-08-04)

| # | 问题 | 修复位置 | 修复方式 |
|---|---|---|---|
| 1 | QR 提取失败 abort 整个登录流程 | `tencent/main.py:288-296` | `_save_tencent_qrcode` 包 try/except,失败只 warning,继续 `_wait_for_tencent_login` |
| 2 | publish 成功后 storage_state 覆盖 cookie 文件,只剩 2 个 cookie | `tencent/main.py:758, 853` + `base_video.py:297` | `_browser_session` 加 `save_state` 参数,tencent upload() 传 `save_state=False` |
| 3 | 多次 cookie_auth 之间 sessionid 快速失效 | `tencent/main.py:347, 409, 454` | 三处改动:`cookie_auth` 只检查文件存在性不开浏览器;`tencent_setup(handle=True)` 总是扫码;`validate_login_and_strategy` 不调 cookie_auth |

### 修复 #3 详情

**原问题**:tencent sessionid 在新浏览器上下文里 22 秒失效。原流程有 3 处 `cookie_auth` 调用(`ensure_login`、`tencent_setup`、`validate_login_and_strategy`),每次都开新浏览器,让 sessionid 加速失效。实测:第一次 `cookie_auth` 通过后 48 秒,第二次 `cookie_auth` 在新浏览器里失效,误判 cookie 失效,直接 raise,`_browser_session` 没机会跑。

**实测时间线**(修复前):

| 时间 | 事件 | 浏览器 |
|---|---|---|
| 00:27:35 | ① `ensure_login` cookie_auth ✅ 通过 | #1 开->关 |
| 00:28:01 | ② `upload()` 开始 | - |
| 00:28:23 | ② `validate_login_and_strategy` cookie_auth ❌ 失效 | #2 开->关 |
| 00:28:23 | raise `RuntimeError("cookie文件已失效")`,upload() 返回失败 | - |
| - | ③ `_browser_session` 没走到 | - |

**修复方案**(三处改动):

1. **`TencentBaseUploader.cookie_auth`** (main.py:409) -- 改成只检查文件存在性,不开浏览器。根因:主动开浏览器校验本身就让 sessionid 失效,所以不校验,实际校验交给 `_browser_session` 导航时暴露(被重定向到 login.html -> `set_input_files` 找不到 input -> upload() 失败)。

2. **`tencent_setup`** (main.py:347) -- `handle=True` 时总是扫码,不管文件是否存在。根因:`ensure_login` 调到 `tencent_setup` 就说明 cookie 已失效(或文件不存在),这时 return True 会让 upload() 用失效 cookie 进 `_browser_session` 失败。

3. **`validate_login_and_strategy`** (main.py:454) -- 不调 `cookie_auth`,只检查文件存在性。`ensure_login` 已验过,再开浏览器是冗余。

**实测时间线**(修复后,2026-08-04 10:55):

| 时间 | 事件 | 浏览器 |
|---|---|---|
| 10:55:04 | `tencent_setup(handle=True)` 触发扫码 | #1 扫码浏览器开 |
| 10:55:43 | 扫码成功,存 cookie | #1 关 |
| 10:55:51 | `validate_upload_args` 开始(扫码后 8 秒) | - |
| 10:55:51 | `validate_login_and_strategy` 通过(不调 cookie_auth) | - |
| 10:55:57 | `_browser_session` 加载 cookie,开始上传 | #2 开 |
| 10:56:12 | 视频发布成功 | #2 关 |

整个流程只开 2 个浏览器(扫码 + `_browser_session`),sessionid 在 8 秒内没失效。

**测试**:`tests/test_tencent_uploader_base.py::TencentRedundantCookieAuthTests` 四个测试覆盖:
- `tencent_setup(handle=True)` 文件存在时也扫码(不 return True)
- `tencent_setup(handle=True)` 文件不存在时扫码
- `validate_login_and_strategy` 不调 cookie_auth
- `cookie_auth` 只检查文件存在性,不开浏览器

**遗留语义变化**:
- `cookie_auth` 不再实际校验 cookie 有效性,只检查文件存在性。cookie 实际失效时,在 `_browser_session` 导航时暴露,upload() 失败,用户需手动删 cookie 文件重扫。
- `tencent_setup(handle=True)` 总是扫码,不管文件是否存在。`examples/get_tencent_cookie.py` 想扫码时直接跑即可。
- 主动校验 tencent cookie 本身就是有毒的操作(开新浏览器让 sessionid 失效),所以这些语义变化是接受的。

**Follow-up 优化(未做)**:`_browser_session` 导航到上传页后,可检查是否被重定向到 login.html,自动触发重新扫码。当前需要用户手动删 cookie 文件重扫。

## 相关文件

- `publish_all.py` - 入口薄壳
- `publish/orchestrator.py` - 发布编排
- `publish/dispatch.py` - 平台分发 + 登录校验
- `uploader/tencent_uploader/main.py` - 微信视频号上传器主逻辑
- `uploader/base_video.py` - `BaseBrowserUploader` 基类(`_browser_session`、`cookie_auth` 模板)
- `login_tencent.py` - 手动扫码登录脚本(绕过自动 QR 提取)
- `refresh_tencent_cookie.py` - 刷新 cookie(导航到上传页等 marker 再存)
- `probe_tencent_qrcode.py` - DOM 探查脚本(验证 QR 选择器)
- `probe_tencent_cookie_check.py` - cookie 校验时序探查脚本
- `tests/test_tencent_uploader_base.py` - 单元测试
