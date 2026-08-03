# Sub-project E: Production Behavior Risks

## 背景

Sub-project B (uploader base class extraction) 的 review 过程中标记了 3 个 Category 5 production behavior risks,明确说"needs production observation, independent sub-project"。Sub-project D (cleanup + test coverage) 显式排除了 Category 5,只覆盖 Categories 1-4。Sub-project E 终于 addressing Category 5。

3 个 issues 都在 cookie/session 管理流程里,是 sub-project B 引入 base class 时产生的行为变化:

1. **storage_state-on-failure**:`_browser_session` 的 finally block 无条件保存 storage_state,即使 upload 抛异常。sub-project B 的 ledger 标记为"highest production risk: if upload fails mid-way, cookie file could be corrupted"。
2. **Premature "cookie 更新完毕" log**:6 个平台的 upload() 方法里,log 在 `_browser_session` 实际保存 storage_state **之前**就打印了。log 说"cookie 更新完毕"但 save 还没发生,误导用户。
3. **cookie_auth headless inconsistency**:base class 硬编码 `headless=True`,但 baijiahao/tencent override 成 `LOCAL_CHROME_HEADLESS`。如果用户设 `LOCAL_CHROME_HEADLESS=False` 调试,只有 baijiahao/tencent 会显示浏览器,其他 4 个平台(weibo/ks/xiaohongshu/douyin)仍然 headless。

## 目标

1. 给 `_browser_session` 加 `save_on_success_only` flag,允许调用方选择"只在成功时保存 storage_state"。默认 False 保持当前行为(backward-compatible)。
2. 修复 11 处 "cookie 更新完毕" log 的时机,从 save 之前移到 save 之后。
3. 统一 cookie_auth 的 headless 参数:base class 从 `headless=True` 改为 `LOCAL_CHROME_HEADLESS`,douyin override 同步修改。
4. 保持现有 158 tests 全绿,新增 ~4-5 tests 覆盖新行为。

## 范围

### Task 1: storage_state-on-failure flag + premature log fix

**1a. `_browser_session` 加 `save_on_success_only` flag:**

`uploader/base_video.py:296-312` 的 `_browser_session` 当前结构:
```python
@asynccontextmanager
async def _browser_session(self, headless: Optional[bool] = None):
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

改为:
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

行为变化:
- `save_on_success_only=False`(默认): 保存行为不变(always save in finally) - backward-compatible
- `save_on_success_only=True`: 只在 yielded block 无异常时保存 - 新行为,opt-in

**1b. 修复 11 处 premature "cookie 更新完毕" log:**

6 个平台的 upload() 方法里,log 在 `async with self._browser_session()` block **内部**、`storage_state` 保存**之前**打印。需移到 `async with` block **之后**(此时 finally block 已执行,storage_state 已保存)。

受影响的 11 处(每平台 Video + Note 各一处,共 6 平台 x 2 = 12,但 baijiahao 的 line 807 是 legacy debug 方法,不改):
- `uploader/weibo_uploader/main.py:527` (WeiboVideo.upload)
- `uploader/weibo_uploader/main.py:651` (WeiboNote.upload)
- `uploader/xiaohongshu_uploader/main.py:736` (XiaoHongShuVideo.upload)
- `uploader/xiaohongshu_uploader/main.py:884` (XiaoHongShuNote.upload)
- `uploader/tencent_uploader/main.py:750` (TencentVideo.upload)
- `uploader/tencent_uploader/main.py:846` (TencentNote.upload)
- `uploader/ks_uploader/main.py:670` (KSVideo.upload)
- `uploader/ks_uploader/main.py:854` (KSNote.upload)
- `uploader/baijiahao_uploader/main.py:384` (BaijiahaoVideo.upload)
- `uploader/douyin_uploader/main.py:700` (DouYinVideo.upload)
- `uploader/douyin_uploader/main.py:860` (DouYinNote.upload)

每处的修改模式(以 weibo:527 为例):

before:
```python
        try:
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
            result["message"] = str(e)
            weibo_logger.error(_msg("❌", f"上传失败: {e}"))
```

after:
```python
        try:
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
            result["message"] = str(e)
            weibo_logger.error(_msg("❌", f"上传失败: {e}"))
