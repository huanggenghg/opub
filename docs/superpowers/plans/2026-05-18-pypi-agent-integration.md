# PyPI Agent 零配置集成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 AI Agent 通过 `pip install hgeng-sau` 后零配置直接使用 CLI 登录和上传视频到多平台。

**Architecture:** 改造 `conf.py` 为自动检测模式（开发/pip）的配置模块，数据目录默认 `~/.social-auto-upload/`；补全依赖声明；放宽 Python 版本到 3.9；新增 `sau status` 和 `sau login` 命令；发布流程自动串联 check → login → publish。

**Tech Stack:** Python 3.9+, patchright, setuptools/packaging

---

### Task 1: 改造 conf.py — 路径解析与配置加载

**Files:**
- Modify: `conf.py` (完全重写)
- Modify: `conf.example.py` (同步更新为新的模板)

- [ ] **Step 1: 重写 conf.py**

将 `conf.py` 替换为自动检测模式的配置模块。开发模式下（项目根有 `uploader/` 目录）行为完全不变，pip 模式下使用 `~/.social-auto-upload/`。

```python
from __future__ import annotations

import json
import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.resolve()


def _detect_mode() -> Path:
    """开发模式：项目根有 uploader/ 目录 → BASE_DIR = 项目根
    pip 模式：→ BASE_DIR = ~/.social-auto-upload/"""
    if (_PROJECT_ROOT / "uploader").is_dir():
        return _PROJECT_ROOT
    return Path(os.environ.get("SAU_HOME", Path.home() / ".social-auto-upload"))


BASE_DIR = _detect_mode()

# 首次运行自动创建数据目录
if not BASE_DIR.exists():
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    (BASE_DIR / "cookies").mkdir(exist_ok=True)


def _load_config() -> dict:
    config_path = BASE_DIR / "config.json"
    if config_path.exists():
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

- [ ] **Step 2: 同步更新 conf.example.py**

将 `conf.example.py` 更新为新的模板，保留注释说明各配置项：

```python
# social-auto-upload 配置文件模板
# pip install 后无需手动创建此文件，conf.py 会自动使用默认值
# 如需自定义配置，请将此文件复制为 config.json 放到数据目录中
#
# 数据目录位置：
#   开发模式：项目根目录（即本文件所在目录）
#   pip 安装模式：~/.social-auto-upload/（可通过 SAU_HOME 环境变量覆盖）
#
# config.json 示例：
# {
#   "chrome_headless": true,
#   "chrome_path": "",
#   "debug": false,
#   "zhipu_api_key": "",
#   "zhipu_vision_model": "glm-4v-plus",
#   "xhs_server": ""
# }
```

- [ ] **Step 3: 验证开发模式不受影响**

在项目根目录下运行：

```bash
python3 -c "from conf import BASE_DIR; print(f'BASE_DIR={BASE_DIR}'); assert 'social-auto-upload' in str(BASE_DIR), 'BASE_DIR should point to project root in dev mode'"
```

Expected: `BASE_DIR=/Users/hgeng/AndroidStudioProjects/social-auto-upload`，断言通过。

- [ ] **Step 4: 验证 pip 模式路径解析**

模拟 pip 安装场景（conf.py 不在项目根目录下）：

```bash
python3 -c "
import tempfile, shutil, os
from pathlib import Path

# 创建临时目录模拟 site-packages
tmpdir = tempfile.mkdtemp()
shutil.copy('conf.py', tmpdir)

