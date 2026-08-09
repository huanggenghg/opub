# B站发布链接抓取 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** B站上传成功后,自动抓取刚发布视频的 BV 号,转成公开链接写入 `result["result_url"]`,让现有 Excel 写入逻辑自动生效。

**Architecture:** 在 `BilibiliUploader` 类上加 3 个方法 (`_list_bvs`/`_match_bv_by_title`/`_capture_bv_after_upload`) 并改 `upload()`:上传前 snapshot BV 集合,上传后轮询 diff 找新 BV,title 匹配作为 fallback。不依赖 list 排序假设,确定性地识别本次上传的 BV。

**Tech Stack:** Python 3.13, unittest, unittest.mock, biliup-rs CLI subprocess

## Global Constraints

- 不动 `dispatch.py`、不动 Excel 写入逻辑、不动其他平台
- biliup-rs 二进制是外部依赖,不改
- URL 格式: `https://www.bilibili.com/video/{BV}`
- 抓 BV 失败不影响发布成功状态(发布已成功,只是缺链接)
- 测试用 `unittest.TestCase` + `unittest.mock.patch`(项目现有模式)
- mock `run_biliup_command` 时用 `subprocess.CompletedProcess` 作为返回值
- 遵循 CLAUDE.md 硬约束:禁止截屏定位 UI、禁止非文本文件调模型 API(本任务不涉及)

---

## File Structure

**Modify:**
- `uploader/bilibili_uploader/main.py` - 加 `import time`,加 3 个方法到 `BilibiliUploader` 类,改 `upload()` 方法(约 90-115 行)

**Create:**
- `tests/test_bilibili_uploader.py` - 新测试文件,测 3 个新方法 + `upload()` 改动

**Not touching:**
- `uploader/bilibili_uploader/runtime.py`(`run_biliup_command` 已存在,直接用)
- `publish/dispatch.py`(已检查 `result.get("result_url")` 并写 Excel)
- `utils/excel_writer.py`(URL 写入逻辑已存在)

---

### Task 1: `_list_bvs()` 方法

**Files:**
- Modify: `uploader/bilibili_uploader/main.py`(在 `BilibiliUploader` 类里加方法,`upload()` 之前)
- Test: `tests/test_bilibili_uploader.py`(新建)

**Interfaces:**
- Consumes: `run_biliup_command(arguments: list[str]) -> subprocess.CompletedProcess[str]`(来自 `runtime.py`,已 import)
- Produces: `BilibiliUploader._list_bvs(self) -> set[str]` - 返回当前账号所有 BV 集合,命令失败返回空集

- [ ] **Step 1: 写失败测试**

创建 `tests/test_bilibili_uploader.py`:

```python
from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from uploader.bilibili_uploader.main import BilibiliUploader


def _make_completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _make_uploader() -> BilibiliUploader:
    return BilibiliUploader(
        title="测试标题",
        file_path="/fake.mp4",
        tags=["测试"],
        account_file="/fake/account.json",
        desc="描述",
    )


class ListBvsTests(unittest.TestCase):
    def test_parses_bv_lines_into_set(self):
        stdout = "BV15r3q6FEYZ\t无小丑\t开放浏览\nBV1QQgy6rEaA\t西南\t开放浏览\nBV1PmMg68ERX\tWHO\t开放浏览\n"
        uploader = _make_uploader()
        with patch("uploader.bilibili_uploader.main.run_biliup_command", return_value=_make_completed(0, stdout=stdout)):
            bvs = uploader._list_bvs()
        self.assertEqual(bvs, {"BV15r3q6FEYZ", "BV1QQgy6rEaA", "BV1PmMg68ERX"})

    def test_returns_empty_set_for_empty_stdout(self):
        uploader = _make_uploader()
        with patch("uploader.bilibili_uploader.main.run_biliup_command", return_value=_make_completed(0, stdout="")):
            bvs = uploader._list_bvs()
        self.assertEqual(bvs, set())

    def test_returns_empty_set_when_command_fails(self):
        uploader = _make_uploader()
        with patch("uploader.bilibili_uploader.main.run_biliup_command", return_value=_make_completed(1, stderr="cookie 失效")):
            bvs = uploader._list_bvs()
        self.assertEqual(bvs, set())

    def test_skips_lines_without_bv_prefix(self):
        stdout = "2026-08-09 22:47:20  INFO biliup_cli::uploader: user: 你的收音机头\nBV15r3q6FEYZ\t无小丑\t开放浏览\n\n"
        uploader = _make_uploader()
        with patch("uploader.bilibili_uploader.main.run_biliup_command", return_value=_make_completed(0, stdout=stdout)):
            bvs = uploader._list_bvs()
        self.assertEqual(bvs, {"BV15r3q6FEYZ"})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_bilibili_uploader.py -v`
