# Sub-project E: Production Behavior Risks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 3 Category 5 production behavior risks: storage_state-on-failure, premature "cookie 更新完毕" log, cookie_auth headless inconsistency.

**Architecture:** 3 sequential tasks: (1) add `save_on_success_only` flag to `_browser_session` + move 11 premature log calls from inside `async with` to after it, (2) standardize cookie_auth headless from hardcoded `True` to `LOCAL_CHROME_HEADLESS`, (3) add tests covering the new behavior. Each task keeps the 158-test regression suite green.

**Tech Stack:** Python 3, pytest, playwright, asynccontextmanager. Base class `BaseBrowserUploader` in `uploader/base_video.py` inherited by 7 browser platforms.

## Global Constraints

- **Branch:** `sub-project-e/production-behavior-risks` (already created from `main`)
- **Test baseline:** 158 tests passing (from sub-projects A+B+C+D). Each task must keep all tests green.
- **base class safety:** `uploader/base_video.py` is inherited by 7 browser platforms. Any refactor must preserve behavior exactly for existing tests.
- **save_on_success_only default:** Must be `False` (preserves current behavior - save always). Opt-in `True` skips save on failure.
- **LOCAL_CHROME_HEADLESS:** Defined in `conf.py` as `_config.get("chrome_headless", False)`. Currently `False` in user's config. Changing cookie_auth from `headless=True` to `LOCAL_CHROME_HEADLESS` IS a behavioral change (cookie_auth becomes non-headless) - this is deliberate, aligning cookie_auth with _browser_session's upload() behavior.
- **Log message:** Keep the exact text "cookie 更新完毕" - only change timing (from before save to after save), not the message.
- **5-param setup signature:** All platform `*_setup` wrappers must keep `(account_file, handle, return_detail, qrcode_callback, headless)` - enforced by tests. Do NOT change setup signatures.

---

### Task 1: storage_state flag + premature log fix

**Files:**
- Modify: `uploader/base_video.py:296-312` (`_browser_session` method)
- Modify: `uploader/weibo_uploader/main.py:527, 651` (WeiboVideo.upload, WeiboNote.upload)
- Modify: `uploader/xiaohongshu_uploader/main.py:736, 884` (XiaoHongShuVideo.upload, XiaoHongShuNote.upload)
- Modify: `uploader/tencent_uploader/main.py:750, 846` (TencentVideo.upload, TencentNote.upload)
- Modify: `uploader/ks_uploader/main.py:670, 854` (KSVideo.upload, KSNote.upload)
- Modify: `uploader/baijiahao_uploader/main.py:384` (BaijiahaoVideo.upload)
- Modify: `uploader/douyin_uploader/main.py:700, 860` (DouYinVideo.upload, DouYinNote.upload)

**Interfaces:**
- Consumes: `LOCAL_CHROME_HEADLESS` from `conf` (already imported in base_video.py)
- Produces: `_browser_session(self, headless=None, save_on_success_only=False)` - new optional param. Existing callers (`async with self._browser_session() as page:`) are unaffected (both params default).

- [ ] **Step 1: Add `save_on_success_only` flag to `_browser_session` in base_video.py**

用 Edit 工具修改 `uploader/base_video.py:296-312`。

old_string:
```python
    @asynccontextmanager
    async def _browser_session(self, headless: Optional[bool] = None):
        """Launch browser + context with stored cookies, yield page.
        Saves storage_state on exit (finally). Ensures cleanup."""
        async with async_playwright() as playwright:
            browser = await self._launch_browser(playwright, headless if headless is not None else self.headless)
            context = await self._init_context(browser, self.account_file)
            page = await context.new_page()
            try:
                yield page
            finally:
                try:
                    await context.storage_state(path=self.account_file)
                except Exception:
                    pass
                await context.close()
                await browser.close()
```