# 在临时目录下运行（没有 uploader/ 目录，应走 pip 模式）
import subprocess
result = subprocess.run(
    ['python3', '-c', 'import sys; sys.path.insert(0, \"' + tmpdir + '\"); from conf import BASE_DIR; print(BASE_DIR)'],
    capture_output=True, text=True
)
print(result.stdout.strip())
assert '.social-auto-upload' in result.stdout, f'Expected ~/.social-auto-upload, got: {result.stdout}'
shutil.rmtree(tmpdir)
print('pip mode test passed')
"
```

Expected: 输出包含 `.social-auto-upload`，断言通过。

- [ ] **Step 5: Commit**

```bash
git add conf.py conf.example.py
git commit -m "refactor: 改造 conf.py 为自动检测模式，支持 pip 安装零配置"
```

---

### Task 2: Python 版本放宽到 >=3.9

**Files:**
- Modify: `pyproject.toml:10` — `requires-python`
- Modify: `myUtils/auth.py:105-120` — `match/case` → `if/elif/else`
- Modify: `sau_cli.py:42,58,71,85,98,112,125` — 去掉 `slots=True`
- Modify: `uploader/douyin_uploader/main.py:1` — 添加 `from __future__ import annotations`
- Modify: `utils/login_qrcode.py:1` — 添加 `from __future__ import annotations`
- Modify: `utils/video_analyzer.py:1` — 添加 `from __future__ import annotations`
- Modify: `utils/image_to_video.py:1` — 添加 `from __future__ import annotations`

- [ ] **Step 1: 修改 pyproject.toml**

将 `requires-python = ">=3.10"` 改为 `requires-python = ">=3.9"`。

- [ ] **Step 2: myUtils/auth.py — match/case → if/elif/else**

将 `myUtils/auth.py` 中的 `match/case` 块替换：

```python
# 原代码（删除）：
    match type:
        case 1:
            return await cookie_auth_xhs(file_path)
        case 2:
            return await cookie_auth_tencent(file_path)
        case 3:
            return await cookie_auth_douyin(file_path)
        case 4:
            return await cookie_auth_ks(file_path)
        case _:
            return False

# 新代码（替换为）：
    if type == 1:
        return await cookie_auth_xhs(file_path)
    elif type == 2:
        return await cookie_auth_tencent(file_path)
    elif type == 3:
        return await cookie_auth_douyin(file_path)
    elif type == 4:
        return await cookie_auth_ks(file_path)
    else:
        return False
```

- [ ] **Step 3: sau_cli.py — 去掉 @dataclass(slots=True)**

将 7 处 `@dataclass(slots=True)` 替换为 `@dataclass`：

```python
# 第 42 行
@dataclass
class DouyinVideoUploadRequest:

# 第 58 行
@dataclass
class DouyinNoteUploadRequest:

# 第 71 行
@dataclass
class KuaishouVideoUploadRequest:

# 第 85 行
@dataclass
class KuaishouNoteUploadRequest:

# 第 98 行
@dataclass
class XiaohongshuVideoUploadRequest:

# 第 112 行
@dataclass
class XiaohongshuNoteUploadRequest:

# 第 125 行
@dataclass
class BilibiliVideoUploadRequest:
```

- [ ] **Step 4: 添加 from __future__ import annotations**

在以下文件的第一行（或 shebang/encoding 声明之后）添加 `from __future__ import annotations`：

- `uploader/douyin_uploader/main.py` — 在现有 import 之前添加
- `utils/login_qrcode.py` — 在 `# -*- coding: utf-8 -*-` 之后添加
- `utils/video_analyzer.py` — 在 `# -*- coding: utf-8 -*-` 之后添加
- `utils/image_to_video.py` — 在 `# -*- coding: utf-8 -*-` 之后添加

- [ ] **Step 5: 验证语法兼容性**

```bash
python3 -c "import ast; ast.parse(open('myUtils/auth.py').read()); print('auth.py OK')"
python3 -c "import ast; ast.parse(open('sau_cli.py').read()); print('sau_cli.py OK')"
python3 -c "import ast; ast.parse(open('uploader/douyin_uploader/main.py').read()); print('douyin OK')"
python3 -c "import ast; ast.parse(open('utils/login_qrcode.py').read()); print('login_qrcode OK')"
python3 -c "import ast; ast.parse(open('utils/video_analyzer.py').read()); print('video_analyzer OK')"
python3 -c "import ast; ast.parse(open('utils/image_to_video.py').read()); print('image_to_video OK')"
```