Expected: 4 个测试 FAIL,报错 `AttributeError: 'BilibiliUploader' object has no attribute '_list_bvs'`

- [ ] **Step 3: 实现方法**

在 `uploader/bilibili_uploader/main.py` 的 `BilibiliUploader` 类里,`async def upload(self)` 之前加:

```python
    def _list_bvs(self) -> set[str]:
        """跑 biliup list,返回当前账号所有 BV 集合。命令失败返回空集,不抛异常。"""
        result = run_biliup_command(["-u", self.account_file, "list"])
        if result.returncode != 0:
            bilibili_logger.warning(f"biliup list 失败,返回空集: {(result.stderr or '').strip()[:200]}")
            return set()
        bvs: set[str] = set()
        for line in (result.stdout or "").splitlines():
            parts = line.split("\t", 2)
            if parts and parts[0].startswith("BV"):
                bvs.add(parts[0])
        return bvs
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_bilibili_uploader.py -v`
Expected: 4 个测试 PASS

- [ ] **Step 5: Commit**

```bash
git add uploader/bilibili_uploader/main.py tests/test_bilibili_uploader.py
git commit -m "feat(bilibili): add _list_bvs() to parse biliup list into BV set"
```

---

### Task 2: `_match_bv_by_title()` 方法

**Files:**
- Modify: `uploader/bilibili_uploader/main.py`(`_list_bvs()` 之后加方法)
- Test: `tests/test_bilibili_uploader.py`(加测试类)

**Interfaces:**
- Consumes: `run_biliup_command`(同上)
- Produces: `BilibiliUploader._match_bv_by_title(self) -> str | None` - 返回 title 匹配的 BV,无匹配返回 None,多个匹配返回第一个 + warning

- [ ] **Step 1: 写失败测试**

在 `tests/test_bilibili_uploader.py` 的 `ListBvsTests` 类之后加:

```python
class MatchBvByTitleTests(unittest.TestCase):
    def test_returns_bv_when_title_matches(self):
        stdout = "BV15r3q6FEYZ\t无小丑\t开放浏览\nBV1QQgy6rEaA\t测试标题\t开放浏览\n"
        uploader = _make_uploader()
        with patch("uploader.bilibili_uploader.main.run_biliup_command", return_value=_make_completed(0, stdout=stdout)):
            bv = uploader._match_bv_by_title()
        self.assertEqual(bv, "BV1QQgy6rEaA")

    def test_returns_none_when_no_match(self):
        stdout = "BV15r3q6FEYZ\t无小丑\t开放浏览\n"
        uploader = _make_uploader()
        with patch("uploader.bilibili_uploader.main.run_biliup_command", return_value=_make_completed(0, stdout=stdout)):
            bv = uploader._match_bv_by_title()
        self.assertIsNone(bv)

    def test_returns_first_bv_when_multiple_matches(self):
        stdout = "BV1111111111\t测试标题\t开放浏览\nBV2222222222\t测试标题\t开放浏览\n"
        uploader = _make_uploader()
        with patch("uploader.bilibili_uploader.main.run_biliup_command", return_value=_make_completed(0, stdout=stdout)):
            bv = uploader._match_bv_by_title()
        self.assertEqual(bv, "BV1111111111")

    def test_returns_none_when_command_fails(self):
        uploader = _make_uploader()
        with patch("uploader.bilibili_uploader.main.run_biliup_command", return_value=_make_completed(1, stderr="cookie 失效")):
            bv = uploader._match_bv_by_title()
        self.assertIsNone(bv)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_bilibili_uploader.py::MatchBvByTitleTests -v`
