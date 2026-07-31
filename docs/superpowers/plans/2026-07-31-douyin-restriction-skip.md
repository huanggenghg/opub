# 抖音账号被限制发布检测与跳过 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在抖音发布流程中检测"健康分不足"等平台限制(Semi UI error toast),优雅跳过该账号而非误判为登录失败。

**Architecture:** 在 `upload()` 的 `set_input_files` 之后等 `.semi-toast-error` 出现(2s),出现则抛 `DouyinPublishRestrictedError`,`publish_to_douyin` 捕获后标为 `account_issue + issue_type=publish_restricted`,复用现有汇总机制。前置修复 `cookie_auth` 的 5s `wait_for_url` 超时(加等 publish 标记渲染最多 20s),否则被限制账号进不到 `upload()`。

**Tech Stack:** Python 3.9+, patchright (Playwright fork), unittest, asyncio

## Global Constraints

- 范围只针对抖音(`uploader/douyin_uploader/main.py` + `publish_all.py:publish_to_douyin`),不动其他平台
- 检测信号基于实测 DOM:`.semi-toast-error` 元素,set_input_files 后 167ms 出现
- 检测函数内部 try/except 兜底,任何异常返回 None(安全默认:按未受限处理)
- `DouYinVideo.upload()` 加 try/finally 与 `DouYinNote.upload()` 既有模式对齐
- 不动 `upload()` 里现有的 `while True` 循环(方案 1 接受的局限)
- 测试沿用 `tests/test_cookie_auth_pages.py` 的 `FakePage`/`FakeLocator` 模式

---

## 文件结构

- `uploader/douyin_uploader/main.py`(修改):
  - 新增 `DouyinPublishRestrictedError` 异常类
  - 新增 `_check_douyin_publish_restriction(page)` 检测函数
  - 新增 `_wait_for_douyin_publish_marker(page, timeout_ms)` 辅助函数
  - 修改 `cookie_auth`:调用上述辅助函数
  - 修改 `DouYinVideo.upload()`:加 try/finally + 限制检测调用点
  - 修改 `DouYinNote.upload_note_content()`:加限制检测调用点
- `publish_all.py`(修改):
  - `publish_to_douyin`:加 `except DouyinPublishRestrictedError` 分支
- `tests/test_cookie_auth_pages.py`(修改):
  - 扩展 `FakeLocator`:`wait_for`、`inner_text`
  - 新增检测函数、cookie_auth 辅助函数的单测
- `tests/test_publish_engine.py`(修改):
  - 新增 `publish_to_douyin` 捕获限制异常的集成单测

---

## Task 1: 新增 DouyinPublishRestrictedError + _check_douyin_publish_restriction + 扩展测试 fakes

**Files:**
- Modify: `uploader/douyin_uploader/main.py`(在 `cookie_auth` 函数之前插入异常类和检测函数)
- Modify: `tests/test_cookie_auth_pages.py`(扩展 FakeLocator,加测试)

**Interfaces:**
- Produces:
  - `DouyinPublishRestrictedError(toast_text: str)` — 异常类,`self.toast_text` 属性
  - `async _check_douyin_publish_restriction(page, timeout_ms=2000) -> str | None` — 返回 toast 文本或 None

- [ ] **Step 1: 扩展 FakeLocator 支持 wait_for 和 inner_text**

在 `tests/test_cookie_auth_pages.py` 的 `FakeLocator` 类中,增加 `wait_for` 和 `inner_text` 方法,并扩展构造参数:

```python
class FakeLocator:
    def __init__(self, count=0, visible=False, text="", wait_raises=None):
        self._count = count
        self._visible = visible
        self._text = text
        self._wait_raises = wait_raises

    @property
    def first(self):
        return self

    async def count(self):
        return self._count

    async def is_visible(self):
        return self._visible

    async def wait_for(self, state="visible", timeout=30000):
        if self._wait_raises is not None:
            raise self._wait_raises
        if not self._visible:
            raise TimeoutError(f"Timeout {timeout}ms exceeded waiting for state={state}")

    async def inner_text(self):
        return self._text
```

