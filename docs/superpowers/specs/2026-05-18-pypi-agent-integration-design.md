# PyPI 包改进设计：Agent 零配置 CLI 集成

## 目标

让 AI Agent 通过 `pip install hgeng-sau` 后直接使用 CLI，零配置即可登录和上传视频到多平台。

核心流程：**选平台 → 选视频 → 填标题描述 → 发布（自动检查登录，未登录则触发登录）**

## 当前阻断问题

| 问题 | 严重性 | 说明 |
|------|--------|------|
| `conf.py` 不存在 | Critical | pip install 后没有此模块，所有 import 崩溃 |
| `BASE_DIR` 指向 site-packages | Critical | `Path(__file__).parent` 在 pip 安装后指向错误目录 |
| cookies 路径错误 | Critical | 基于 BASE_DIR 拼接，找不到 cookies |
| 缺少依赖 | High | `zhipuai`、`xhs` 未在 pyproject.toml 声明 |
| Skill 文档错误 | High | 写的 `playwright install` 但实际用 `patchright` |
| Python 版本限制 | Medium | `>=3.10` 可放宽到 `>=3.9`，覆盖更多 agent 环境 |
| 发布时无自动登录 | Medium | cookie 失效直接报错，需手动重新登录 |

## 改动 1：conf.py 改造 — 路径解析与配置加载

**现状**：`conf.py` 是用户手动从 `conf.example.py` 复制创建的，包含硬编码的 `BASE_DIR`、API key 等。pip install 后不存在。

**改造后**：`conf.py` 变成自动计算的配置模块，无需用户手动创建。

```python
from pathlib import Path
import os

_PROJECT_ROOT = Path(__file__).parent.resolve()

def _detect_mode() -> Path:
    """开发模式：项目根有 uploader/ 目录 → BASE_DIR = 项目根
       pip 模式：→ BASE_DIR = ~/.social-auto-upload/"""
    if (_PROJECT_ROOT / "uploader").is_dir():
        return _PROJECT_ROOT
    return Path(os.environ.get("SAU_HOME", Path.home() / ".social-auto-upload"))

BASE_DIR = _detect_mode()

# 首次运行自动创建目录
if not BASE_DIR.exists():
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "cookies").mkdir(exist_ok=True)

# 可选配置：从 config.json 读取，没有则为默认值
def _load_config():
    config_path = BASE_DIR / "config.json"
    if config_path.exists():
        import json
        with open(config_path) as f:
            return json.load(f)
    return {}

_config = _load_config()

LOCAL_CHROME_HEADLESS = _config.get("chrome_headless", True)
LOCAL_CHROME_PATH = _config.get("chrome_path", "")
DEBUG_MODE = _config.get("debug", False)
ZHIPU_API_KEY = _config.get("zhipu_api_key", "")
ZHIPU_VISION_MODEL = _config.get("zhipu_vision_model", "glm-4v-plus")
XHS_SERVER = _config.get("xhs_server", "")
```

**关键点**：
- 开发模式下行为完全不变（`BASE_DIR` 仍指向项目根）
- pip 模式下自动使用 `~/.social-auto-upload/`，首次运行自动创建目录
- `config.json` 是可选的，没有也能跑（登录、上传不需要 API key）
- 环境变量 `SAU_HOME` 可覆盖路径
- 其他模块的 `from conf import BASE_DIR` 完全不用改

## 改动 2：数据目录结构

pip install 后首次运行 `sau` 时，自动创建 `~/.social-auto-upload/` 目录结构：

```
~/.social-auto-upload/
├── config.json          # 可选，用户配置（API key 等）
├── cookies/             # 登录后自动生成
│   ├── weibo_uploader/
│   │   └── account.json
│   ├── douyin_uploader/
│   │   └── account.json
│   └── ...
├── templates/           # 可选，内容模板
│   └── content_templates.json
└── videos/              # 可选，默认视频目录
```

初始化逻辑在 `conf.py` 中 `BASE_DIR` 解析后执行，目录不存在则自动 `mkdir -p`。`config.json` 不存在时用空默认值。

## 改动 3：Python 版本放宽到 >=3.9