new_string:
```python
    @asynccontextmanager
    async def _browser_session(self, headless: Optional[bool] = None, save_on_success_only: bool = False):
        """Launch browser + context with stored cookies, yield page.
        Saves storage_state on exit. If save_on_success_only=True, skips save
        when the yielded block raised an exception."""
        async with async_playwright() as playwright:
            browser = await self._launch_browser(playwright, headless if headless is not None else self.headless)
            context = await self._init_context(browser, self.account_file)
            page = await context.new_page()
            success = False
            try:
                yield page
                success = True
            finally:
                if not save_on_success_only or success:
                    try:
                        await context.storage_state(path=self.account_file)
                    except Exception:
                        pass
                await context.close()
                await browser.close()
```

- [ ] **Step 2: Run base uploader session tests to verify flag doesn't break existing behavior**

Run:
```bash
.venv/bin/python -m pytest tests/test_base_uploader_session.py -v
```
Expected: 3 tests pass (existing tests use default `save_on_success_only=False`, behavior unchanged).

- [ ] **Step 3: Move "cookie 更新完毕" log in WeiboVideo.upload (weibo_uploader/main.py:527)**

用 Edit 工具,把 log 从 `async with` block 内部移到外部。

old_string:
```python
            async with self._browser_session() as page:
                video_link = await self.upload_video_content(page)
                weibo_logger.success(_msg("🥳", "cookie 更新完毕"))
                result["success"] = True
                if video_link:
                    result["result_url"] = video_link
                    result["message"] = f"发布成功，视频链接: {video_link}"
                else:
                    result["message"] = "发布成功，但未获取到视频链接"
        except Exception as e:
```

new_string:
```python
            async with self._browser_session() as page:
                video_link = await self.upload_video_content(page)
                result["success"] = True
                if video_link:
                    result["result_url"] = video_link
                    result["message"] = f"发布成功，视频链接: {video_link}"
                else:
                    result["message"] = "发布成功，但未获取到视频链接"
            weibo_logger.success(_msg("🥳", "cookie 更新完毕"))
        except Exception as e:
```

- [ ] **Step 4: Move "cookie 更新完毕" log in WeiboNote.upload (weibo_uploader/main.py:651)**

old_string:
```python
            async with self._browser_session() as page:
                await self.upload_note_content(page)
                weibo_logger.success(_msg("🥳", "cookie 更新完毕"))
                result["success"] = True
                result["message"] = "发布成功"
        except Exception as e:
```

new_string:
```python
            async with self._browser_session() as page:
                await self.upload_note_content(page)
                result["success"] = True
                result["message"] = "发布成功"
            weibo_logger.success(_msg("🥳", "cookie 更新完毕"))
        except Exception as e:
```

- [ ] **Step 5: Move "cookie 更新完毕" log in XiaoHongShuVideo.upload (xiaohongshu_uploader/main.py:736)**

old_string:
```python
            async with self._browser_session() as page:
                share_result = await self.upload_video_content(page)
                xiaohongshu_logger.success(_msg("🥳", "cookie 更新完毕"))

                share_link = share_result.get("share_link", "") if share_result else ""
                note_id = share_result.get("note_id", "") if share_result else ""

                result["success"] = True
                result["message"] = "发布成功"

                if share_link:
                    xiaohongshu_logger.info(_msg("🔗", f"分享链接: {share_link}"))
                    result["result_url"] = share_link

                    # 写入Excel
                    try:
                        excel_result = write_video_link(video_link=share_link)
                        if excel_result["success"]:
                            xiaohongshu_logger.success(_msg("📝", f"已写入Excel: {excel_result['filepath']}"))
                        else:
                            xiaohongshu_logger.warning(_msg("⚠️", f"写入Excel失败: {excel_result['message']}"))
                    except Exception as excel_err:
                        xiaohongshu_logger.warning(_msg("⚠️", f"写入Excel异常: {excel_err}"))

                if note_id:
                    result["result_id"] = note_id

                if not share_link:
                    share_msg = share_result.get("message", "") if share_result else ""
                    result["message"] = f"发布成功，但获取分享链接失败: {share_msg}"
        except Exception as e:
```

