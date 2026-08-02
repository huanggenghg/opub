# 百家号发布后抓取内容公开链接设计

## 背景

百家号 `BaiJiaHaoVideo.upload()` 发布成功后,只 `wait_for_url("...clue**")` 检测跳转到 clue 成功提示页,**未抓取发布内容的公开链接**。微博/小红书/快手均已在 `upload()` 返回 `video_link`/`share_link`,并由 `publish_to_xxx` 写入 Excel(微博)或塞入 response(小红书/快手)。百家号需要对齐微博模式:返回 `video_link` + 写 Excel。

## 真实信号(基于实测)

### clue 页无可用链接(否决方案 A)

- 用户手动发布后确认:clue 页(`https://baijiahao.baidu.com/builder/rc/clue**`)是"发布成功"提示页,**无内容公开链接**
- 结论:clue 页抓取方案否决

### 内容管理页结构(方案 B 锁定)

调研脚本 dump `https://baijiahao.baidu.com/builder/rc/content` 渲染后 DOM(1MB+):

- **页面性质:** SPA,初始 HTML 只有 `<div id="root"></div>` 骨架,列表靠 JS 异步渲染
- **渲染等待:** `page.goto` 用 `wait_until="domcontentloaded"` 会 60s 超时(SPA 持续加载);改用 `wait_for_function("#root 有内容")` + 额外 wait 列表 selector
- **列表容器:** `div.client_pages_content_v2_components_articleList`
- **列表项:** `div.client_pages_content_v2_components_articleItem`
- **排序:** 时间倒序,**第一条 = 最新发布**(实测第一条 id=`1872396938046079637` 标题"demo" 是最新内容)
- **列表项内 `<a>` 标签 href 格式:** `http://baijiahao.baidu.com/builder/preview/s?id={ID}`(创作者后台预览链接,**非公开链接**)
- **公开链接转换:** 从 preview href 提取 `id` 参数,拼 `https://baijiahao.baidu.com/s?id={ID}`(百家号公开链接标准格式)

### 公开链接可访问性

`https://baijiahao.baidu.com/s?id={ID}` 是百家号公开链接标准格式。WebFetch 验证时被重定向到百度验证码页(`wappass.baidu.com/...captcha/tuxing.html`),原因是 WebFetch 无 cookie 被反爬,**不代表链接无效**(重定向 URL 里含 `baijiahao_id={ID}` 证明 id 有效)。审核通过后浏览器正常可访问;归档用 URL 足够。

### cookie 状态

调研期间 cookie 有效(访问内容管理页未被重定向到登录页)。

## 架构

```
publish_to_baijiahao (publish_all.py)
  └─ BaiJiaHaoVideo.main()
      └─ upload(playwright)
          ├─ ...现有上传/发布流程不变...
          ├─ wait_for_url("...clue**") 成功                    [现有]
          ├─ ★ if publish_date == 0 (立即发布):
          │     └─ _capture_content_url(page) -> str | None    [新增]
          ├─ else (定时发布): 跳过                              [新增]
          └─ return {"video_link": str | None}                 [改: None -> dict]
  └─ result = await uploader.main()
  └─ video_link = result.get("video_link", "")
      ├─ 非空 -> response["video_link"]=link, write_video_link(link), print "📝 视频链接已写入 Excel"
      └─ 空 -> response 不含 video_link
  └─ return {"success": True, "message": "发布成功"[, "video_link": link]}
```

## 组件

### 修改 `uploader/baijiahao_uploader/main.py`

**`BaiJiaHaoVideo.upload()`** -- 返回值 `None` 改为 `dict`:

在 `wait_for_url("...clue**")` 成功后、`context.storage_state` 之前插入:

```python
video_link = None
if self.publish_date == 0:  # 立即发布才抓
    video_link = await self._capture_content_url(page)
else:
    baijiahao_logger.info("定时发布,跳过内容链接抓取")
```

方法末尾 `return {"video_link": video_link}`。`BJH_PROBE_DUMP` 临时逻辑删除。

**新增 `BaiJiaHaoVideo._capture_content_url(page) -> str | None`:**

```python
async def _capture_content_url(self, page: Page) -> str | None:
    """跳转内容管理页,取第一条列表项的公开链接。抓不到返回 None。"""
    content_url = "https://baijiahao.baidu.com/builder/rc/content"
    try:
        await page.goto(content_url, timeout=60000, wait_until="domcontentloaded")
    except Exception as e:
        baijiahao_logger.warning(f"goto 内容管理页异常(继续): {e}")

    # 等 SPA 渲染
    try:
        await page.wait_for_function(
            "() => { const r = document.querySelector('#root'); return r && r.children.length > 0; }",
            timeout=30000,
        )
    except Exception:
        pass

    # 轮询列表项出现(刚发布可能延迟入列),5s 间隔,最多 30s
    item_locator = page.locator("div.client_pages_content_v2_components_articleItem")
    for _ in range(6):
        if await item_locator.count() > 0:
            break
        await asyncio.sleep(5)
    else:
        baijiahao_logger.warning("内容管理页未出现列表项,跳过链接抓取")
        return None

    # 取第一个 articleItem 里的 preview href
    href = await item_locator.first.locator('a[href*="builder/preview/s?id="]').first.get_attribute("href")
    public_url = _extract_bjh_public_url_from_preview_href(href)
    if public_url:
        baijiahao_logger.success(f"已抓取内容公开链接: {public_url}")
    else:
        baijiahao_logger.warning(f"无法从 href 提取 id: {href}")
    return public_url
```

**新增模块级纯函数:**