Expected: 全部输出 `OK`。

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml myUtils/auth.py sau_cli.py uploader/douyin_uploader/main.py utils/login_qrcode.py utils/video_analyzer.py utils/image_to_video.py
git commit -m "chore: 放宽 Python 版本要求到 >=3.9，移除 3.10+ 语法"
```

---

### Task 3: 依赖补全

**Files:**
- Modify: `pyproject.toml` — dependencies 和 optional-dependencies

- [ ] **Step 1: 更新 pyproject.toml 依赖声明**

将 `[project]` 下的 `dependencies` 替换为：

```toml
dependencies = [
  "loguru>=0.7.3",
  "opencv-python>=4.13.0",
  "patchright>=1.52.0",
  "qrcode>=8.0",
  "requests>=2.32.3",
  "segno>=1.6.6",
  "xhs>=0.2.13",
  "pillow>=10.0",
]
```

将 `[project.optional-dependencies]` 替换为：

```toml
[project.optional-dependencies]
analyze = ["zhipuai>=2.0.0"]
web = [
  "Flask[async]>=3.1",
  "flask-cors>=6.0",
]
```

- [ ] **Step 2: 验证依赖声明**

```bash
python3 -c "
from pyproject_parser import PyProject
# 简单验证：确保 toml 可解析
import tomllib
with open('pyproject.toml', 'rb') as f:
    data = tomllib.load(f)
deps = data['project']['dependencies']
opt_deps = data['project']['optional-dependencies']
print('Core deps:', [d.split('>=')[0] for d in deps])
print('Optional deps:', {k: [d.split('>=')[0] for d in v] for k, v in opt_deps.items()})
assert 'xhs' in str(deps), 'xhs should be in core deps'
assert 'zhipuai' in str(opt_deps.get('analyze', [])), 'zhipuai should be in analyze optional'
print('Dependency check passed')
"
```

Expected: 输出包含 `xhs` 在 core deps 中，`zhipuai` 在 analyze optional 中。

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: 补全依赖声明，添加 xhs/pillow 到核心依赖，zhipuai 到可选依赖"
```

---

### Task 4: 新增 sau status 命令

**Files:**
- Modify: `sau_cli.py` — `build_parser()` 添加 status 子命令，`dispatch()` 添加 status 分支

- [ ] **Step 1: 在 build_parser() 中添加 status 子命令**

在 `build_parser()` 函数中，`platform_parsers` 定义之前（约第 442 行），添加 status 子命令解析器：

```python
    # === status 子命令 ===
    status_parser = parser.add_parser("status", help="Check environment and login status")
```

注意：`status` 不是 platform 子命令，应该添加到主 parser 而非 `platform_parsers`。需要将 `build_parser()` 中的 subparsers 结构调整为支持顶层 `status` 命令。

当前结构是 `parser.add_subparsers(dest="platform", required=True)`，所有子命令都是 platform。需要改为 `dest="command"` 并在 dispatch 中同时处理 `command="status"` 和 `command=<platform>` 的情况。

具体改动：

1. 将 `parser.add_subparsers(dest="platform", required=True)` 改为 `parser.add_subparsers(dest="command", required=True)`

2. 添加 status 子命令：
```python
    status_parser = parser.add_parser("status", help="Check environment and login status")
```

3. 所有原有 `platform_parsers.add_parser(...)` 调用保持不变，但变量名从 `platform_parsers` 改为 `subparsers`（或保持不变，只是 dest 变了）

4. 在 `dispatch()` 中，将所有 `args.platform` 引用改为 `args.command`

- [ ] **Step 2: 在 dispatch() 中添加 status 分支**

在 `dispatch()` 函数开头添加 status 处理逻辑：

```python
    # === 处理 status 命令 ===
    if args.command == "status":
        import shutil
        import subprocess

        # Python 版本
        import sys
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        print(f"Python: {py_ver} ✓")

        # 浏览器驱动
        try:
            result = subprocess.run(
                ["patchright", "install", "--dry-run", "chromium"],
                capture_output=True, text=True, timeout=10,
            )
            # dry-run 不可用，换用 which 检测
            patchright_path = shutil.which("patchright")
            if patchright_path:
                print(f"Browser: patchright found at {patchright_path}")
            else:
                print("Browser: patchright not found (run: patchright install chromium)")
        except Exception:
            print("Browser: unable to check")

        # 配置目录
        from conf import BASE_DIR
        config_path = BASE_DIR / "config.json"
        if config_path.exists():
            print(f"Config: {config_path}")
        else:
            print(f"Config: {config_path} (not found, using defaults)")

        # Cookies 状态
        cookies_dir = BASE_DIR / "cookies"
        platforms = {
            "weibo": "weibo_uploader",
            "kuaishou": "ks_uploader",
            "douyin": "douyin_uploader",
            "xiaohongshu": "xiaohongshu_uploader",
            "bilibili": "bilibili_uploader",
            "tencent": "tencent_uploader",
            "baijiahao": "baijiahao_uploader",
            "tk": "tk_uploader",
        }
        ready = []
        for name, subdir in platforms.items():
            cookie_dir = cookies_dir / subdir
            if cookie_dir.exists():
                accounts = list(cookie_dir.glob("*.json"))
                if accounts:
                    acct_names = [a.stem for a in accounts]
                    print(f"  {name}: {', '.join(acct_names)}")
                    ready.append(name)
                else:
                    print(f"  {name}: no accounts")
            else:
                print(f"  {name}: no accounts")

        if ready:
            print(f"Platforms ready: {', '.join(ready)}")
        else:
            print("Platforms ready: none (login required)")

        return 0
```