new_string:
```python
            async with self._browser_session() as page:
                share_result = await self.upload_video_content(page)

                share_link = share_result.get("share_link", "") if share_result else ""
                note_id = share_result.get("note_id", "") if share_result else ""

                result["success"] = True
                result["message"] = "发布成功"

                if share_link:
                    xiaohongshu_logger.info(_msg("🔗", f"分享链接: {share_link}"))
                    result["result_url"] = share_link

                    # 写入Excel
                    try:
                        excel_result = write_video_link(video_link=share_link)
                        if excel_result["success"]:
                            xiaohongshu_logger.success(_msg("📝", f"已写入Excel: {excel_result['filepath']}"))
                        else:
                            xiaohongshu_logger.warning(_msg("⚠️", f"写入Excel失败: {excel_result['message']}"))
                    except Exception as excel_err:
                        xiaohongshu_logger.warning(_msg("⚠️", f"写入Excel异常: {excel_err}"))

                if note_id:
                    result["result_id"] = note_id

                if not share_link:
                    share_msg = share_result.get("message", "") if share_result else ""
                    result["message"] = f"发布成功，但获取分享链接失败: {share_msg}"
            xiaohongshu_logger.success(_msg("🥳", "cookie 更新完毕"))
        except Exception as e:
```

- [ ] **Step 6: Move "cookie 更新完毕" log in XiaoHongShuNote.upload (xiaohongshu_uploader/main.py:884)**

old_string:
```python
            async with self._browser_session() as page:
                share_result = await self.upload_note_content(page)
                xiaohongshu_logger.success(_msg("🥳", "cookie 更新完毕"))

                share_link = share_result.get("share_link", "") if share_result else ""
                note_id = share_result.get("note_id", "") if share_result else ""

                result["success"] = True
                result["message"] = "发布成功"

                if share_link:
                    xiaohongshu_logger.info(_msg("🔗", f"分享链接: {share_link}"))
                    result["result_url"] = share_link

                    # 写入Excel
                    try:
                        excel_result = write_video_link(video_link=share_link)
                        if excel_result["success"]:
                            xiaohongshu_logger.success(_msg("📝", f"已写入Excel: {excel_result['filepath']}"))
                        else:
                            xiaohongshu_logger.warning(_msg("⚠️", f"写入Excel失败: {excel_result['message']}"))
                    except Exception as excel_err:
                        xiaohongshu_logger.warning(_msg("⚠️", f"写入Excel异常: {excel_err}"))

                if note_id:
                    result["result_id"] = note_id

                if not share_link:
                    share_msg = share_result.get("message", "") if share_result else ""
                    result["message"] = f"发布成功，但获取分享链接失败: {share_msg}"
        except Exception as e:
```

new_string:
```python
            async with self._browser_session() as page:
                share_result = await self.upload_note_content(page)

                share_link = share_result.get("share_link", "") if share_result else ""
                note_id = share_result.get("note_id", "") if share_result else ""

                result["success"] = True
                result["message"] = "发布成功"

                if share_link:
                    xiaohongshu_logger.info(_msg("🔗", f"分享链接: {share_link}"))
                    result["result_url"] = share_link

                    # 写入Excel
                    try:
                        excel_result = write_video_link(video_link=share_link)
                        if excel_result["success"]:
                            xiaohongshu_logger.success(_msg("📝", f"已写入Excel: {excel_result['filepath']}"))
                        else:
                            xiaohongshu_logger.warning(_msg("⚠️", f"写入Excel失败: {excel_result['message']}"))
                    except Exception as excel_err:
                        xiaohongshu_logger.warning(_msg("⚠️", f"写入Excel异常: {excel_err}"))

                if note_id:
                    result["result_id"] = note_id

                if not share_link:
                    share_msg = share_result.get("message", "") if share_result else ""
                    result["message"] = f"发布成功，但获取分享链接失败: {share_msg}"
            xiaohongshu_logger.success(_msg("🥳", "cookie 更新完毕"))
        except Exception as e:
```

- [ ] **Step 7: Move "cookie 更新完毕" log in TencentVideo.upload (tencent_uploader/main.py:750)**

old_string:
```python
            async with self._browser_session() as page:
                await self.upload_video_content(page)
                tencent_logger.success(_msg("🥳", "cookie 更新完毕"))
                result["success"] = True
                result["message"] = "发布成功"
        except Exception as e:
```

