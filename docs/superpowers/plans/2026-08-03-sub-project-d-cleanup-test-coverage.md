# Sub-project D: Cleanup + Test Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean up dead dependencies, dead code/attributes, and unused params from sub-projects B+C, plus add test coverage for Note upload() methods and cookie_gen edge cases.

**Architecture:** 4 sequential tasks: dependency cleanup (requirements.txt) -> base_video.py cookie_gen duplication refactor -> platform uploader cleanup (bilibili/ks/xiaohongshu) -> test coverage (Note upload tests + cookie_gen edge case tests). Each task keeps the 152-test regression suite green.

**Tech Stack:** Python 3, pytest, playwright, biliup CLI. requirements.txt is UTF-16 LE encoded (must use Python for edits, not the Edit tool).

## Global Constraints

- **Branch:** `sub-project-d/cleanup-test-coverage` (already created from `main`)
- **Test baseline:** 152 tests passing (from sub-projects A+B+C). Each task must keep all tests green.
- **requirements.txt encoding:** UTF-16 LE with CRLF/LF mixed terminators. MUST use Python (`open(path, encoding='utf-16')`) for edits, NOT the Edit tool (which converts to UTF-8 and corrupts the file).
- **base class safety:** `uploader/base_video.py` is inherited by all 8 platform uploaders. Any refactor must preserve behavior exactly - the existing test suite (`test_base_uploader.py`, `test_base_uploader_login.py`, `test_base_uploader_session.py`) is the safety net.
- **5-param setup signature:** All platform `*_setup` module-level wrappers must keep the signature `(account_file, handle, return_detail, qrcode_callback, headless)` - enforced by tests in every `test_*_uploader_base.py`. Do NOT remove `return_detail` from any setup signature.
- **PlatformResultExtras contract:** `{"success": bool, "message": str, "result_url"?: str, "result_id"?: str, "account_issue"?: bool, "issue_type"?: str}` from `uploader/base_video.py:22-31`.

---

### Task 1: Dependency Cleanup

**Files:**
- Modify: `requirements.txt` (remove 9 dead package lines)

**Interfaces:**
- Consumes: 无
- Produces: 干净的 requirements.txt,无 dead dependencies

**Dead packages to remove (9 total):**
- `alembic==1.16.1` (orphaned by db/ deletion in sub-project C)
- `SQLAlchemy==2.0.41` (orphaned by db/ deletion)
- `Mako==1.3.10` (alembic template dependency)
- `blinker==1.9.0` (Flask transitive)
- `click==8.2.1` (Flask transitive)
- `itsdangerous==2.2.0` (Flask transitive)
- `Jinja2==3.1.6` (Flask transitive)
- `MarkupSafe==3.0.2` (Jinja2/Mako transitive)
- `Werkzeug==3.1.3` (Flask transitive)

- [ ] **Step 1: Verify dead packages are not imported anywhere**

Run:
```bash
grep -rn "import alembic\|import sqlalchemy\|import mako\|import blinker\|import click\|import itsdangerous\|import jinja2\|import markupsafe\|import werkzeug\|from alembic\|from sqlalchemy\|from mako\|from blinker\|from click\|from itsdangerous\|from jinja2\|from markupsafe\|from werkzeug" --include="*.py" . | grep -v ".venv" | grep -v "__pycache__"
```
Expected: 无输出(所有 dead packages 确认无 import)。

- [ ] **Step 2: Remove 9 dead package lines from requirements.txt using Python**

requirements.txt 是 UTF-16 LE 编码,不能用 Edit 工具(会转 UTF-8)。用 Python 脚本删除:

Run:
```bash
.venv/bin/python -c "
path = 'requirements.txt'
content = open(path, encoding='utf-16').read()
dead = {'alembic==1.16.1', 'SQLAlchemy==2.0.41', 'Mako==1.3.10', 'blinker==1.9.0', 'click==8.2.1', 'itsdangerous==2.2.0', 'Jinja2==3.1.6', 'MarkupSafe==3.0.2', 'Werkzeug==3.1.3'}
lines = content.splitlines()
new_lines = [l for l in lines if l not in dead]
new_content = '\n'.join(new_lines)
if content.endswith('\n'):
    new_content += '\n'
open(path, 'w', encoding='utf-16').write(new_content)
print(f'Removed {len(lines) - len(new_lines)} lines')
"
```
Expected: 输出 `Removed 9 lines`。