- [ ] **Step 3: 全局替换 args.platform → args.command**

在 `sau_cli.py` 中，将所有 `args.platform` 替换为 `args.command`。这包括：

- `dispatch()` 函数中所有 `if args.platform == "xxx"` 判断
- `main()` 函数中如有引用

使用 `replace_all` 方式替换。

- [ ] **Step 4: 验证 status 命令**

```bash
python3 sau_cli.py status
```

Expected: 输出 Python 版本、浏览器状态、配置目录、各平台 cookie 状态。

- [ ] **Step 5: 验证原有命令不受影响**

```bash
python3 sau_cli.py --help
python3 sau_cli.py douyin --help
python3 sau_cli.py publish --help
```

Expected: 帮助信息正常显示，包含 status 子命令。

- [ ] **Step 6: Commit**

```bash
git add sau_cli.py
git commit -m "feat: 新增 sau status 命令，环境与登录状态预检查"
```

---

### Task 5: 新增 sau login 统一入口

**Files:**
- Modify: `sau_cli.py` — `build_parser()` 添加 login 子命令，`dispatch()` 添加 login 分支

- [ ] **Step 1: 在 build_parser() 中添加 login 子命令**

在 status_parser 之后添加：

```python
    # === login 子命令 ===
    login_parser = parser.add_parser("login", help="Login to a platform")
    login_parser.add_argument("--platform", required=True,
                              choices=["douyin", "kuaishou", "xiaohongshu", "bilibili", "weibo", "tencent", "baijiahao", "tk"],
                              help="Platform to login")
    login_parser.add_argument("--account", required=True, help="Account name")
    login_parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
```

- [ ] **Step 2: 在 dispatch() 中添加 login 分支**

在 status 分支之后添加：

```python
    # === 处理 login 命令 ===
    if args.command == "login":
        platform = args.platform
        account = args.account
        account_file = resolve_account_file(platform, account)
        headless = args.headless

        setup_map = {
            "douyin": ("uploader.douyin_uploader.main", "douyin_setup"),
            "kuaishou": ("uploader.ks_uploader.main", "ks_setup"),
            "xiaohongshu": ("uploader.xiaohongshu_uploader.main", "xiaohongshu_setup"),
            "weibo": ("uploader.weibo_uploader.main", "weibo_setup"),
            "tencent": ("uploader.tencent_uploader.main", "tencent_setup"),
            "baijiahao": ("uploader.baijiahao_uploader.main", "baijiahao_setup"),
            "tk": ("uploader.tk_uploader.main", "tiktok_setup"),
            "bilibili": ("uploader.bilibili_uploader.runtime", "run_biliup_command"),
        }

        entry = setup_map.get(platform)
        if not entry:
            print(f"Unsupported platform: {platform}", file=sys.stderr)
            return 1

        import importlib
        module = importlib.import_module(entry[0])
        func = getattr(module, entry[1])

        # bilibili 特殊处理
        if platform == "bilibili":
            result = func(["-u", str(account_file), "login"], interactive=True)
            return 0 if result.returncode == 0 else 1

        # baijiahao 和 tk 的 setup 签名不同
        if platform in ("baijiahao", "tk"):
            result = await func(str(account_file), handle=True)
        else:
            result = await func(str(account_file), handle=True, return_detail=True, headless=headless)

        if isinstance(result, dict):
            if result.get("success"):
                print(f"Login successful: {platform}")
                return 0
            else:
                print(f"Login failed: {result.get('message', 'unknown error')}", file=sys.stderr)
                return 1
        elif isinstance(result, bool):
            return 0 if result else 1
        else:
            return 0
```