new_string:
```python
            async with self._browser_session() as page:
                await self.upload_video_content(page)
                result["success"] = True
                result["message"] = "发布成功"
            tencent_logger.success(_msg("🥳", "cookie 更新完毕"))
        except Exception as e:
```

- [ ] **Step 8: Move "cookie 更新完毕" log in TencentNote.upload (tencent_uploader/main.py:846)**

old_string:
```python
                await self.submit_publish(page)

                tencent_logger.success(_msg("🥳", "cookie 更新完毕"))
                result["success"] = True
                result["message"] = "发布成功"
        except Exception as e:
```

new_string:
```python
                await self.submit_publish(page)

                result["success"] = True
                result["message"] = "发布成功"
            tencent_logger.success(_msg("🥳", "cookie 更新完毕"))
        except Exception as e:
```

- [ ] **Step 9: Move "cookie 更新完毕" log in KSVideo.upload (ks_uploader/main.py:670)**

old_string:
```python
            async with self._browser_session() as page:
                share_result = await self.upload_video_content(page)
                kuaishou_logger.success(_msg("🥳", "cookie 更新完毕"))

                share_link = share_result.get("share_link", "") if share_result else ""
                video_id = share_result.get("video_id", "") if share_result else ""

                result["success"] = True
                result["message"] = "发布成功"

                if share_link:
                    result["result_url"] = share_link

                if video_id:
                    result["result_id"] = video_id

                if not share_link:
                    result["message"] = "发布成功，但获取分享链接失败"
        except Exception as e:
```

new_string:
```python
            async with self._browser_session() as page:
                share_result = await self.upload_video_content(page)

                share_link = share_result.get("share_link", "") if share_result else ""
                video_id = share_result.get("video_id", "") if share_result else ""

                result["success"] = True
                result["message"] = "发布成功"

                if share_link:
                    result["result_url"] = share_link

                if video_id:
                    result["result_id"] = video_id

                if not share_link:
                    result["message"] = "发布成功，但获取分享链接失败"
            kuaishou_logger.success(_msg("🥳", "cookie 更新完毕"))
        except Exception as e:
```

- [ ] **Step 10: Move "cookie 更新完毕" log in KSNote.upload (ks_uploader/main.py:854)**

old_string:
```python
            async with self._browser_session() as page:
                share_result = await self.upload_note_content(page)
                kuaishou_logger.success(_msg("🥳", "cookie 更新完毕"))

                share_link = share_result.get("share_link", "") if share_result else ""
                video_id = share_result.get("video_id", "") if share_result else ""

                result["success"] = True
                result["message"] = "发布成功"

                if share_link:
                    result["result_url"] = share_link

                if video_id:
                    result["result_id"] = video_id

                if not share_link:
                    result["message"] = "发布成功，但获取分享链接失败"
        except Exception as e:
```

new_string:
```python
            async with self._browser_session() as page:
                share_result = await self.upload_note_content(page)

                share_link = share_result.get("share_link", "") if share_result else ""
                video_id = share_result.get("video_id", "") if share_result else ""

                result["success"] = True
                result["message"] = "发布成功"

                if share_link:
                    result["result_url"] = share_link

                if video_id:
                    result["result_id"] = video_id

                if not share_link:
                    result["message"] = "发布成功，但获取分享链接失败"
            kuaishou_logger.success(_msg("🥳", "cookie 更新完毕"))
        except Exception as e:
```

- [ ] **Step 11: Move "cookie 更新完毕" log in BaijiahaoVideo.upload (baijiahao_uploader/main.py:384)**

old_string:
```python
            async with self._browser_session() as page:
                video_link = await self.upload_video_content(page)
                baijiahao_logger.success(_msg("🥳", "cookie 更新完毕"))
                result["success"] = True
                if video_link:
                    result["result_url"] = video_link
                    result["message"] = f"发布成功，视频链接: {video_link}"
                else:
                    result["message"] = "发布成功"
        except Exception as e:
```

new_string:
```python
            async with self._browser_session() as page:
                video_link = await self.upload_video_content(page)
                result["success"] = True
                if video_link:
                    result["result_url"] = video_link
                    result["message"] = f"发布成功，视频链接: {video_link}"
                else:
                    result["message"] = "发布成功"
            baijiahao_logger.success(_msg("🥳", "cookie 更新完毕"))
        except Exception as e:
```

