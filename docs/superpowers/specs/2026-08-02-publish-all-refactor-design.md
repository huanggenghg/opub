# publish_all.py 清洁架构重构设计

## 背景

`publish_all.py` 是 CLI 发布路径的核心,1225 行 god module,混杂 6 类职责:配置解析、运行时 preflight、内容生成、8 平台 dispatch、结果报告、流程编排。维护成本高:改一个平台 dispatch 可能碰到无关代码,新增字段要在多个不相关函数间跳。

用户主线工作流是 `python publish_all.py`(读 `publish_config.ini` -> 多平台批量发布),并以此形式提供给 AI agent 调用。`hgsau_cli.py` 作为独立 CLI 文件存在,但用户不用,且其 `publish` 子命令冗余(只有一个子命令)。

本 spec 是项目清洁架构重构的第一个子项目(sub-project A):拆分 `publish_all.py` 内部分层,合并 CLI 入口。后续 sub-project B(uploader 公共基类)、C(myUtils/utils 合并)、D(死代码清理)、E(配置约定统一)、F(前后端打通)各自独立 spec。

## 范围

**在范围内:**
- `publish_all.py`(1225 行)-> `publish/` 包(7 模块)+ 薄壳
- `hgsau_cli.py` 删除,argparse 合并进 `publish/orchestrator.py::main()`
- `pyproject.toml` 更新(`hgsau = "publish_all:main"`,从 `py-modules` 移除 `hgsau_cli`)
- `tests/test_hgsau_cli.py` 改写为 `tests/test_publish_cli.py`
- 新增 `tests/test_publish_dispatch.py` + `tests/test_publish_reporter.py`

**不在范围内(留给后续 spec):**
- `myUtils/` / `hgsau_backend.py` / `hgsau_frontend/` 完全不碰
- Uploader 公共基类抽取(sub-project B)
- 死代码清理:`probe_*.py`、`douyin/xiaohongshu_get_share_link.py`、`build/lib/`、旧 egg-info、`tk_uploader/main_chrome.py`、`baijiahao_uploader/main.py::ai2video`、`TencentNote` stub(sub-project D)
- Cookie 路径约定统一(sub-project E)
- `publish_config.ini` 格式变更
- `PublishOverrides` dataclass 字段变更
- 新异常分类体系
- JSON 输出 / `--keep-config` 等 agent 友好化旗标(后续 spec)

## 架构

### 模块结构

新建 `publish/` 包,7 个模块 + `__init__` + `publish_all.py` 薄壳:

| 模块 | 行数预估 | 拥有内容(从 publish_all.py 迁入) |
|---|---|---|
| `publish/__init__.py` | ~15 | re-export `run_publish` / `run_publish_sync` / `PublishOverrides` |
| `publish/constants.py` | ~40 | `PLATFORM_NAMES` / `TITLE_LIMITS` / `PUBLISH_TASK_FIELD_DEFAULTS` |
| `publish/config.py` | ~200 | `read_config` / `parse_config` / `apply_overrides` / `reset_publish_task_fields` / `default_params_from_overrides` / `_split_csv` / `_discover_account_files` |
| `publish/runtime.py` | ~100 | `runtime_preflight` / `patchright_available` / `playwright_browser_cache_dirs` / `patchright_chromium_installed` / `install_patchright_chromium` / `run_async_for_test` |
| `publish/content.py` | ~150 | `get_video_content` / `fill_empty_content` / `load_content_templates` / `get_video_files` / `truncate_title` / `resolve_path` |
| `publish/dispatch.py` | ~350 | 8 个 `publish_to_*` + `publish_to_platform` + `ensure_login` / `ensure_account_login` / `platform_requires_account_login` + `PlatformResult` TypedDict + `_PLATFORM_LOGIN` / `_PUBLISH_DISPATCH` 注册表 |
| `publish/reporter.py` | ~80 | `print_header` / `print_results` / `print_summary`(新增,从 `run_publish_with_params` 末尾抽出) |
| `publish/orchestrator.py` | ~190 | `run_publish` / `run_publish_with_params` / `publish_one_item` / `main`(含 argparse) |
| `publish_all.py` | ~15 | 薄壳:re-export 测试和外部依赖的所有名字 |

### 设计决策

