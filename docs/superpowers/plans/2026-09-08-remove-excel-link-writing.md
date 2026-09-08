# Remove Excel Link Writing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop all Excel link persistence, remove the Excel utility, and expose each successful platform URL in the stable publish summary for Agent aggregation.

**Architecture:** Uploaders remain responsible for capturing public URLs and returning them as `result_url`. Dispatch becomes side-effect free, while `publish.reporter` is the only user-facing formatter for platform URLs. The obsolete Excel helper is removed rather than retained as compatibility surface.

**Tech Stack:** Python 3.9+, `unittest`, async platform uploaders, opub CLI documentation

---

## File Structure

- Modify `tests/test_publish_reporter.py`: specify summary formatting for success results with and without URLs.
- Create `tests/test_no_excel_link_writes.py`: enforce removal of the Excel helper and production references.
- Modify `publish/reporter.py`: append a non-empty `result_url` to successful platform lines.
- Modify `publish/dispatch.py`: remove dispatch-layer Excel imports and writes.
- Modify `uploader/douyin_uploader/main.py`: remove uploader-layer Excel import and write.
- Modify `uploader/xiaohongshu_uploader/main.py`: remove video/note Excel imports and writes.
- Modify `uploader/ks_uploader/main.py`: remove video/note Excel imports and writes.
- Delete `utils/excel_writer.py`: remove the deprecated persistence API.
- Modify `skills/opub-cli/SKILL.md`: document result-summary extraction instead of Excel output.

### Task 1: Specify the Result Summary and No-Excel Contract

**Files:**
- Modify: `tests/test_publish_reporter.py`
- Create: `tests/test_no_excel_link_writes.py`

- [ ] **Step 1: Write failing reporter tests**

Add to `tests/test_publish_reporter.py`:

```python
class PrintResultsSuccessUrlTests(unittest.TestCase):
    def test_success_line_contains_result_url(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            print_results({
                "douyin": {
                    "success": True,
                    "message": "发布成功",
                    "result_url": "https://www.douyin.com/video/123",
                }
            })
        self.assertIn("抖音: ✅ 成功 https://www.douyin.com/video/123", out.getvalue())

    def test_success_line_without_result_url_has_no_placeholder(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            print_results({"douyin": {"success": True, "message": "发布成功"}})
        self.assertIn("抖音: ✅ 成功", out.getvalue())
        self.assertNotIn("None", out.getvalue())
```

- [ ] **Step 2: Write the failing production-side-effect test**

Create `tests/test_no_excel_link_writes.py`:

```python
import unittest
from pathlib import Path


class NoExcelLinkWritesTests(unittest.TestCase):
    PRODUCTION_FILES = [
        Path("publish/dispatch.py"),
        Path("uploader/douyin_uploader/main.py"),
        Path("uploader/xiaohongshu_uploader/main.py"),
        Path("uploader/ks_uploader/main.py"),
    ]

    def test_excel_writer_module_is_removed(self):
        self.assertFalse(Path("utils/excel_writer.py").exists())

    def test_publish_code_has_no_excel_writer_references(self):
        for path in self.PRODUCTION_FILES:
            with self.subTest(path=path):
                source = path.read_text(encoding="utf-8")
                self.assertNotIn("excel_writer", source)
                self.assertNotIn("write_video_link", source)
```

- [ ] **Step 3: Run tests and verify they fail for the intended reasons**

Run:

```bash
python -m unittest tests.test_publish_reporter tests.test_no_excel_link_writes -v
```

Expected: the URL-format test fails because the URL is absent, and both no-Excel tests fail because the module and references still exist.

- [ ] **Step 4: Commit the contract tests**

```bash
git add tests/test_publish_reporter.py tests/test_no_excel_link_writes.py
git commit -m "test: specify agent-only publish link reporting"
```

### Task 2: Print Links in the Stable Result Summary

**Files:**
- Modify: `publish/reporter.py:20-31`
- Test: `tests/test_publish_reporter.py`

- [ ] **Step 1: Implement minimal successful-link formatting**

Change the success branch in `print_results` to:

```python
        if result["success"]:
            result_url = result.get("result_url")
            status = "✅ 成功"
            if result_url:
                status = f"{status} {result_url}"
```

Keep the existing failure branch unchanged.

- [ ] **Step 2: Run reporter tests**

Run:

```bash
python -m unittest tests.test_publish_reporter -v
```

Expected: all reporter tests pass.

- [ ] **Step 3: Commit reporter behavior**

```bash
git add publish/reporter.py tests/test_publish_reporter.py
git commit -m "feat: include links in publish result summary"
```

### Task 3: Remove Every Excel Persistence Side Effect

