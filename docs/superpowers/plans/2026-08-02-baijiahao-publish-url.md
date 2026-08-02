# 百家号发布后抓取内容公开链接 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让百家号发布成功后抓取内容公开链接(`https://baijiahao.baidu.com/s?id={ID}`),对齐微博模式写入 Excel 并塞入 response。

**Architecture:** 立即发布成功跳转 clue 页后,导航到内容管理页 `builder/rc/content`,取列表第一条 `articleItem` 的 `builder/preview/s?id={ID}` href,提取 id 拼公开链接。`upload()` 返回 `{"video_link": str|None}`,`publish_to_baijiahao` 接收后调 `write_video_link` 写 Excel。定时发布跳过抓取。

**Tech Stack:** Python + patchright(playwright fork) + unittest,对齐项目现有 `test_weibo_uploader.py` 测试约定(只测纯函数,不测 playwright page 操作)。

## Global Constraints

- **链接源唯一:** 内容管理页 `https://baijiahao.baidu.com/builder/rc/content` 列表第一条 `div.client_pages_content_v2_components_articleItem` 内的 `a[href*="builder/preview/s?id="]`。selector 来自真实 DOM dump,非假设。
- **URL 转换:** 从 preview href 提取 `id` 参数(`re.search(r"[?&]id=(\d+)", href)`),拼 `https://baijiahao.baidu.com/s?id={ID}`。
- **定时发布跳过:** `self.publish_date == 0` 为立即发布(`main.py:357` 现有逻辑),非 0 跳过抓取,`video_link=None`。
- **抓取失败不算发布失败:** 发布本身成功(`wait_for_url clue` 已过)后,任何抓取失败只 warning,`success=True`。
- **测试约定:** 对齐 `tests/test_weibo_uploader.py` -- 只测纯函数(用 FakePage/FakeLocator mock),不测 playwright page 操作。`_capture_content_url` 靠手动验证。
- **不用截屏定位:** 全程 DOM/页面源码(项目 feedback memory 约束)。

## File Structure

**Create:**
- `tests/test_baijiahao_uploader.py` -- 单元测试,测 `_extract_bjh_public_url_from_preview_href` 纯函数

**Modify:**
- `uploader/baijiahao_uploader/main.py`:
  - 顶部新增 `import re`
  - 新增模块级函数 `_extract_bjh_public_url_from_preview_href(href)`
  - `BaiJiaHaoVideo` 类新增方法 `_capture_content_url(self, page)`
  - `BaiJiaHaoVideo.upload()` (line 177):返回值 `None` -> `dict`,在 wait_for_url clue 成功后插入抓取调用,删除 `BJH_PROBE_DUMP` 临时逻辑(line 299-311)
  - `BaiJiaHaoVideo.main()` (line 459):透传 `upload()` 返回值
- `publish_all.py`:
  - `publish_to_baijiahao` (line 818-849):接收 `uploader.main()` 返回值,调 `write_video_link` 写 Excel,对齐 `publish_to_weibo` (line 930-944) 模式

**Delete(清理):**
- `probe_bjh_clue.py` (项目根,调研脚本)
- `probe_bjh_content_list.py` (项目根,调研脚本)
- `output/bjh_content_list_dump.html`, `output/bjh_content_list_links.txt` (调研 dump 文件)

---

### Task 1: 纯函数 `_extract_bjh_public_url_from_preview_href` + 单测

**Files:**
- Create: `tests/test_baijiahao_uploader.py`
- Modify: `uploader/baijiahao_uploader/main.py:2-13`(顶部 import 区)、模块级(在 `BAIJIAHAO_HOME_URL` 常量后、`baijiahao_cookie_gen` 函数前)

**Interfaces:**
- Produces: `_extract_bjh_public_url_from_preview_href(href: str | None) -> str | None` -- 输入 `builder/preview/s?id={ID}` href,返回 `https://baijiahao.baidu.com/s?id={ID}` 或 None

- [ ] **Step 1: 写失败测试**

创建 `tests/test_baijiahao_uploader.py`:

```python
import unittest

from uploader.baijiahao_uploader.main import _extract_bjh_public_url_from_preview_href


class ExtractBjhPublicUrlTests(unittest.TestCase):
    def test_extracts_id_from_preview_href(self):
        href = "http://baijiahao.baidu.com/builder/preview/s?id=1872396938046079637"
        self.assertEqual(
            _extract_bjh_public_url_from_preview_href(href),
            "https://baijiahao.baidu.com/s?id=1872396938046079637",
        )

    def test_returns_none_for_none_input(self):
        self.assertIsNone(_extract_bjh_public_url_from_preview_href(None))

    def test_returns_none_for_href_without_id(self):
        self.assertIsNone(_extract_bjh_public_url_from_preview_href("https://example.com/no-id"))

    def test_handles_https_and_extra_query_params(self):
        href = "https://baijiahao.baidu.com/builder/preview/s?id=123&other=456"
        self.assertEqual(
            _extract_bjh_public_url_from_preview_href(href),
            "https://baijiahao.baidu.com/s?id=123",
        )

    def test_returns_none_for_empty_string(self):
        self.assertIsNone(_extract_bjh_public_url_from_preview_href(""))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试验证失败**

Run: `python -m pytest tests/test_baijiahao_uploader.py -v`
Expected: FAIL with `ImportError: cannot import name '_extract_bjh_public_url_from_preview_href'`

- [ ] **Step 3: 实现 `import re` + 纯函数**

在 `uploader/baijiahao_uploader/main.py` line 8(`import asyncio` 后)加:

```python
import re
```

在 `BAIJIAHAO_HOME_URL` 常量(line 15-16)后、`baijiahao_cookie_gen` 函数(line 19)前加:

```python
def _extract_bjh_public_url_from_preview_href(href: str | None) -> str | None:
    """从 builder/preview/s?id={ID} href 提取 id,拼公开链接 https://baijiahao.baidu.com/s?id={ID}。"""
    if not href:
        return None
    m = re.search(r"[?&]id=(\d+)", href)
    return f"https://baijiahao.baidu.com/s?id={m.group(1)}" if m else None
```

- [ ] **Step 4: 跑测试验证通过**

Run: `python -m pytest tests/test_baijiahao_uploader.py -v`
Expected: PASS(5 个测试全过)

- [ ] **Step 5: commit**

```bash
git add tests/test_baijiahao_uploader.py uploader/baijiahao_uploader/main.py
git commit -m "feat(baijiahao): add _extract_bjh_public_url_from_preview_href pure function with tests"
```

---

### Task 2: `_capture_content_url` 方法 + `upload()` 返回 dict + `main()` 透传 + 删 BJH_PROBE_DUMP

**Files:**
- Modify: `uploader/baijiahao_uploader/main.py`
  - `BaiJiaHaoVideo` 类新增方法 `_capture_content_url`(放在 `upload` 方法后、`uploading_video` 方法前,line 332 附近)
  - `BaiJiaHaoVideo.upload()` (line 177-330):改返回类型 + 插入抓取调用 + 删 BJH_PROBE_DUMP(line 299-311)
  - `BaiJiaHaoVideo.main()` (line 459-463):透传返回值

**Interfaces:**
- Consumes: `_extract_bjh_public_url_from_preview_href` (from Task 1)
- Produces:
  - `BaiJiaHaoVideo._capture_content_url(self, page: Page) -> str | None`
  - `BaiJiaHaoVideo.upload(self, playwright: Playwright) -> dict` -- 返回 `{"video_link": str | None}`
  - `BaiJiaHaoVideo.main(self) -> dict` -- 透传 upload() 返回值

- [ ] **Step 1: 新增 `_capture_content_url` 方法**

在 `uploader/baijiahao_uploader/main.py` 的 `BaiJiaHaoVideo` 类里,`upload` 方法结束后(line 330 `await browser.close()` 后的空行)、`@async_retry` 装饰的 `uploading_video` 方法前(line 333)插入:

```python
    async def _capture_content_url(self, page: Page) -> str | None:
        """跳转内容管理页,取第一条列表项的公开链接。抓不到返回 None。"""
        content_url = "https://baijiahao.baidu.com/builder/rc/content"
        try:
            await page.goto(content_url, timeout=60000, wait_until="domcontentloaded")
        except Exception as e:
            baijiahao_logger.warning(f"goto 内容管理页异常(继续): {e}")

        try:
            await page.wait_for_function(
                "() => { const r = document.querySelector('#root'); return r && r.children.length > 0; }",
                timeout=30000,
            )
        except Exception:
            pass

        item_locator = page.locator("div.client_pages_content_v2_components_articleItem")
        for _ in range(6):
            if await item_locator.count() > 0:
                break
            await asyncio.sleep(5)
        else:
            baijiahao_logger.warning("内容管理页未出现列表项,跳过链接抓取")
            return None

        href = await item_locator.first.locator('a[href*="builder/preview/s?id="]').first.get_attribute("href")
        public_url = _extract_bjh_public_url_from_preview_href(href)
        if public_url:
            baijiahao_logger.success(f"已抓取内容公开链接: {public_url}")
        else:
            baijiahao_logger.warning(f"无法从 href 提取 id: {href}")
        return public_url