- [ ] **Step 12: Move "cookie 更新完毕" log in DouYinVideo.upload (douyin_uploader/main.py:700)**

old_string:
```python
            async with self._browser_session() as page:
                video_link = await self.upload_video_content(page)
                douyin_logger.success(_msg("🥳", "cookie 更新完毕"))
                result["success"] = True
                if video_link:
                    result["result_url"] = video_link
                    result["message"] = f"发布成功，视频链接: {video_link}"
                else:
                    result["message"] = "发布成功"
        except DouyinPublishRestrictedError as exc:
```

new_string:
```python
            async with self._browser_session() as page:
                video_link = await self.upload_video_content(page)
                result["success"] = True
                if video_link:
                    result["result_url"] = video_link
                    result["message"] = f"发布成功，视频链接: {video_link}"
                else:
                    result["message"] = "发布成功"
            douyin_logger.success(_msg("🥳", "cookie 更新完毕"))
        except DouyinPublishRestrictedError as exc:
```

- [ ] **Step 13: Move "cookie 更新完毕" log in DouYinNote.upload (douyin_uploader/main.py:860)**

old_string:
```python
                await self.upload_note_content(page)
                douyin_logger.success(_msg("🥳", "cookie 更新完毕"))
                result["success"] = True
                result["message"] = "发布成功"
        except DouyinPublishRestrictedError as exc:
```

new_string:
```python
                await self.upload_note_content(page)
                result["success"] = True
                result["message"] = "发布成功"
            douyin_logger.success(_msg("🥳", "cookie 更新完毕"))
        except DouyinPublishRestrictedError as exc:
```

- [ ] **Step 14: Verify no "cookie 更新完毕" log remains inside async with blocks**

Run:
```bash
grep -B2 "cookie 更新完毕" uploader/*_uploader/main.py | grep "async with" || echo "No log inside async with - OK"
```
Expected: `No log inside async with - OK`

- [ ] **Step 15: Run full regression suite**

Run:
```bash
.venv/bin/python -m pytest tests/ -v 2>&1 | tail -5
```
Expected: `158 passed`。

- [ ] **Step 16: Commit**

```bash
git add uploader/base_video.py uploader/weibo_uploader/main.py uploader/xiaohongshu_uploader/main.py uploader/tencent_uploader/main.py uploader/ks_uploader/main.py uploader/baijiahao_uploader/main.py uploader/douyin_uploader/main.py
git commit -m "$(cat <<'EOF'
fix(base): add save_on_success_only flag + fix premature cookie log timing

- _browser_session: add save_on_success_only param (default False preserves
  current always-save behavior; True skips save on failure)
- Move 11 "cookie 更新完毕" log calls from inside async with block to after
  it (after storage_state save in finally). Log no longer fires on failure.
EOF
)"
```

---

### Task 2: cookie_auth headless standardization

**Files:**
- Modify: `uploader/base_video.py:204` (base class cookie_auth)
- Modify: `uploader/douyin_uploader/main.py:322` (douyin cookie_auth override)

**Interfaces:**
- Consumes: `LOCAL_CHROME_HEADLESS` from `conf` (already imported in both files)
- Produces: cookie_auth uses `LOCAL_CHROME_HEADLESS` instead of hardcoded `True`

- [ ] **Step 1: Change base class cookie_auth headless to LOCAL_CHROME_HEADLESS**

用 Edit 工具修改 `uploader/base_video.py:204`。

old_string:
```python
            browser = await cls._launch_browser(playwright, headless=True)
```

new_string:
```python
            browser = await cls._launch_browser(playwright, headless=LOCAL_CHROME_HEADLESS)
```

**Note:** This old_string appears in both `cookie_auth` (line 204) and possibly other methods. If the Edit tool reports the string is not unique, include more context:

old_string (with context):
```python
    async def cookie_auth(cls, account_file: str) -> bool:
        """Navigate to upload page, check if still logged in."""
        if not os.path.exists(account_file):
            return False
        async with async_playwright() as playwright:
            browser = await cls._launch_browser(playwright, headless=True)
```

