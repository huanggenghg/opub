# Weibo Result URL Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Return the newly published Weibo video's real public URL by reading the first management-list record's `oid` instead of clicking a virtualized card that can open the previous video.

**Architecture:** Keep the existing rule that the newly published video is the first management-list item and becomes ready when it is editable and no longer publishing. Add one helper that fetches the first `/api/video/list?cursor=0` record and one pure helper that validates its title, readiness, and string `oid`; the publish loop polls those helpers and builds the public URL without opening a popup.

**Tech Stack:** Python 3.9+, Patchright async browser API, unittest/pytest, setuptools/uv, PyPI.

---

## File Structure

- `uploader/weibo_uploader/main.py`: fetch and validate the first management-list video record, then return its public URL after approval.
- `tests/test_weibo_uploader_base.py`: regression and edge-case coverage for management-list URL extraction.
- `pyproject.toml`, `uv.lock`, `skills/opub-cli/SKILL.md`, `tests/test_package_build.py`: synchronize patch version `0.8.22`.

### Task 1: Add the failing Weibo management-list regression tests

**Files:**
- Modify: `tests/test_weibo_uploader_base.py`
- Test: `tests/test_weibo_uploader_base.py`

- [ ] **Step 1: Write the failing tests**

Add imports for `_fetch_first_weibo_video` and `_weibo_video_result_url`, then add tests equivalent to:

```python
class _FakeWeiboVideoListPage:
    def __init__(self, payload):
        self.payload = payload
        self.evaluate = AsyncMock(return_value=payload)


class WeiboManagementResultUrlTests(unittest.TestCase):
    def test_uses_first_management_record_oid_instead_of_old_second_video(self):
        page = _FakeWeiboVideoListPage({
            "data": {
                "videos": [
                    {
                        "oid": "1034:5347014536265775",
                        "editable": 1,
                        "publishing": False,
                        "titles": [{"title": "本次视频", "default": True}],
                    },
                    {
                        "oid": "1034:5345980510306307",
                        "editable": 1,
                        "publishing": False,
                        "titles": [{"title": "旧视频", "default": True}],
                    },
                ]
            },
            "ok": 1,
        })

        first_video = asyncio.run(_fetch_first_weibo_video(page))
        result_url = _weibo_video_result_url(first_video, "本次视频")

        self.assertEqual(
            result_url,
            "https://weibo.com/tv/show/1034:5347014536265775",
        )
        page.evaluate.assert_awaited_once()

    def test_rejects_publishing_video(self):
        self.assertIsNone(_weibo_video_result_url({
            "oid": "1034:5347014536265775",
            "editable": 0,
            "publishing": True,
            "titles": [{"title": "本次视频", "default": True}],
        }, "本次视频"))

    def test_rejects_mismatched_title(self):
        self.assertIsNone(_weibo_video_result_url({
            "oid": "1034:5345980510306307",
            "editable": 1,
            "publishing": False,
            "titles": [{"title": "旧视频", "default": True}],
        }, "本次视频"))

    def test_rejects_invalid_oid(self):
        self.assertIsNone(_weibo_video_result_url({
            "oid": 5347014536265775,
            "editable": 1,
            "publishing": False,
            "titles": [{"title": "本次视频", "default": True}],
        }, "本次视频"))
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_weibo_uploader_base.py::WeiboManagementResultUrlTests -q
```

Expected: collection fails because `_fetch_first_weibo_video` and `_weibo_video_result_url` do not exist.

### Task 2: Read the first management record and replace popup URL extraction

**Files:**
- Modify: `uploader/weibo_uploader/main.py:1-150`
- Modify: `uploader/weibo_uploader/main.py:582-633`
- Test: `tests/test_weibo_uploader_base.py`

- [ ] **Step 1: Implement the management-list helpers**

Add `import re`, then replace `_open_first_video_link` with:

```python
async def _fetch_first_weibo_video(page: Page) -> dict | None:
    payload = await page.evaluate("""async () => {
        const response = await fetch(`/api/video/list?cursor=0&_=${Date.now()}`, {
            cache: 'no-store',
            credentials: 'include',
        });
        if (!response.ok) {
            throw new Error(`微博视频列表请求失败: HTTP ${response.status}`);
        }
        return await response.json();
    }""")
    videos = payload.get("data", {}).get("videos", []) if isinstance(payload, dict) else []
    return videos[0] if videos and isinstance(videos[0], dict) else None


def _weibo_video_result_url(video: dict | None, expected_title: str) -> str | None:
    if not isinstance(video, dict):
        return None
    if video.get("publishing") or not video.get("editable"):
        return None

    titles = video.get("titles")
    actual_title = None
    if isinstance(titles, list):
        default_title = next(
            (item for item in titles if isinstance(item, dict) and item.get("default")),
            None,
        )
        selected = default_title or next((item for item in titles if isinstance(item, dict)), None)
        if selected:
            actual_title = selected.get("title")
    if not isinstance(actual_title, str) or actual_title.strip() != expected_title.strip():
        return None

    oid = video.get("oid")
    if not isinstance(oid, str) or re.fullmatch(r"1034:\d+", oid) is None:
        return None
    return f"https://weibo.com/tv/show/{oid}"
```