- [ ] **Step 3: 验证 login 命令帮助**

```bash
python3 sau_cli.py login --help
```

Expected: 显示 `--platform` 和 `--account` 参数说明。

- [ ] **Step 4: Commit**

```bash
git add sau_cli.py
git commit -m "feat: 新增 sau login 统一入口，支持所有平台登录"
```

---

### Task 6: 发布流程自动串联 check → login → publish

**Files:**
- Modify: `sau_cli.py` — `dispatch()` 中 publish 分支的发布逻辑

- [ ] **Step 1: 添加 ensure_login 辅助函数到 sau_cli.py**

在 `sau_cli.py` 中（`resolve_account_file` 函数之后）添加：

```python
async def _ensure_login(platform: str, account_file: Path, headless: bool = False) -> bool:
    """检查 cookie 有效性，无效则自动触发登录。返回 True 表示已登录。"""
    check_funcs = {
        "douyin": ("uploader.douyin_uploader.main", "cookie_auth"),
        "kuaishou": ("uploader.ks_uploader.main", "cookie_auth"),
        "xiaohongshu": ("uploader.xiaohongshu_uploader.main", "cookie_auth"),
        "weibo": ("uploader.weibo_uploader.main", "cookie_auth"),
        "tencent": ("uploader.tencent_uploader.main", "cookie_auth"),
        "baijiahao": ("uploader.baijiahao_uploader.main", "cookie_auth"),
        "tk": ("uploader.tk_uploader.main", "cookie_auth"),
    }

    # Bilibili 特殊处理
    if platform == "bilibili":
        from uploader.bilibili_uploader.runtime import run_biliup_command
        result = run_biliup_command(["-u", str(account_file), "renew"])
        if result.returncode == 0:
            return True
        print(f"Cookie invalid, triggering login for bilibili...")
        result = run_biliup_command(["-u", str(account_file), "login"], interactive=True)
        return result.returncode == 0

    module_path, func_name = check_funcs.get(platform, (None, None))
    if not module_path:
        print(f"No check function for platform: {platform}", file=sys.stderr)
        return False

    import importlib
    module = importlib.import_module(module_path)
    check_func = getattr(module, func_name)

    # 检查 cookie
    if await check_func(str(account_file)):
        return True

    # Cookie 无效，自动触发登录
    print(f"Cookie invalid, triggering login for {platform}...")
    setup_funcs = {
        "douyin": ("uploader.douyin_uploader.main", "douyin_setup"),
        "kuaishou": ("uploader.ks_uploader.main", "ks_setup"),
        "xiaohongshu": ("uploader.xiaohongshu_uploader.main", "xiaohongshu_setup"),
        "weibo": ("uploader.weibo_uploader.main", "weibo_setup"),
        "tencent": ("uploader.tencent_uploader.main", "tencent_setup"),
        "baijiahao": ("uploader.baijiahao_uploader.main", "baijiahao_setup"),
        "tk": ("uploader.tk_uploader.main", "tiktok_setup"),
    }

    setup_path, setup_name = setup_funcs.get(platform, (None, None))
    if not setup_path:
        print(f"No login function for platform: {platform}", file=sys.stderr)
        return False

    setup_module = importlib.import_module(setup_path)
    setup_func = getattr(setup_module, setup_name)

    # baijiahao 和 tk 的 setup 签名不同
    if platform in ("baijiahao", "tk"):
        result = await setup_func(str(account_file), handle=True)
    else:
        result = await setup_func(str(account_file), handle=True, return_detail=True, headless=headless)

    if isinstance(result, dict):
        return result.get("success", False)
    return bool(result)
```

- [ ] **Step 2: 修改 publish 分支，发布前调用 _ensure_login**

在 `sau_cli.py` 的 `dispatch()` 函数中，publish 分支的内层循环（遍历 account_files 的 for 循环内），在 `platform_params = {**video_params, "account_file": account_file}` 之前，添加登录检查：