new_string (with context):
```python
    async def cookie_auth(cls, account_file: str) -> bool:
        """Navigate to upload page, check if still logged in."""
        if not os.path.exists(account_file):
            return False
        async with async_playwright() as playwright:
            browser = await cls._launch_browser(playwright, headless=LOCAL_CHROME_HEADLESS)
```

- [ ] **Step 2: Change douyin cookie_auth headless to LOCAL_CHROME_HEADLESS**

用 Edit 工具修改 `uploader/douyin_uploader/main.py:322`。

old_string:
```python
    async def cookie_auth(cls, account_file: str) -> bool:
        """Override: douyin cookie 校验需要等待 publish marker + DOM marker 检查。"""
        if not os.path.exists(account_file):
            return False
        async with async_playwright() as playwright:
            browser = await cls._launch_browser(playwright, headless=True)
```

new_string:
```python
    async def cookie_auth(cls, account_file: str) -> bool:
        """Override: douyin cookie 校验需要等待 publish marker + DOM marker 检查。"""
        if not os.path.exists(account_file):
            return False
        async with async_playwright() as playwright:
            browser = await cls._launch_browser(playwright, headless=LOCAL_CHROME_HEADLESS)
```

- [ ] **Step 3: Verify no headless=True remains in cookie_auth methods**

Run:
```bash
grep -n "headless=True" uploader/base_video.py uploader/douyin_uploader/main.py
```
Expected: 无输出(或只在不相关的行,如 `_browser_session` 里 `self.headless` 不是 `True`)。如果输出里有 cookie_auth 相关的 `headless=True`,说明修改不完整。

- [ ] **Step 4: Run full regression suite**

Run:
```bash
.venv/bin/python -m pytest tests/ -v 2>&1 | tail -5
```
Expected: `158 passed`。

- [ ] **Step 5: Commit**

```bash
git add uploader/base_video.py uploader/douyin_uploader/main.py
git commit -m "$(cat <<'EOF'
fix(cookie_auth): standardize headless to LOCAL_CHROME_HEADLESS

Base class and douyin cookie_auth were hardcoded to headless=True, while
baijiahao/tencent already used LOCAL_CHROME_HEADLESS. Standardize all to
LOCAL_CHROME_HEADLESS so cookie validation respects the user's debug
setting (same as _browser_session's upload() behavior).

Behavioral change: when LOCAL_CHROME_HEADLESS=False (current config),
cookie_auth now shows the browser window. This is deliberate - aligns
cookie_auth with upload() and baijiahao/tencent.
EOF
)"
```

---

### Task 3: Test coverage for new behavior

**Files:**
- Modify: `tests/test_base_uploader_session.py` (add save_on_success_only tests + headless test)
- Modify: `tests/test_weibo_uploader_base.py` (add log timing test)

**Interfaces:**
- Consumes: `FakeUploader`, `FakePage`, `FakeContext`, `FakeBrowser`, `FakePlaywright` from `test_base_uploader_session.py` (existing test infrastructure)
- Consumes: `WeiboVideo`, `weibo_logger` from `uploader/weibo_uploader/main.py`
- Produces: 4 new tests (2 save_on_success_only + 1 log timing + 1 headless)

- [ ] **Step 1: Add save_on_success_only=True skips save on failure test**

用 Edit 工具,在 `tests/test_base_uploader_session.py` 的 `BrowserSessionTests` class 里,`test_storage_state_saved_on_exception` 方法之后(line 97 之后)添加新测试:

old_string:
```python
        # finally block must still save storage_state
        self.assertEqual(len(fake_context.storage_state_calls), 1)

    def test_context_and_browser_closed_on_exit(self):
```