- [ ] **Step 3: Verify removal**

Run:
```bash
.venv/bin/python -c "
content = open('requirements.txt', encoding='utf-16').read()
for line in content.splitlines():
    low = line.lower()
    if any(p in low for p in ['alembic','sqlalchemy','mako','blinker','click','itsdangerous','jinja2','markupsafe','werkzeug']):
        print(f'STILL PRESENT: {line}')
        break
else:
    print('All 9 dead packages removed')
"
```
Expected: 输出 `All 9 dead packages removed`。

- [ ] **Step 4: Verify pip install still succeeds**

Run:
```bash
.venv/bin/pip install -e . 2>&1 | tail -3
```
Expected: 安装成功,无报错。

- [ ] **Step 5: Run regression test suite**

Run:
```bash
.venv/bin/python -m pytest tests/ -v 2>&1 | tail -5
```
Expected: `152 passed`。

- [ ] **Step 6: Commit**

```bash
git add requirements.txt
git commit -m "$(cat <<'EOF'
chore: remove 9 dead dependencies from requirements.txt

Remove Flask transitive deps (blinker, click, itsdangerous, Jinja2,
MarkupSafe, Werkzeug) and db/ orphans (alembic, SQLAlchemy, Mako).
None are imported anywhere. Flask itself was removed in sub-project C.
EOF
)"
```

---

### Task 2: base_video.py cookie_gen Duplication Refactor

**Files:**
- Modify: `uploader/base_video.py:241-295` (cookie_gen method)

**Interfaces:**
- Consumes: `_build_login_result` helper, `cls.cookie_auth`, `cls.is_login_completed`, `cls.extract_qrcode_src`, `cls.PLATFORM_NAME`
- Produces: 新的 `_save_state_and_validate` classmethod(私有,只被 cookie_gen 调用)

**Background:** cookie_gen 里有 6 行 save_state+cookie_auth+build_result block 重复出现两次:
- Line 265-271: pre-check branch(当 new_page 已是登录态时)
- Line 279-285: QR flow branch(当轮询检测到登录完成时)

两处逻辑完全相同,提取为 `_save_state_and_validate` helper。

**Spec 2b 决策(pre-check branch):** 采用 Option A - 保留 pre-check branch。提取 helper 后该 branch 变为单行 `result = await cls._save_state_and_validate(...)`,足够简洁。删除该 branch 需修改依赖它的 test,风险更高,不值得。

**Spec 2c 决策(cosmetic issues):** 提取 helper 本身就是主要的 cosmetic 改进(消除 6 行 duplication)。spec 提到的 "extra blank lines、dead 注释" 等 review findings 没有具体行号,implementer 在 Step 1 读 cookie_gen 时若发现明显的 dead 注释可顺手删除,但不主动搜索 cosmetic 问题。

- [ ] **Step 1: Read current cookie_gen to confirm line numbers**

Run:
```bash
sed -n '240,296p' uploader/base_video.py
```
Expected: 看到 cookie_gen 方法,含两处重复的 save_state+cookie_auth+build_result block。

- [ ] **Step 2: Add `_save_state_and_validate` classmethod**

用 Edit 工具,在 `cookie_gen` 方法之前(line 240 的 `@classmethod` 之前)插入新 helper:

old_string:
```python
    @classmethod
    async def cookie_gen(
```

new_string:
```python
    @classmethod
    async def _save_state_and_validate(cls, context, account_file, page):
        """Save storage state and validate cookie. Returns login result dict."""
        await page.wait_for_timeout(2000)
        await context.storage_state(path=account_file)
        if await cls.cookie_auth(account_file):
            return _build_login_result(True, "success", f"{cls.PLATFORM_NAME}扫码登录成功", account_file, None, page.url)
        return _build_login_result(False, "cookie_invalid", f"{cls.PLATFORM_NAME}扫码完成但 cookie 校验失败", account_file, None, page.url)

    @classmethod
    async def cookie_gen(
```

