# 去掉 publish_config.ini 依赖(CLI 唯一入口)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 硬删除 `publish_config.ini` 配置文件模式,`opub` 变为纯 CLI 参数、无状态的多平台发布命令。

**Architecture:** 把 `PublishOverrides` 扩展为唯一参数源(新增 note/images/convert_to_video/video_duration 字段),`default_params_from_overrides(overrides)` 成为唯一 params 构建路径;`run_publish(overrides)` 去掉 config_file 参数并前置校验;删除 read_config/parse_config/reset_publish_task_fields/apply_overrides 全套 config 逻辑。下游 `params` dict 流(dispatch/content)完全不动。

**Tech Stack:** Python 3.9+, argparse, unittest(现有测试体系)

**Spec:** `docs/superpowers/specs/2026-08-20-drop-publish-config-design.md`

## Global Constraints

- CLI 必填项:`--platforms`;素材二选一:`--video` 或 `--note` + `--images`;`--note` 与 `--video` 互斥(CFG-001)
- 图转视频参数:`--convert-to-video`(flag,默认 false)、`--video-duration`(float,默认 5),仅 note 模式生效
- 错误码与退出码体系不变(CFG/ENV/AUTH/PUB/RUN,10/11/12/0/1/2),仅提示文案从 ini 指引改为 CLI 参数指引
- `--config` 参数删除,`publish_config.ini` 从版本库和本地删除
- 账号文件纯自动发现(`cookies/` 目录扫描),不加每平台 account 参数
- 不做全链路 PublishSpec 类型化重构,不动 `douyin_config.ini`/`xiaohongshu_config.ini` 等平台级配置
- 版本 bump 0.5.2 -> 0.6.0(破坏性变更)
- 文档中文优先;本项目禁止截图定位 UI、禁止非文本文件调大模型 API(与本次改动无关,但为项目硬约束)

---

### Task 1: config 层 — PublishOverrides 扩展与唯一构建路径

**Files:**
- Modify: `publish/config.py`
- Modify: `tests/test_publish_engine.py`(重写 2 个用例)
- 不动: `publish/orchestrator.py`(Task 2 处理,本任务结束时 read_config 等仍存在且可用)

**Interfaces:**
- Produces: `PublishOverrides` 新字段 `note: bool = False`、`images: Optional[str] = None`、`convert_to_video: bool = False`、`video_duration: float = 5.0`;`default_params_from_overrides(overrides: Optional[PublishOverrides] = None) -> Dict[str, Any]`(签名从无参改为可选单参)
- Consumes: 无(原有 `_split_csv`、`_discover_account_files` 继续使用)

- [ ] **Step 1: 写失败测试(重写 test_publish_engine.py 中两个 config 用例)**

在 `tests/test_publish_engine.py` 中,删除 `test_reset_publish_task_fields_clears_one_time_fields_and_keeps_accounts` 和 `test_apply_overrides_merges_publish_fields` 两个用例(后续任务再删 reset 函数本体),原地加入:

```python
    def test_default_params_from_overrides_builds_full_params(self):
        publish_time = publish_all.datetime.strptime("2026-05-30 21:30", "%Y-%m-%d %H:%M")
        overrides = publish_all.PublishOverrides(
            platforms="douyin,weibo",
            video="videos/demo.mp4",
            title="标题",
            desc="描述",
            tags="标签1,标签2",
            schedule=publish_time,
            start_from=3,
            force=True,
        )

        params = publish_all.default_params_from_overrides(overrides)

        self.assertEqual(params["content_type"], "video")
        self.assertEqual(params["enabled_platforms"], ["douyin", "weibo"])
        self.assertEqual(params["video_file"], "videos/demo.mp4")
        self.assertEqual(params["title"], "标题")
        self.assertEqual(params["desc"], "描述")
        self.assertEqual(params["tags"], ["标签1", "标签2"])
        self.assertEqual(params["publish_strategy"], "scheduled")
        self.assertEqual(params["publish_time"], publish_time)
        self.assertEqual(params["start_from"], 3)
        self.assertTrue(params["force"])
        self.assertFalse(params["convert_to_video"])
        self.assertEqual(params["video_duration"], 5)

    def test_default_params_from_overrides_note_mode(self):
        overrides = publish_all.PublishOverrides(
            platforms="xiaohongshu",
            note=True,
            images="images/a.png, images/b.png",
            convert_to_video=True,
            video_duration=8,
        )

        params = publish_all.default_params_from_overrides(overrides)

        self.assertEqual(params["content_type"], "note")
        self.assertEqual(params["images"], ["images/a.png", "images/b.png"])
        self.assertEqual(params["video_file"], "")
        self.assertTrue(params["convert_to_video"])
        self.assertEqual(params["video_duration"], 8)
        self.assertEqual(params["publish_strategy"], "immediate")
        self.assertIsNone(params["publish_time"])

    def test_default_params_from_overrides_without_overrides_uses_defaults(self):
        params = publish_all.default_params_from_overrides()

        self.assertEqual(params["content_type"], "video")
        self.assertEqual(params["enabled_platforms"], [])
        self.assertEqual(params["video_file"], "")
        self.assertEqual(params["start_from"], 1)
        self.assertFalse(params["convert_to_video"])
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_publish_engine -v 2>&1 | tail -20`
Expected: FAIL/ERROR,`unexpected keyword argument 'note'`(`PublishOverrides` 尚无新字段)或 `default_params_from_overrides() takes 0 positional arguments`

