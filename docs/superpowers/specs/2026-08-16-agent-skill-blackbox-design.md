# Agent 技能黑盒化设计（hgsau-cli SKILL.md + CLI 自描述）

日期：2026-08-16
状态：已与用户确认设计，待实现

## 背景与目标

项目定位是以 Agent 平台技能工具接入（如腾讯 WorkBuddy、Claude Code 等支持 SKILL.md 的环境），不做独立 SaaS/GUI。当 Agent 获知并使用"发布"技能时，底层实现所在的代码仓对 Agent 必须是黑盒：Agent 不 clone 仓库、不读源码、不知道目录结构。

黑盒的本质是：**任何 Agent 完成一次发布所需的信息，要么在 SKILL.md 里，要么能从某次 `hgsau` 命令的输出里拿到**。不满足这条的，视为 bug（补文档或补 CLI 输出），而不是让 Agent 去读代码。

已确认的关键决策：

- 目标环境：所有能加载 SKILL.md 的 Agent 平台，统一走 SKILL.md 路线（不做 MCP）。
- 安装来源：pip 包 `hgsau` 为唯一入口，SKILL.md 零仓库引用。
- 信息不足时：CLI 自描述优先，不附额外排查文档，不引导 Agent 读代码。

## 总体架构：三层契约

```
┌─ Agent（WorkBuddy / Claude Code / 任何支持 SKILL.md 的平台）
│    只读两样东西：
│    ① SKILL.md          -- 静态契约（怎么装、怎么配、怎么调、结果怎么读）
│    ② hgsau 运行时输出   -- 动态契约（--help、--version、进度、结构化结果、错误+建议动作）
│
├─ 分发物：pip 包 hgsau（pypi/testpypi），唯一入口
└─ 代码仓：黑盒。Agent 永远不需要 clone、不需要读源码、不需要知道目录结构
```

选型说明（已对比过的替代方案）：

- SKILL.md 打进 pip 包分发（`hgsau skill` 导出）：各平台 skill 注册机制不同，从包提取仍需适配层，复杂度转移而非消除。可作为后续版本绑定增强，本次不做。
- MCP 工具化：接口最严格，但扫码登录等人工介入环节在纯 RPC 模型里更难处理，且与已定的 SKILL.md 路线相悖。不做。

## 组件 1：SKILL.md 重写

重写 `skills/hgsau-cli/SKILL.md`，章节结构：

1. **frontmatter**：name/description/version 保持现有形式；version 字段与 pip 包版本对齐，发版时同步更新。
2. **这是什么**：一句话--"pip 包 hgsau，把视频/图文一键发布到 7 个国内平台"。
3. **安装**：`pip install hgsau` + 系统依赖（chromium、ffmpeg）。删除 `uv pip install -e .`、`cp conf.example.py conf.py` 等一切仓库操作；conf 生成改由 CLI 承担（见组件 2 第 3 项）。
4. **配置**：publish_config.ini 字段表（保留现有内容，含一次性字段 vs 长期字段的说明）。
5. **调用**：`hgsau` + 命令行临时覆盖参数（保留现有内容）。
6. **读取结果**（新增）：退出码表 + 结果汇总输出的格式说明（见组件 3）。
7. **Agent 注意事项**：保留现有内容，删除"优先相信 pyproject.toml，不要把 requirements.txt 视为主线真相"等实现层提示--黑盒下 Agent 不该知道 pyproject 的存在。

触发场景、平台列表（7 平台）等现有达标内容原样保留。

## 组件 2：CLI 自描述清单

现状缺口与补齐项：

1. **`hgsau --help` 全量参数化审查**：确保每个参数的作用、取值、与 ini 字段的对应关系一句话说清。`--help` 输出是 SKILL.md 之外的第二份权威文档。
2. **`hgsau --version`**：输出包版本号，Agent 用它对照 SKILL.md 的 version 字段判断文档与安装版本是否匹配。
3. **首次运行初始化**：pip 安装后机器上没有 `conf.example.py`。CLI 在检测到缺 conf.py 时自动生成默认配置并提示用户按需修改，保持无子命令的单入口形式，不新增 `hgsau init` 命令。
4. **环境预检输出带修复动作**：现有预检（patchright/chromium）失败时，输出"缺什么 + 怎么装"，例如：`[hgsau] ENV-002: 未找到 Chromium。建议: 运行 patchright install chromium`。Agent 拿到即可直接执行或转告用户。
5. **结果汇总结构化呈现**：发布结束的汇总表保持稳定格式（平台 | 状态 | 链接/错误码），SKILL.md 第 6 节解释该格式，Agent 靠解析规则读结果。
6. **不加 `--json`**（YAGNI）：文本表格对 Agent 已可解析，将来有平台真需要再加。

## 组件 3：退出码与错误码

退出码从二值 0/1 扩展为语义化（区分"流程没跑起来"和"跑起来但部分失败"）：

| 退出码 | 含义 | Agent 下一步 |
| --- | --- | --- |
| 0 | 全部平台发布成功 | 汇报结果链接 |
| 1 | 部分平台成功、部分失败 | 读汇总表，向用户汇报成败明细 |
| 2 | 全部平台发布失败 | 读各平台错误码，按建议动作处理 |
| 10 | 配置错误（字段缺失/格式错/文件不存在） | 按错误码提示修配置或加 CLI 覆盖参数 |
| 11 | 环境错误（Chromium/ffmpeg/patchright 缺失） | 执行或建议预检输出中的安装命令后重试 |
| 12 | 账号未登录且扫码未完成 | 引导用户扫码（SKILL.md 注意事项已有指引） |

错误码体系：`CFG-xxx`（配置）、`ENV-xxx`（环境）、`AUTH-xxx`（登录）、`PUB-xxx`（平台发布失败，每平台一个明细码）。

错误输出统一格式：

```
[hgsau] <错误码>: <人话描述>。建议: <可执行的动作>
```

## 错误处理原则

- 每个 SKILL.md 未覆盖的运行时情况，都应落进上述错误码/退出码体系并带建议动作；出现体系外的裸异常堆栈视为 bug，需归类收编。
- 微信视频号等需要人工扫码的环节保持现状（headless=False 浏览器直接扫码），错误输出引导 Agent 告知用户介入，不自行重试。

## 测试策略

- **单元测试**：退出码映射、错误码分配、错误消息格式（`[hgsau] CODE: desc。建议: action`）用 mock 失败路径断言覆盖。
- **e2e 验证**：环境预检、首次运行初始化、真实发布维持现有手工验证方式（真实平台不可 mock，符合项目一贯做法）。
- **SKILL.md 与 CLI 一致性**：发版时人工核对 SKILL.md version、参数表、退出码表与当前 CLI 输出一致。

## 不做的事

- 不做 MCP server。
- 不做 SKILL.md 的 pip 包内分发（留作后续版本绑定增强）。
- 不加 `--json` 输出。
- 不改变无子命令的单入口 CLI 形式。