- [ ] **Step 3: Replace pre-check branch (first duplication) with helper call**

用 Edit 工具,把 pre-check branch 里的 save_state+cookie_auth+build_result block 替换为单行 helper 调用:

old_string:
```python
                if pre_url and pre_url != "about:blank" and await cls.is_login_completed(page):
                    await page.wait_for_timeout(2000)
                    await context.storage_state(path=account_file)
                    if await cls.cookie_auth(account_file):
                        result = _build_login_result(True, "success", f"{cls.PLATFORM_NAME}扫码登录成功", account_file, None, page.url)
                    else:
                        result = _build_login_result(False, "cookie_invalid", f"{cls.PLATFORM_NAME}扫码完成但 cookie 校验失败", account_file, None, page.url)
                else:
```

new_string:
```python
                if pre_url and pre_url != "about:blank" and await cls.is_login_completed(page):
                    result = await cls._save_state_and_validate(context, account_file, page)
                else:
```

- [ ] **Step 4: Replace QR flow branch (second duplication) with helper call**

用 Edit 工具,把 QR flow branch 里的 save_state+cookie_auth+build_result block 替换为单行 helper 调用:

old_string:
```python
                        if await cls.is_login_completed(page):
                            await page.wait_for_timeout(2000)
                            await context.storage_state(path=account_file)
                            if await cls.cookie_auth(account_file):
                                result = _build_login_result(True, "success", f"{cls.PLATFORM_NAME}扫码登录成功", account_file, None, page.url)
                            else:
                                result = _build_login_result(False, "cookie_invalid", f"{cls.PLATFORM_NAME}扫码完成但 cookie 校验失败", account_file, None, page.url)
                            break
```

new_string:
```python
                        if await cls.is_login_completed(page):
                            result = await cls._save_state_and_validate(context, account_file, page)
                            break
```

- [ ] **Step 5: Verify base uploader tests pass**

Run:
```bash
.venv/bin/python -m pytest tests/test_base_uploader.py tests/test_base_uploader_login.py tests/test_base_uploader_session.py -v
```
Expected: 全绿(这些测试覆盖 cookie_gen 行为,refactor 不能破坏)。

- [ ] **Step 6: Run full regression suite**

Run:
```bash
.venv/bin/python -m pytest tests/ -v 2>&1 | tail -5
```
Expected: `152 passed`。

- [ ] **Step 7: Commit**

```bash
git add uploader/base_video.py
git commit -m "$(cat <<'EOF'
refactor(base): extract cookie_gen save+validate duplication into helper

cookie_gen 里 save_state+cookie_auth+build_result block 重复出现两次
(pre-check branch 和 QR flow branch)。提取为 _save_state_and_validate
classmethod,两处调用 helper。行为完全不变。
EOF
)"
```

---

### Task 3: Platform Uploader Cleanup

**Files:**
- Modify: `uploader/bilibili_uploader/main.py:39` (remove publish_strategy storage)
- Modify: `uploader/bilibili_uploader/main.py:84-108` (update upload() docstring)
- Modify: `uploader/ks_uploader/main.py:415` (remove self.local_executable_path)
- Modify: `uploader/xiaohongshu_uploader/main.py:429` (remove self.local_executable_path)

**Interfaces:**
- Consumes: 无
- Produces: 干净的平台 uploader 代码

**Note on scope deviation:** Spec said "移除 return_detail param" for bilibili,但 `test_setup_signature_is_5_params` 测试在 `tests/test_bilibili_uploader_base.py:15-19` 断言 5-param signature。所有平台的 `*_setup` wrapper 都必须保持 5-param signature。所以 return_detail 保留,只在 docstring 里注明 ignored。这是 plan 对 spec 的合理 deviation。

