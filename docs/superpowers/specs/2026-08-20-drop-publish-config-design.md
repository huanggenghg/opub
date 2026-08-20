# 设计:去掉 publish_config.ini 依赖,CLI 成为唯一入口

日期:2026-08-20
状态:已获用户批准
版本影响:0.5.2 -> 0.6.0(破坏性变更)

## 背景与目标

`opub` 当前有两种运行模式:读取 `publish_config.ini` 的完整模式(CLI 参数仅作临时覆盖)和无配置文件时的纯 CLI 模式(`--platforms + --video`,账号自动发现)。AGENT.md/README/SKILL.md 均把配置文件描述为"主要控制文件"。

作为 Agent 平台技能工具接入的产品方向下,有状态的配置文件对 Agent 调用方是负担:需要先写文件再调用、发布后字段被自动清空、两套入口契约。目标:**硬删除配置文件模式,CLI 参数成为唯一入口**,opub 变为无状态命令。

用户决策记录:

1. 硬删除,CLI 唯一入口(不保留 config 可选模式)
2. config 独有的图文能力(content_type/images/convert_to_video/video_duration)全部升为 CLI 参数
3. 每平台账号文件纯自动发现(cookies/ 目录扫描),不加每平台 account 参数
4. 实现路线:就地收编 overrides(不动下游 params dict 流),不做全链路类型化重构
5. 版本库里和用户本地的 publish_config.ini 都删除

## CLI 契约(新)

```bash
# 视频发布(必填:--platforms + --video)
opub --platforms douyin,weibo --video videos/demo.mp4 --title "标题" --tags "a,b"

# 图文发布
opub --platforms xiaohongshu --note --images img1.jpg,img2.jpg --title "标题"

# 图文转视频(用于视频号/百家号等不支持图文的平台)
opub --platforms tencent --note --images img1.jpg --convert-to-video --video-duration 5

# 定时 / 断点续传 / 强制重新生成
opub --platforms weibo --video demo.mp4 --schedule "2026-08-21 12:00" --start-from 2 --force
```

参数清单:

| 参数 | 类型/默认 | 说明 |
| --- | --- | --- |
| `--platforms` | 必填,逗号分隔 | 启用平台 |
| `--video` | 路径/目录 | 视频文件或目录 |
| `--note` | flag | 切换为图文模式(content_type=note) |
| `--images` | 逗号分隔路径 | 图文图片 |
| `--convert-to-video` | flag,默认 false | 图文转视频(仅 note 模式生效) |
| `--video-duration` | float,默认 5 | 图转视频每张图时长(秒) |
| `--title` / `--desc` / `--tags` | 字符串 | 内容元数据,留空走自动生成 |
| `--schedule` | `YYYY-MM-DD HH:MM` | 指定后本次为定时发布 |
| `--start-from` | int,默认 1 | 断点续传起始序号 |
| `--force` | flag | 强制重新生成视频配置 |

校验规则(退出码 10,CFG-xxx):

- 缺 `--platforms`:CFG-002,提示提供 --platforms
- `--video` 与(`--note` + `--images`)两者皆缺:CFG-001,提示提供 --video 或 --note --images
- note 模式缺 `--images`:CFG-004,提示提供 --images
- `--convert-to-video` 但缺 `--images`:CFG-004 同上
- `--video` 与 `--note` 同时给出:CFG-001,提示二者互斥,二选一

## 模块变更

### publish/config.py

- `PublishOverrides` 扩展字段:`note: bool`、`images: Optional[str]`(逗号分隔)、`convert_to_video: bool`、`video_duration: float`(默认 5)
- `default_params_from_overrides(overrides)` 成为唯一构建路径:从 overrides 构建完整 params dict,含 `_discover_account_files()` 自动发现
- 删除:`read_config`、`parse_config`、`reset_publish_task_fields`、`apply_overrides`(合并逻辑并入构建路径)
- `publish/constants.py` 删除 `PUBLISH_TASK_FIELD_DEFAULTS`,保留 `TITLE_LIMITS`

### publish/orchestrator.py

- `run_publish(overrides)` 签名去掉 `config_file`;`main()` 直接传 overrides
- 删除发布后 `reset_publish_task_fields` 的 finally 分支(opub 无状态化)
- `build_parser()`:删 `--config`,加 `--note/--images/--convert-to-video/--video-duration`,更新 prog description
- CFG-001/002/003/004 错误提示文案改为对应 CLI 参数指引(不再引用 ini 字段)

### 不动的部分

- `run_publish_with_params` 及下游 `params` dict 流(dispatch.py 五个平台分支、content.py)完全不动
- `douyin_config.ini`、`xiaohongshu_config.ini` 等平台级配置与本次无关,不动
- cookies 自动发现逻辑(`_discover_account_files`)不动,成为账号唯一来源

## 仓库文件与文档

- `git rm publish_config.ini`,并删除用户本地副本(已确认)
- `skills/opub-cli/SKILL.md`:删「配置文件位置」「publish_config.ini 关键字段」「一次性字段 vs 长期字段」三节;「调用」示例全改纯 CLI;frontmatter description 去掉 publish_config.ini 触发词;version 同步 0.6.0
- `AGENT.md`:删"Prefer publish_config.ini plus opub"及相关段落,重写为纯 CLI 用法
- `README.md`:删配置文件章节,重写快速开始为纯 CLI
- `CLAUDE.md`:Project Overview 中"platform, account, media... configured in publish_config.ini"改为通过 CLI 参数指定

## 测试

- `tests/test_publish_cli.py` 重写:删 `--config` 默认值断言,新增参数解析用例(note/images/convert-to-video/video_duration、互斥校验、必填校验)
- `tests/test_publish_engine.py` 重写:fixture 不再生成 ini,直接构造 overrides 走新入口
- 单测全过后跑一次真实 e2e(小红书,`opub --platforms xiaohongshu --video ...`),确认纯 CLI 路径端到端可用

## 发布

- pyproject/SKILL.md version bump 0.6.0
- e2e 验证通过后发 PyPI

## 明确不做

- 不做全链路 PublishSpec 类型化重构
- 不加每平台账号指定参数(自动发现够用)
- 不保留 config 兼容/过渡模式
- 不动平台级 config(douyin_config.ini 等)