Expected: 4 个测试 FAIL,报错 `AttributeError: 'BilibiliUploader' object has no attribute '_match_bv_by_title'`

- [ ] **Step 3: 实现方法**

在 `uploader/bilibili_uploader/main.py` 的 `_list_bvs()` 方法之后加:

```python
    def _match_bv_by_title(self) -> str | None:
        """fallback: 在 biliup list 里找 title 等于 self.title 的行,返回 BV。"""
        result = run_biliup_command(["-u", self.account_file, "list"])
        if result.returncode != 0:
            return None
        matches: list[str] = []
        for line in (result.stdout or "").splitlines():
            parts = line.split("\t", 2)
            if len(parts) >= 2 and parts[0].startswith("BV") and parts[1] == self.title:
                matches.append(parts[0])
        if not matches:
            return None
        if len(matches) > 1:
            bilibili_logger.warning(f"title 匹配到多个 BV: {matches},取第一个")
        return matches[0]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_bilibili_uploader.py -v`
Expected: 全部 PASS(8 个测试)

- [ ] **Step 5: Commit**

```bash
git add uploader/bilibili_uploader/main.py tests/test_bilibili_uploader.py
git commit -m "feat(bilibili): add _match_bv_by_title() as BV capture fallback"
```

---

### Task 3: `_capture_bv_after_upload()` 方法

**Files:**
- Modify: `uploader/bilibili_uploader/main.py`(文件顶部加 `import time`,`_match_bv_by_title()` 之后加方法)
- Test: `tests/test_bilibili_uploader.py`(加测试类)

**Interfaces:**
- Consumes: `self._list_bvs() -> set[str]`(Task 1)、`self._match_bv_by_title() -> str | None`(Task 2)
- Produces: `BilibiliUploader._capture_bv_after_upload(self, before_bvs: set[str], max_retries: int = 3, delay: float = 2.0) -> str | None` - 返回本次上传的新 BV,全部失败返回 None

- [ ] **Step 1: 写失败测试**

在 `tests/test_bilibili_uploader.py` 的 `MatchBvByTitleTests` 类之后加:

```python
class CaptureBvAfterUploadTests(unittest.TestCase):
    def test_returns_new_bv_when_diff_has_exactly_one(self):
        uploader = _make_uploader()
        before = {"BV1111111111"}
        with patch.object(uploader, "_list_bvs", return_value={"BV1111111111", "BV2222222222"}), \
             patch.object(uploader, "_match_bv_by_title") as match_mock:
            bv = uploader._capture_bv_after_upload(before, max_retries=3, delay=0)
        self.assertEqual(bv, "BV2222222222")
        match_mock.assert_not_called()

    def test_falls_back_to_title_match_after_retries_exhausted(self):
        uploader = _make_uploader()
        before = {"BV1111111111"}
        with patch.object(uploader, "_list_bvs", return_value={"BV1111111111"}), \
             patch.object(uploader, "_match_bv_by_title", return_value="BV3333333333") as match_mock:
            bv = uploader._capture_bv_after_upload(before, max_retries=2, delay=0)
        self.assertEqual(bv, "BV3333333333")
        self.assertEqual(match_mock.call_count, 1)

    def test_falls_back_to_title_match_when_multiple_new_bvs(self):
        uploader = _make_uploader()
        before = {"BV1111111111"}
        after = {"BV1111111111", "BV2222222222", "BV3333333333"}
        with patch.object(uploader, "_list_bvs", return_value=after), \
             patch.object(uploader, "_match_bv_by_title", return_value="BV2222222222") as match_mock:
            bv = uploader._capture_bv_after_upload(before, max_retries=3, delay=0)
        self.assertEqual(bv, "BV2222222222")
        self.assertEqual(match_mock.call_count, 1)

    def test_returns_none_when_all_paths_fail(self):
        uploader = _make_uploader()
        before = {"BV1111111111"}
        with patch.object(uploader, "_list_bvs", return_value={"BV1111111111"}), \
             patch.object(uploader, "_match_bv_by_title", return_value=None):
            bv = uploader._capture_bv_after_upload(before, max_retries=2, delay=0)
        self.assertIsNone(bv)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_bilibili_uploader.py::CaptureBvAfterUploadTests -v`