```python
                # 自动检查登录状态，未登录则触发登录
                if not await _ensure_login(platform, Path(account_file)):
                    result_key = platform if len(account_files) == 1 else f"{platform}_{acct_idx + 1}"
                    results[result_key] = {"success": False, "message": f"登录失败: {platform}"}
                    print(f"  ✗ Failed: login required but failed")
                    continue
```

- [ ] **Step 3: 同步修改 publish_all.py 的 ensure_login**

`publish_all.py` 中已有 `ensure_login()` 函数（lines 276-299），当前逻辑是直接调用 `*_setup(account_file, handle=True)`。需要改为先 check 再 login 的模式：

在 `ensure_login()` 函数中，在调用 `*_setup` 之前，先调用对应的 `cookie_auth` 检查：

```python
async def ensure_login(platform, account_file):
    """确保已登录，未登录则自动触发登录"""
    # 先检查 cookie 是否有效
    check_map = {
        "douyin": "uploader.douyin_uploader.main:cookie_auth",
        "xiaohongshu": "uploader.xiaohongshu_uploader.main:cookie_auth",
        "kuaishou": "uploader.ks_uploader.main:cookie_auth",
        "weibo": "uploader.weibo_uploader.main:cookie_auth",
        "tencent": "uploader.tencent_uploader.main:cookie_auth",
        "baijiahao": "uploader.baijiahao_uploader.main:cookie_auth",
        "tk": "uploader.tk_uploader.main:cookie_auth",
    }

    check_entry = check_map.get(platform)
    if check_entry:
        module_path, func_name = check_entry.rsplit(":", 1)
        import importlib
        module = importlib.import_module(module_path)
        check_func = getattr(module, func_name)
        if await check_func(account_file):
            return True

    # cookie 无效，触发登录
    # ... 保留原有的 setup 调用逻辑不变
```

- [ ] **Step 4: 验证 publish 命令帮助**

```bash
python3 sau_cli.py publish --help
```

Expected: 帮助信息正常显示。

- [ ] **Step 5: Commit**

```bash
git add sau_cli.py publish_all.py
git commit -m "feat: 发布流程自动串联 check → login → publish"
```

---

### Task 7: Skill 文档更新

**Files:**
- Modify: `skills/sau-cli/SKILL.md`

- [ ] **Step 1: 重写 SKILL.md**