- [ ] **Step 1: Read bilibili main.py to confirm line numbers**

Run:
```bash
sed -n '34,40p' uploader/bilibili_uploader/main.py
```
Expected: 看到 line 39 `self.publish_strategy = publish_strategy`。

- [ ] **Step 2: Remove publish_strategy storage from BilibiliUploader.__init__**

用 Edit 工具,删除 `self.publish_strategy = publish_storage` 行。`publish_strategy` param 保留在 __init__ signature(dispatch.py 传它),但不存储(从不读取):

old_string:
```python
        self.desc = desc
        self.publish_strategy = publish_strategy
        self.tid = tid
```

new_string:
```python
        self.desc = desc
        self.tid = tid
```

- [ ] **Step 3: Update BilibiliUploader.setup docstring to note return_detail is ignored**

用 Edit 工具,更新 setup 方法的 docstring:

old_string:
```python
        """5-param signature for dispatch compatibility. qrcode_callback/headless ignored (CLI)."""
```

new_string:
```python
        """5-param signature for dispatch compatibility.

        return_detail/qrcode_callback/headless are ignored (CLI platform -
        biliup doesn't support QR callbacks or headless mode).
        """
```

- [ ] **Step 4: Update BilibiliUploader.upload docstring to note raw_output is not returned**

用 Edit 工具,在 upload 方法 docstring 后加注释:

old_string:
```python
    async def upload(self) -> PlatformResultExtras:
        """用 biliup 上传视频到 B站。"""
```

new_string:
```python
    async def upload(self) -> PlatformResultExtras:
        """用 biliup 上传视频到 B站。

        Returns PlatformResultExtras without raw_output (biliup stdout
        is logged but not returned - no consumer in the codebase).
        """
```

- [ ] **Step 5: Read ks_uploader main.py to confirm local_executable_path line**

Run:
```bash
sed -n '414,416p' uploader/ks_uploader/main.py
```
Expected: 看到 line 415 `self.local_executable_path = LOCAL_CHROME_PATH`。

- [ ] **Step 6: Remove self.local_executable_path from KSBaseUploader**

用 Edit 工具删除 `uploader/ks_uploader/main.py:415` 的 `self.local_executable_path = LOCAL_CHROME_PATH`。ks_uploader 在 line 188-189 直接用 `LOCAL_CHROME_PATH`(不通过 self),所以删 self attribute 不影响 launch 逻辑。

old_string:
```python
        self.headless = headless
        self.local_executable_path = LOCAL_CHROME_PATH
        self.date_format = "%Y-%m-%d %H:%M"
```

new_string:
```python
        self.headless = headless
        self.date_format = "%Y-%m-%d %H:%M"
```

- [ ] **Step 7: Remove self.local_executable_path from XiaoHongShuBaseUploader**

用 Edit 工具删除 `uploader/xiaohongshu_uploader/main.py:429` 的 `self.local_executable_path = LOCAL_CHROME_PATH`:

old_string:
```python
        self.date_format = "%Y年%m月%d日 %H:%M"
        self.local_executable_path = LOCAL_CHROME_PATH
        self.headless = headless
```

new_string:
```python
        self.date_format = "%Y年%m月%d日 %H:%M"
        self.headless = headless
```

**重要:** 不要动 `uploader/baijiahao_uploader/main.py:132` 的 `self.local_executable_path = LOCAL_CHROME_PATH` - baijiahao 在 line 566 的 `ai2video` 里读取它,sub-project B final fix 已确认保留。

- [ ] **Step 8: Remove unused imports from xiaohongshu_uploader/main.py**

Plan 阶段 grep 确认:xiaohongshu 导入了 `PublishStrategy`、`_build_launch_kwargs`、`_get_qrcode_utils` 但从未使用(publish_strategy 参数类型是 `str` 而非 `PublishStrategy`;launch 由 base class 的 `_browser_session` 处理,不需自己导入 `_build_launch_kwargs`)。

用 Edit 工具,修改 `uploader/xiaohongshu_uploader/main.py:14-23` 的 import block:

old_string:
```python
from uploader.base_video import (
    BaseBrowserUploader,
    PlatformResultExtras,
    PublishStrategy,
    _build_launch_kwargs,
    _build_login_result,
    _emit_qrcode_callback,
    _get_qrcode_utils,
    _msg,
)
```

new_string:
```python
from uploader.base_video import (
    BaseBrowserUploader,
    PlatformResultExtras,
    _build_login_result,
    _emit_qrcode_callback,
    _msg,
)
```

- [ ] **Step 9: Remove unused PublishStrategy import from douyin_uploader/main.py**

Plan 阶段 grep 确认:douyin 导入了 `PublishStrategy` 但从未使用(publish_strategy 参数类型是 `str`)。`_build_launch_kwargs` 和 `_get_qrcode_utils` 在 douyin 里**有使用**(line 175, 248, 250),不能删。

用 Edit 工具,修改 `uploader/douyin_uploader/main.py:16-25` 的 import block:

old_string:
```python
from uploader.base_video import (
    BaseBrowserUploader,
    PlatformResultExtras,
    PublishStrategy,
    _build_launch_kwargs,
    _build_login_result,
    _emit_qrcode_callback,
    _get_qrcode_utils,
    _msg,
)
```

new_string:
```python
from uploader.base_video import (
    BaseBrowserUploader,
    PlatformResultExtras,
    _build_launch_kwargs,
    _build_login_result,
    _emit_qrcode_callback,
    _get_qrcode_utils,
    _msg,
)
```

- [ ] **Step 10: Verify no local_executable_path references remain in ks/xiaohongshu**

Run:
```bash
grep -n "local_executable_path" uploader/ks_uploader/main.py uploader/xiaohongshu_uploader/main.py
```
Expected: 无输出。(`uploader/baijiahao_uploader/main.py` 仍有,符合预期)

- [ ] **Step 11: Verify no publish_strategy storage remains in bilibili**

Run:
```bash
grep -n "self.publish_strategy" uploader/bilibili_uploader/main.py
```
Expected: 无输出。

- [ ] **Step 12: Verify no unused imports remain in xiaohongshu/douyin**

Run:
```bash
grep -n "PublishStrategy\|_build_launch_kwargs\|_get_qrcode_utils" uploader/xiaohongshu_uploader/main.py
grep -n "PublishStrategy" uploader/douyin_uploader/main.py
```
Expected: xiaohongshu 无输出。douyin 无输出。

- [ ] **Step 13: Run platform uploader tests**

Run:
```bash
.venv/bin/python -m pytest tests/test_bilibili_uploader_base.py tests/test_ks_uploader_base.py tests/test_xiaohongshu_uploader_base.py tests/test_douyin_uploader_base.py -v
```
Expected: 全绿。

- [ ] **Step 14: Run full regression suite**

Run:
```bash
.venv/bin/python -m pytest tests/ -v 2>&1 | tail -5
```
Expected: `152 passed`。

- [ ] **Step 15: Commit**

```bash
git add uploader/bilibili_uploader/main.py uploader/ks_uploader/main.py uploader/xiaohongshu_uploader/main.py uploader/douyin_uploader/main.py
git commit -m "$(cat <<'EOF'
chore(uploaders): remove dead attributes, unused imports, document ignored params

- bilibili: remove unused self.publish_strategy storage (param kept for
  dispatch compat, never read). Document return_detail/raw_output in
  docstrings.
- ks/xiaohongshu: remove self.local_executable_path (set but never read;
  launch uses LOCAL_CHROME_PATH directly). baijiahao's local_executable_path
  kept - used in ai2video.
- xiaohongshu: remove unused imports (PublishStrategy, _build_launch_kwargs,
  _get_qrcode_utils) - publish_strategy typed as str, launch handled by
  base class.
- douyin: remove unused PublishStrategy import - publish_strategy typed
  as str.
EOF
)"
```

---

### Task 4: Test Coverage - Note upload() + cookie_gen Edge Cases