Expected: 4 个测试 FAIL,报错 `AttributeError: 'BilibiliUploader' object has no attribute '_capture_bv_after_upload'`

- [ ] **Step 3: 加 `import time`**

在 `uploader/bilibili_uploader/main.py` 顶部 import 区(`from __future__ import annotations` 之后,`import os` 附近)加:

```python
import time
```

- [ ] **Step 4: 实现方法**

在 `_match_bv_by_title()` 方法之后加:

```python
    def _capture_bv_after_upload(self, before_bvs: set[str], max_retries: int = 3, delay: float = 2.0) -> str | None:
        """上传后轮询 biliup list,找本次上传产生的新 BV。

        - 1 个新 BV: 返回它(主路径)
        - 0 个新 BV: sleep 后重试
        - >1 个新 BV: 立刻 fallback 到 title 匹配
        - 重试耗尽: fallback 到 title 匹配
        """
        for attempt in range(max_retries):
            after_bvs = self._list_bvs()
            new_bvs = after_bvs - before_bvs
            if len(new_bvs) == 1:
                return next(iter(new_bvs))
            if len(new_bvs) > 1:
                bilibili_logger.warning(f"diff 出 {len(new_bvs)} 个新 BV,fallback 到 title 匹配: {new_bvs}")
                return self._match_bv_by_title()
            if attempt < max_retries - 1:
                time.sleep(delay)
        bilibili_logger.warning(f"重试 {max_retries} 次仍未拿到新 BV,fallback 到 title 匹配")
        return self._match_bv_by_title()
```

