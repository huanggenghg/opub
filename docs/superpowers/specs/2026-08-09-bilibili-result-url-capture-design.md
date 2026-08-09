# B站发布链接抓取设计

**日期**: 2026-08-09
**作者**: 黄耿
**状态**: 已批准,待实现

## 背景

B站上传器 (`uploader/bilibili_uploader/main.py`) 走 biliup-rs 二进制 subprocess 调用,
上传成功后只返回 `{"success": True, "message": "发布成功"}`,不抓取公开链接。

其他平台(百家号、视频号等)都在发布后抓取内容公开链接写入 Excel
(通过 `dispatch.py:175` 检查 `result.get("result_url")` 并调 `write_video_link`)。
B站缺这一环,导致 Excel 里 B站那行总是空。

## 目标

上传成功后,自动抓取刚发布视频的 BV 号,转成公开链接
`https://www.bilibili.com/video/{BV}`,塞进 `result["result_url"]`,
让现有 Excel 写入逻辑自动生效。

## 调研结论(基于真实数据)

1. **`biliup upload` stdout 不含 BV/URL** - biliup-rs 源码
   (`crates/biliup-cli/src/uploader.rs`) 确认 upload 后只打印
   `"Upload completed: ..."` 和 `"All files uploaded successfully"`,
   不输出 bvid/aid/URL。解析 stdout 这条路走不通。

2. **`biliup list` 不显式排序** - 调 B站 `recent_archives` API,
   API 名暗示按时间倒序,但 biliup 代码不强制排序。

3. **`biliup list` 输出格式**: tab 分隔 `BV\tnormalize-title\t状态`,
   例如 `BV15r3q6FEYZ\t无小丑 打爆机了\t开放浏览`。

4. **实测观察**: 2026-08-09 上传 "测试视频发布" 后立即跑 `biliup list`,
   第一条是 "无小丑 打爆机了"(非本次上传)。说明要么不按时间倒序,
   要么有 API 延迟。因此不能靠 "取 list 第一条" 来识别本次上传。

5. **`biliup show <BV>`** 返回详细 JSON(含 bvid/aid/ctime/title),
   但需要先知道 BV,不能用来发现 BV。

## 方案

**snapshot + diff + 重试 + title fallback**。

不依赖排序假设,不依赖 title 匹配作为主路径,能确定性地识别 "这次上传的那个 BV"。

## 改动范围

只动 `uploader/bilibili_uploader/main.py`,加 3 个方法 + 改 `upload()`。
不动 dispatch.py、不动 Excel 写入逻辑、不动其他平台。

## 新增方法(都在 `BilibiliUploader` 类上)

### `_list_bvs() -> set[str]`

跑 `biliup -u <account_file> list`,解析 stdout,返回 BV 集合。

- 解析逻辑: 按 `\n` 拆行,每行按 `\t` 拆前 2 段,第一段以 `BV` 开头就加入集合
- 命令失败(returncode != 0)或 stdout 为空: 返回空集 + log warning
- 不抛异常,不阻塞上传流程

### `_match_bv_by_title() -> str | None`

跑 `biliup -u <account_file> list`,找 title 等于 `self.title` 的行,返回 BV。

- 找到 1 个: 返回 BV
- 找到 0 个: 返回 None
- 找到多个: 返回第一个 + log warning(重名场景,无法确定哪个是本次)

### `_capture_bv_after_upload(before_bvs: set[str]) -> str | None`

轮询 3 次,间隔 2 秒。每次跑 `_list_bvs()`,计算 `after_bvs - before_bvs`:

- 1 个新 BV: 返回它(主路径)
- 0 个新 BV: sleep 2 秒后重试
- >1 个新 BV: 立刻 fallback 到 `_match_bv_by_title()`(极端场景,有其他上传并发)
- 重试耗尽(3 次都没拿到 1 个新 BV): fallback 到 `_match_bv_by_title()`
- 全部失败: 返回 None

## `upload()` 改动

```
1. before_bvs = self._list_bvs()          # 失败就空集,继续
2. 跑 biliup upload (现有逻辑,不变)
3. 上传失败 -> 返回 failure(不变,不抓 BV)
4. 上传成功 -> bv = self._capture_bv_after_upload(before_bvs)
5. 若 bv:
       result["result_url"] = f"https://www.bilibili.com/video/{bv}"
       log success "已抓取内容链接: <url>"
6. 若无 bv:
       log warning "未能抓取 BV,请到 B站创作中心查看"
       返回 success(发布本身成功,只是没抓到链接)
```

## 关键决策

- **抓 BV 失败不影响发布成功状态**: 发布已成功,只是缺链接。用户可手动去创作中心查。
- **snapshot 失败不阻塞上传**: `before_bvs = {}`,后续走 title fallback。
- **URL 格式**: `https://www.bilibili.com/video/{BV}`(B站标准公开链接)。
- **3 次重试 / 2 秒间隔**: 总最坏 ~10 秒(3 次 list 调用 + 2 次 sleep,
  每次 list 约 1-2 秒)。B站 API 若 eventual consistency,
  10 秒内应能反映新上传。若仍拿不到,fallback 到 title 匹配。
- **不动 dispatch.py**: 它已经检查 `result.get("result_url")` 并写 Excel,
  B站上传器把 URL 塞进 result 即可,无需改下游。

## 错误处理

| 场景 | 处理 |
|------|------|
| snapshot 时 `biliup list` 失败 | `before_bvs = {}`,log warning,继续上传 |
| 上传后 3 次重试都拿到 0 个新 BV | fallback 到 title 匹配 |
| 上传后拿到多个新 BV | fallback 到 title 匹配 |
| title 匹配也失败 | log warning,返回 success 不带 result_url |
| cookie 在上传后过期 | `biliup list` 失败,返回 None,log warning |

## 测试

### 单元测试

1. **`_list_bvs()` 解析**: 喂 mock stdout(含正常行、空行、异常行),断言返回的 BV 集合正确。
2. **`_capture_bv_after_upload()` 分支**:
   - 1 个新 BV -> 返回它
   - 0 个新 BV(3 次都 0) -> fallback title 匹配
   - >1 个新 BV -> 立刻 fallback title 匹配
   - 用 monkeypatch 替换 `_list_bvs` 和 `_match_bv_by_title`,不真跑 biliup
3. **`upload()` 集成**: monkeypatch `run_biliup_command`,模拟上传成功 + list 返回新 BV,
   断言 `result["result_url"]` 是预期 URL。

### 手测

跑 `hgsau --platforms bilibili --video videos/demo.mp4 --title "..."`,
看日志有 "已抓取内容链接: https://www.bilibili.com/video/BVxxx",
看 Excel 里 B站那行有链接。

## 非目标

- 不改 biliup-rs 二进制本身(也改不了,是外部依赖)
- 不改 B站登录/cookie 流程
- 不抓取视频的 aid/统计数据等其他信息
- 不处理 B站视频审核状态(审核中/已发布都算成功,只要有 BV 就抓)
