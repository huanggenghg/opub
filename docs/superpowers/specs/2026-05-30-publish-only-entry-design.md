# 仅保留统一发布入口设计

## 目标

将 `social-auto-upload` 简化为一个用户级发布工作流：

```bash
hgsau publish
```

项目当前处于开发阶段，不要求兼容旧命令。CLI 不再把平台级登录、校验、上传命令作为公开用法提供给用户。

项目从旧项目克隆迭代而来，本次也同步完成命名收敛：旧有 `sau` 命名统一迁移为 `hgsau`。

用户心智应收敛为：

```text
编辑 publish_config.ini -> 运行 hgsau publish -> 自动完成环境预检、登录校验、发布和汇总
```

## 非目标

- 不保留平台级 CLI 命令作为公开入口。
- 不保留 `sau status`、`sau login`、`sau generate` 作为公开入口。
- 不在 `sau_cli.py` 和 `publish_all.py` 中继续维护两套发布调度逻辑。
- 不重新设计各平台 uploader 内部实现，除非统一发布流程必须调整调用方式。
- 不提供国际化文档或双语 CLI 文案；本项目文档和主要提示文案以中文为准。

## 命名收敛

本次不做兼容层，旧 `sau` 命名应完整下线。目标是让用户、Agent、测试和代码入口都只看到 `hgsau`。

需要统一修改：

- CLI 命令：`sau` 改为 `hgsau`。
- Python 分发包名：`pyproject.toml` 中 `[project].name` 改为 `hgsau`。
- Python console script：`pyproject.toml` 中入口改为 `hgsau = "hgsau_cli:main"`。
- CLI 主文件：`sau_cli.py` 重命名为 `hgsau_cli.py`。
- 测试文件与 import：测试中不再 `import sau_cli`，改为 `import hgsau_cli`。
- 文档命令示例：全部使用 `hgsau publish`。
- Agent 指引：全部使用 `hgsau publish`。
- 用户可见错误提示：避免继续提示用户运行 `sau ...`。

内部如果仍有变量名、函数名带 `sau` 但不影响用户和维护理解，可以在实现中按触达范围清理。CLI 入口、文件名、测试和文档属于必须清理范围。

## 公开 CLI

唯一公开命令：

```bash
hgsau publish
```

支持的覆盖参数：

```bash
--config publish_config.ini
--platforms douyin,weibo
--video videos/demo.mp4
--title "标题"
--desc "描述"
--tags 标签1,标签2
--schedule "2026-05-30 21:30"
--start-from 3
--force
```

这些参数只用于覆盖本次运行的配置。常规用法仍然是编辑 `publish_config.ini` 后执行 `hgsau publish`。

移除公开命令：

- `sau status`
- `sau login`
- `sau generate`
- `sau douyin ...`
- `sau kuaishou ...`
- `sau xiaohongshu ...`
- `sau bilibili ...`

旧 `sau` 顶层命令本身也不再提供。安装后应生成 `hgsau` 命令，而不是 `sau` 命令。

如果旧命令背后的函数仍有复用价值，可以保留为内部 Python 函数，但不能再挂到 CLI parser 上。

## 配置模型

`publish_config.ini` 是发布配置的主入口，负责描述：

- `content_type`：`video` 或 `note`
- 内容字段：`title`、`desc`、`tags`
- 素材字段：`video_file`、`images`
- 发布时间：`publish_strategy`、`publish_time`
- 批量控制：`start_from`
- 启用平台：`[platforms].enabled`
- 账号文件：`[platforms].<platform>_account`

CLI 参数只能作为一次性覆盖，不替代配置文件模型。

## 统一工作流

`hgsau publish` 执行完整发布场景：

```text
运行环境预检
-> 读取配置
-> 合并 CLI 覆盖参数
-> 发布前置校验
-> 解析视频或图文任务
-> 遍历每条内容
   -> 遍历每个启用平台
      -> 遍历每个账号
         -> 校验账号登录态
         -> 登录态无效或账号文件缺失时触发登录
         -> 登录成功后继续发布
         -> 登录失败则记录该账号/平台失败
      -> 继续下一个平台
-> 输出单条内容结果和总体汇总
```

用户执行 `hgsau publish` 就表示授权执行完整链路。流程中不再出现“先校验，等待用户确认后再发布”的二段式步骤。

## 运行环境预检

运行环境预检是机器和依赖层面的检查，不涉及用户账号，也不判断 cookie 是否有效。

它负责检查本次发布流程运行所需的基础环境：

- Python 版本是否满足项目要求。
- 核心依赖是否可导入。
- `patchright` 是否已安装。
- Patchright Chromium 浏览器驱动是否已安装。
- 项目数据目录、配置文件路径、cookies 目录等基础路径是否可访问。

处理策略：

- 能自动修复的环境问题应在 `hgsau publish` 内部自动处理，例如安装缺失的 Patchright Chromium。
- 自动修复失败时，流程直接以非零退出码结束，并输出清晰错误。
- 不提供独立的 `hgsau status` 用户入口。
- 不要求用户先运行环境检查命令，再决定是否发布。