- [ ] **Step 2: 写检测函数的失败测试**

在 `tests/test_cookie_auth_pages.py` 中新增测试类 `DouyinRestrictionDetectorTests`:

```python
class DouyinRestrictionDetectorTests(unittest.TestCase):
    def test_detector_returns_text_when_toast_visible(self):
        page = FakePage(
            "https://creator.douyin.com/creator-micro/content/upload",
            {
                ".semi-toast-error": FakeLocator(
                    count=1, visible=True, text="作品发布失败，健康分不足投稿功能受限"
                )
            },
        )

        result = asyncio.run(douyin_main._check_douyin_publish_restriction(page, timeout_ms=500))

        self.assertEqual(result, "作品发布失败，健康分不足投稿功能受限")

    def test_detector_returns_none_when_toast_not_visible(self):
        page = FakePage(
            "https://creator.douyin.com/creator-micro/content/upload",
            {".semi-toast-error": FakeLocator(count=0, visible=False)},
        )

        result = asyncio.run(douyin_main._check_douyin_publish_restriction(page, timeout_ms=500))

        self.assertIsNone(result)

    def test_detector_returns_none_on_unexpected_error(self):
        page = FakePage(
            "https://creator.douyin.com/creator-micro/content/upload",
            {".semi-toast-error": FakeLocator(wait_raises=RuntimeError("oops"))},
        )

        result = asyncio.run(douyin_main._check_douyin_publish_restriction(page, timeout_ms=500))

        self.assertIsNone(result)
```

- [ ] **Step 3: 运行测试验证失败**

Run: `python -m pytest tests/test_cookie_auth_pages.py::DouyinRestrictionDetectorTests -v`
Expected: FAIL with `AttributeError: module 'uploader.douyin_uploader.main' has no attribute '_check_douyin_publish_restriction'`

- [ ] **Step 4: 实现异常类和检测函数**

在 `uploader/douyin_uploader/main.py` 中,在 `cookie_auth` 函数定义之前(约 line 95 前)插入:

```python
class DouyinPublishRestrictedError(Exception):
    """抖音账号被限制发布(如健康分不足)时抛出。"""
    def __init__(self, toast_text: str):
        self.toast_text = toast_text
        super().__init__(f"账号被限制发布: {toast_text}")


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

- [ ] **Step 5: 运行测试验证通过**

Run: `python -m pytest tests/test_cookie_auth_pages.py::DouyinRestrictionDetectorTests -v`
Expected: PASS(3 个测试全过)

- [ ] **Step 6: 提交**

```bash
git add uploader/douyin_uploader/main.py tests/test_cookie_auth_pages.py
git commit -m "feat(douyin): add publish-restriction detector and exception"
```

---

## Task 2: 修复 cookie_auth 超时 + 新增 _wait_for_douyin_publish_marker 辅助函数

**Files:**
- Modify: `uploader/douyin_uploader/main.py`(`cookie_auth` 函数,约 line 95-110)
- Modify: `tests/test_cookie_auth_pages.py`(加测试)

**Interfaces:**
- Produces:
  - `async _wait_for_douyin_publish_marker(page, timeout_ms=20000) -> None` — 等 publish 标记渲染,超时静默返回
- Consumes: `FakeLocator.wait_for`(Task 1 已加)

- [ ] **Step 1: 写辅助函数的失败测试**

在 `tests/test_cookie_auth_pages.py` 的 `DouyinRestrictionDetectorTests` 类中(或新建 `DouyinCookieAuthWaitTests` 类)加测试:

```python
class DouyinCookieAuthWaitTests(unittest.TestCase):
    def test_wait_for_publish_marker_returns_silently_when_visible(self):
        page = FakePage(
            "https://creator.douyin.com/creator-micro/content/upload",
            {"text:发布视频": FakeLocator(count=1, visible=True)},
        )

        # 不应抛异常
        asyncio.run(douyin_main._wait_for_douyin_publish_marker(page, timeout_ms=500))

    def test_wait_for_publish_marker_silent_on_timeout(self):
        page = FakePage(
            "https://creator.douyin.com/creator-micro/content/upload",
            {"text:发布视频": FakeLocator(count=0, visible=False)},
        )

        # 超时也不应抛异常(静默返回,由 _is_douyin_auth_page_valid 兜底)
        asyncio.run(douyin_main._wait_for_douyin_publish_marker(page, timeout_ms=500))