- [ ] **Step 2: Poll the helpers after publish confirmation**

Replace the DOM card count, edit-button check, and `_open_first_video_link` call with:

```python
weibo_logger.info(_msg("🔍", "开始检查第一条视频的审核状态..."))
for attempt in range(30):
    try:
        first_video = await _fetch_first_weibo_video(page)
    except Exception as exc:
        weibo_logger.warning(_msg("⚠️", f"第 {attempt + 1} 次读取视频列表失败: {exc}"))
        first_video = None

    video_link = _weibo_video_result_url(first_video, self.title)
    if video_link:
        weibo_logger.success(_msg("✅", f"第 {attempt + 1} 次检查: 视频审核通过"))
        weibo_logger.success(_msg("🔗", f"视频链接: {video_link}"))
        return video_link

    weibo_logger.info(_msg("⏳", f"第 {attempt + 1} 次检查: 视频仍在审核中..."))
    await page.wait_for_timeout(5000)

weibo_logger.warning(_msg("⚠️", "审核或链接获取超时，请稍后手动检查"))
return None
```

Do not click a video card or open a popup.

- [ ] **Step 3: Run focused tests and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_weibo_uploader_base.py tests/test_weibo_uploader.py -q
```

Expected: all Weibo tests pass.

- [ ] **Step 4: Run the full suite**

Run:

```bash
.venv/bin/python -m pytest tests license_server/tests -q
```

Expected: all tests pass with zero failures.

### Task 3: Release patch version 0.8.22

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `skills/opub-cli/SKILL.md`
- Modify: `tests/test_package_build.py`

- [ ] **Step 1: Add the failing version consistency expectation**

Change `tests/test_package_build.py::PackageBuildTests::test_release_version_is_consistent` to expect `0.8.22` in `pyproject.toml`, `uv.lock`, and the repository skill metadata.

- [ ] **Step 2: Run the version test and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_package_build.py::PackageBuildTests::test_release_version_is_consistent -q
```

Expected: failure because the package metadata still reports `0.8.21`.

- [ ] **Step 3: Synchronize version metadata**

Set the package and skill versions to `0.8.22`, then run:

```bash
uv lock
```

- [ ] **Step 4: Verify tests and distributions**

Run:

```bash
.venv/bin/python -m pytest tests license_server/tests -q
release_dir=$(mktemp -d)
.venv/bin/python -m build --outdir "$release_dir"
.venv/bin/python -m twine check "$release_dir"/*
```

Expected: all tests pass; wheel and source distribution build; `twine check` passes both artifacts.

- [ ] **Step 5: Commit and push**

Stage only the task files, commit with `Fix Weibo published video result URL`, and push `main`. Wait for the Python 3.9 and 3.12 CI jobs to pass before uploading to PyPI.

- [ ] **Step 6: Publish and verify**

Upload the verified `opub-0.8.22*` artifacts from the temporary release directory to PyPI, push tag `v0.8.22`, verify PyPI JSON and Simple API propagation, compare uploaded artifact hashes, and install `opub==0.8.22` into a fresh Python 3.9 environment outside the checkout. Confirm `opub --version` and import paths come from the fresh environment.

### Task 4: Run one confirmed real Weibo publication

**Files:**
- No repository file changes.

- [ ] **Step 1: Confirm external publication inputs**

Before invoking `opub`, obtain explicit user confirmation of the video path, title, description, and tags. Do not reuse a prior run or choose a file from disk without confirmation.

- [ ] **Step 2: Publish once and capture structured output**

Run the installed `opub 0.8.22` with `--platforms weibo --output json` and the exact confirmed inputs. Redirect stdout and stderr to internal temporary logs; do not expose raw publishing logs or credentials.

- [ ] **Step 3: Verify the returned URL without republishing**

Open the returned `result_url` read-only using the persisted Weibo session. Verify that the page title or body contains the confirmed publication title and that the video element has a playable source. If the link cannot be verified, report publication success separately from link verification failure and do not publish again.