- [ ] **Step 3: 实现 — 扩展 PublishOverrides 并改造构建函数**

`publish/config.py` 中:

3a. `PublishOverrides` dataclass 追加 4 个字段(在 `force` 之后):

```python
@dataclass
class PublishOverrides:
    platforms: Optional[str] = None
    video: Optional[str] = None
    title: Optional[str] = None
    desc: Optional[str] = None
    tags: Optional[str] = None
    schedule: Optional[datetime] = None
    start_from: Optional[int] = None
    force: bool = False
    note: bool = False
    images: Optional[str] = None
    convert_to_video: bool = False
    video_duration: float = 5.0
```

3b. `default_params_from_overrides()` 整体替换为:

```python
def default_params_from_overrides(overrides: Optional[PublishOverrides] = None) -> Dict[str, Any]:
    overrides = overrides or PublishOverrides()
    params: Dict[str, Any] = {
        "content_type": "note" if overrides.note else "video",
        "title": overrides.title or "",
        "desc": overrides.desc or "",
        "tags": _split_csv(overrides.tags),
        "video_file": overrides.video or "",
        "images": _split_csv(overrides.images),
        "publish_strategy": "scheduled" if overrides.schedule else "immediate",
        "publish_time": overrides.schedule,
        "enabled_platforms": _split_csv(overrides.platforms),
        "platforms": _discover_account_files(),
        "convert_to_video": overrides.convert_to_video,
        "video_duration": overrides.video_duration,
        "start_from": overrides.start_from if overrides.start_from else 1,
    }
    if overrides.force:
        params["force"] = True
    return params
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m unittest tests.test_publish_engine tests.test_publish_cli -v 2>&1 | tail -10`
Expected: 全部 PASS(cli 测试中 `default_params_from_overrides()` 无参调用仍兼容)

- [ ] **Step 5: Commit**

```bash
git add publish/config.py tests/test_publish_engine.py
git commit -m "feat(config): PublishOverrides gains note/images/convert_to_video fields, becomes sole params source"
```

---

### Task 2: orchestrator — 切换纯 overrides 入口,删除 config 读取逻辑

**Files:**
- Modify: `publish/orchestrator.py:14-19`(imports)、`:228-264`(run_publish/run_publish_sync)、`:279-297`(build_parser 描述、main)
- Modify: `publish/config.py`(删除 4 个函数)
- Modify: `publish/constants.py`(删除 PUBLISH_TASK_FIELD_DEFAULTS)
- Modify: `publish_all.py:18-38`(imports)
- Modify: `tests/test_publish_engine.py`(删 3 个 config 用例,加 4 个校验用例)
- Modify: `tests/test_publish_cli.py:75-83`(main 用例)

**Interfaces:**
- Consumes: Task 1 的 `default_params_from_overrides(overrides)`、扩展后的 `PublishOverrides`
- Produces: `run_publish(overrides: Optional[PublishOverrides] = None) -> int`、`run_publish_sync(overrides: Optional[PublishOverrides] = None) -> int`(config_file 参数消失,`publish/__init__.py` 的 re-export 签名随之变化但无需改文件)

- [ ] **Step 1: 写失败测试**

`tests/test_publish_engine.py`:删除 `test_run_publish_sync_returns_config_error_when_config_has_no_enabled_platforms`、`test_run_publish_sync_resets_task_fields_after_config_run`、`test_run_publish_sync_uses_cli_overrides_without_config_file` 三个用例,加入:

```python
class RunPublishValidationTests(unittest.TestCase):
    def _stderr_code(self, overrides):
        import contextlib, io
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = publish_all.run_publish_sync(overrides)
        return code, stderr.getvalue()

    def test_missing_platforms_returns_config_error(self):
        code, stderr = self._stderr_code(publish_all.PublishOverrides(video="videos/demo.mp4"))
        self.assertEqual(code, 10)
        self.assertIn("CFG-002", stderr)

    def test_missing_video_and_note_returns_config_error(self):
        code, stderr = self._stderr_code(publish_all.PublishOverrides(platforms="weibo"))
        self.assertEqual(code, 10)
        self.assertIn("CFG-001", stderr)

    def test_note_with_video_returns_config_error(self):
        code, stderr = self._stderr_code(
            publish_all.PublishOverrides(platforms="weibo", video="v.mp4", note=True, images="a.png")
        )
        self.assertEqual(code, 10)
        self.assertIn("CFG-001", stderr)

    def test_run_publish_builds_params_and_calls_engine(self):
        overrides = publish_all.PublishOverrides(
            platforms="weibo", video="videos/demo.mp4", title="标题"
        )
        with patch("publish.orchestrator.run_publish_with_params", new=AsyncMock(return_value=0)) as run_params:
            code = publish_all.run_publish_sync(overrides)

        self.assertEqual(code, 0)
        params = run_params.await_args.args[0]
        self.assertEqual(params["enabled_platforms"], ["weibo"])
        self.assertEqual(params["video_file"], "videos/demo.mp4")
        self.assertEqual(params["title"], "标题")
```

`tests/test_publish_cli.py` 中 `test_main_calls_run_publish_with_overrides` 整体替换为:

```python
    def test_main_calls_run_publish_with_overrides(self):
        with patch("publish.orchestrator.run_publish", new=AsyncMock(return_value=0)) as run_publish:
            code = publish_all.main(["--platforms", "weibo", "--title", "标题"])

        self.assertEqual(code, 0)
        overrides = run_publish.await_args.args[0]
        self.assertEqual(overrides.platforms, "weibo")
        self.assertEqual(overrides.title, "标题")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_publish_engine tests.test_publish_cli -v 2>&1 | tail -20`
Expected: 新校验用例 FAIL(`run_publish_sync() missing...` 或走旧 config 分支报 CFG-001 文件不存在)

- [ ] **Step 3: 实现 orchestrator 切换**

3a. `publish/orchestrator.py` imports(第 14-19 行)改为只留两项:

```python
from publish.config import (
    PublishOverrides,
    default_params_from_overrides,
)
```

3b. `run_publish` / `run_publish_sync`(原 228-264 行)整体替换:

```python
async def run_publish(overrides: Optional[PublishOverrides] = None) -> int:
    overrides = overrides or PublishOverrides()

    if not overrides.platforms:
        print_error("CFG-002", "未指定启用平台", "提供 --platforms，逗号分隔平台标识（见 opub --help）")
        return EXIT_CONFIG_ERROR
    if overrides.note and overrides.video:
        print_error("CFG-001", "--note 与 --video 互斥", "二选一：图文用 --note --images，视频用 --video")
        return EXIT_CONFIG_ERROR
    if not overrides.note and not overrides.video:
        print_error("CFG-001", "缺少发布素材", "提供 --video（视频发布）或 --note --images（图文发布）")
        return EXIT_CONFIG_ERROR

    params = default_params_from_overrides(overrides)
    return await run_publish_with_params(params)


def run_publish_sync(overrides: Optional[PublishOverrides] = None) -> int:
    return asyncio.run(run_publish(overrides))
```

3c. `main()` 中的调用改为 `return asyncio.run(run_publish(_build_overrides(args)))`(去掉 `args.config` 实参)。

3d. `run_publish_with_params` 内 3 处错误文案改为 CLI 指引(逻辑不动):
- CFG-002 行:"未配置启用平台" 建议改为 `"提供 --platforms，逗号分隔平台标识"`
- 两处 CFG-004 行:建议改为 `"提供 --images 设置图片路径（英文逗号分隔）"`
- CFG-003 行:建议改为 `"检查 --video 路径是否正确"`

- [ ] **Step 4: 删除 config 死代码**