```

log 从 `async with` block 内部移到外部(但仍在 `try` 内)。这样:
- upload 成功:`async with` 正常退出 -> finally 保存 storage_state -> log 打印(准确)
- upload 抛异常:`except` 捕获 -> log 不打印(准确,不应说"cookie 更新完毕")

**注意:** 不改 baijiahao:807(`baijiahao_logger.info('cookie更新完毕！')`) - 这是 legacy debug 方法里的手动 save+log,不走 `_browser_session`,不在范围内。

**验证:**
- `tests/test_base_uploader_session.py` 全绿(现有 2 个 storage_state 测试 + 新增测试)
- 158 tests 全绿
- `grep -rn "cookie 更新完毕" uploader/` 仍返回 11 处(位置变了,数量不变)
- log 不再在 `async with` block 内部出现

### Task 2: cookie_auth headless standardization

**2a. base class cookie_auth:**

`uploader/base_video.py:204`:
```python
browser = await cls._launch_browser(playwright, headless=True)
```
改为:
```python
browser = await cls._launch_browser(playwright, headless=LOCAL_CHROME_HEADLESS)
```

**2b. douyin cookie_auth override:**

`uploader/douyin_uploader/main.py:322`:
```python
browser = await cls._launch_browser(playwright, headless=True)
```
改为:
```python
browser = await cls._launch_browser(playwright, headless=LOCAL_CHROME_HEADLESS)
```

**2c. 不改 baijiahao/tencent:**

baijiahao(`uploader/baijiahao_uploader/main.py:155`)和 tencent(`uploader/tencent_uploader/main.py:405`)已经用 `LOCAL_CHROME_HEADLESS`。它们的 override 保留(有额外的 DOM marker / publish marker 等待逻辑,不只是改 headless)。

**验证:**
- `grep -n "headless=True" uploader/base_video.py uploader/douyin_uploader/main.py` 在 cookie_auth 方法里无输出
- 158 tests 全绿
- **行为变化说明:** `LOCAL_CHROME_HEADLESS` 在 conf.py 中默认 `False`(`_config.get("chrome_headless", False)`)。当前 base class cookie_auth 硬编码 `headless=True`,改后用 `LOCAL_CHROME_HEADLESS`(=False)。这意味着 cookie_auth 会从 headless 变成非 headless(显示浏览器窗口)。这是**刻意的**标准化:upload() 里的 `_browser_session` 已经用 `LOCAL_CHROME_HEADLESS`(通过 `self.headless`),只有 cookie_auth 不一致。改后 cookie_auth 和 upload() 行为一致 — 如果用户设 `LOCAL_CHROME_HEADLESS=False` 调试,cookie 校验和上传都显示浏览器;设 `True` 时都 headless。baijiahao/tencent 已经是这个行为,标准统一。

### Task 3: 测试覆盖

**3a. save_on_success_only 行为测试:**

在 `tests/test_base_uploader_session.py` 添加:
- `test_browser_session_saves_storage_state_on_failure_by_default`:验证 `save_on_success_only=False`(默认)时,upload 抛异常后 storage_state 仍被保存(preserves current behavior)
- `test_browser_session_skips_storage_state_on_failure_when_opted_in`:验证 `save_on_success_only=True` 时,upload 抛异常后 storage_state 不被保存

**3b. log timing 测试:**

在 `tests/test_weibo_uploader_base.py` 添加 `test_log_not_printed_when_upload_raises_exception`:验证 upload() 抛异常时 "cookie 更新完毕" log 不打印(log 现在在 `async with` block 外部,异常时跳过)。用 `patch.object(weibo_logger, "success")` 验证 log 未被调用。这是 log 时机修复的核心验证 - 如果 log 还在 `async with` 内部,异常时 log 仍会打印(因为 log 在 upload_video_content 之后、异常之前)。

**3c. headless standardization 测试:**

在 `tests/test_base_uploader_session.py`(或新文件 `tests/test_base_uploader_cookie_auth.py`)添加 `test_cookie_auth_uses_local_chrome_headless`:用 `patch.object(BaseBrowserUploader, "_launch_browser")` 捕获调用参数,验证 `headless` 参数等于 `LOCAL_CHROME_HEADLESS` 的值(而非硬编码 `True`)。

**验证:**
- 新增 ~4-5 tests
- 总测试数 ~162-163
- 全绿

## 分支策略

- 新分支:`sub-project-e/production-behavior-risks`,从 `main`(已含 A+B+C+D)拉出
- 合并回 main 后删除 feature branch

## 测试策略

### 回归测试(每个 task 都要保持)
- `pytest tests/ -v` 全绿
- Task 1-2:158 tests
- Task 3:~162-163 tests(158 + ~4-5 new)

### 行为不变验证
- `save_on_success_only` 默认 False,保存行为不变(backward-compatible)
- log 数量不变(11 处),只是位置变了(async with 内部 -> 外部)

### 行为变化(刻意的)
- cookie_auth headless: base class 从 `headless=True` 改为 `LOCAL_CHROME_HEADLESS`(默认 False)。cookie_auth 会显示浏览器窗口,与 upload() 的 `_browser_session` 行为一致。baijiahao/tencent 已经是这个行为,此改动让 4 个平台(weibo/ks/xiaohongshu/douyin)对齐。

### 关键验证
- storage_state 在 `save_on_success_only=True` + 异常时不保存
- storage_state 在 `save_on_success_only=False` + 异常时仍保存(current behavior)
- log 在 `async with` block 外部(之后)打印
- base class cookie_auth 用 `LOCAL_CHROME_HEADLESS`

## 不在范围

- **Category 6 (design tradeoffs):** tk firefox->chromium anti-crawl risk、*_setup wrappers、douyin navigation inconsistency - track only,无 code 改动
- **Category 7 (test tooling):** test_examples_no_deprecated_calls.py AST-based scanning - nice-to-have,低优先级
- **Category 8 (benign):** CLAUDE.md commit hygiene - 无需 action
- baijiahao:807 legacy debug 方法的 log - 不走 _browser_session,不在范围内
- 改变 `save_on_success_only` 的默认值(保持 False = current behavior)
- 改变 log 消息内容(只改时机,不改文案)
- 任何新 feature 或超出 Category 5 的 refactoring

## 迁移顺序(给 writing-plans 的提示)

建议拆 3 个 task,顺序执行:

1. **Task 1: storage_state flag + premature log fix** - base_video.py 加 flag + 6 个平台文件移 log。最大的 task,触 7 个文件但都是机械改动。
2. **Task 2: headless standardization** - base_video.py + douyin 各改 1 行。最小。
3. **Task 3: 测试覆盖** - 4-5 个新测试。依赖 Task 1-2 代码稳定。

Task 1 和 Task 2 独立(触不同行)。Task 3 依赖 Task 1-2 完成。