**Files:**
- Modify: `tests/test_weibo_uploader_base.py` (add WeiboNoteUploadTests class)
- Modify: `tests/test_ks_uploader_base.py` (add KSNoteUploadTests class)
- Modify: `tests/test_douyin_uploader_base.py` (add DouYinNoteUploadTests class)
- Modify: `tests/test_base_uploader_login.py` (add cookie_gen edge case tests)

**Interfaces:**
- Consumes: `WeiboNote`, `KSNote`, `DouYinNote` classes(各自平台的 main.py)
- Consumes: `FakeUploader`, `FakePage`, `FakeContext`, `FakePlaywright`(test_base_uploader_login.py 已定义)
- Produces: 6 个新测试(3 Note upload + 3 cookie_gen edge case)

**Note on storage_state-on-failure tests:** Spec Task 4b 说要加 `test_browser_session_saves_storage_state_on_success` 和 `test_browser_session_saves_storage_state_on_failure`。但这两个测试已存在于 `tests/test_base_uploader_session.py:64` (`test_storage_state_saved_on_normal_exit`) 和 `:81` (`test_storage_state_saved_on_exception`)。sub-project B 的 deferred finding 不准确。Plan 不加重复测试,只在 progress ledger 里 note 这个发现。

- [ ] **Step 1: Add WeiboNote upload test to test_weibo_uploader_base.py**

用 Edit 工具,在 `WeiboVideoUploadTests` class 之后(line 49 之后)、`ModuleWrapperTests` class 之前(line 51)插入新 class:

old_string:
```python
        self.assertEqual(result["result_url"], "https://weibo.com/v/123")


class ModuleWrapperTests(unittest.TestCase):
```

new_string:
```python
        self.assertEqual(result["result_url"], "https://weibo.com/v/123")


class WeiboNoteUploadTests(unittest.TestCase):
    def test_upload_returns_platform_result_extras(self):
        import asyncio
        uploader = WeiboNote(
            image_paths=["/fake.jpg"], note="test note", tags=[],
            publish_date=0, account_file="/fake.json",
        )
        with patch.object(uploader, "_browser_session") as mock_session, \
             patch.object(uploader, "validate_upload_args", AsyncMock()), \
             patch.object(WeiboNote, "upload_note_content", AsyncMock()):
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def fake_session():
                class FakePage:
                    url = "https://weibo.com/upload/channel"
                yield FakePage()

            mock_session.return_value = fake_session()
            result = asyncio.run(uploader.upload())
        self.assertTrue(result["success"])
        self.assertEqual(result["message"], "发布成功")


class ModuleWrapperTests(unittest.TestCase):
```

- [ ] **Step 2: Run WeiboNote test to verify it passes**

Run:
```bash
.venv/bin/python -m pytest tests/test_weibo_uploader_base.py::WeiboNoteUploadTests -v
```
Expected: `1 passed`。

- [ ] **Step 3: Add KSNote upload test to test_ks_uploader_base.py**

用 Edit 工具,在 `KSVideUploadTests` class 之后(line 39 之后)、`ModuleWrapperTests` class 之前(line 42)插入新 class:

old_string:
```python
        self.assertEqual(result["result_id"], "vid123")


class ModuleWrapperTests(unittest.TestCase):
```

new_string:
```python
        self.assertEqual(result["result_id"], "vid123")


class KSNoteUploadTests(unittest.TestCase):
    def test_upload_returns_unified_dict(self):
        import asyncio
        uploader = KSNote(
            image_paths=["/fake.jpg"], note="test note", tags=[],
            publish_date=0, account_file="/fake.json",
        )
        with patch.object(KSNote, "upload_note_content", AsyncMock(return_value={"share_link": "https://kuaishou.com/n/abc", "video_id": "nid123"})), \
             patch.object(uploader, "validate_upload_args", AsyncMock()):
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def fake_session():
                class FakePage:
                    url = "https://cp.kuaishou.com"
                yield FakePage()

            with patch.object(uploader, "_browser_session", return_value=fake_session()):
                result = asyncio.run(uploader.upload())
        self.assertTrue(result["success"])
        self.assertEqual(result["result_url"], "https://kuaishou.com/n/abc")
        self.assertEqual(result["result_id"], "nid123")


class ModuleWrapperTests(unittest.TestCase):
```