- `publish_all.py` 保留为薄壳,re-export 所有测试依赖的名字(`run_publish` / `run_publish_sync` / `PublishOverrides` / `apply_overrides` / `reset_publish_task_fields` / `run_publish_with_params` / `publish_one_item` / `publish_to_douyin` / `runtime_preflight`)-- 向后兼容零破坏
- `constants.py` 单独抽出,打破 dispatch↔reporter 互相依赖 `PLATFORM_NAMES` 的循环
- `resolve_path` + `truncate_title` + `get_video_files` 放 `content.py` 而非 `config.py`,因为它们解析的是"要发什么内容",不是 INI 配置
- `reporter.py` 把现在藏在 `run_publish_with_params`(行 1154-1179)里的总体汇总和账号异常反馈抽出来,`orchestrator` 只负责流程串联

## 向后兼容边界

### 外部入口(合并后)

| 调用方 | 依赖 | 状态 |
|---|---|---|
| `python publish_all.py [--platforms ...] [--video ...] ...` | `publish_all.main`(含 argparse) | 新增 argparse 旗标 |
| `hgsau [--platforms ...] ...` | `publish_all:main` 控制台脚本 | 保留命令,去掉 `publish` 子命令,改指向 `publish_all:main` |
| `hgsau_cli.py` | - | **删除** |
| `tests/test_publish_engine.py` | `from publish_all import run_publish_sync / run_publish_with_params / apply_overrides / reset_publish_task_fields / publish_to_douyin / publish_one_item / runtime_preflight` | 全部 re-export,不破坏 |
| `publish_config.ini` 格式 | `[common]` + `[platforms]` | 不变 |
| `pyproject.toml` | `hgsau = "hgsau_cli:main"` | 改为 `hgsau = "publish_all:main"`,从 `py-modules` 删 `hgsau_cli` |

### CLI 合并理由

`hgsau_cli.py` 只做两件事 `publish_all.py` 没做的:argparse 覆盖旗标 + `hgsau` 控制台脚本入口。合并后:
- argparse 进 `publish/orchestrator.py::main()`
- `hgsau` 命令保留(用户确认 agent 在别处运行,项目以 `pip install` 部署,需要 PATH 里的命令)
- 去掉 `publish` 子命令(只有一个子命令,冗余)
- `python publish_all.py --platforms douyin --video x.mp4` 和 `hgsau --platforms douyin --video x.mp4` 走同一份代码

### 不动的边界

- `PublishOverrides` dataclass 字段(shape 锁定)
- `run_publish(config_file, overrides)` / `run_publish_sync` 签名
- cookie 路径约定(快手异常路径留给 sub-project E)
- `utils/excel_writer.write_video_link` 行为(baijiahao 发布后写 Excel 的副作用保留)
- `myUtils/` / `hgsau_backend.py` / `hgsau_frontend/` 完全不碰

## Dispatch 层

### PlatformResult TypedDict

当前 8 个 `publish_to_*` 返回 `dict`,字段不固定(`success`/`message` 必有,`share_link`/`video_link`/`account_issue`/`issue_type` 可选)。引入 TypedDict 让契约显式:

```python
class PlatformResult(TypedDict):
    success: bool
    message: str

class PlatformResultExtras(PlatformResult, total=False):
    share_link: str
    video_link: str
    account_issue: bool
    issue_type: str
```

每个 `publish_to_*` 返回 `PlatformResultExtras`;reporter 只读 `success`/`message`/`account_issue`。

### 合并 ensure_login 两份分发表

当前 `ensure_login`(行 532-584)有两份重复分发:`check_map` dict(8 条,cookie_auth 检查)+ if/elif 链(7 条,*_setup 触发)。合成一份注册表:

```python
_PLATFORM_LOGIN = {
    "douyin":      ("uploader.douyin_uploader.main",      "cookie_auth", "douyin_setup"),
    "xiaohongshu": ("uploader.xiaohongshu_uploader.main", "cookie_auth", "xiaohongshu_setup"),
    "kuaishou":    ("uploader.ks_uploader.main",          "cookie_auth", "ks_setup"),
    "tencent":     ("uploader.tencent_uploader.main",     "cookie_auth", "tencent_setup"),
    "baijiahao":   ("uploader.baijiahao_uploader.main",   "cookie_auth", "baijiahao_setup"),
    "bilibili":    ("uploader.bilibili_uploader.main",    "cookie_auth", "bilibili_setup"),
    "weibo":       ("uploader.weibo_uploader.main",       "cookie_auth", "weibo_setup"),
    # tk 不需要账号登录
}
```