```

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_cookie_auth_pages.py::DouyinCookieAuthWaitTests -v`
Expected: FAIL with `AttributeError: module 'uploader.douyin_uploader.main' has no attribute '_wait_for_douyin_publish_marker'`

- [ ] **Step 3: 实现辅助函数并修改 cookie_auth**

在 `uploader/douyin_uploader/main.py` 中,在 `_check_douyin_publish_restriction` 之后插入辅助函数:

```python
async def _wait_for_douyin_publish_marker(page: Page, timeout_ms: int = 20000) -> None:
    """等上传页 publish 标记渲染。超时静默返回,由 _is_douyin_auth_page_valid 兜底判定。"""
    try:
        await page.get_by_text("发布视频", exact=True).first.wait_for(state="visible", timeout=timeout_ms)
    except Exception:
        pass
```

修改 `cookie_auth` 函数,在 `wait_for_url` 之后、`_is_douyin_auth_page_valid` 之前调用辅助函数:

```python
async def cookie_auth(account_file):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            context = await browser.new_context(storage_state=account_file)
            context = await set_init_script(context)
            page = await context.new_page()
            await page.goto(DOUYIN_UPLOAD_URL)
            try:
                await page.wait_for_url(DOUYIN_UPLOAD_URL, timeout=5000)
            except Exception:
                return False

            await _wait_for_douyin_publish_marker(page)
            return await _is_douyin_auth_page_valid(page)
        finally:
            await browser.close()
```

- [ ] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_cookie_auth_pages.py::DouyinCookieAuthWaitTests -v`
Expected: PASS(2 个测试全过)

- [ ] **Step 5: 运行既有 cookie_auth 相关测试确保无回归**

Run: `python -m pytest tests/test_cookie_auth_pages.py -v`
Expected: PASS(所有测试通过,包括既有的 `test_douyin_auth_page_*`)

- [ ] **Step 6: 提交**

```bash
git add uploader/douyin_uploader/main.py tests/test_cookie_auth_pages.py
git commit -m "fix(douyin): wait for publish marker render in cookie_auth (20s timeout)"
```

---

## Task 3: publish_to_douyin 捕获 DouyinPublishRestrictedError

**Files:**
- Modify: `publish_all.py`(`publish_to_douyin` 函数,约 line 592-643)
- Modify: `tests/test_publish_engine.py`(加集成单测)

**Interfaces:**
- Consumes: `DouyinPublishRestrictedError`(Task 1 已定义)
- Produces: `publish_to_douyin` 在限制时返回 `{"success": False, "message": "账号被限制发布: <toast>", "account_issue": True, "issue_type": "publish_restricted"}`

- [ ] **Step 1: 写失败测试**

在 `tests/test_publish_engine.py` 中新增测试(参照既有 `PublishEngineTests` 模式,用 `patch` + `AsyncMock`):

```python
def test_publish_to_douyin_marks_restriction_as_account_issue(self):
    from uploader.douyin_uploader.main import DouyinPublishRestrictedError

    params = {
        "account_file": "cookies/douyin_uploader/account.json",
        "title": "标题",
        "tags": [],
        "publish_strategy": "immediate",
        "publish_time": None,
        "content_type": "video",
        "video_file": "videos/demo.mp4",
        "desc": "",
    }

    async def fake_main():
        raise DouyinPublishRestrictedError("作品发布失败，健康分不足投稿功能受限")

    with patch("uploader.douyin_uploader.main.DouYinVideo") as MockDouYinVideo:
        MockDouYinVideo.return_value.main = AsyncMock(side_effect=fake_main)
        result = publish_all.run_async_for_test(publish_all.publish_to_douyin(params))

    self.assertFalse(result["success"])
    self.assertTrue(result["account_issue"])
    self.assertEqual(result["issue_type"], "publish_restricted")
    self.assertIn("健康分不足", result["message"])
