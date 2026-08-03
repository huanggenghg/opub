# Sub-project F: Production Risk Adoption

## 背景

Sub-project E added the `save_on_success_only: bool = False` flag to `_browser_session` in `uploader/base_video.py`。flag 的目的是解决 E 标记的最高优先级生产风险:upload 失败时 `_browser_session` 的 finally block 无条件保存 storage_state,可能用 partial/corrupted session state 覆盖有效的 cookie 文件。

E 的最终 review 明确指出这个问题:`save_on_success_only` flag 是 infrastructure-only - 没有任何 caller 使用 `True`。所有 11 个 upload 方法仍用默认 `False`,storage_state-on-failure 风险在生产环境中仍然活跃。

E 还 parked 2 个 test gap:
1. DouYinNote 的 publish_restricted 测试缺失(只有 DouYinVideo 有)
2. 没有正面测试验证 "cookie 更新完毕" log 在成功时确实触发(E 只测了失败时不触发 + ordering 不变量)

F 关闭 E 的 loop:adopt `save_on_success_only=True` 在 11 个 upload 方法里,并补 2 个 test gap。

## 目标

1. 11 个 upload 方法显式传 `save_on_success_only=True` 给 `_browser_session`,让 upload 失败时不保存 storage_state(防止 cookie 文件被 partial/corrupted state 覆盖)。
2. 添加 DouYinNote publish_restricted 测试,镜像现有 DouYinVideo 的测试。
3. 添加正面测试验证 "cookie 更新完毕" log 在成功时触发。
4. 保持 163 tests 全绿,新增 ~2 tests 达到 165。

## 范围

### Task 1: save_on_success_only adoption

11 个 upload 方法显式传 `save_on_success_only=True`:

- `uploader/weibo_uploader/main.py` (WeiboVideo.upload, WeiboNote.upload)
- `uploader/xiaohongshu_uploader/main.py` (XiaoHongShuVideo.upload, XiaoHongShuNote.upload)
- `uploader/tencent_uploader/main.py` (TencentVideo.upload, TencentNote.upload)
- `uploader/ks_uploader/main.py` (KSVideo.upload, KSNote.upload)
- `uploader/baijiahao_uploader/main.py` (BaijiahaoVideo.upload)
- `uploader/douyin_uploader/main.py` (DouYinVideo.upload, DouYinNote.upload)

每处的修改模式(以 weibo Video 为例):

before:
```python
            async with self._browser_session() as page:
```

after:
```python
            async with self._browser_session(save_on_success_only=True) as page:
```

**行为变化(刻意的):** upload 失败时不再保存 storage_state。cookie 文件保留 upload 前的状态。trade-off:如果 cookie 在 session 期间被刷新但 upload 因非 cookie 原因失败,刷新后的 cookie 会丢失 - 但这比用 partial/corrupted state 覆盖有效 cookie 文件更好。

**采用 explicit per-call 而非 class attribute 或 flip default:**
- explicit per-call 在每个 call site 清晰表达 intent
- `_browser_session` 的 default 保持 `False`(backward-compatible,future caller 想要 always-save 行为仍可用)
- 不改变 `_browser_session` 的 method contract

**验证:**
- `grep -rn "self._browser_session()" uploader/` 返回 0 结果(所有 11 处都改为 `save_on_success_only=True`)
- `grep -rn "save_on_success_only=True" uploader/` 返回 11 处
- 163 tests 全绿

### Task 2: DouYinNote publish_restricted 测试

在 `tests/test_douyin_uploader_base.py` 的 `DouYinNoteUploadTests` class 里(line 65-88,现有 `test_upload_returns_success_dict` 之后)添加 `test_note_upload_maps_restriction_to_account_issue`,镜像现有 `test_upload_maps_restriction_to_account_issue`(line 42-62,测试 DouYinVideo)。

**注意:** DouYinNote.upload() 在调用 upload_note_content 之前会 `page.goto(DOUYIN_UPLOAD_URL)` + `page.wait_for_url(DOUYIN_UPLOAD_URL)`,所以 FakePage 需要 `goto` 和 `wait_for_url` 方法(参考现有 `DouYinNoteUploadTests.test_upload_returns_success_dict` 的 FakePage,line 79-82)。

新测试:
```python
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
```

**验证:**
- `pytest tests/test_douyin_uploader_base.py -v` 通过(原有 + 新增测试)
- 新测试覆盖 DouYinNote.upload() 的 `except DouyinPublishRestrictedError` 分支(line 863 附近)

### Task 3: 正面 log-firing-on-success 测试

在 `tests/test_weibo_uploader_base.py` 的 `WeiboLogTimingTests` class(E 创建)添加 `test_log_printed_on_success`。

测试逻辑:
- 用 WeiboVideo,patch `_browser_session`、`validate_upload_args`、`upload_video_content`(return success)
- patch `weibo_logger` 捕获 success 调用
- 运行 upload()
- 验证 "cookie 更新完毕" log 确实被调用(成功时)

```python
def test_log_printed_on_success(self):
    """On success, 'cookie 更新完毕' log fires. Complements the failure-path
    test (verifies log does NOT fire on failure) and ordering test."""
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
```

**验证:**
- `pytest tests/test_weibo_uploader_base.py::WeiboLogTimingTests -v` 通过(2 tests:原有失败路径 + 新增成功路径)

## 分支策略

- 新分支:`sub-project-f/production-risk-adoption`,从 `main`(已含 A+B+C+D+E)拉出
- 合并回 main 后删除 feature branch

## 测试策略

### 回归测试(每个 task 都要保持)
- `pytest tests/ -v` 全绿
- Task 1:163 tests
- Task 2:164 tests(163 + 1 new)
- Task 3:165 tests(164 + 1 new)

### 行为变化(刻意的)
- 11 个 upload 方法失败时不再保存 storage_state。cookie 文件保留 upload 前状态。
- 这是 E 标记的最高优先级生产风险的 mitigation。trade-off 可接受(refreshed cookie 丢失 < cookie 文件损坏)。

### 关键验证
- 所有 11 处 `self._browser_session()` 改为 `self._browser_session(save_on_success_only=True)`
- DouYinNote publish_restricted 测试通过
- 正面 log-firing-on-success 测试通过
- 163 tests 不回归

## 不在范围

- **tk firefox->chromium anti-crawl risk:** Category 6 - 无法在无海外网络环境验证,track only
- **Douyin navigation inconsistency:** Category 6 - DouYinVideo 在 upload_video_content 里 navigate,DouYinNote 在 upload() 里 navigate。设计一致性问题,非生产风险,separate concern
- **Bilibili dead params cleanup:** `publish_strategy` param in `__init__` silently dropped - minor API cleanliness,非生产风险
- **AST-based test scanning:** Category 7 - test_examples_no_deprecated_calls.py 升级,nice-to-have 低优先级
- ***_setup wrapper consolidation:** ks/tencent/douyin 的 *_setup 不是 thin wrapper(有 QR-refresh-on-expiry 逻辑)- B 确认为 justified deviation
- **改 `save_on_success_only` 的 default:** 保持 `False`(backward-compatible)。F 通过 explicit per-call adoption 而非 flip default