```python
import re

def _extract_bjh_public_url_from_preview_href(href: str | None) -> str | None:
    """从 builder/preview/s?id={ID} href 提取 id,拼公开链接。"""
    if not href:
        return None
    m = re.search(r"[?&]id=(\d+)", href)
    return f"https://baijiahao.baidu.com/s?id={m.group(1)}" if m else None
```

**`BaiJiaHaoVideo.main()`** -- 透传 `upload()` 返回值:

```python
async def main(self):
    async with async_playwright() as playwright:
        return await self.upload(playwright)
```

### 修改 `publish_all.py` `publish_to_baijiahao` (line 818-849)

对齐 `publish_to_weibo` (line 930-944) 模式:

```python
from utils.excel_writer import write_video_link  # 顶部 import 或函数内

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
```

## 数据流

```
upload() 发布成功 -> wait_for_url("...clue**") 通过
  ├─ publish_date != 0 (定时) -> video_link=None, log "定时发布,跳过"
  └─ publish_date == 0 (立即) -> _capture_content_url(page)
        ├─ goto 内容管理页 (try/except 接受超时)
        ├─ wait_for_function #root 有内容 (30s 超时, 超时也继续)
        ├─ 轮询 articleItem 出现 (5s × 6 = 30s)
        ├─ 取第一个 articleItem 的 a[href*=preview/s?id=] 的 href
        ├─ _extract_bjh_public_url_from_preview_href(href) -> 公开链接 or None
        ├─ 命中 -> log success, return 链接
        └─ 未命中 -> log warning, return None
main() 透传 -> publish_to_baijiahao
  ├─ video_link 非空 -> response["video_link"]=link, write_video_link, print
  └─ video_link 空 -> response 不含 video_link
return {"success": True, "message": "发布成功"[, "video_link": link]}
```

## 错误处理

| 场景 | 行为 |
|------|------|
| 定时发布 (`publish_date != 0`) | 跳过抓取,`video_link=None`,log info,**不算失败** |
| `goto 内容管理页` 超时 | warning,继续后续 wait(已 try/except) |
| `wait_for_function #root` 超时 | 静默继续(可能 SPA 慢) |
| 列表项 30s 内未出现 | warning,`video_link=None`,**不算失败** |
| href 不含 id | warning,`video_link=None`,**不算失败** |
| `write_video_link` 抛异常 | `print("⚠️ 写入 Excel 异常")`,不影响 `success=True` (对齐微博) |
| `wait_for_url clue` 失败 | 现有逻辑保留(raise Exception) |

**核心原则:** 发布本身成功(`wait_for_url clue` 已过)后,链接抓取失败**绝不**让发布标失败。

## 测试

### 单元测试(新增 `tests/test_baijiahao_uploader.py`)

用 unittest + FakePage/FakeLocator mock(对齐 `tests/test_weibo_uploader.py` 风格),只测纯函数:

```python
class ExtractBjhPublicUrlTests(unittest.TestCase):
    def test_extracts_id_from_preview_href(self):
        href = "http://baijiahao.baidu.com/builder/preview/s?id=1872396938046079637"
        self.assertEqual(
            _extract_bjh_public_url_from_preview_href(href),
            "https://baijiahao.baidu.com/s?id=1872396938046079637",
        )

    def test_returns_none_for_none(self):
        self.assertIsNone(_extract_bjh_public_url_from_preview_href(None))

    def test_returns_none_for_no_id(self):
        self.assertIsNone(_extract_bjh_public_url_from_preview_href("https://example.com/no-id"))

    def test_handles_https_and_query_order(self):
        href = "https://baijiahao.baidu.com/builder/preview/s?id=123&other=456"
        self.assertEqual(
            _extract_bjh_public_url_from_preview_href(href),
            "https://baijiahao.baidu.com/s?id=123",
        )
```

**不测** `_capture_content_url` 整体(涉及 page.goto/wait_for_function/locator,mock 成本高且价值低)。

### 手动验证

1. 配置 `publish_config.ini` 启用 baijiahao + 测试视频 + 立即发布
2. 跑 `python publish_all.py`
3. 观察日志:出现 `已抓取内容公开链接: https://baijiahao.baidu.com/s?id=...`
4. 观察控制台:出现 `📝 视频链接已写入 Excel: https://baijiahao.baidu.com/s?id=...`
5. 检查 Excel 文件:新增一行含该链接
6. 浏览器访问该链接(已登录态):正常显示刚发的视频

## 实现约束

- **先调研再设计已满足:** 本设计的 selector(`client_pages_content_v2_components_articleItem`、`a[href*="builder/preview/s?id="]`)来自真实 DOM dump,非假设
- **不用截屏定位:** 全程用 DOM/页面源码(符合项目 feedback memory)

## 清理项

实现完成后删除调研产物:
- `probe_bjh_clue.py`(项目根)
- `probe_bjh_content_list.py`(项目根)
- `uploader/baijiahao_uploader/main.py` 里的 `BJH_PROBE_DUMP` 临时逻辑
- `output/bjh_clue_*` 和 `output/bjh_content_list_*` dump 文件

## 验收标准

1. 立即发布成功后,日志含 `已抓取内容公开链接: https://baijiahao.baidu.com/s?id=...`
2. Excel 新增一行含该链接
3. 定时发布跳过抓取,日志含 `定时发布,跳过内容链接抓取`,response 不含 `video_link`,`success=True`
4. 链接抓取失败(列表未出现/href 无 id)时,warning 日志,`success=True`,response 不含 `video_link`
5. 单元测试 `_extract_bjh_public_url_from_preview_href` 全部通过
6. 调研产物已清理