```

把测试加到 `PublishEngineTests` 类中(或新建一个测试类)。注意:`videos/demo.mp4` 需存在(已存在)。

- [ ] **Step 2: 运行测试验证失败**

Run: `python -m pytest tests/test_publish_engine.py -k test_publish_to_douyin_marks_restriction -v`
Expected: FAIL — 当前 `publish_to_douyin` 的 `except Exception` 把 `DouyinPublishRestrictedError` 当普通异常处理,返回的 dict 没有 `account_issue`/`issue_type` 字段

- [ ] **Step 3: 修改 publish_to_douyin 加 except 分支**

在 `publish_all.py` 的 `publish_to_douyin` 函数中,在 `except Exception as e:` 之前加一个专门的 `except DouyinPublishRestrictedError` 分支。同时在函数顶部的 import 处加上异常类导入:

```python
async def publish_to_douyin(params: dict) -> dict:
    """发布到抖音"""
    from uploader.douyin_uploader.main import DouYinVideo, DouYinNote, DouyinPublishRestrictedError

    account_file = resolve_path(params["account_file"])

    title = truncate_title(params["title"], "douyin")
    tags = params["tags"]
    publish_strategy = params["publish_strategy"]
    publish_time = params["publish_time"]
    content_type = params["content_type"]

    try:
        if content_type == "video":
            video_file = resolve_path(params["video_file"])
            if not video_file or not os.path.exists(video_file):
                return {"success": False, "message": f"视频文件不存在: {video_file}"}

            uploader = DouYinVideo(
                title=title,
                file_path=video_file,
                tags=tags,
                publish_date=publish_time or 0,
                account_file=account_file,
                desc=params["desc"],
                publish_strategy=publish_strategy,
            )
            await uploader.main()
            return {"success": True, "message": "发布成功"}
        else:
            images = params["images"]
            if not images:
                return {"success": False, "message": "图文模式需要提供图片"}

            image_paths = [resolve_path(img) for img in images]
            for img_path in image_paths:
                if not os.path.exists(img_path):
                    return {"success": False, "message": f"图片文件不存在: {img_path}"}

            uploader = DouYinNote(
                image_paths=image_paths,
                note=params["desc"],
                tags=tags,
                publish_date=publish_time or 0,
                account_file=account_file,
                title=title,
                publish_strategy=publish_strategy,
            )
            await uploader.douyin_upload_note()
            return {"success": True, "message": "发布成功"}
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

- [ ] **Step 4: 运行测试验证通过**

Run: `python -m pytest tests/test_publish_engine.py -k test_publish_to_douyin_marks_restriction -v`
Expected: PASS

- [ ] **Step 5: 运行 publish_engine 全部测试确保无回归**

Run: `python -m pytest tests/test_publish_engine.py -v`
Expected: PASS(所有既有测试通过)

- [ ] **Step 6: 提交**

```bash
git add publish_all.py tests/test_publish_engine.py
git commit -m "feat(douyin): publish_to_douyin catches restriction as account_issue"
```

---

## Task 4: 在 DouYinVideo.upload() 加限制检测 + try/finally

**Files:**
- Modify: `uploader/douyin_uploader/main.py`(`DouYinVideo.upload` 方法,约 line 543-653)

**Interfaces:**
- Consumes:
  - `_check_douyin_publish_restriction(page)`(Task 1)
  - `DouyinPublishRestrictedError`(Task 1)
- Produces: `DouYinVideo.upload()` 在 set_input_files 后检测限制,命中则抛 `DouyinPublishRestrictedError`;异常时正确清理 browser/context