- `publish/config.py`:删除 `read_config`、`reset_publish_task_fields`、`apply_overrides`、`parse_config` 四个函数;顶部 `import configparser`、`import os`、`import re`、`from publish.constants import PUBLISH_TASK_FIELD_DEFAULTS, TITLE_LIMITS` 一并删除(删完后确认无残留引用);模块 docstring 改为 `"""发布参数构建:PublishOverrides 是唯一参数源,cookies/ 账号自动发现"""`
- `publish/constants.py`:删除 `PUBLISH_TASK_FIELD_DEFAULTS` 整块
- `publish_all.py`:从 `publish.config` import 中删掉 `apply_overrides`、`parse_config`、`read_config`、`reset_publish_task_fields`;从 `publish.constants` import 中删掉 `PUBLISH_TASK_FIELD_DEFAULTS`

- [ ] **Step 5: 运行全量测试确认通过**

Run: `python -m unittest discover -s tests -v 2>&1 | tail -10`
Expected: 全部 PASS(config 相关旧用例已在本任务删除,`test_help_documents_ini_field_mapping` 仍通过——帮助文案 Task 3 才改)

- [ ] **Step 6: Commit**

```bash
git add publish/orchestrator.py publish/config.py publish/constants.py publish_all.py tests/test_publish_engine.py tests/test_publish_cli.py
git commit -m "feat(orchestrator): CLI-only entry, drop publish_config.ini reading and field reset"
```

---

### Task 3: CLI 参数面 — 新参数与帮助文案

**Files:**
- Modify: `publish/orchestrator.py:271-317`(build_parser、_build_overrides)
- Modify: `tests/test_publish_cli.py`(parser 用例重写)

**Interfaces:**
- Consumes: Task 1/2 的 `PublishOverrides` 字段
- Produces: argparse 参数 `--note`(dest `note`)、`--images`(dest `images`)、`--convert-to-video`(dest `convert_to_video`)、`--video-duration`(dest `video_duration`,type=float default=5);`--config` 不复存在

- [ ] **Step 1: 写失败测试**

`tests/test_publish_cli.py`:

1a. `test_parser_accepts_defaults_no_subcommand` 替换为:

```python
    def test_parser_defaults(self):
        parser = publish_all.build_parser()
        args = parser.parse_args([])

        self.assertFalse(hasattr(args, "config"))
        self.assertIsNone(args.platforms)
        self.assertIsNone(args.video)
        self.assertIsNone(args.images)
        self.assertFalse(args.note)
        self.assertFalse(args.convert_to_video)
        self.assertEqual(args.video_duration, 5)
```

1b. `test_parser_accepts_overrides` 中删掉 `"--config", "my.ini",` 两行和 `self.assertEqual(args.config, "my.ini")` 断言。

1c. 新增:

```python
    def test_parser_accepts_note_mode_args(self):
        parser = publish_all.build_parser()
        args = parser.parse_args(
            [
                "--platforms", "xiaohongshu",
                "--note",
                "--images", "images/a.png,images/b.png",
                "--convert-to-video",
                "--video-duration", "8",
            ]
        )

        self.assertTrue(args.note)
        self.assertEqual(args.images, "images/a.png,images/b.png")
        self.assertTrue(args.convert_to_video)
        self.assertEqual(args.video_duration, 8)

    def test_parser_rejects_config_flag(self):
        parser = publish_all.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["--config", "my.ini"])
```

1d. `test_help_documents_ini_field_mapping` 替换为:

```python
    def test_help_documents_cli_surface(self):
        help_text = publish_all.build_parser().format_help()
        for fragment in ["--platforms", "--video", "--note", "--images", "--convert-to-video", "--video-duration", "--schedule"]:
            self.assertIn(fragment, help_text)
        self.assertNotIn("publish_config.ini", help_text)
        self.assertNotIn("[common]", help_text)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m unittest tests.test_publish_cli -v 2>&1 | tail -20`
Expected: 新用例 FAIL(`--config` 仍存在、`--note` 等不存在)

- [ ] **Step 3: 实现 build_parser 与 _build_overrides**

`build_parser()` 中:

- `description` 改为 `"把视频/图文一键发布到抖音/小红书/快手/微博/B站/视频号/百家号。必填 --platforms，素材提供 --video（视频）或 --note --images（图文）。"`
- 删除 `--config` 一行
- 各参数 help 去掉 ini 映射文案,按此改写/新增(顺序即此):

