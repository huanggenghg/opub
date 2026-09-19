# Issue 报告：视频号/快手/B站 发布失败诊断（2026-09-19）

> 环境：macOS (darwin, x86_64)，opub 0.8.10（68de10d），WorkBuddy 沙箱内运行（patchright Chromium + Chrome channel）。
> 当轮结果：抖音/小红书/百家号/微博 ✅ 成功；视频号/快手/B站 ❌ 失败。以下为逐平台复现与根因。

## 1. 视频号（tencent）：cookie 已失效，但登录检查误报 PAGE-001，未触发扫码

**现象**：发布报 `PAGE-001 登录检查页面未能识别，尚未确认登录失效`，有头/无头一致，单跑复现。

**复现**（storage_state 用 cookies/tencent_uploader/account.json，headless chromium）：

```
goto https://channels.weixin.qq.com/platform/post/create (domcontentloaded) + 5s
FINAL_URL: https://channels.weixin.qq.com/login.html
TITLE:     视频号助手
```

**根因**：cookie 失效后页面 302 到 `login.html`，但 `cookie_auth` 的判定链没有把这次跳转识别为"登录失效"：

- URL 不等于 UPLOAD_URL → 走 `LoginCheckError('page')`（PAGE-001），而不是返回 False 触发扫码；
- 该跳转是登录失效的确定性证据（非慢加载、非风控页）。

**建议修复**：`cookie_auth` 中 URL 校验前先检查"当前 URL 是否落在 LOGIN_URL（login.html）"——是则 `return False`（登录失效），让上层走扫码流程；其余 URL 不匹配再保留 PAGE-001。

## 2. 快手（kuaishou）：页面改版导致登录完成判定失灵（PAGE-001）

**现象**：发布报 `PAGE-001`，单跑 13s 即失败，稳定复现。手动加载页面 URL **不发生跳转**、标题正常（"快手创作者服务平台"），`main#login-form` 数量为 0（不是登录页）。

**页面实测**（headless chromium，storage_state 用 cookies/ks_uploader/account.json）：

```
FINAL_URL: https://cp.kuaishou.com/article/publish/video   ← 未跳转
TITLE:     快手创作者服务平台
button[class^="_upload-btn"] 匹配数: 0        ← 旧判定选择器失效
页面 button 共 1 个: class='el-button confirm__btn el-button--primary el-button--medium', 文本="确定"
main#login-form: 0
```

**根因**：上传页改版，出现一个带 `el-button confirm__btn`（"确定"）的弹窗，旧选择器 `button[class^="_upload-btn"]` 已匹配不到；`is_login_completed` 找不到上传按钮 → False → PAGE-001。cookie 本身很可能仍有效。

**建议修复**：
1. 页面加载后若存在 `el-button.confirm__btn` 弹窗先点击"确定"关闭，再判定；
2. 更新/兜底上传按钮选择器（新页面类名走 element-plus 体系，建议同时用文本或稳定容器定位做 fallback）。

## 3. B站（bilibili）：biliup 登录检查 NET-001（网络超时）

**现象**：发布报 `NET-001 登录检查时网络连接失败或超时`（有头批跑，duration ~7min）。biliup 二进制 v1.2.2 在位（只读预检通过），疑似 `list/renew` 查询 60s 超时。同机同时段其他平台网络正常。

**建议排查**：本机直接跑 `~/.opub/tools/biliup/macos-x86_64/biliup` 对应查询子命令看是否可复现超时；确认是否为 biliup 与 B站接口的偶发网络问题或代理环境变量（HTTP_PROXY 等）被沙箱环境改变所致。

## 4. 附带观察：多平台批跑的偶发 ENV-006

同一素材批量跑 7 平台时，抖音/百家号随机报 `ENV-006`（本机环境或账号文件不可用）；**单平台重跑即成功**（两平台均复现"批跑失败→单跑成功"）。疑似多浏览器并发资源竞争/启动竞态，建议并发登录检查加串行化或重试一次。

## 5. 沙箱环境注意（非 opub bug）

WorkBuddy 沙箱会拦截 Chrome channel 启动时的 `code_sign_clone`、`GoogleUpdater` 写入（stderr 告警，不致命，抖音/百家号仍成功）。sqlite 在 `~/.opub` 下会被沙箱代理破坏（disk I/O error），需用 `SAU_HOME` 指到可写工作区。