**说明:** 此任务是接线 + 清理重构,无直接单测(需真实浏览器)。由 Task 3 的集成单测(mock uploader 抛异常)覆盖异常处理,Task 6 的全量测试 + 手动验证覆盖接线正确性。

- [ ] **Step 1: 修改 DouYinVideo.upload() — 加 try/finally + 限制检测**

在 `uploader/douyin_uploader/main.py` 的 `DouYinVideo.upload` 方法中,做两处改动:

**改动 A:加限制检测调用点**

在 `await page.locator("div[class^='container'] input").set_input_files(self.file_path)` 之后、`while True:`(等发布表单页)之前插入:

```python
        await page.locator("div[class^='container'] input").set_input_files(self.file_path)

        restriction_text = await _check_douyin_publish_restriction(page)
        if restriction_text:
            raise DouyinPublishRestrictedError(restriction_text)

        while True:
```

**改动 B:加 try/finally 确保异常时清理**

把 `page = await context.new_page()` 到方法末尾的 `await browser.close()` 包进 try/finally,加 `upload_success` 标志。改动后的结构:

```python
        browser = await playwright.chromium.launch(headless=self.headless)
        context = await browser.new_context(
            storage_state=f"{self.account_file}",
            permissions=["geolocation"],
        )
        context = await set_init_script(context)

        upload_success = False
        try:
            page = await context.new_page()
            await page.goto("https://creator.douyin.com/creator-micro/content/upload")
            douyin_logger.info(_msg("🏃", f"小人开始搬运视频: {self.title}.mp4"))
            douyin_logger.info(_msg("🧭", "小人正在赶往上传主页"))
            await page.wait_for_url("https://creator.douyin.com/creator-micro/content/upload")
            await page.locator("div[class^='container'] input").set_input_files(self.file_path)

            restriction_text = await _check_douyin_publish_restriction(page)
            if restriction_text:
                raise DouyinPublishRestrictedError(restriction_text)

            while True:
                # ... 现有的等发布表单页循环 ...

            await asyncio.sleep(1)
            # ... 现有的填标题、等上传完成、设封面、点发布循环 ...

            while True:
                # ... 现有的点发布循环 ...
                break

            upload_success = True
        finally:
            if upload_success:
                await context.storage_state(path=self.account_file)
                douyin_logger.success(_msg("🥳", "cookie 更新完毕"))
                await asyncio.sleep(2)
            await context.close()
            await browser.close()
```

注意:
- `while True` 循环体内的代码保持不变,只是缩进进 try 块
- `storage_state` + `asyncio.sleep(2)` + `context.close()` + `browser.close()` 移到 finally,且只在 `upload_success=True` 时执行 storage_state 保存
- 限制检测抛异常时 `upload_success` 仍为 False,finally 不保存 storage_state(正确,因为没发布成功)

- [ ] **Step 2: 运行既有测试确保无回归**

Run: `python -m pytest tests/test_cookie_auth_pages.py tests/test_publish_engine.py -v`
Expected: PASS(所有既有测试通过)

- [ ] **Step 3: 提交**

```bash
git add uploader/douyin_uploader/main.py
git commit -m "feat(douyin): wire restriction detection into DouYinVideo.upload + try/finally cleanup"
```

---

## Task 5: 在 DouYinNote.upload_note_content() 加限制检测

**Files:**
- Modify: `uploader/douyin_uploader/main.py`(`DouYinNote.upload_note_content` 方法,约 line 741-783)

**Interfaces:**
- Consumes:
  - `_check_douyin_publish_restriction(page)`(Task 1)
  - `DouyinPublishRestrictedError`(Task 1)
- Produces: `DouYinNote.upload_note_content()` 在 set_input_files 后检测限制,命中则抛 `DouyinPublishRestrictedError`(由 `DouYinNote.upload()` 既有 try/finally 处理清理)

**说明:** `DouYinNote.upload()`(约 line 785-812)已有 try/finally,异常时正确清理,无需改动。此任务只加检测调用点。无直接单测,由 Task 6 全量测试覆盖。