- [ ] **Step 4: Run KSNote test to verify it passes**

Run:
```bash
.venv/bin/python -m pytest tests/test_ks_uploader_base.py::KSNoteUploadTests -v
```
Expected: `1 passed`。

- [ ] **Step 5: Add DouYinNote upload test to test_douyin_uploader_base.py**

用 Edit 工具,在 `DouYinVideoUploadTests` class 之后(line 62 之后)、`ModuleWrapperTests` class 之前(line 65)插入新 class:

old_string:
```python
        self.assertEqual(result["issue_type"], "publish_restricted")


class ModuleWrapperTests(unittest.TestCase):
```

new_string:
```python
        self.assertEqual(result["issue_type"], "publish_restricted")


class DouYinNoteUploadTests(unittest.TestCase):
    def test_upload_returns_success_dict(self):
        import asyncio
        uploader = DouYinNote(
            image_paths=["/fake.jpg"], note="test note", tags=[],
            publish_date=0, account_file="/fake.json",
        )
        with patch.object(uploader, "validate_upload_args", AsyncMock()):
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def fake_session():
                class FakePage:
                    url = "https://creator.douyin.com"
                    async def goto(self, url):
                        pass
                    async def wait_for_url(self, url):
                        pass
                yield FakePage()

            with patch.object(uploader, "_browser_session", return_value=fake_session()), \
                 patch.object(DouYinNote, "upload_note_content", AsyncMock()):
                result = asyncio.run(uploader.upload())
        self.assertTrue(result["success"])


class ModuleWrapperTests(unittest.TestCase):
```

- [ ] **Step 6: Run DouYinNote test to verify it passes**

Run:
```bash
.venv/bin/python -m pytest tests/test_douyin_uploader_base.py::DouYinNoteUploadTests -v
```
Expected: `1 passed`。

- [ ] **Step 7: Add cookie_gen timeout test to test_base_uploader_login.py**

用 Edit 工具,在 `CookieGenTests` class 里(line 130 之后,`if __name__` 之前)添加 timeout 测试:

old_string:
```python
        self.assertTrue(result["success"])
        self.assertTrue(fake_context.storage_state_saved)


if __name__ == "__main__":
```

new_string:
```python
        self.assertTrue(result["success"])
        self.assertTrue(fake_context.storage_state_saved)

    def test_cookie_gen_returns_timeout_when_login_never_completes(self):
        """cookie_gen polls 100 times; if is_login_completed never returns True, returns timeout result."""
        with patch("uploader.base_video.async_playwright") as mock_ap, \
             patch("uploader.base_video.set_init_script", side_effect=lambda ctx: ctx), \
             patch.object(FakeUploader, "is_login_completed", AsyncMock(return_value=False)):
            # FakeContext returns login URL for all gotos - is_login_completed mocked to always False
            fake_context = FakeContext("https://example.com/login", "https://example.com/login")
            fake_pw = FakePlaywright(fake_context)
            mock_ap.return_value = fake_pw
            with patch.object(FakeUploader, "cookie_auth", AsyncMock(return_value=True)):
                result = asyncio.run(FakeUploader.cookie_gen("/fake.json"))
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "timeout")

    def test_cookie_gen_invokes_qrcode_callback(self):
        """cookie_gen calls qrcode_callback with QR code src when extract_qrcode_src returns a URL."""
        callback_calls = []

        async def fake_callback(data):
            callback_calls.append(data)

        with patch("uploader.base_video.async_playwright") as mock_ap, \
             patch("uploader.base_video.set_init_script", side_effect=lambda ctx: ctx), \
             patch.object(FakeUploader, "is_login_completed", AsyncMock(side_effect=[False, True])):
            fake_context = FakeContext("https://example.com/login", "https://example.com/upload")
            fake_pw = FakePlaywright(fake_context)
            mock_ap.return_value = fake_pw
            with patch.object(FakeUploader, "cookie_auth", AsyncMock(return_value=True)):
                result = asyncio.run(FakeUploader.cookie_gen("/fake.json", qrcode_callback=fake_callback))
        self.assertTrue(callback_calls, "qrcode_callback should have been called")
        self.assertIn("qrcode", callback_calls[0])

    def test_cookie_gen_handles_exception(self):
        """cookie_gen catches exceptions during the login flow and returns failed result."""
        with patch("uploader.base_video.async_playwright") as mock_ap, \
             patch("uploader.base_video.set_init_script", side_effect=lambda ctx: ctx):
            fake_context = FakeContext("https://example.com/login", "https://example.com/upload")
            fake_pw = FakePlaywright(fake_context)
            mock_ap.return_value = fake_pw
            # Make page.goto raise an exception
            with patch.object(FakePage, "goto", AsyncMock(side_effect=RuntimeError("network error"))):
                result = asyncio.run(FakeUploader.cookie_gen("/fake.json"))
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "failed")
        self.assertIn("network error", result["message"])


if __name__ == "__main__":
```

