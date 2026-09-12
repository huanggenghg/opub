# opub CLI

本页是面向用户的统一命令行说明。`opub` 通过一个命令完成素材准备、账号检查和多平台发布；每个平台只自动发现一个规范账号文件。

## 安装

```bash
pip install opub
opub --version
opub --repair-env
```

首次运行会创建 `~/.opub/` 数据目录。发布预检只检查环境，不安装或更新依赖。浏览器自动化需要 Chromium，图文转视频还需要 MoviePy/Pillow 和 ffmpeg。

`opub --repair-env` 使用当前解释器重新安装项目及其依赖，并安装 Chromium；已安装的 opub 版本保持不变，依赖按该版本声明解析。在源码目录运行时使用当前源码的依赖声明。若解释器缺少 pip，会先尝试用 ensurepip 安装。该命令不需要许可，不能与发布或激活参数混用。每个安装步骤最多等待 600 秒。

需要图文转视频时运行 `opub --repair-env --with-video`，或使用 `pip install "opub[video]"` 安装可选依赖。系统 ffmpeg 仍需另行安装。安装失败时按 `ENV-xxx` 建议处理。

## 发布

视频：

```bash
opub --platforms douyin,weibo --video videos/demo.mp4 --title "标题" --tags "标签1,标签2"
```

图文：

```bash
opub --platforms xiaohongshu --note --images img1.jpg,img2.jpg --title "标题"
```

定时、选择目录起始序号和强制重新生成（时间需晚于当前时间两小时）：

```bash
opub --platforms weibo --video videos/ --title "标题" --schedule "2027-01-01 12:00" --start-from 2 --force
```

素材路径、标题、描述、标签和目标平台应由用户明确提供；一个规范账号文件对应一个平台账号。发布成功后命令会输出各平台结果及链接。

## 发布前检查与任务恢复

```bash
# 只检查，不执行发布；无需激活
opub --platforms douyin,weibo --video videos/demo.mp4 --title "标题" --dry-run --output json

# 使用实际发布返回的任务编号，不混入新的发布参数
opub --resume RUN_ID --output json
```

`--dry-run` 检查平台能力、文件存在性/可读性/扩展名、目录起始序号、标题、定时及本机依赖。不会打开浏览器、登录、发布、转换图片或自动生成文案，也不会创建发布记录；标题来自显式输入、已有同名 JSON 或本地模板。它不验证平台登录状态或素材实际编码。图文转视频也会检查 MoviePy 和 ffmpeg。实际发布前同样检查全部素材并解析全部标题。

直接图文支持抖音、小红书、快手、微博；其他平台需使用 `--convert-to-video`。当前 B站接口没有传递定时时间，带 B站的定时任务返回 `CFG-006`，避免误发。定时需晚于当前时间两小时；恢复时仍将执行的项也需满足此条件。

实际发布创建唯一 `run_id`，逐素材、逐平台保存结果。`--resume` 沿用该任务的文案、平台、账号文件路径及素材，不重新生成文案或转换图片：

- 已成功：沿用原结果及链接，标记 `reused: true`，不再登录或提交。
- 尚未执行或确认未提交的失败：可继续执行；例如登录检查阶段失败、上传器明确返回可安全重试。
- 中断或提交结果不明：返回 `RUN-004`，不自动重发。先到平台核对作品，确认需要再次发布后为相应素材和平台创建新任务。

恢复会核对原素材的 SHA-256 指纹；缺失、内容改变或记录无效返回 `RUN-003`。记录无法读写返回 `RUN-005`，停止继续提交。全部项已完成时，恢复无需浏览器环境，也不再校验已完成项的发布时间。

记录位于数据目录的 `publish-history.sqlite3`：安装版默认 `~/.opub/`，源码运行默认仓库根目录，`SAU_HOME` 可覆盖。记录包含素材/账号文件路径、文案、标签、时间及发布结果，不保存 cookie 内容或激活凭据。账号路径固定，但不会核验同一路径下账号身份是否被替换，恢复前应保持原账号。删除记录会失去该任务的恢复保护。

普通发布命令即使参数相同也创建新任务。`--start-from` 仅从目录第 N 个视频开始新任务，不能替代 `--resume`，也不支持对单个文件使用大于 1 的序号。

## 付费许可

`opub 0.x 创始版`售价 ¥9.90，在爱发电商品页购买：<https://afdian.com/item/69bf71f0a9f511f1bc065254001e7c00>。opub 自身不设账号。购买时无需提前注册爱发电；请使用你自己的手机号或邮箱完成验证，首次购买时爱发电会自动生成账号。付款后复制爱发电发放的激活码；请勿向 Agent 提供验证码或账号密码。激活码首次兑换后绑定一个设备。许可不迁移、不解绑、不提供换机重置；新电脑重新购买。许可覆盖 `0.x`，已安装的 `0.x` 版本可永久离线使用；未来大版本需要单独购买。支付方式由用户在爱发电页面选择。公开 Python 包是诚实用户门禁，属于非强 DRM，不是强制性防破解方案。