**Files:**
- Modify: `publish/dispatch.py`
- Modify: `uploader/douyin_uploader/main.py`
- Modify: `uploader/xiaohongshu_uploader/main.py`
- Modify: `uploader/ks_uploader/main.py`
- Delete: `utils/excel_writer.py`
- Test: `tests/test_no_excel_link_writes.py`

- [ ] **Step 1: Remove dispatch-layer imports and write blocks**

In each of `publish_to_tencent`, `publish_to_baijiahao`, `publish_to_bilibili`, and `publish_to_weibo`:

```python
        result = await uploader.upload()
        return result
```

Remove each local `from utils.excel_writer import write_video_link` and the entire conditional block that calls it. Preserve uploader construction, exception handling, and the returned result.

- [ ] **Step 2: Remove uploader-layer imports and write blocks**

Remove `from utils.excel_writer import write_video_link` from the Douyin, Xiaohongshu, and Kuaishou uploader modules.

For Douyin, retain URL capture and logging:

```python
                video_link = await self._get_video_link(page)
                if video_link:
                    douyin_logger.info(_msg("🔗", f"视频链接: {video_link}"))
                else:
                    douyin_logger.warning(_msg("⚠️", "未能获取视频链接"))
```

For both Xiaohongshu upload methods, retain only:

```python
                if share_link:
                    xiaohongshu_logger.info(_msg("🔗", f"分享链接: {share_link}"))
                    result["result_url"] = share_link
```

For both Kuaishou content methods, retain link logging without persistence:

```python
        if share_link_result["success"] and share_link_result["share_link"]:
            share_link = share_link_result["share_link"]
            kuaishou_logger.info(_msg("🔗", f"分享链接: {share_link}"))
```

- [ ] **Step 3: Delete the obsolete utility**

Delete `utils/excel_writer.py`. Do not delete or modify any existing user `.xlsx` files.

- [ ] **Step 4: Run the no-Excel and uploader contract tests**

Run:

```bash
python -m unittest \
  tests.test_no_excel_link_writes \
  tests.test_douyin_uploader_base \
  tests.test_xiaohongshu_uploader_base \
  tests.test_ks_uploader_base \
  tests.test_tencent_uploader_base \
  tests.test_baijiahao_uploader_base \
  tests.test_bilibili_uploader \
  tests.test_weibo_uploader_base -v
```

Expected: all tests pass and URL-bearing uploader results still contain `result_url`.

- [ ] **Step 5: Commit persistence removal**

```bash
git add publish/dispatch.py uploader/douyin_uploader/main.py uploader/xiaohongshu_uploader/main.py uploader/ks_uploader/main.py tests/test_no_excel_link_writes.py
git add -u utils/excel_writer.py
git commit -m "refactor: remove Excel publish link persistence"
```

### Task 4: Update the Agent Contract and Verify the Feature

**Files:**
- Modify: `skills/opub-cli/SKILL.md:120-160`
- Test: `tests/test_publish_cli.py`

- [ ] **Step 1: Strengthen the documentation contract test**

In `SkillDocBlackboxTests`, add:

```python
    def test_agent_extracts_links_from_summary_without_excel(self):
        text = self.SKILL_PATH.read_text(encoding="utf-8")
        self.assertIn("从发布结果汇总中提取结果链接", text)
        self.assertNotIn("写入 Excel 结果文件", text)
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
python -m unittest tests.test_publish_cli.SkillDocBlackboxTests.test_agent_extracts_links_from_summary_without_excel -v
```

Expected: FAIL because the skill still describes Excel output.

- [ ] **Step 3: Update result-reading documentation**

Replace the final sentence under `结果汇总格式` with:

```markdown
成功平台的结果链接显示在对应平台的汇总行中。Agent 从发布结果汇总中提取结果链接并反馈给用户，不创建或依赖 Excel 结果文件。
```

- [ ] **Step 4: Run focused and full tests**

Run:

```bash
python -m unittest tests.test_publish_cli tests.test_publish_reporter tests.test_no_excel_link_writes -v
python -m unittest discover -s tests -v
```

Expected: both commands pass with zero failures and zero errors.

- [ ] **Step 5: Run static verification**

Run:

```bash
rg -n "excel_writer|write_video_link|写入Excel|写入 Excel" publish uploader utils skills/opub-cli/SKILL.md
git diff --check
git status --short
```

Expected: `rg` has no matches; `git diff --check` exits zero; status contains only intended feature files plus any pre-existing unrelated user files.

- [ ] **Step 6: Commit documentation and final verification changes**

```bash
git add skills/opub-cli/SKILL.md tests/test_publish_cli.py
git commit -m "docs: make agents aggregate publish links"
```