- [ ] **Step 1: 修改 DouYinNote.upload_note_content() — 加限制检测**

在 `uploader/douyin_uploader/main.py` 的 `DouYinNote.upload_note_content` 方法中,在 `await page.locator("div[class^='container'] input[accept*='image']").set_input_files(self.image_paths)` 之后、`while True:`(等图文发布页面)之前插入:

```python
        await page.locator("div[class^='container'] input[accept*='image']").set_input_files(self.image_paths)

        restriction_text = await _check_douyin_publish_restriction(page)
        if restriction_text:
            raise DouyinPublishRestrictedError(restriction_text)

        while True:
```

- [ ] **Step 2: 运行既有测试确保无回归**

Run: `python -m pytest tests/test_cookie_auth_pages.py tests/test_publish_engine.py -v`
Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add uploader/douyin_uploader/main.py
git commit -m "feat(douyin): wire restriction detection into DouYinNote.upload_note_content"
```

---

## Task 6: 全量测试 + 手动验证

**Files:**
- 无修改,只验证

- [ ] **Step 1: 运行全量测试**

Run: `python -m pytest tests/ -v`
Expected: PASS(所有测试通过,无回归)

- [ ] **Step 2: 检查 import 无循环引用**

Run: `python -c "import uploader.douyin_uploader.main; import publish_all; print('imports OK')"`
Expected: 输出 `imports OK`,无异常

- [ ] **Step 3: 手动验证(可选,需被限制账号)**

若有被限制账号,跑:
```bash
python -c "
import asyncio
from uploader.douyin_uploader import main as douyin_main

async def _bypass(account_file):
    return True
douyin_main.cookie_auth = _bypass

from uploader.douyin_uploader.main import DouYinVideo

async def main():
    uploader = DouYinVideo(
        title='测试',
        file_path='videos/demo.mp4',
        tags=[],
        publish_date=0,
        account_file='cookies/douyin_uploader/account.json',
        desc='',
        publish_strategy='immediate',
        headless=False,
    )
    try:
        await asyncio.wait_for(uploader.main(), timeout=30)
        print('未触发限制(账号可能已恢复)')
    except Exception as e:
        print(f'捕获到: {type(e).__name__}: {e}')

asyncio.run(main())
"
```
Expected: 输出 `捕获到: DouyinPublishRestrictedError: 账号被限制发布: 作品发布失败，健康分不足投稿功能受限...`

- [ ] **Step 4: 清理调试脚本(可选)**

调查期间创建的调试脚本可保留(未跟踪)或删除:
```bash
# 如要删除:
rm -f debug_douyin_publish_form.py debug_douyin_real_publish.py debug_douyin_upload_stuck.py debug_douyin_image_toast.py
```

---

## 自审清单

**Spec 覆盖:**
- ✅ cookie_auth 5s 超时修复 — Task 2
- ✅ DouyinPublishRestrictedError 异常类 — Task 1
- ✅ _check_douyin_publish_restriction 检测函数 — Task 1
- ✅ DouYinVideo.upload() 调用点 + try/finally — Task 4
- ✅ DouYinNote.upload_note_content() 调用点 — Task 5
- ✅ publish_to_douyin 捕获异常 — Task 3
- ✅ 测试 — Task 1(检测函数)+ Task 2(cookie_auth 辅助)+ Task 3(集成)

**类型一致性:**
- `DouyinPublishRestrictedError(toast_text)` — Task 1 定义,Task 3/4/5 使用,属性名 `toast_text` 一致
- `_check_douyin_publish_restriction(page, timeout_ms=2000)` — Task 1 定义,Task 4/5 调用,签名一致
- `_wait_for_douyin_publish_marker(page, timeout_ms=20000)` — Task 2 定义,Task 2 内 cookie_auth 调用,签名一致

**已知局限(方案 1 接受,已在 spec 记录):**
- `upload()` 里 `while True` 点发布循环仍可能死循环(若 toast 检测漏报)
- 视频上传的限制 toast 未独立验证(用户确认与图片相同)