```

- [ ] **Step 2: 改 `upload()` -- 删 BJH_PROBE_DUMP + 插入抓取调用 + 末尾 return dict**

在 `uploader/baijiahao_uploader/main.py`:

**(a)** 改 `upload` 方法签名(line 177):

```python
    async def upload(self, playwright: Playwright) -> dict:
```

**(b)** 替换 line 296-323 的 try/except 块(含 BJH_PROBE_DUMP 逻辑),改为:

```python
        video_link = None
        try:
            await page.wait_for_url("https://baijiahao.baidu.com/builder/rc/clue**", timeout=30000)
            baijiahao_logger.success("视频发布成功")
            if self.publish_date == 0:
                video_link = await self._capture_content_url(page)
            else:
                baijiahao_logger.info("定时发布,跳过内容链接抓取")
        except Exception:
            current_url = page.url
            baijiahao_logger.warning(f"未跳转到 clue 页, 当前 URL: {current_url}")
            body_text = await page.evaluate(
                "() => (document.body && document.body.innerText) ? document.body.innerText.slice(0, 1000) : ''"
            )
            if "发布成功" in body_text or "成功" in body_text:
                baijiahao_logger.success(f"检测到发布成功标志, URL: {current_url}")
            else:
                baijiahao_logger.error(f"发布可能失败, body 文本前 500 字: {body_text[:500]}")
                raise Exception(f"发布后未跳转 clue 页, 当前 URL: {current_url}")
```

**(c)** 在 `await browser.close()`(line 330)后、方法结束前加 return:

```python
        await context.close()
        await browser.close()
        return {"video_link": video_link}
```

- [ ] **Step 3: 改 `main()` 透传返回值**

替换 `uploader/baijiahao_uploader/main.py:459-463` 的 `main` 方法:

```python
    async def main(self):
        async with async_playwright() as playwright:
            return await self.upload(playwright)
```

- [ ] **Step 4: 手动验证 -- 立即发布抓取链接**

配置 `publish_config.ini`(用户已清空,需临时填回):

```ini
[common]
content_type = video
title = 测试-链接抓取-可删除
video_file = videos/demo.mp4
publish_strategy = immediate

[platforms]
enabled = baijiahao
```

Run: `python publish_all.py`
Expected:
- 日志含 `已抓取内容公开链接: https://baijiahao.baidu.com/s?id=...`
- 发布结果 `百家号: ✅ 成功`
- Excel **暂未写入**(Task 3 才加),此任务只验证链接抓取

验证后**清空** `publish_config.ini`(用户已清空过,保持清空状态):把 `title`/`video_file`/`enabled` 改回空。

- [ ] **Step 5: commit**

```bash
git add uploader/baijiahao_uploader/main.py
git commit -m "feat(baijiahao): capture content public URL after immediate publish"
```

---

### Task 3: `publish_to_baijiahao` 对齐微博(接 result + 写 Excel)

**Files:**
- Modify: `publish_all.py:818-849`(`publish_to_baijiahao` 函数)

**Interfaces:**
- Consumes: `BaiJiaHaoVideo.main() -> {"video_link": str | None}` (from Task 2)、`utils.excel_writer.write_video_link`
- Produces: `publish_to_baijiahao` 返回 `{"success": bool, "message": str[, "video_link": str]}`

- [ ] **Step 1: 改 `publish_to_baijiahao` 接收 result + 写 Excel**

参考 `publish_all.py:882-944` 的 `publish_to_weibo`(同样在函数内 `from utils.excel_writer import write_video_link`)。

替换 `publish_all.py:818-849` 的 `publish_to_baijiahao` 整个函数体为:

```python
async def publish_to_baijiahao(params: dict) -> dict:
    """发布到百家号"""
    from uploader.baijiahao_uploader.main import BaiJiaHaoVideo
    from utils.excel_writer import write_video_link

    account_file = resolve_path(params["account_file"])

    title = truncate_title(params["title"], "baijiahao")
    tags = params["tags"]
    publish_strategy = params["publish_strategy"]
    publish_time = params["publish_time"]
    content_type = params["content_type"]

    try:
        if content_type == "video":
            video_file = resolve_path(params["video_file"])
            if not video_file or not os.path.exists(video_file):
                return {"success": False, "message": f"视频文件不存在: {video_file}"}

            uploader = BaiJiaHaoVideo(
                title=title,
                file_path=video_file,
                tags=tags,
                publish_date=publish_time or 0,
                account_file=account_file,
            )
        else:
            return {"success": False, "message": "百家号不支持图文发布，请使用 convert_to_video=true 转为视频发布"}

        result = await uploader.main()
        video_link = result.get("video_link", "") if result else ""

        response = {"success": True, "message": "发布成功"}
        if video_link:
            response["video_link"] = video_link
            try:
                write_result = write_video_link(video_link)
                if write_result["success"]:
                    print(f"  📝 视频链接已写入 Excel: {video_link}")
                else:
                    print(f"  ⚠️ 写入 Excel 失败: {write_result['message']}")
            except Exception as e:
                print(f"  ⚠️ 写入 Excel 异常: {e}")

        return response
    except Exception as e:
        return {"success": False, "message": str(e)}
```

- [ ] **Step 2: 手动验证 -- 立即发布写 Excel**

配置 `publish_config.ini`(临时填回,同 Task 2 Step 4):

```ini
[common]
content_type = video
title = 测试-链接抓取-可删除
video_file = videos/demo.mp4
publish_strategy = immediate

[platforms]
enabled = baijiahao
```

Run: `python publish_all.py`
Expected:
- 日志含 `已抓取内容公开链接: https://baijiahao.baidu.com/s?id=...`
- 控制台含 `📝 视频链接已写入 Excel: https://baijiahao.baidu.com/s?id=...`
- 检查 Excel 文件(由 `write_video_link` 写入,路径见 `utils/excel_writer.py`)新增一行含该链接
- 发布结果 `百家号: ✅ 成功`

验证后清空 `publish_config.ini` 的 `title`/`video_file`/`enabled`。

- [ ] **Step 3: 手动验证 -- 定时发布跳过抓取**

配置 `publish_config.ini`:

```ini
[common]
content_type = video
title = 测试-定时-可删除
video_file = videos/demo.mp4
publish_strategy = scheduled
publish_time = 2026-08-03 10:00

[platforms]
enabled = baijiahao
```

Run: `python publish_all.py`
Expected:
- 日志含 `定时发布,跳过内容链接抓取`
- 发布结果 `百家号: ✅ 成功`
- 控制台**不**含 `📝 视频链接已写入 Excel`
- Excel 不新增行

注意:定时发布会真实占用百家号后台一条定时任务,验证后需登录百家号后台取消该定时发布。

验证后清空 `publish_config.ini`。

- [ ] **Step 4: commit**

```bash
git add publish_all.py
git commit -m "feat(baijiahao): write published video link to Excel via write_video_link"
```

---

### Task 4: 清理调研产物

**Files:**
- Delete: `probe_bjh_clue.py`, `probe_bjh_content_list.py`
- Delete: `output/bjh_content_list_dump.html`, `output/bjh_content_list_links.txt`

**Interfaces:**
- 无(纯清理)

- [ ] **Step 1: 删除调研脚本**

```bash
rm probe_bjh_clue.py probe_bjh_content_list.py
```

- [ ] **Step 2: 删除调研 dump 文件**

```bash
rm output/bjh_content_list_dump.html output/bjh_content_list_links.txt
```

- [ ] **Step 3: 确认 main.py 的 BJH_PROBE_DUMP 逻辑已删**

Task 2 Step 2 已用真实抓取逻辑替换了 line 296-323 的整块(含 BJH_PROBE_DUMP),此处只验证:

Run: `grep -n "BJH_PROBE_DUMP" uploader/baijiahao_uploader/main.py`
Expected: 无输出(已无残留)

- [ ] **Step 4: 跑单测确认无回归**

Run: `python -m pytest tests/test_baijiahao_uploader.py -v`
Expected: PASS(5 个测试全过)

- [ ] **Step 5: 跑全量单测确认无回归**

Run: `python -m pytest tests/ -v`
Expected: 所有测试 PASS

- [ ] **Step 6: commit**

```bash
git add -A
git commit -m "chore(baijiahao): remove probe scripts and dump artifacts"
```

- [ ] **Step 7: 验证 git status 干净**

Run: `git status --short`
Expected: 无 probe 脚本/dump 文件残留(可能有 `.claude/settings*.json`、`publish_config.ini` 等非本任务相关改动,忽略)