受 `patchright` 约束（`Requires-Python: >=3.9`），下限为 3.9。

需要修改的代码：

| 改动 | 文件 | 工作量 |
|------|------|--------|
| `match/case` → `if/elif/else` | `myUtils/auth.py` | 6 行 |
| 去掉 `@dataclass(slots=True)` 的 `slots=True` | `sau_cli.py` | 7 处 |
| 补 `from __future__ import annotations` | `uploader/douyin_uploader/main.py`, `utils/login_qrcode.py` | 2 处 |
| dataclass 字段 `X \| Y` → `Optional[X]` | `sau_cli.py` | 10 处字段 |

`pyproject.toml` 改为 `requires-python = ">=3.9"`。

## 改动 4：依赖补全

```toml
dependencies = [
    # 核心依赖 — 登录、上传、发布必须
    "loguru>=0.7.3",
    "patchright>=1.52.0",
    "qrcode>=8.0",
    "requests>=2.32",
    "segno>=1.6.6",
    "xhs>=0.2.13",
    "pillow>=10.0",
    "opencv-python>=4.13.0",
]

[project.optional-dependencies]
analyze = ["zhipuai>=2.0.0"]   # sau generate 需要
web = ["Flask[async]>=3.1", "flask-cors>=6.0"]  # Web UI 需要
```

**原则**：`pip install hgeng-sau` 只装核心依赖，登录和上传即可工作。视频分析通过 `pip install hgeng-sau[analyze]` 按需安装。

## 改动 5：新增 `sau status` 命令

环境预检查命令，Agent 执行发布前先调此命令了解环境状态：

```bash
$ sau status
Python: 3.13.2 ✓
Browser: patchright chromium installed ✓
Config: ~/.social-auto-upload/config.json (not found, using defaults)
Cookies:
  weibo: no accounts
  kuaishou: no accounts
  douyin: no accounts
Platforms ready: none (login required)
```

实现位置：`sau_cli.py` 的 `dispatch()` 函数中新增 `status` 分支。

## 改动 6：新增 `sau login` 统一入口

语法糖，等价于 `sau <platform> login`：

```bash
sau login --platform weibo --account myaccount
# 等价于
sau weibo login --account myaccount
```

实现位置：`sau_cli.py` 的 `dispatch()` 函数中新增 `login` 分支，路由到对应平台的 login 函数。

## 改动 7：发布流程自动串联 check → login → publish

在 `publish_all.py` 的 `publish_to_platform()` 中，发布前自动检查 cookie 有效性：

```
publish_to_platform()
  → 调用平台 check 方法
  → cookie 有效 → 直接发布
  → cookie 无效/不存在 → 自动触发 login 流程
    → login 成功 → 继续发布
    → login 失败 → 返回失败结果
```

**对外暴露单一入口**：Agent 只需执行 `sau publish`，不需要手动分步执行 check/login/publish。

## 改动 8：Skill 文档更新

`skills/sau-cli/SKILL.md` 修正：

| 修正项 | 原内容 | 新内容 |
|--------|--------|--------|
| 浏览器安装 | `playwright install chromium` | `patchright install chromium` |
| 前置步骤 | 手动复制 `conf.example.py` | 删除，零配置 |
| 新增命令 | 无 | `sau status`、`sau login` |
| 自动登录 | 无 | 发布时自动检查登录状态 |
| 环境变量 | 无 | `SAU_HOME` 可覆盖数据目录 |

Agent 核心交互流程：

```
Agent 收到发布请求
  → sau status（检查环境）
  → sau publish --platforms weibo --video xxx --title xxx
    → 内部自动 check cookie
    → cookie 无效 → 自动触发 login（扫码）
    → 登录成功 → 继续发布
  → 返回结果
```

Agent 只需知道 `sau status` 和 `sau publish` 两个命令。

## 不在本次范围内

- MCP Server 集成（后续扩展）
- 视频分析多模态功能（`sau generate`，需 zhipuai API key，后续扩展）
- Web UI 相关改进
- `xhs_uploader`（旧版小红书上传器）的 playwright 兼容问题