`ensure_login` 从 ~50 行缩到 ~15 行;`platform_requires_account_login` 变成 `return platform in _PLATFORM_LOGIN`。

### publish_to_platform 用 dict 查表

```python
_PUBLISH_DISPATCH = {
    "douyin": publish_to_douyin,
    "xiaohongshu": publish_to_xiaohongshu,
    "kuaishou": publish_to_kuaishou,
    "tencent": publish_to_tencent,
    "baijiahao": publish_to_baijiahao,
    "bilibili": publish_to_bilibili,
    "weibo": publish_to_weibo,
}
# tk 走 stub 分支
```

加平台 = 加一行,不改 dispatcher 逻辑。

### 8 个 publish_to_* 保持独立

每个平台的 uploader 类名、构造参数(baijiahao 不收 `desc`/`publish_strategy`、bilibili 是函数不是类)、结果提取(xhs 取 `share_link`、baijiahao 取 `video_link` 还要写 Excel)、异常处理(douyin 捕获 `DouyinPublishRestrictedError`)都不同。强行合并会引入分支复杂度,得不偿失。这部分重复留到 sub-project B 抽 uploader 公共基类时自然解决。

## 数据流

```
publish_all.main()                          # 薄壳 -> orchestrator.main()
└─ orchestrator.main()                      # argparse 解析 -> PublishOverrides
   └─ orchestrator.run_publish(config, overrides)
      ├─ config.read_config() -> raw dict
      ├─ config.parse_config() -> params
      ├─ config.apply_overrides(params, overrides) -> merged params
      └─ orchestrator.run_publish_with_params(params)
         ├─ [if note+convert] content.convert_images_to_video() -> video_path
         ├─ content.get_video_files() -> [video_path, ...]
         ├─ runtime.runtime_preflight() -> bool
         └─ for each video:
            ├─ content.get_video_content(video, ...) -> (title, desc)
            └─ orchestrator.publish_one_item(video_params)
               ├─ reporter.print_header(params)
               ├─ for each platform:
               │  ├─ dispatch.ensure_account_login(platform, account_file) -> bool
               │  └─ dispatch.publish_to_platform(platform, params) -> PlatformResult
               └─ reporter.print_results(results)
         └─ reporter.print_summary(all_results)
      [finally] config.reset_publish_task_fields(config_path)
```

**关键约束:**
- 每层只调相邻层,不跨层(`orchestrator` 调 `config`/`runtime`/`content`/`dispatch`/`reporter`,后五者互不调用)
- `publish_one_item` 留在 `orchestrator.py`(它是流程串联,不是 dispatch 职责)
- 副作用边界清晰:`config` 只读写 INI,`runtime` 只装 chromium,`content` 只解析内容,`dispatch` 只调 uploader,`reporter` 只 print

## Reporter 与错误处理

### Reporter 抽取

当前 `run_publish_with_params`(行 1154-1179)末尾藏着总体汇总和账号异常反馈逻辑。抽到 `reporter.py`:

```python
def print_header(params: dict) -> None: ...           # 已存在,迁移
def print_results(results: dict) -> None: ...         # 已存在,迁移
def print_summary(all_results: dict) -> None: ...     # 新增,从 run_publish_with_params 抽出
```

`print_summary` 接收 `all_results: dict[video_file, dict[platform, PlatformResult]]`,负责:
- 成功/失败次数统计
- 账号异常反馈(聚合 `account_issue=True` 的失败,去重,提示用户检查账号)

`orchestrator.run_publish_with_params` 末尾缩成一行:`reporter.print_summary(all_results)`。

### 错误处理边界

| 层 | 错误处理 |
|---|---|
| `dispatch.publish_to_*` | try/except 包 `uploader.main()`,返回 `PlatformResult(success=False, message=str(e))`;特定异常(如 `DouyinPublishRestrictedError`)标 `account_issue=True` + `issue_type` |
| `dispatch.ensure_account_login` | 返回 bool,失败由 `publish_one_item` 跳过该平台 |
| `orchestrator.publish_one_item` | 单平台失败不中断,继续下个平台(已测试) |
| `orchestrator.run_publish_with_params` | 任意发布失败 -> 返回 1(已测试) |
| `runtime.runtime_preflight` | 失败返回 False,`run_publish_with_params` 返回 1 |
| `config` / `content` | 异常上抛,由 `run_publish` 或 `main` 兜底 print |