查看许可状态：

```bash
opub --license-status
```

首次激活：

```bash
opub --activate
opub --activate --code OPUB0-ABCDE-FGHJK-MNPQR-STVWX-YZ234-56789
```

交互运行 `opub --activate` 会打开爱发电购买页，并提示输入爱发电发放的激活码。使用 `--code` 可供 Agent 或非交互环境直接兑换。购买和首次激活需要网络，激活完成后已安装的 `0.x` 版本可永久离线运行。

### Agent 使用流程

Agent 必须先保留已经确认的发布输入，并在发布前静默运行 `opub --license-status`。退出码为 13 时运行 `opub --activate` 打开购买页；用户取得激活码后运行带 `--code` 的命令。支付方式由用户在爱发电页面选择。Agent 不得在用户可见消息、异常或 internal log 中展示完整激活码或设备 hash。激活成功后自动继续同一个发布任务，不重复问参数。

Agent 只负责打开购买页和接收用户付款后提供的激活码，不得代填或索取手机号、邮箱验证码、爱发电账号或密码。

### 许可错误与建议

错误格式为 `[opub] LIC-xxx: <描述>。建议: <动作>`。

| 错误码 | 含义 | 建议 |
| --- | --- | --- |
| `LIC-001` | 尚未激活 | 执行激活命令 |
| `LIC-002` | 损坏签名 | 联系支持并提供错误码 |
| `LIC-003` | 许可属于其他设备 | 新电脑重新购买 |
| `LIC-004` | 稳定设备标识不可用 | 联系支持并提供错误码 |
| `LIC-011` | 服务不可用 | 稍后重试 |
| `LIC-013` | 激活码无效 | 检查激活码后重新激活 |
| `LIC-014` | 激活码已绑定其他设备 | 当前电脑重新购买 |
| `LIC-015` | 当前客户端版本不适用 | 升级或切换到 opub 0.x 后重试 |

退出码 `13` 表示需要首次付费激活。发布本身仍使用稳定退出码：`0` 全部成功、`1` 部分成功、`2` 全部失败、`10` 配置错误、`11` 环境错误、`12` 登录未完成。

## 结果与错误

流程错误写入 stderr：

```text
[opub] <错误码>: <描述>。建议: <可执行的动作>
```

发布汇总写入 stdout，并包含平台成功/失败、`PUB-<platform>` 错误码、结果链接和总体计数。配置问题看 `CFG-xxx`，环境问题看 `ENV-xxx`，登录问题看 `AUTH-xxx`；不要把内部调试日志当作用户结果。

登录检查区分以下情况：明确登录失效或缺少账号文件时才引导扫码；`NET-001` 表示网络失败或超时，`PAGE-001` 表示页面无法识别，`ENV-006` 表示本机环境或账号文件不可用。这三类问题不会自动扫码或重试发布，按对应建议处理。若全部平台都因这些检查失败，退出码为 2；只有全部失败且均为账号问题时才返回 12。

### JSON 输出

```bash
opub --platforms douyin,weibo --video demo.mp4 --title "标题" --output json >result.json 2>diagnostics.log
```

默认 `--output text` 保持终端汇总。JSON 模式下，stdout 只输出一份 UTF-8 JSON 文档，过程日志及子进程输出写入 stderr；`--help` 和 `--version` 仍显示原有文本。JSON 模式同样适用于环境修复和许可命令。

示例（单个平台成功）：

```json
{
  "schema_version": 1,
  "mode": "publish",
  "run_id": "12345678-1234-1234-1234-123456789abc",
  "planned": [],
  "exit_code": 0,
  "summary": {"success": 1, "failed": 0},
  "results": [{
    "material": "/path/demo.mp4",
    "content_type": "video",
    "platform": "douyin",
    "success": true,
    "message": "发布成功",
    "error_code": null,
    "result_url": "https://www.douyin.com/video/123",
    "result_id": "123",
    "safe_to_retry": false,
    "reused": false,
    "action": null
  }],
  "errors": []
}
```

`material` 在视频模式为路径字符串，在图文模式为图片路径数组。`result_url`/`result_id` 未取得时为 null，不影响成功状态。`errors` 收集流程错误，每项包含 `error_code`、`message`、`action`，不需要解析中文日志。

结果逐平台保留，后续异常不会丢弃已完成项。`summary` 只统计已记录的平台结果；配置错误、许可错误、意外异常和中断还必须查看 `exit_code` 与 `errors`，不能仅凭计数判断整次任务成功。中断返回 130 和 `RUN-002`。只有 `safe_to_retry` 明确为 true 时才允许自动重试；缺省为 false，以免重复发布。

`mode` 区分 `publish`、`resume`、`dry_run`。未创建任务时 `run_id` 为 null；检查通过的 dry-run 将素材、标题、平台、时间和转换标记放入 `planned`，`results` 为空。`reused` 表示沿用历史成功结果，计入成功汇总，但本次没有再次发布。部分失败后应保留 `run_id`，使用恢复命令，避免重跑普通命令导致成功平台再次发布。