- [ ] **Step 5: 跑测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_bilibili_uploader.py -v`
Expected: 全部 PASS(12 个测试)

- [ ] **Step 6: Commit**

```bash
git add uploader/bilibili_uploader/main.py tests/test_bilibili_uploader.py
git commit -m "feat(bilibili): add _capture_bv_after_upload() with retry+diff+fallback"
```

---

### Task 4: 改 `upload()` 方法,接入 BV 抓取

**Files:**
- Modify: `uploader/bilibili_uploader/main.py`(`upload()` 方法,约 87-115 行)
- Test: `tests/test_bilibili_uploader.py`(加测试类)

**Interfaces:**
- Consumes: `self._list_bvs()`(Task 1)、`self._capture_bv_after_upload()`(Task 3)
- Produces: 改后的 `upload()` 在成功路径返回 `{"success": True, "message": "发布成功", "result_url"?: str}`(`result_url` 可选,抓到才加)

- [ ] **Step 1: 写失败测试**

在 `tests/test_bilibili_uploader.py` 的 `CaptureBvAfterUploadTests` 类之后加:

```python
class UploadWireTests(unittest.TestCase):
    def test_upload_success_with_bv_sets_result_url(self):
        import asyncio
        uploader = _make_uploader()
        upload_completed = _make_completed(0, stdout="Upload completed: demo.mp4")

        def fake_run_biliup_command(args):
            if "upload" in args:
                return upload_completed
            return _make_completed(0, stdout="")

        with patch("uploader.bilibili_uploader.main.run_biliup_command", side_effect=fake_run_biliup_command), \
             patch("os.path.exists", return_value=True), \
             patch.object(uploader, "_list_bvs", return_value=set()), \
             patch.object(uploader, "_capture_bv_after_upload", return_value="BV15r3q6FEYZ") as capture_mock:
            result = asyncio.run(uploader.upload())

        self.assertTrue(result["success"])
        self.assertEqual(result["result_url"], "https://www.bilibili.com/video/BV15r3q6FEYZ")
        capture_mock.assert_called_once_with(set())

    def test_upload_success_without_bv_leaves_result_url_absent(self):
        import asyncio
        uploader = _make_uploader()
        upload_completed = _make_completed(0, stdout="Upload completed: demo.mp4")

        with patch("uploader.bilibili_uploader.main.run_biliup_command", return_value=upload_completed), \
             patch("os.path.exists", return_value=True), \
             patch.object(uploader, "_list_bvs", return_value=set()), \
             patch.object(uploader, "_capture_bv_after_upload", return_value=None):
            result = asyncio.run(uploader.upload())

        self.assertTrue(result["success"])
        self.assertNotIn("result_url", result)

    def test_upload_failure_does_not_call_capture(self):
        import asyncio
        uploader = _make_uploader()
        upload_failed = _make_completed(1, stderr="cookie 失效")

        with patch("uploader.bilibili_uploader.main.run_biliup_command", return_value=upload_failed), \
             patch("os.path.exists", return_value=True), \
             patch.object(uploader, "_list_bvs", return_value=set()) as list_mock, \
             patch.object(uploader, "_capture_bv_after_upload") as capture_mock:
            result = asyncio.run(uploader.upload())

        self.assertFalse(result["success"])
        capture_mock.assert_not_called()
        list_mock.assert_called_once()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/python -m pytest tests/test_bilibili_uploader.py::UploadWireTests -v`
Expected: 3 个测试 FAIL,前两个报错 `KeyError: 'result_url'`(result_url 没被设置),第三个报错 `capture_mock.assert_not_called()` 失败

- [ ] **Step 3: 改 `upload()` 方法**

把 `uploader/bilibili_uploader/main.py` 的 `upload()` 方法(当前 87-115 行)整体替换为:

```python
    async def upload(self) -> PlatformResultExtras:
        """用 biliup 上传视频到 B站。

        上传成功后会尝试抓取本次发布视频的公开链接,写入 result_url。
        抓取失败不影响发布成功状态(发布已成功,只是缺链接)。
        """
        tag_str = ",".join(self.tags) if isinstance(self.tags, list) else str(self.tags)
        if not os.path.exists(self.file_path):
            return {"success": False, "message": f"视频文件不存在: {self.file_path}"}

        before_bvs = self._list_bvs()

        args = [
            "-u", self.account_file,
            "upload",
            self.file_path,
            "--title", self.title,
            "--desc", self.desc or "",
            "--tag", tag_str,
            "--tid", str(self.tid),
        ]
        bilibili_logger.info(f"biliup 上传: {self.file_path}, title={self.title}, tid={self.tid}")
        result = run_biliup_command(args)
        stdout = result.stdout or ""
        stderr = result.stderr or ""

        if result.returncode != 0:
            bilibili_logger.error(f"biliup 上传失败: {stderr.strip()[:300]}")
            return {"success": False, "message": f"biliup 上传失败: {stderr.strip()[:200]}"}

        bilibili_logger.success(f"biliup 上传成功: {stdout.strip()[:300]}")
        result_dict: PlatformResultExtras = {"success": True, "message": "发布成功"}
        bv = self._capture_bv_after_upload(before_bvs)
        if bv:
            url = f"https://www.bilibili.com/video/{bv}"
            result_dict["result_url"] = url
            bilibili_logger.success(f"已抓取内容链接: {url}")
        else:
            bilibili_logger.warning("未能抓取 BV,请到 B站创作中心查看")
        return result_dict