- [ ] **Step 8: Run cookie_gen edge case tests**

Run:
```bash
.venv/bin/python -m pytest tests/test_base_uploader_login.py -v
```
Expected: 全绿,包括新增的 3 个测试(test_cookie_gen_returns_timeout_when_login_never_completes, test_cookie_gen_invokes_qrcode_callback, test_cookie_gen_handles_exception)。

如果 timeout 测试因为 100 次轮询太慢而超时,检查 FakePage.wait_for_timeout 是否是 no-op(line 34-35 已确认是 `pass`)。如果仍然慢,可能需要 mock `page.wait_for_timeout` 来跳过等待。implementer 根据实际情况调整。

- [ ] **Step 9: Run full regression suite**

Run:
```bash
.venv/bin/python -m pytest tests/ -v 2>&1 | tail -5
```
Expected: `158 passed`(152 原有 + 6 新增:3 Note upload + 3 cookie_gen edge case)。

- [ ] **Step 10: Commit**

```bash
git add tests/test_weibo_uploader_base.py tests/test_ks_uploader_base.py tests/test_douyin_uploader_base.py tests/test_base_uploader_login.py
git commit -m "$(cat <<'EOF'
test: add Note upload() tests and cookie_gen edge case tests

Add WeiboNote/KSNote/DouYinNote upload() tests (parallel to existing
Video tests) and 3 cookie_gen edge case tests (timeout, qrcode_callback
invocation, exception handling).

Note: storage_state-on-failure tests already exist in
test_base_uploader_session.py (test_storage_state_saved_on_exception),
so no duplicates added.
EOF
)"
```

---

## 完成验证

所有 4 个 task 完成后,运行最终验证:

- [ ] **最终 Step 1: 完整测试套件**

Run:
```bash
.venv/bin/python -m pytest tests/ -v 2>&1 | tail -10
```
Expected: `158 passed`,0 failed。

- [ ] **最终 Step 2: 无 dead package 残留**

Run:
```bash
.venv/bin/python -c "
content = open('requirements.txt', encoding='utf-16').read()
for line in content.splitlines():
    low = line.lower()
    if any(p in low for p in ['alembic','sqlalchemy','mako','blinker','click','itsdangerous','jinja2','markupsafe','werkzeug']):
        print(f'RESIDUAL: {line}')
        break
else:
    print('No dead packages')
"
```
Expected: `No dead packages`。

- [ ] **最终 Step 3: 无 self.local_executable_path in ks/xiaohongshu**

Run:
```bash
grep -n "self.local_executable_path" uploader/ks_uploader/main.py uploader/xiaohongshu_uploader/main.py
```
Expected: 无输出。

- [ ] **最终 Step 4: 提交历史检查**

Run:
```bash
git log --oneline main..HEAD
```
Expected: 看到 4 个 task 的 commit。