```python
    parser.add_argument("--platforms", default=None, help="启用的平台，逗号分隔（必填）")
    parser.add_argument("--video", default=None, help="视频文件或目录路径")
    parser.add_argument("--note", action="store_true", help="图文模式：以 --images 的图片发布图文")
    parser.add_argument("--images", default=None, help="图文图片路径，逗号分隔（图文模式必填）")
    parser.add_argument("--convert-to-video", action="store_true", help="图文转视频后发布（仅 --note 模式生效）")
    parser.add_argument("--video-duration", type=float, default=5, help="图转视频每张图片时长（秒，默认 5）")
    parser.add_argument("--title", default=None, help="标题（留空则自动生成）")
    parser.add_argument("--desc", default=None, help="描述（留空则自动生成）")
    parser.add_argument("--tags", default=None, help="话题标签，逗号分隔")
    parser.add_argument("--schedule", type=_schedule_value, default=None, help=f"定时发布时间，格式 {schedule_help}")
    parser.add_argument("--start-from", type=int, default=None, help="断点续传起始序号，1 起")
    parser.add_argument("--force", action="store_true", help="强制重新生成视频配置")
```

`_build_overrides()` 追加四个字段:

```python
def _build_overrides(args: argparse.Namespace) -> PublishOverrides:
    return PublishOverrides(
        platforms=args.platforms,
        video=args.video,
        title=args.title,
        desc=args.desc,
        tags=args.tags,
        schedule=args.schedule,
        start_from=args.start_from,
        force=args.force,
        note=args.note,
        images=args.images,
        convert_to_video=args.convert_to_video,
        video_duration=args.video_duration,
    )
```

- [ ] **Step 4: 运行全量测试确认通过**

Run: `python -m unittest discover -s tests -v 2>&1 | tail -10`
Expected: 全部 PASS

- [ ] **Step 5: 手工冒烟**

Run: `opub --help && opub`(无参数)
Expected: help 显示新参数面;无参数运行 stderr 输出 CFG-001 缺素材提示、退出码 10

- [ ] **Step 6: Commit**

```bash
git add publish/orchestrator.py tests/test_publish_cli.py
git commit -m "feat(cli): add --note/--images/--convert-to-video/--video-duration, drop --config"
```

---

### Task 4: 文档契约与仓库清理

**Files:**
- Modify: `skills/opub-cli/SKILL.md`
- Modify: `AGENT.md`
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `pyproject.toml`(version)
- Delete: `publish_config.ini`(git rm,同时删除本地副本——用户已确认)
- Test: `tests/test_publish_cli.py` 的 `SkillDocBlackboxTests`(现有用例,改文案后须仍通过)

**Interfaces:**
- Consumes: Task 3 的最终 CLI 参数面
- Produces: SKILL.md version "0.6.0"、pyproject version = "0.6.0"

- [ ] **Step 1: 重写 SKILL.md 相关章节**

`skills/opub-cli/SKILL.md`:

- frontmatter `version: "0.5.2"` -> `"0.6.0"`;`description` 中 "配置多平台发布、发布到..." 保留,删掉 "publish_config.ini" 字样与 "配置" 触发词中的文件引用(改为 "调用 opub CLI")
- 删除整节:「配置」(含「配置文件位置」「publish_config.ini 关键字段」「一次性字段 vs 长期字段」三个小节)
- 「触发场景」中 "排查 `opub`、`publish_config.ini`、Chromium..." 改为 "排查 `opub`、Chromium..."
- 「调用」节整体替换为:

```markdown
## 调用

`opub` 是无状态命令,每次发布的全部信息通过命令行参数传入:

```bash
# 视频发布(必填:--platforms + --video)
opub --platforms douyin,weibo --video videos/demo.mp4 --title "标题" --tags "标签1,标签2"

# 图文发布
opub --platforms xiaohongshu --note --images img1.jpg,img2.jpg --title "标题"

# 图文转视频(视频号/百家号等不支持图文的平台)
opub --platforms tencent --note --images img1.jpg --convert-to-video --video-duration 5

# 定时 / 断点续传 / 强制重新生成
opub --platforms weibo --video videos/demo.mp4 --schedule "2026-08-21 12:00" --start-from 2 --force

opub --version                        # 查看已安装版本
opub --help                           # 全部参数说明
```

参数说明:`--title`/`--desc` 留空时自动生成;`--schedule` 指定后本次为定时发布;账号文件从数据目录 `cookies/` 自动发现(微博支持多账号,每个账号各发一遍),无需配置。
```

