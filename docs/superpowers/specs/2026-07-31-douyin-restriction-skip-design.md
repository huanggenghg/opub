# 抖音账号被限制发布(健康分不足)场景的检测与跳过设计

## 背景

抖音账号可能因"健康分不足"等平台限制,出现"能登录但无法发布"的状态:cookie 仍有效(账号在登录态),但平台在上传资源时用 Semi UI error toast 拦截,导致发布流程卡死。

现有流程对此场景的处理是**误判为 `login_failed`**(原因见下文"cookie_auth 5 秒超时问题"),消息具有误导性,且用户无法区分"真的登录失败"和"被平台限制发布"。

## 真实信号(基于实测)

用被限制账号 + MutationObserver 捕获到限制信号:

- **DOM 元素:** `.semi-toast.semi-toast-error`(外层 `.semi-toast-wrapper`)
- **toast 文本(实测):** `作品发布失败，健康分不足投稿功能受限，详情请查看抖音app-安全中心-健康分`
- **出现时机:** `set_input_files` 触发后 **167ms** 弹出
- **持久性:** 3 秒后仍可见(非瞬时)
- **触发范围:** 视频和图片上传均触发(用户确认)

## cookie_auth 5 秒超时问题(前置修复)

调查中发现 `cookie_auth` 的 `wait_for_url(timeout=5000)` 太短:被限制账号的页面要 10-25 秒才渲染出 publish 标记(发布视频/发布图文/input[file])。5 秒时页面还在"加载中",`_is_douyin_auth_page_valid` 因 publish 标记不可见而返回 False,`cookie_auth` 误判 cookie 失效。

后果:账号被标为 `login_failed` 跳过,`publish_to_platform` 不会被调用,限制检测(在 `upload()` 里)永远跑不到。

**修复:** 在 `wait_for_url` 之后、`_is_douyin_auth_page_valid` 之前,等 publish 标记渲染(最多 20 秒)。

## 架构

```
publish_one_item (publish_all.py)
  ├─ ensure_account_login -> cookie_auth          [修] 等 publish 标记渲染,最多 20s
  ├─ publish_to_platform -> publish_to_douyin
  │   └─ DouYinVideo.upload() / DouYinNote.upload_note_content()
  │       ├─ page.goto(upload_url) + wait_for_url             [现有]
  │       ├─ set_input_files(...)                              [现有]
  │       ├─ ★ _check_douyin_publish_restriction(page)         [新增] 等 .semi-toast-error,2s 超时
  │       │     └─ 出现 -> raise DouyinPublishRestrictedError(toast_text)
  │       └─ ...后续上传/发布流程不变...
  └─ publish_to_douyin 捕获 DouyinPublishRestrictedError
      └─ 返回 {account_issue:True, issue_type:"publish_restricted", message 含 toast 文本}
            ↓
       现有 run_publish_with_params 末尾汇总打印 account_issue(无需改动)
```

**范围:** 只针对抖音。其他平台(快手/腾讯/百家号/微博)不在本次范围。

## 组件

### 1. `cookie_auth` 修复(`uploader/douyin_uploader/main.py`)

在 `wait_for_url` 之后、`_is_douyin_auth_page_valid` 之前,等 publish 标记渲染:

```python
await page.goto(DOUYIN_UPLOAD_URL)
try:
    await page.wait_for_url(DOUYIN_UPLOAD_URL, timeout=5000)
except Exception:
    return False
try:
    await page.get_by_text("发布视频", exact=True).first.wait_for(state="visible", timeout=20000)
except Exception:
    pass
return await _is_douyin_auth_page_valid(page)
```

### 2. 异常类 `DouyinPublishRestrictedError`

```python
class DouyinPublishRestrictedError(Exception):
    """抖音账号被限制发布(如健康分不足)时抛出。"""
    def __init__(self, toast_text: str):
        self.toast_text = toast_text
        super().__init__(f"账号被限制发布: {toast_text}")
```

### 3. 检测函数 `_check_douyin_publish_restriction`

```python
async def _check_douyin_publish_restriction(page: Page, timeout_ms: int = 2000) -> str | None:
    """set_input_files 后检查是否出现限制 toast。返回 toast 文本,无则 None。"""
    toast = page.locator('.semi-toast-error').first
    try:
        await toast.wait_for(state="visible", timeout=timeout_ms)
        text = await toast.inner_text()
        return text.strip() or None
    except Exception:
        return None
```

基于真实数据:toast 在 set_input_files 后 167ms 出现,2 秒超时余量充足,单次等待非轮询。

### 4. 调用点

**`DouYinVideo.upload()`(`set_input_files` 之后、`while True` 等发布表单页之前插入):**

```python
await page.locator("div[class^='container'] input").set_input_files(self.file_path)

restriction_text = await _check_douyin_publish_restriction(page)
if restriction_text:
    raise DouyinPublishRestrictedError(restriction_text)

while True:
    ...
```

