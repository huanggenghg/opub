# Sub-project F: Production Risk Adoption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the loop on sub-project E's parked production risk by adopting `save_on_success_only=True` in all 12 upload methods + fill 2 test gaps E parked.

**Architecture:** 3 sequential tasks: (1) flip 12 `async with self._browser_session()` calls to `save_on_success_only=True` across 7 platform files, (2) add DouYinNote publish_restricted test, (3) add positive log-firing-on-success test. Each task keeps the 163-test regression suite green.

**Tech Stack:** Python 3, pytest, playwright, asynccontextmanager. Base class `BaseBrowserUploader` in `uploader/base_video.py` inherited by 7 browser platforms.

## Global Constraints

- **Branch:** `sub-project-f/production-risk-adoption` (already created from `main`)
- **Test baseline:** 163 tests passing (from sub-projects A+B+C+D+E). Each task must keep all tests green.
- **save_on_success_only default:** Stays `False` in `_browser_session` signature (backward-compatible). F adopts `True` via explicit per-call, NOT by flipping the default.
- **All 12 upload methods adopt True:** The spec listed 11 methods (mirroring E's log-timing scope), but `tk_uploader/main.py:94` also uses `_browser_session()` and must be included. Tk doesn't have a "cookie 更新完毕" log so E's spec didn't list it, but F's save_on_success_only adoption applies to all `_browser_session()` callers.
- **Behavioral change (deliberate):** On upload failure, storage_state is NO LONGER saved. Cookie file retains pre-upload state. This prevents cookie corruption when uploads fail mid-way.
- **Log message text:** Keep "cookie 更新完毕" unchanged where it exists.

---

### Task 1: save_on_success_only adoption (12 methods, 7 files)

**Files:**
- Modify: `uploader/weibo_uploader/main.py:525, 649` (WeiboVideo.upload, WeiboNote.upload)
- Modify: `uploader/xiaohongshu_uploader/main.py:734, 882` (XiaoHongShuVideo.upload, XiaoHongShuNote.upload)
- Modify: `uploader/tencent_uploader/main.py:748, 835` (TencentVideo.upload, TencentNote.upload)
- Modify: `uploader/ks_uploader/main.py:668, 852` (KSVideo.upload, KSNote.upload)
- Modify: `uploader/baijiahao_uploader/main.py:382` (BaijiahaoVideo.upload)
- Modify: `uploader/douyin_uploader/main.py:698, 854` (DouYinVideo.upload, DouYinNote.upload)
- Modify: `uploader/tk_uploader/main.py:94` (TkUploader.upload)

**Interfaces:**
- Consumes: `_browser_session(self, headless=None, save_on_success_only=False)` from `BaseBrowserUploader` (added in sub-project E)
- Produces: All 12 upload methods now pass `save_on_success_only=True`, skipping storage_state save on failure

- [ ] **Step 1: Change weibo_uploader/main.py - both calls**

Use Edit tool with `replace_all: true` on `uploader/weibo_uploader/main.py`.

old_string:
```
            async with self._browser_session() as page:
```

new_string:
```
            async with self._browser_session(save_on_success_only=True) as page:
```

replace_all: true (replaces both line 525 and line 649)

- [ ] **Step 2: Change xiaohongshu_uploader/main.py - both calls**

Use Edit tool with `replace_all: true` on `uploader/xiaohongshu_uploader/main.py`.

old_string:
```
            async with self._browser_session() as page:
```

new_string:
```
            async with self._browser_session(save_on_success_only=True) as page:
```

replace_all: true (replaces both line 734 and line 882)

- [ ] **Step 3: Change tencent_uploader/main.py - both calls**

Use Edit tool with `replace_all: true` on `uploader/tencent_uploader/main.py`.

old_string:
```
            async with self._browser_session() as page:
```

new_string:
```
            async with self._browser_session(save_on_success_only=True) as page:
```

replace_all: true (replaces both line 748 and line 835)

- [ ] **Step 4: Change ks_uploader/main.py - both calls**

Use Edit tool with `replace_all: true` on `uploader/ks_uploader/main.py`.

old_string:
```
            async with self._browser_session() as page:
```

new_string:
```
            async with self._browser_session(save_on_success_only=True) as page:
```

replace_all: true (replaces both line 668 and line 852)

- [ ] **Step 5: Change baijiahao_uploader/main.py - single call**

Use Edit tool on `uploader/baijiahao_uploader/main.py`.

old_string:
```
            async with self._browser_session() as page:
```

new_string:
```
            async with self._browser_session(save_on_success_only=True) as page:
```

- [ ] **Step 6: Change douyin_uploader/main.py - both calls**

Use Edit tool with `replace_all: true` on `uploader/douyin_uploader/main.py`.

old_string:
```
            async with self._browser_session() as page:
```

new_string:
```
            async with self._browser_session(save_on_success_only=True) as page:
```

replace_all: true (replaces both line 698 and line 854)

- [ ] **Step 7: Change tk_uploader/main.py - single call**

Use Edit tool on `uploader/tk_uploader/main.py`.

old_string:
```
            async with self._browser_session() as page:
```

new_string:
```
            async with self._browser_session(save_on_success_only=True) as page:
```

- [ ] **Step 8: Verify no bare _browser_session() calls remain**

Run:
```bash
grep -rn "self._browser_session()" uploader/
```
Expected: No output (all 12 calls now pass `save_on_success_only=True`).

- [ ] **Step 9: Verify 12 save_on_success_only=True calls exist**

Run:
```bash
grep -rn "save_on_success_only=True" uploader/ | wc -l
```
Expected: `12`

- [ ] **Step 10: Run full regression suite**

Run:
```bash
.venv/bin/python -m pytest tests/ -v 2>&1 | tail -5
```
Expected: `163 passed`.

- [ ] **Step 11: Commit**

```bash
git add uploader/weibo_uploader/main.py uploader/xiaohongshu_uploader/main.py uploader/tencent_uploader/main.py uploader/ks_uploader/main.py uploader/baijiahao_uploader/main.py uploader/douyin_uploader/main.py uploader/tk_uploader/main.py
git commit -m "$(cat <<'EOF'
fix(uploaders): adopt save_on_success_only=True in all 12 upload methods

Closes sub-project E's parked production risk: the save_on_success_only
flag existed but no caller used True. All 12 upload() methods across 7
platform files now pass save_on_success_only=True, so storage_state is
NOT saved when upload fails mid-way. This prevents cookie file corruption
on partial-failure uploads.

Behavioral change: on upload failure, cookie file retains pre-upload
state. Trade-off: refreshed cookies during a failed session are lost,
but this is preferable to overwriting a valid cookie file with partial
state.

Note: tk_uploader was not in E's log-timing scope (tk has no "cookie
更新完毕" log) but is included here because it uses _browser_session().
EOF
)"
```

---

### Task 2: DouYinNote publish_restricted test

**Files:**
- Modify: `tests/test_douyin_uploader_base.py` (add test to `DouYinNoteUploadTests` class)

**Interfaces:**
- Consumes: `DouYinNote`, `DouyinPublishRestrictedError` from `uploader/douyin_uploader/main.py` (already imported in test file)
- Produces: `test_note_upload_maps_restriction_to_account_issue` test

- [ ] **Step 1: Add DouYinNote publish_restricted test**

Use Edit tool on `tests/test_douyin_uploader_base.py`. Add the new test after the existing `test_upload_returns_success_dict` in `DouYinNoteUploadTests` class (after line 88, before the `ModuleWrapperTests` class).

old_string:
```python
            with patch.object(uploader, "_browser_session", return_value=fake_session()), \
                 patch.object(DouYinNote, "upload_note_content", AsyncMock()):
                result = asyncio.run(uploader.upload())
        self.assertTrue(result["success"])


class ModuleWrapperTests(unittest.TestCase):
```

new_string:
```python
            with patch.object(uploader, "_browser_session", return_value=fake_session()), \
                 patch.object(DouYinNote, "upload_note_content", AsyncMock()):
                result = asyncio.run(uploader.upload())
        self.assertTrue(result["success"])

    def test_note_upload_maps_restriction_to_account_issue(self):
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
                 patch.object(DouYinNote, "upload_note_content", AsyncMock(side_effect=DouyinPublishRestrictedError("限制"))):
                result = asyncio.run(uploader.upload())
        self.assertFalse(result["success"])
        self.assertTrue(result["account_issue"])
        self.assertEqual(result["issue_type"], "publish_restricted")


class ModuleWrapperTests(unittest.TestCase):
```

- [ ] **Step 2: Run the new test**

Run:
```bash
.venv/bin/python -m pytest tests/test_douyin_uploader_base.py::DouYinNoteUploadTests::test_note_upload_maps_restriction_to_account_issue -v
```
Expected: `1 passed`

- [ ] **Step 3: Run full douyin test suite**

Run:
```bash
.venv/bin/python -m pytest tests/test_douyin_uploader_base.py -v
```
Expected: All tests pass (original + 1 new).

- [ ] **Step 4: Run full regression suite**

Run:
```bash
.venv/bin/python -m pytest tests/ -v 2>&1 | tail -5
```
Expected: `164 passed` (163 + 1 new).

- [ ] **Step 5: Commit**

```bash
git add tests/test_douyin_uploader_base.py
git commit -m "$(cat <<'EOF'
test(douyin): add DouYinNote publish_restricted test

Mirrors the existing DouYinVideo test_upload_maps_restriction_to_account_issue
for DouYinNote. Verifies DouYinNote.upload() maps DouyinPublishRestrictedError
to {"account_issue": True, "issue_type": "publish_restricted"}.

Closes sub-project D's deferred test gap: only DouYinVideo had the test.
EOF
)"
```

---

### Task 3: Positive log-firing-on-success test

**Files:**
- Modify: `tests/test_weibo_uploader_base.py` (add test to `WeiboLogTimingTests` class from sub-project E)

**Interfaces:**
- Consumes: `WeiboVideo`, `weibo_logger` from `uploader/weibo_uploader/main.py` (already imported in test file)
- Produces: `test_log_printed_on_success` test

- [ ] **Step 1: Add positive log-firing-on-success test**

Use Edit tool on `tests/test_weibo_uploader_base.py`. Add the new test to the `WeiboLogTimingTests` class (created in sub-project E), after the existing `test_log_not_printed_when_upload_raises_exception` test.

First, read the current end of `WeiboLogTimingTests` class to find the exact insertion point. The class currently has one test method. Add the new test after it, before the `ModuleWrapperTests` class.

old_string:
```python
        for call in mock_logger.success.call_args_list:
            args, kwargs = call
            if args and "cookie 更新完毕" in str(args[0]):
                self.fail("cookie 更新完毕 log was printed on failure - should only print on success")


class ModuleWrapperTests(unittest.TestCase):
```

new_string:
```python
        for call in mock_logger.success.call_args_list:
            args, kwargs = call
            if args and "cookie 更新完毕" in str(args[0]):
                self.fail("cookie 更新完毕 log was printed on failure - should only print on success")

    def test_log_printed_on_success(self):
        """On success, 'cookie 更新完毕' log fires. Complements the failure-path
        test (verifies log does NOT fire on failure) and the ordering test in
        test_base_uploader_session.py (verifies storage_state saves before code
        after async with runs)."""
        import asyncio
        uploader = WeiboVideo(
            title="test", file_path="/fake.mp4", tags=[],
            publish_date=0, account_file="/fake.json",
        )
        with patch.object(uploader, "validate_upload_args", AsyncMock()), \
             patch.object(uploader, "_browser_session") as mock_session, \
             patch.object(WeiboVideo, "upload_video_content", AsyncMock(return_value="https://weibo.com/v/123")), \
             patch("uploader.weibo_uploader.main.weibo_logger") as mock_logger:
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def fake_session():
                class FakePage:
                    url = "https://weibo.com/upload"
                yield FakePage()

            mock_session.return_value = fake_session()
            result = asyncio.run(uploader.upload())
        self.assertTrue(result["success"])
        # "cookie 更新完毕" log must be called on success
        success_calls = []
        for call in mock_logger.success.call_args_list:
            args, kwargs = call
            if args and "cookie 更新完毕" in str(args[0]):
                success_calls.append(call)
        self.assertEqual(len(success_calls), 1)


class ModuleWrapperTests(unittest.TestCase):
```

- [ ] **Step 2: Run the new test**

Run:
```bash
.venv/bin/python -m pytest tests/test_weibo_uploader_base.py::WeiboLogTimingTests::test_log_printed_on_success -v
```
Expected: `1 passed`

- [ ] **Step 3: Run full weibo test suite**

Run:
```bash
.venv/bin/python -m pytest tests/test_weibo_uploader_base.py -v
```
Expected: All tests pass (original + 1 new).

- [ ] **Step 4: Run full regression suite**

Run:
```bash
.venv/bin/python -m pytest tests/ -v 2>&1 | tail -5
```
Expected: `165 passed` (164 + 1 new).

- [ ] **Step 5: Commit**

```bash
git add tests/test_weibo_uploader_base.py
git commit -m "$(cat <<'EOF'
test(weibo): add positive log-firing-on-success test

Verifies "cookie 更新完毕" log DOES fire on upload success. Complements
sub-project E's failure-path test (log does NOT fire on failure) and
ordering test (storage_state saves before code after async with).

Closes sub-project E's parked test gap: no positive test verified the
log fires on success after storage_state save.
EOF
)"
```

---

## 完成验证

所有 3 个 task 完成后,运行最终验证:

- [ ] **最终 Step 1: 完整测试套件**

Run:
```bash
.venv/bin/python -m pytest tests/ -v 2>&1 | tail -10
```
Expected: `165 passed`,0 failed。

- [ ] **最终 Step 2: 无 bare _browser_session() 调用**

Run:
```bash
grep -rn "self._browser_session()" uploader/ || echo "OK - all callers pass save_on_success_only"
```
Expected: `OK - all callers pass save_on_success_only`

- [ ] **最终 Step 3: 12 处 save_on_success_only=True**

Run:
```bash
grep -rn "save_on_success_only=True" uploader/ | wc -l
```
Expected: `12`

- [ ] **最终 Step 4: 提交历史检查**

Run:
```bash
git log --oneline main..HEAD
```
Expected: 看到 3 个 task 的 commit + 1 个 spec commit。