- 「Agent 注意事项」不动

- [ ] **Step 2: 更新 AGENT.md / README.md / CLAUDE.md**

- `AGENT.md:23` "Prefer `publish_config.ini` plus `opub` over legacy example scripts" 改为 "Prefer `opub` CLI over legacy example scripts"
- `AGENT.md:77-102`:删掉 publish_config.ini 相关段落(配置文件说明、"编辑 publish_config.ini" 步骤、config 相关提示),保留纯 CLI 调用示例与 `opub --help`
- `README.md:43-56`:快速开始的"编辑 publish_config.ini"步骤删掉,重写为 Task 4 Step 1 同款 CLI 示例;删掉"publish_config.ini 是主要控制文件…"整段,替换为一句:"`opub` 是无状态命令,全部配置通过命令行参数传入,账号文件从 `cookies/` 目录自动发现。"
- `CLAUDE.md` Project Overview 末段 "Platform, account, media, metadata, and schedule settings should be configured in `publish_config.ini`." 改为 "Platform, account, media, metadata, and schedule settings are passed as command-line arguments (`opub --platforms ... --video ...`); account files are auto-discovered from the `cookies/` directory."
- `CLAUDE.md` Command-line Interface 节 "Temporary overrides are allowed for one publish run" 改为 "All settings are provided as CLI arguments for each run"

- [ ] **Step 3: 删除配置文件并 bump 版本**

```bash
git rm publish_config.ini
```

(该文件同时是用户本地副本,git rm 即物理删除;执行前用 `ls publish_config.ini` 确认存在。)

`pyproject.toml`:`version = "0.5.2"` -> `version = "0.6.0"`

- [ ] **Step 4: 运行全量测试确认通过(含 SkillDocBlackboxTests)**

Run: `python -m unittest discover -s tests -v 2>&1 | tail -10`
Expected: 全部 PASS(SKILL.md 不含 "publish_all"、"pyproject.toml" 等禁词——注意新文案别引入)

- [ ] **Step 5: Commit**

```bash
git add skills/opub-cli/SKILL.md AGENT.md README.md CLAUDE.md pyproject.toml
git commit -m "docs!: CLI-only contract, remove publish_config.ini, bump 0.6.0"
```

---

### Task 5: 回归验证、真实 e2e 与发版

**Files:**
- 无代码改动;产出验证记录与 PyPI 发布

**Interfaces:**
- Consumes: 前四个任务的完整 CLI 面

- [ ] **Step 1: 全量测试**

Run: `python -m unittest discover -s tests -v 2>&1 | tail -10`
Expected: 全部 PASS

- [ ] **Step 2: 真实 e2e(小红书,流程历史上已验证)**

先与用户确认可以真实发布,然后:

```bash
opub --platforms xiaohongshu --video videos/demo.mp4 --title "opub 0.6.0 纯CLI验证"
```

Expected: 退出码 0,输出含 "✅ 成功" 与分享链接。若账号需扫码,引导用户扫码后重试。

- [ ] **Step 3: 发 PyPI(需用户确认后执行)**

发版凭据在 `.secrets/`(项目惯例,直接执行 twine,不让用户跑命令):

```bash
rm -rf dist && python -m build && twine upload dist/* 
```

(token 按 `.secrets/` 目录实际内容取正式 PyPI token;上传后 `pip index versions opub` 或 PyPI 页面确认 0.6.0。)

- [ ] **Step 4: 收尾**

- 确认本地 `publish_config.ini` 已不存在(`ls publish_config.ini` 应报 No such file)
- 向用户汇报:e2e 结果、发布链接、版本号

---

## Self-Review 记录

- Spec 覆盖:CLI 契约(Task 3)、config 层(Task 1/2)、orchestrator(Task 2)、文档与文件删除(Task 4)、测试(Task 1-4 内嵌)、e2e 与发版(Task 5)、"明确不做"均未违反 ✓
- 占位符扫描:无 TBD/TODO;所有代码步骤含完整代码 ✓
- 类型一致性:`PublishOverrides` 字段名(note/images/convert_to_video/video_duration)在 Task 1 定义,Task 3 `_build_overrides` 使用一致;`default_params_from_overrides(overrides)` 签名 Task 1 定义、Task 2 调用一致;argparse dest 命名(`--convert-to-video` -> `convert_to_video`)与字段一致 ✓