**`DouYinNote.upload_note_content()`(`set_input_files` 之后插入)** 同样的检测代码。

### 5. `DouYinVideo.upload()` 清理(前置改动)

现状无 `try/finally`,抛异常时 browser/context 不显式关闭。加 `try/finally`,与 `DouYinNote.upload()` 既有模式对齐:只在无异常时保存 storage_state,始终关闭 context/browser。

### 6. `publish_to_douyin` 捕获异常(`publish_all.py`)

```python
from uploader.douyin_uploader.main import DouyinPublishRestrictedError

try:
    if content_type == "video":
        ...
        await uploader.main()
        return {"success": True, "message": "发布成功"}
    else:
        ...
except DouyinPublishRestrictedError as exc:
    return {
        "success": False,
        "message": f"账号被限制发布: {exc.toast_text}",
        "account_issue": True,
        "issue_type": "publish_restricted",
    }
except Exception as e:
    return {"success": False, "message": str(e)}
```

现有 `run_publish_with_params` 末尾的 `account_issue` 汇总会自动包含 `issue_type=publish_restricted` 条目,无需改动。

## 数据流

```
cookie_auth(已修) ─True─> ensure_account_login ─True─> publish_to_douyin
                                                              │
                                                              ▼
                                                    DouYinVideo.upload()
                                                              │
                                              goto + set_input_files
                                                              │
                                                              ▼
                                          ★ _check_douyin_publish_restriction
                                              │                    │
                                    toast 出现                  toast 未出现(2s 超时)
                                              │                    │
                                              ▼                    ▼
                                  raise DouyinPublishRestrictedError  继续正常发布流程
                                              │
                                              ▼
                                    publish_to_douyin 捕获
                                              │
                                              ▼
                              {account_issue:True, issue_type:"publish_restricted"}
                                              │
                                              ▼
                              run_publish_with_params 末尾汇总打印
```

## 错误处理

- **检测函数自身失败:** `_check_douyin_publish_restriction` 内部 try/except 兜底,任何异常(超时、page 异常、inner_text 失败)都返回 None。安全默认:检测失败 -> 按未受限处理,继续正常流程。
- **toast 出现但非限制类:** `semi-toast-error` 是通用错误 toast。任何在上传触发瞬间出现的 error toast 都意味着发不了,跳过是对的。toast 文本原样进 message,用户能看到具体原因。
- **2 秒延迟成本:** 每次发布(含正常账号)都会等 2 秒看 toast 是否出现。发布流程本身要几十秒到几分钟,2 秒占比小,可接受。
- **cookie_auth 20 秒等待:** 只在页面慢渲染时触发(正常快渲染立即返回)。最坏情况:未登录账号等 20 秒才判定 login_failed。可接受(登录校验低频)。

## 已知局限(方案 1 接受)

- `upload()` 里 `while True` 点发布循环(line 617-647)和等上传完成循环(line 562-600)仍是无限循环。若落地页检测漏报(toast 超过 2s 才出现,或 toast class 不匹配),仍可能卡死。基于实测 toast 167ms 出现,2s 超时余量充足,风险可控。
- 视频上传的限制 toast 未独立用 MutationObserver 验证(用户确认与图片相同)。

## 测试

沿用 `tests/test_cookie_auth_pages.py` 的 `FakePage`/`FakeLocator` 模式。

### `_check_douyin_publish_restriction` 单测
- toast 可见 -> 返回 toast 文本
- toast 不可见(超时) -> 返回 None
- toast 元素抛异常 -> 返回 None

### `cookie_auth` 修复后单测
- 页面立即显示 publish 标记 -> 返回 True(快速路径)
- 页面延迟显示 publish 标记 -> 等待后返回 True(新行为)
- 页面显示 login 标记 -> 返回 False

### `publish_to_douyin` 集成单测(mock uploader)
- `uploader.main()` 抛 `DouyinPublishRestrictedError` -> 返回 `{account_issue:True, issue_type:"publish_restricted", message 含 toast 文本}`
- `uploader.main()` 正常完成 -> 返回 `{success:True}`
- `uploader.main()` 抛其他异常 -> 返回 `{success:False, message: str(e)}`(现有行为)

### 无法自动化测试的
真实限制账号的端到端流程(需真账号)。检测逻辑简单 + 基于真实 DOM 信号,风险可控。

## 涉及文件

- `uploader/douyin_uploader/main.py`:加 `DouyinPublishRestrictedError`、`_check_douyin_publish_restriction`;修 `cookie_auth`;`DouYinVideo.upload()` 和 `DouYinNote.upload_note_content()` 加调用点 + `DouYinVideo.upload()` 加 try/finally
- `publish_all.py`:`publish_to_douyin` 加 `except DouyinPublishRestrictedError` 分支
- `tests/test_cookie_auth_pages.py`:加新单测