运行环境预检和账号登录校验必须分开实现。环境预检只回答“这台机器能不能运行发布流程”，不回答“某个平台账号是否已登录”。

## 账号登录校验

账号登录校验属于发布流程的一部分，只针对本次配置启用的平台和账号执行。

它负责：

- 解析本次启用平台的账号文件配置。
- 检查账号文件是否存在。
- 检查 cookie 或登录态是否有效。
- 登录态无效时触发对应平台登录流程。
- 登录成功后继续本次发布。
- 登录失败时记录该账号/平台失败，并继续处理其他平台或账号。

账号登录校验不能作为独立用户步骤暴露。用户不需要先执行 `check` 或 `login`，再执行 `publish`。

## 架构

### `publish_all.py`

`publish_all.py` 成为唯一发布引擎，负责：

- 运行环境预检
- 配置文件读取
- 配置解析
- CLI 覆盖参数合并
- 素材发现
- 图文转视频
- 视频同名配置文件中的标题和描述解析
- 账号文件路径解析
- 账号登录态校验
- 登录失败兜底
- 平台发布分发
- 结果汇总

对 CLI 暴露一个异步函数，例如：

```python
async def run_publish(config_file: str, overrides: PublishOverrides) -> int:
    ...
```

`PublishOverrides` 可以是 dataclass，也可以是显式 dict，但必须便于测试，不应依赖 argparse 的 `Namespace`。

### `hgsau_cli.py`

`hgsau_cli.py` 收敛成很薄的 CLI 包装层：

- 构建只包含 `publish` 的 parser。
- 解析 `publish` 覆盖参数。
- 调用 `publish_all.run_publish(...)`。
- 返回发布引擎的退出码。

删除旧公开命令的 parser 构造和 dispatch 分支。统一发布仍需要的辅助代码应移动到 `publish_all.py` 或平台模块中。

### 平台 Uploader

各平台 uploader 继续负责平台内部的浏览器自动化或 API 调用。统一发布引擎通过 `publish_to_platform` 或小型分发表调用平台 uploader。

实现时不能新增平台级 CLI 路径。

## 错误处理

发布开始前的致命错误应直接返回非零退出码：

- 配置文件不存在，且 CLI 参数不足以组成一次发布。
- 未启用任何平台。
- 当前内容类型缺少必要素材，例如视频模式没有视频、图文模式没有图片。
- 定时发布时间格式错误。
- 内容类型不支持。
- 运行环境预检失败且无法自动修复。

平台级或账号级错误应记录到结果汇总中，不阻断其他平台：

- 账号文件缺失。
- cookie 无效且登录失败。
- 平台 uploader 抛出异常。
- 平台不支持当前内容类型，例如只支持视频的平台收到图文任务。

最终退出码：

- 全部尝试发布成功时返回 `0`。
- 发布前置校验失败、运行环境预检失败，或任意一次平台发布失败时返回 `1`。

## 文档

用户和 Agent 文档只讲一个入口：

```bash
hgsau publish
```

需要更新：

- `AGENT.md`
- `README.md`
- `docs/install.md`
- `docs/CLI.md`
- `docs/agent-bootstrap.md`

文档重点说明：

- `publish_config.ini` 是主要控制面。
- `hgsau publish` 会在内部自动完成运行环境预检、账号登录校验和发布。
- 用户不需要手动执行 `status`、`login`、`check` 或平台级上传命令。
- 旧 `sau` 命令和 `sau_cli.py` 命名已经下线，统一使用 `hgsau`。
- 本项目不做国际化文档维护，当前文档以中文为准。

历史设计和计划文档位于 `docs/superpowers/` 下，不需要批量重写。

## 测试

更新或替换 CLI 测试，覆盖新入口：

- parser 接受 `hgsau publish`。
- parser 接受支持的 publish 覆盖参数。
- parser 拒绝已移除的公开命令，例如 `hgsau douyin ...`。
- 安装后的 console script 为 `hgsau`，不再生成 `sau`。
- `hgsau publish` 会调用统一发布引擎，并传入解析后的覆盖参数。
- CLI 覆盖参数和 `publish_config.ini` 合并结果稳定。
- 运行环境预检缺少驱动时会尝试自动安装或返回清晰失败。
- 账号登录态无效时会触发登录。
- 单个平台或账号失败后，其他平台继续执行。
- 任意一次平台发布失败时最终退出码为 `1`。

自动化测试使用 mock 替代真实浏览器登录和真实平台上传，不依赖真实账号会话。

## 迁移说明

不要求兼容旧命令，因此旧脚本可以被破坏。替代方式是配置 `publish_config.ini` 并执行 `hgsau publish`。

示例：

```bash
# 旧方式
sau douyin upload-video --account creator --file videos/demo.mp4 --title "标题"

# 新方式
hgsau publish --platforms douyin --video videos/demo.mp4 --title "标题"
```

常规使用建议写入 `publish_config.ini` 后执行：

```bash
hgsau publish
```