```markdown
---
name: sau-cli
description: Use when operating the social-auto-upload CLI tool — checking environment, logging in, uploading videos, publishing to platforms, or analyzing video content. Also use when a user asks to publish/upload to Douyin, Xiaohongshu, Kuaishou, Weibo, Bilibili, Tencent, Baijiahao, or TikTok via command line.
---

# sau CLI 使用指南

## 前置依赖

使用前必须确保：

1. **安装包**：`pip install hgeng-sau`
2. **浏览器驱动**：`patchright install chromium`
3. **环境检查**：`sau status`（确认环境就绪）

无需手动配置任何文件，安装后即可使用。

## CLI 命令总览

```
sau <子命令> [选项]
```

| 子命令 | 说明 | 是否需要登录 |
|---------|------|-------------|
| `status` | 检查环境与登录状态 | 否 |
| `login` | 登录指定平台（扫码） | 否（登录本身） |
| `generate` | 分析视频帧，自动生成标题描述 | 否（需智谱 API key） |
| `publish` | 一键多平台发布（读配置文件） | 自动检查，未登录则触发登录 |
| `douyin` | 抖音：login / check / upload-video / upload-note | 是 |
| `kuaishou` | 快手：login / check / upload-video / upload-note | 是 |
| `xiaohongshu` | 小红书：login / check / upload-video / upload-note | 是 |
| `bilibili` | B站：login / check / upload-video | 是 |

## 常用命令

### 环境检查

```bash
sau status                    # 检查 Python、浏览器、配置、各平台登录状态
```

### 登录

```bash
sau login --platform weibo --account <账号名>       # 微博登录
sau login --platform douyin --account <账号名>       # 抖音登录
sau login --platform kuaishou --account <账号名>     # 快手登录
sau login --platform xiaohongshu --account <账号名>  # 小红书登录
sau login --platform bilibili --account <账号名>     # B站登录
sau login --platform tencent --account <账号名>      # 微信视频号登录
sau login --platform baijiahao --account <账号名>    # 百家号登录
sau login --platform tk --account <账号名>           # TikTok 登录
```

登录后 cookie 保存在 `~/.social-auto-upload/cookies/` 目录。

### 一键多平台发布

```bash
sau publish                                    # 按 publish_config.ini 配置发布
sau publish --platforms weibo,xiaohongshu      # 覆盖启用平台
sau publish --title "我的标题" --video videos/  # 覆盖标题和视频路径
sau publish --start-from 5                     # 从第5个视频开始（断点续传）
sau publish --schedule "2026-05-20 12:00"      # 定时发布
sau publish --force                            # 强制重新生成视频配置
sau publish --config my_config.ini             # 指定配置文件
```

**自动登录**：发布时自动检查各平台 cookie 有效性，无效则自动触发登录流程（扫码），无需手动分步操作。

### 单平台上传

```bash
sau douyin upload-video --account <账号> --file <视频> --title <标题> [--tags 标签1,标签2] [--schedule 2026-05-20 12:00]
sau kuaishou upload-video --account <账号> --file <视频> --title <标题>
sau xiaohongshu upload-video --account <账号> --file <视频> --title <标题>
sau bilibili upload-video --account <账号> --file <视频> --title <标题> --desc <描述> --tid <分区ID>
```

### 视频内容分析（可选功能）

```bash
pip install hgeng-sau[analyze]                 # 安装视频分析依赖
sau generate --dir videos/                     # 分析目录下所有视频
sau generate --dir videos/ --force             # 强制重新分析
```

## 配置（可选）

默认无需配置。如需自定义，在 `~/.social-auto-upload/config.json` 中设置：

```json
{
  "chrome_headless": true,
  "chrome_path": "",
  "debug": false,
  "zhipu_api_key": "",
  "zhipu_vision_model": "glm-4v-plus",
  "xhs_server": ""
}
```

环境变量 `SAU_HOME` 可覆盖数据目录（默认 `~/.social-auto-upload/`）。

## Agent 交互流程

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

## 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| Browser: patchright not found | 未安装浏览器驱动 | `patchright install chromium` |
| cookie missing or expired | 未登录或 cookie 过期 | `sau login --platform <平台> --account <账号>` |
| 未找到视频文件 | video_file 路径错误 | 路径相对于数据目录，或用 `--video` 覆盖 |
| 标题为空 | 未配置标题 | `sau generate` 自动生成（需安装 analyze 依赖），或 `--title` 手动指定 |
| 浏览器启动失败 | 未安装浏览器驱动 | `patchright install chromium` |
| 智谱 API 报错 | 未配置 API key | 在 config.json 中填入 zhipu_api_key |
```

- [ ] **Step 2: Commit**

```bash
git add skills/sau-cli/SKILL.md
git commit -m "docs: 更新 sau-cli Skill 文档，零配置 + 自动登录 + sau status"
```

---

### Task 8: 版本升级与最终验证

**Files:**
- Modify: `pyproject.toml` — version bump

- [ ] **Step 1: 升级版本号**

将 `pyproject.toml` 中的 `version = "0.1.1"` 改为 `version = "0.2.0"`（本次改动包含新功能和架构改进，属于 minor 版本升级）。

- [ ] **Step 2: 全量验证**

```bash
# 语法检查
python3 -c "import ast; ast.parse(open('conf.py').read()); print('conf.py OK')"
python3 -c "import ast; ast.parse(open('sau_cli.py').read()); print('sau_cli.py OK')"
python3 -c "import ast; ast.parse(open('publish_all.py').read()); print('publish_all.py OK')"
python3 -c "import ast; ast.parse(open('myUtils/auth.py').read()); print('auth.py OK')"

# CLI 帮助检查
python3 sau_cli.py --help
python3 sau_cli.py status
python3 sau_cli.py login --help
python3 sau_cli.py publish --help
python3 sau_cli.py douyin --help
```

Expected: 所有语法检查通过，CLI 帮助正常显示。

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: 版本升级到 0.2.0"
```