new_string:
```python
        # finally block must still save storage_state
        self.assertEqual(len(fake_context.storage_state_calls), 1)

    def test_browser_session_skips_save_on_failure_when_opted_in(self):
        """save_on_success_only=True skips storage_state save when yielded block raises."""
        uploader = FakeUploader.__new__(FakeUploader)
        uploader.account_file = "/fake/account.json"
        uploader.headless = True
        fake_context = FakeContext()
        with patch("uploader.base_video.async_playwright") as mock_ap, \
             patch("uploader.base_video.set_init_script", side_effect=lambda ctx: ctx), \
             patch("uploader.base_video.os.path.exists", return_value=True):
            mock_ap.return_value = FakePlaywright(fake_context)

            async def run():
                async with uploader._browser_session(save_on_success_only=True) as page:
                    raise RuntimeError("upload failed")
            with self.assertRaises(RuntimeError):
                asyncio.run(run())
        # save_on_success_only=True + exception -> no save
        self.assertEqual(len(fake_context.storage_state_calls), 0)

    def test_browser_session_saves_on_success_when_opted_in(self):
        """save_on_success_only=True still saves when yielded block succeeds."""
        uploader = FakeUploader.__new__(FakeUploader)
        uploader.account_file = "/fake/account.json"
        uploader.headless = True
        fake_context = FakeContext()
        with patch("uploader.base_video.async_playwright") as mock_ap, \
             patch("uploader.base_video.set_init_script", side_effect=lambda ctx: ctx), \
             patch("uploader.base_video.os.path.exists", return_value=True):
            mock_ap.return_value = FakePlaywright(fake_context)

            async def run():
                async with uploader._browser_session(save_on_success_only=True) as page:
                    pass  # success
            asyncio.run(run())
        self.assertEqual(len(fake_context.storage_state_calls), 1)

    def test_context_and_browser_closed_on_exit(self):
```

- [ ] **Step 2: Run new save_on_success_only tests**

Run:
```bash
.venv/bin/python -m pytest tests/test_base_uploader_session.py -v
```
Expected: 5 tests pass (3 existing + 2 new).

- [ ] **Step 3: Add cookie_auth headless standardization test**

用 Edit 工具,在 `tests/test_base_uploader_session.py` 的 `BrowserSessionTests` class 末尾(`test_context_and_browser_closed_on_exit` 之后,`if __name__` 之前)添加新测试:

old_string:
```python
        self.assertTrue(fake_context.closed)


if __name__ == "__main__":
```

new_string:
```python
        self.assertTrue(fake_context.closed)

    def test_cookie_auth_uses_local_chrome_headless(self):
        """Base class cookie_auth passes LOCAL_CHROME_HEADLESS to _launch_browser,
        not hardcoded True."""
        from conf import LOCAL_CHROME_HEADLESS
        uploader = FakeUploader.__new__(FakeUploader)
        captured_headless = []

        async def fake_launch_browser(playwright, headless):
            captured_headless.append(headless)
            return FakeBrowser(FakeContext())

        with patch("uploader.base_video.async_playwright") as mock_ap, \
             patch("uploader.base_video.set_init_script", side_effect=lambda ctx: ctx), \
             patch("uploader.base_video.os.path.exists", return_value=False):
            mock_ap.return_value = FakePlaywright(FakeContext())
            with patch.object(FakeUploader, "_launch_browser", side_effect=fake_launch_browser):
                asyncio.run(FakeUploader.cookie_auth("/fake.json"))
        self.assertEqual(captured_headless, [LOCAL_CHROME_HEADLESS])


if __name__ == "__main__":
```

- [ ] **Step 4: Run headless standardization test**

Run:
```bash
.venv/bin/python -m pytest tests/test_base_uploader_session.py::BrowserSessionTests::test_cookie_auth_uses_local_chrome_headless -v
```
Expected: `1 passed`。

- [ ] **Step 5: Add log timing test to test_weibo_uploader_base.py**

用 Edit 工具,在 `tests/test_weibo_uploader_base.py` 的 `WeiboNoteUploadTests` class 之后(line 73 附近)、`ModuleWrapperTests` class 之前添加新 class。

先读文件确认当前结构:
```bash
sed -n '60,80p' tests/test_weibo_uploader_base.py
```

然后添加 `WeiboLogTimingTests` class。old_string 取决于文件实际内容,但大致是:

old_string:
```python
        self.assertTrue(result["success"])
        self.assertEqual(result["message"], "发布成功")


class ModuleWrapperTests(unittest.TestCase):
```