**不引入新异常分类**(当前 `account_issue` + `issue_type` 二字段够用;真要扩留到 sub-project B)。reporter 只负责呈现,不改错误语义。

## 测试策略

### 现有测试(零修改)

`tests/test_publish_engine.py`(427 行,4 测试类,16 用例)通过 `from publish_all import ...` 调用。`publish_all.py` 是薄壳 re-export 所有名字,这些测试不改一个字就继续通过 -- 这是回归安全网。

### 改写

`tests/test_hgsau_cli.py`(110 行)当前测 `hgsau publish` 子命令。合并后子命令没了,改写为测 `publish_all.main` 的新 argparse surface(`--platforms` / `--video` / `--schedule` 等),并改名为 `tests/test_publish_cli.py` 跟新模块对齐。

### 新增

| 测试文件 | 测什么 |
|---|---|
| `tests/test_publish_dispatch.py` | `_PLATFORM_LOGIN` 覆盖 8 个平台(防漂移);`_PUBLISH_DISPATCH` 覆盖所有 enabled 平台;`ensure_login` 合并 check+setup 逻辑(mock 两侧) |
| `tests/test_publish_reporter.py` | `print_summary` 聚合 `account_issue` 去重正确;成功/失败计数正确 |

### 不新增的

- `config.py` / `runtime.py` / `content.py` 的单元测试 -- 已被 `test_publish_engine.py` 通过公共 API 覆盖
- 端到端发布测试 -- 当前就没有,本 spec 不引入
- 薄壳 re-export smoke test -- `test_publish_engine.py` 的 import 已经是 smoke test,漏名字会立刻挂

## 死代码处理

### 本 spec 范围内清理

- `hgsau_cli.py` 删除(CLI 合并)
- `pyproject.toml` 的 `py-modules` 移除 `hgsau_cli`,`[project.scripts]` 改 `hgsau = "publish_all:main"`

### 留给 sub-project D(不在本 spec)

| 文件 | 状态 | 不动原因 |
|---|---|---|
| `probe_ks_*.py` ×3, `probe_tencent_*.py` ×2 | Aug 2 新建的调试探针 | 用户可能在活跃用 |
| `douyin_get_share_link.py`, `xiaohongshu_get_share_link.py` | 逻辑已在 uploader 内 | 跟 publish_all 无关 |
| `build/lib/`, 旧 egg-info | 构建残留 | 需确认 gitignore 状态 |
| `tk_uploader/main_chrome.py`, `baijiahao_uploader/main.py::ai2video`, `TencentNote` | 未用/不可达/stub | 需逐个确认 |

## 迁移顺序

实现时按此顺序走,每步后跑测试确保不破:

1. 创建 `publish/` 包空模块 + `__init__.py`
2. 按 §架构表格迁移函数到对应模块(保持函数体不动,只搬位置)
3. `publish_all.py` 改为薄壳 re-export
4. 跑 `tests/test_publish_engine.py` 确认全绿(回归安全网生效)
5. argparse 从 `hgsau_cli.py` 迁到 `publish/orchestrator.py::main()`
6. 删 `hgsau_cli.py`,改 `pyproject.toml`
7. 改写 `tests/test_hgsau_cli.py` -> `tests/test_publish_cli.py`
8. 新增 `tests/test_publish_dispatch.py` + `tests/test_publish_reporter.py`
9. 合并 `ensure_login` 两份分发表为 `_PLATFORM_LOGIN` 注册表
10. `publish_to_platform` if/elif -> dict 查表
11. 抽 `reporter.print_summary`
12. 跑全量测试 + `python publish_all.py --help` + 一次真实发布验证

## 验证标准

- `pytest tests/` 全绿
- `python publish_all.py --help` 显示新 argparse
- `hgsau --help` 显示新 argparse(去掉 `publish` 子命令)
- `python publish_all.py`(无参)读 `publish_config.ini` 跑一次,行为与重构前一致