```

- [ ] **Step 4: 跑全部测试确认通过**

Run: `.venv/bin/python -m pytest tests/test_bilibili_uploader.py -v`
Expected: 全部 PASS(15 个测试)

也跑下整个 bilibili 测试套件确保没破坏其他:
Run: `.venv/bin/python -m pytest tests/test_bilibili_uploader_base.py tests/test_bilibili_runtime.py tests/test_bilibili_uploader.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add uploader/bilibili_uploader/main.py tests/test_bilibili_uploader.py
git commit -m "feat(bilibili): wire BV capture into upload(), set result_url for Excel"
```

---

### Task 5: 手测端到端

**Files:**
- 不改文件,只跑实际发布验证

- [ ] **Step 1: 跑实际发布**

Run: `.venv/bin/hgsau --platforms bilibili --video videos/demo.mp4 --title "BV 抓取测试" --desc "测试自动抓取链接" --tags "测试"`

Expected 日志包含:
- `biliup 上传成功: ...`
- `已抓取内容链接: https://www.bilibili.com/video/BVxxx`

- [ ] **Step 2: 检查 Excel**

Run: `.venv/bin/python -c "from openpyxl import load_workbook; wb=load_workbook('output/75条自媒体链接-'+__import__('datetime').date.today().strftime('%m%d')+'-黄耿.xlsx'); [print(r) for r in wb.active.iter_rows(values_only=True)]"`

Expected: 最后一行有 `https://www.bilibili.com/video/BVxxx`

- [ ] **Step 3: 清理测试视频(可选)**

去 B站创作中心删除测试视频,或留着也行。

- [ ] **Step 4: 不需要 commit**

手测不产生代码改动,跳过 commit 步骤。

---

## Self-Review

**1. Spec coverage:**
- ✓ `_list_bvs()` - Task 1
- ✓ `_match_bv_by_title()` - Task 2
- ✓ `_capture_bv_after_upload()` with retry + diff + fallback - Task 3
- ✓ 改 `upload()` 接入 BV 抓取 - Task 4
- ✓ snapshot 失败不阻塞上传 - Task 4 实现(before_bvs 来自 `_list_bvs()`,失败返回空集,不抛异常)
- ✓ 抓 BV 失败不影响发布成功状态 - Task 4 测试 `test_upload_success_without_bv_leaves_result_url_absent` 验证
- ✓ 上传失败不抓 BV - Task 4 测试 `test_upload_failure_does_not_call_capture` 验证
- ✓ URL 格式 `https://www.bilibili.com/video/{BV}` - Task 4 实现和测试都用这个格式
- ✓ 手测 - Task 5

**2. Placeholder scan:** 无 TBD/TODO,所有步骤都有完整代码。

**3. Type consistency:**
- `_list_bvs() -> set[str]` - Task 1 定义,Task 3 和 Task 4 消费,类型一致
- `_match_bv_by_title() -> str | None` - Task 2 定义,Task 3 消费,类型一致
- `_capture_bv_after_upload(before_bvs: set[str], max_retries: int = 3, delay: float = 2.0) -> str | None` - Task 3 定义,Task 4 消费(`uploader._capture_bv_after_upload(before_bvs)`),类型一致
- Task 4 测试里 `capture_mock.assert_called_once_with(set())` 验证了调用签名

**4. 风险点:**
- Task 4 测试 `test_upload_success_with_bv_sets_result_url` 用 `side_effect=fake_run_biliup_command` 区分 upload 和 list 调用。但 `upload()` 里只调一次 `run_biliup_command`(upload 那次),`_list_bvs` 已被 patch 成不调 `run_biliup_command`。所以 `side_effect` 其实用不到,可以简化。但保留也不影响正确性(fake 函数对非 upload 调用返回空 stdout,不会被调用到)。保留更安全。
- Task 5 手测依赖真实 B站账号 cookie 有效。若 cookie 过期,需先 `biliup login` 重新登录。