new_string:
```python
        self.assertTrue(result["success"])
        self.assertEqual(result["message"], "发布成功")


class WeiboLogTimingTests(unittest.TestCase):
    def test_log_not_printed_when_upload_raises_exception(self):
        """When upload() raises an exception, 'cookie 更新完毕' log must NOT fire.
        Log is now after the async with block (after storage_state save),
        so exceptions skip it."""
        import asyncio
        from unittest.mock import AsyncMock, patch
        uploader = WeiboVideo(
            title="test", file_path="/fake.mp4", tags=[],
            publish_date=0, account_file="/fake.json",
        )
        with patch.object(uploader, "validate_upload_args", AsyncMock()), \
             patch.object(uploader, "_browser_session") as mock_session, \
             patch.object(uploader, "upload_video_content", AsyncMock(side_effect=RuntimeError("upload failed"))), \
             patch("uploader.weibo_uploader.main.weibo_logger") as mock_logger:
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def fake_session():
                class FakePage:
                    url = "https://weibo.com/upload"
                yield FakePage()

            mock_session.return_value = fake_session()
            result = asyncio.run(uploader.upload())
        self.assertFalse(result["success"])
        # "cookie 更新完毕" log must NOT be called when upload fails
        for call in mock_logger.success.call_args_list:
            args, kwargs = call
            if args and "cookie 更新完毕" in str(args[0]):
                self.fail("cookie 更新完毕 log was printed on failure - should only print on success")


class ModuleWrapperTests(unittest.TestCase):
```

- [ ] **Step 6: Run log timing test**

Run:
```bash
.venv/bin/python -m pytest tests/test_weibo_uploader_base.py::WeiboLogTimingTests -v
```
Expected: `1 passed`。

- [ ] **Step 7: Run full regression suite**

Run:
```bash
.venv/bin/python -m pytest tests/ -v 2>&1 | tail -5
```
Expected: `162 passed`(158 + 4 new: 2 save_on_success_only + 1 headless + 1 log timing)。

- [ ] **Step 8: Commit**

```bash
git add tests/test_base_uploader_session.py tests/test_weibo_uploader_base.py
git commit -m "$(cat <<'EOF'
test: add coverage for save_on_success_only, headless standardization, log timing

- test_browser_session_skips_save_on_failure_when_opted_in: verifies
  save_on_success_only=True skips storage_state save on exception
- test_browser_session_saves_on_success_when_opted_in: verifies
  save_on_success_only=True still saves on success
- test_cookie_auth_uses_local_chrome_headless: verifies base class
  cookie_auth passes LOCAL_CHROME_HEADLESS (not hardcoded True)
- test_log_not_printed_when_upload_raises_exception: verifies "cookie
  更新完毕" log does not fire when upload() raises (log is after async
  with block, not inside it)
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
Expected: `162 passed`,0 failed。

- [ ] **最终 Step 2: 无 "cookie 更新完毕" log 在 async with 内部**

Run:
```bash
grep -B5 "cookie 更新完毕" uploader/*_uploader/main.py | grep "async with" || echo "OK - no log inside async with"
```
Expected: `OK - no log inside async with`

- [ ] **最终 Step 3: 无 headless=True 在 cookie_auth 方法里**

Run:
```bash
.venv/bin/python -c "
import ast
for f in ['uploader/base_video.py', 'uploader/douyin_uploader/main.py']:
    tree = ast.parse(open(f).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == 'cookie_auth':
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    for kw in child.keywords:
                        if kw.arg == 'headless' and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                            print(f'{f}:cookie_auth still has headless=True')
print('Check complete')
"
```
Expected: `Check complete`(无 "still has headless=True" 输出)。

- [ ] **最终 Step 4: save_on_success_only flag 存在**

Run:
```bash
grep -n "save_on_success_only" uploader/base_video.py
```
Expected: 2 行(函数签名 1 行 + if 条件 1 行)。

- [ ] **最终 Step 5: 提交历史检查**

Run:
```bash
git log --oneline main..HEAD
```
Expected: 看到 3 个 task 的 commit + 1 个 spec commit。
