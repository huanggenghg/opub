# Sub-project C: 清理废弃 Web 版本 + 修复 examples 断链 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除废弃的 Flask backend + Vue frontend + myUtils/ 桥接层,清理 web 依赖,更新文档反映 CLI-only 定位,修复 examples/ 里 6 个脚本调用已删除别名的断链。

**Architecture:** 纯清理 + 修复,无新功能。删除 8 个文件/目录,修改 4 个配置/文档文件,修复 6 个 examples 脚本的 12 处 `app.<deprecated>()` 调用改为 `app.upload()` + `PlatformResultExtras` 结果检查。每个 task 保持 CLI 回归网全绿(150 tests)。

**Tech Stack:** Python 3.9+, pytest, patchright(playwright fork),无 Flask/Vue/前端

## Global Constraints

- **分支:** 从 `sub-project-b/uploader-base-class` 拉新分支 `sub-project-c/cleanup-legacy-web`(不是 main,因为 examples 修复依赖 sub-project B 的新 `upload()` 方法)
- **Python 3.9+ 兼容**(`from __future__ import annotations` 已在各 uploader 里用)
- **回归网全绿:** 每个 task 结束时 `tests/test_publish_engine.py` / `tests/test_publish_dispatch.py` / `tests/test_publish_reporter.py` / `tests/test_publish_cli.py` 必须全绿(150 passed,0 failed)
- **PlatformResultExtras 契约**(`uploader/base_video.py:22-31`):
  ```python
  class PlatformResult(TypedDict):
      success: bool
      message: str

  class PlatformResultExtras(PlatformResult, total=False):
      result_url: str
      result_id: str
      account_issue: bool
      issue_type: str
  ```
- **upload() 方法:** 所有平台的 `*Video` / `*Note` 类都有 `async def upload(self) -> PlatformResultExtras`,无参数,用 `__init__` 设置的 self.* 属性
- **禁止截屏定位 UI**(项目 hard constraint,本 plan 不涉及但适用)
- **不保留向后兼容:** 彻底删除,不保留 alias shim(sub-project B Task 9 已删别名,本 plan 修复调用方)
- **频繁提交:** 每个 task 至少一个 commit

---

### Task 1: 删除废弃 Web 代码

**Files:**
- Delete: `myUtils/` (整个目录,含 `__init__.py`、`postVideo.py`、`auth.py`、`login.py`)
- Delete: `hgsau_backend.py`
- Delete: `hgsau_backend/` (整个目录,含 `README.md`)
- Delete: `hgsau_frontend/` (整个目录,Vue.js 前端)
- Delete: `Dockerfile`
- Delete: `db/` (整个目录,含 `createTable.py`、`database.db`)
- Delete: `docs/legacy-web.md`

**Interfaces:**
- Consumes: 无(纯删除)
- Produces: 无 myUtils/、hgsau_backend、hgsau_frontend、db/ 残留的干净仓库

- [ ] **Step 1: 确认当前分支状态**

Run:
```bash
git branch --show-current
git log --oneline -1
```
Expected: 当前在 `sub-project-b/uploader-base-class`,HEAD 是 `238475a` (spec commit) 或更新的 commit。

- [ ] **Step 2: 创建 sub-project C 分支**

Run:
```bash
git checkout -b sub-project-c/cleanup-legacy-web
```
Expected: 切换到新分支 `sub-project-c/cleanup-legacy-web`。

- [ ] **Step 3: 删除废弃文件和目录**

Run:
```bash
git rm -r myUtils/ hgsau_backend.py hgsau_backend/ hgsau_frontend/ Dockerfile db/ docs/legacy-web.md
```
Expected: 8 个目标被删除,`git status` 显示这些为 `deleted`。

- [ ] **Step 4: 验证无残留引用**

Run:
```bash
grep -rn "myUtils\|hgsau_backend\|hgsau_frontend" --include="*.py" --include="*.md" --include="*.toml" --include="*.txt" --include="*.cfg" --include="*.ini" . | grep -v ".venv" | grep -v "__pycache__" | grep -v ".git/"
```
Expected: 无输出(或只有 git 历史里的引用,不在工作树)。

如果输出有残留,逐一修复(删除对应 import 或引用)。

- [ ] **Step 5: 验证 CLI 入口仍能 import**

Run:
```bash
.venv/bin/python -c "import publish_all; print('publish_all OK')"
```
Expected: 输出 `publish_all OK`,无 ImportError。

- [ ] **Step 6: 运行回归测试套件**

Run:
```bash
.venv/bin/python -m pytest tests/test_publish_engine.py tests/test_publish_dispatch.py tests/test_publish_reporter.py tests/test_publish_cli.py -v
```
Expected: `150 passed`,0 failed。

- [ ] **Step 7: 提交**

Run:
```bash
git commit -m "$(cat <<'EOF'
chore: delete legacy web code (myUtils, hgsau_backend, hgsau_frontend, Dockerfile, db)

项目定位已切到 CLI + 脚本为主,不涉及前后端页面。删除废弃的 Flask
backend、Vue frontend、myUtils 桥接层、Dockerfile、db 建表脚本和
legacy-web 说明文档。CLI 主线(publish_all.py / publish/ 包)不受影响。
EOF
)"
```
Expected: commit 成功,工作树干净。

---

### Task 2: 清理 web 依赖

**Files:**
- Modify: `requirements.txt:3` (删 `aiohttp-cors==0.8.1`)
- Modify: `requirements.txt:24-25` (删 `Flask[async]==3.1.1` 和 `flask-cors==6.0.0`)
- Modify: `pyproject.toml:43-47` (删 `[project.optional-dependencies]` 段的 `web = [...]`)

**Interfaces:**
- Consumes: 无
- Produces: 干净的依赖声明,无 web 相关包

- [ ] **Step 1: 读 requirements.txt 确认当前状态**

Run:
```bash
grep -n "aiohttp-cors\|Flask\|flask-cors" requirements.txt
```
Expected:
```
3:aiohttp-cors==0.8.1
24:Flask[async]==3.1.1
25:flask-cors==6.0.0
```

- [ ] **Step 2: 删除 requirements.txt 里的三行 web 依赖**

用 Edit 工具,逐行删除:
- 删 `aiohttp-cors==0.8.1` (line 3)
- 删 `Flask[async]==3.1.1` (line 24)
- 删 `flask-cors==6.0.0` (line 25)

- [ ] **Step 3: 验证 requirements.txt 改动**

Run:
```bash
grep -n "aiohttp-cors\|Flask\|flask-cors" requirements.txt
```
Expected: 无输出(三行都删干净了)。

- [ ] **Step 4: 读 pyproject.toml 确认当前状态**

Run:
```bash
grep -n -A 3 "optional-dependencies" pyproject.toml
```
Expected:
```
43:[project.optional-dependencies]
44:web = [
45:  "Flask[async]==3.1.1",
46:  "flask-cors==6.0.0",
47:]
```

- [ ] **Step 5: 删除 pyproject.toml 里的 web 段**

用 Edit 工具,删除以下内容(包括 `[project.optional-dependencies]` header,因为 web 是唯一的可选依赖):

```toml
[project.optional-dependencies]
web = [
  "Flask[async]==3.1.1",
  "flask-cors==6.0.0",
]
```

删除后,`[project.scripts]` 段和 `[tool.uv]` 段之间应该只有一个空行。

- [ ] **Step 6: 验证 pyproject.toml 改动**

Run:
```bash
grep -n "optional-dependencies\|Flask\|flask-cors\|web = " pyproject.toml
```
Expected: 无输出。

- [ ] **Step 7: 验证 pip install -e . 仍成功**

Run:
```bash
.venv/bin/pip install -e . 2>&1 | tail -5
```
Expected: 安装成功,无 Flask 相关报错(如果有 Flask 残留引用会在这里暴露)。

- [ ] **Step 8: 运行回归测试套件**

Run:
```bash
.venv/bin/python -m pytest tests/test_publish_engine.py tests/test_publish_dispatch.py tests/test_publish_reporter.py tests/test_publish_cli.py -v
```
Expected: `150 passed`,0 failed。

- [ ] **Step 9: 提交**

Run:
```bash
git add requirements.txt pyproject.toml
git commit -m "$(cat <<'EOF'
chore: remove web dependencies (Flask, flask-cors, aiohttp-cors)

清理 requirements.txt 和 pyproject.toml 里的 web 相关依赖。这些包只被
已删除的 hgsau_backend.py 使用。aiohttp-cors 在代码里从未被引用,顺手清掉。
EOF
)"
```
Expected: commit 成功。

---

### Task 3: 更新文档反映 CLI-only 定位

**Files:**
- Modify: `README.md:103` (删 legacy-web.md 引用行)
- Modify: `CLAUDE.md:11-32` (重写 Project Overview,删 Backend/Frontend 段)
- Modify: `CLAUDE.md:60-89` (重写 Building and Running,删 Backend server + Frontend 子段)
- Modify: `CLAUDE.md:108-113` (重写 Development Conventions,删 myUtils/hgsau_frontend/database.db/package.json 引用)

**Interfaces:**
- Consumes: 无
- Produces: 反映 CLI-only 定位的文档

- [ ] **Step 1: 读 README.md 确认 line 103**

Run:
```bash
sed -n '100,106p' README.md
```
Expected: 看到 line 103 是 `- 历史 Web 说明请看：[历史 Web 版本说明](./docs/legacy-web.md)`

- [ ] **Step 2: 删除 README.md line 103**

用 Edit 工具,删除整行:
```
- 历史 Web 说明请看：[历史 Web 版本说明](./docs/legacy-web.md)
```

- [ ] **Step 3: 验证 README.md 改动**

Run:
```bash
grep -n "legacy-web\|历史 Web" README.md
```
Expected: 无输出(line 237 的 "封装了 api 接口和 web 前端管理界面" 在作者 credits 区,保留不动,不属于"历史 Web"关键词)。

- [ ] **Step 4: 读 CLAUDE.md 的 Project Overview 段**

Run:
```bash
sed -n '11,32p' CLAUDE.md
```
Expected: 看到 "The project consists of a Python backend and a Vue.js frontend." + Backend/Frontend 子段。

- [ ] **Step 5: 重写 CLAUDE.md Project Overview 段**

用 Edit 工具,把以下内容:

```
The project consists of a Python backend and a Vue.js frontend.

**Backend:**

*   Framework: Flask
*   Core Functionality:
    *   Handles file uploads and management.
    *   Interacts with a SQLite database to store information about files and user accounts.
    *   Uses `playwright` for browser automation to interact with social media platforms.
    *   Provides a RESTful API for the frontend to consume.
    *   Uses Server-Sent Events (SSE) for real-time communication with the frontend during the login process.

**Frontend:**

*   Framework: Vue.js
*   Build Tool: Vite
*   UI Library: Element Plus
*   State Management: Pinia
*   Routing: Vue Router
*   Core Functionality:
    *   Provides a web interface for managing social media accounts, video files, and publishing videos.
    *   Communicates with the backend via a RESTful API.

**Command-line Interface:**
```

替换为:

```
The project consists of a Python CLI tool and uploader modules.

**Command-line Interface:**
```

- [ ] **Step 6: 读 CLAUDE.md 的 Building and Running 段**

Run:
```bash
sed -n '55,95p' CLAUDE.md
```
Expected: 看到 Backend 子段(含 "Initialize the database" 和 "Run the backend server")和 Frontend 子段。

- [ ] **Step 7: 重写 CLAUDE.md Building and Running 段**

这个段当前结构是:`### Backend`(含 5 步)-> `### Frontend`(含 3 步)-> `### Command-line Interface`。需要:
1. 把 `### Backend` header 改成 `### Setup`(这些步骤是 CLI 也需要的通用安装)
2. 保留步骤 1-3(Install dependencies、Playwright、ffmpeg)
3. 删除步骤 4(Initialize the database - db/ 已在 Task 1 删除)
4. 删除步骤 5(Run the backend server - hgsau_backend.py 已在 Task 1 删除)
5. 删除整个 `### Frontend` 子段
6. 保留 `### Command-line Interface` 子段

用 Edit 工具,把以下内容(从 `### Backend` 到 `### Frontend` 子段结束,即 `npm run dev` 后的 `` ``` `` 和 `The frontend development server will start on...` 行):

```
### Backend

1.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

2.  **Install Playwright browser drivers:**
    ```bash
    playwright install chromium
    ```

3.  **Install ffmpeg (required for image-to-video conversion):**
    The `convert_to_video` feature uses moviepy + ffmpeg to turn image notes into slideshow videos. moviepy is installed from `requirements.txt`, but ffmpeg must be installed separately as a system dependency:
    *   macOS: `brew install ffmpeg`
    *   Ubuntu/Debian: `sudo apt-get install ffmpeg`
    *   Windows: download from https://ffmpeg.org/download.html and add to PATH

4.  **Initialize the database:**
    ```bash
    python db/createTable.py
    ```

5.  **Run the backend server:**
    ```bash
    python hgsau_backend.py
    ```
    The backend server will start on `http://localhost:5409`.

### Frontend

1.  **Navigate to the frontend directory:**
    ```bash
    cd hgsau_frontend
    ```

2.  **Install dependencies:**
    ```bash
    npm install
    ```

3.  **Run the development server:**
    ```bash
    npm run dev
    ```
    The frontend development server will start on `http://localhost:5173`.

### Command-line Interface
```

替换为:

```
### Setup

1.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

2.  **Install Playwright browser drivers:**
    ```bash
    playwright install chromium
    ```

3.  **Install ffmpeg (required for image-to-video conversion):**
    The `convert_to_video` feature uses moviepy + ffmpeg to turn image notes into slideshow videos. moviepy is installed from `requirements.txt`, but ffmpeg must be installed separately as a system dependency:
    *   macOS: `brew install ffmpeg`
    *   Ubuntu/Debian: `sudo apt-get install ffmpeg`
    *   Windows: download from https://ffmpeg.org/download.html and add to PATH

### Command-line Interface
```

这样保留了 Install dependencies / Playwright / ffmpeg 三个步骤(改到 `### Setup` 下),删除了 Initialize database、Run backend server、整个 Frontend 子段。

- [ ] **Step 8: 读 CLAUDE.md 的 Development Conventions 段**

Run:
```bash
sed -n '105,120p' CLAUDE.md
```
Expected: 看到引用 myUtils、hgsau_frontend、database.db、package.json 的条目。

- [ ] **Step 9: 重写 CLAUDE.md Development Conventions 段**

用 Edit 工具,把以下内容:

```
*   The backend code is located in the root directory and the `myUtils` and `uploader` directories.
*   The frontend code is located in the `hgsau_frontend` directory.
*   The project uses a SQLite database for data storage. The database file is located at `db/database.db`.
*   The `conf.example.py` file should be copied to `conf.py` and configured with the appropriate settings.
*   The `requirements.txt` file lists the Python dependencies.
*   The `package.json` file in the `hgsau_frontend` directory lists the frontend dependencies.
```

替换为:

```
*   The code is located in the root directory and the `uploader` directory.
*   The `conf.example.py` file should be copied to `conf.py` and configured with the appropriate settings.
*   The `requirements.txt` file lists the Python dependencies.
```

- [ ] **Step 10: 验证 CLAUDE.md 无 web 残留**

Run:
```bash
grep -n "Flask\|Vue\|frontend\|backend\|RESTful\|SSE\|5409\|hgsau_backend\|hgsau_frontend\|myUtils\|database.db\|npm\|5173" CLAUDE.md
```
Expected: 无输出(所有 web 相关引用都清干净了)。

- [ ] **Step 11: 运行回归测试套件(纯文档改动,但确认无副作用)**

Run:
```bash
.venv/bin/python -m pytest tests/test_publish_engine.py tests/test_publish_dispatch.py tests/test_publish_reporter.py tests/test_publish_cli.py -v
```
Expected: `150 passed`,0 failed。

- [ ] **Step 12: 提交**

Run:
```bash
git add README.md CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: update README and CLAUDE.md to reflect CLI-only positioning

移除 README 里的 legacy-web.md 引用。重写 CLAUDE.md 的 Project Overview、
Building and Running、Development Conventions 三段,删除 Flask/Vue/backend/
frontend/SSE/RESTful/5409/npm 等所有 web 相关描述,保留 CLI 主线说明。
EOF
)"
```
Expected: commit 成功。

---

### Task 4: 修复 examples 断链

**Files:**
- Create: `tests/test_examples_no_deprecated_calls.py`
- Modify: `examples/upload_to_kuaishou.py:42,67`
- Modify: `examples/upload_to_douyin.py:116,168`
- Modify: `examples/upload_video_to_baijiahao.py:27`
- Modify: `examples/upload_video_to_tiktok.py:30`
- Modify: `examples/upload_video_to_xiaohongshu.py:125,181`
- Modify: `examples/upload_video_to_tencent.py:41,61,81,102`

**Interfaces:**
- Consumes: `PlatformResultExtras` 契约来自 `uploader/base_video.py:22-31`(sub-project B 产出)
- Consumes: 各平台 `*Video` / `*Note` 类的 `async def upload(self) -> PlatformResultExtras` 方法(sub-project B 产出)
- Produces: 6 个 examples 脚本改用 `app.upload()` + 结果检查,展示新返回契约

- [ ] **Step 1: 写失败测试 - 扫描 examples/ 里是否还有已删除别名的调用**

Create `tests/test_examples_no_deprecated_calls.py`:

```python
"""验证 examples/ 里的脚本不再调用已删除的别名方法。

sub-project B Task 9 删除了各平台 uploader 的 main() / <platform>_upload_video() /
<platform>_upload_note() 别名 wrapper。sub-project C Task 4 修复 examples/ 里的
调用方,改用 app.upload()。这个测试扫描 examples/ 确保没有残留的已删除别名调用。
"""
import re
from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"

# 已删除的别名方法名(sub-project B Task 9 删除)
DEPRECATED_CALL_PATTERNS = [
    r"\.main\(\)",
    r"\.douyin_upload_video\(\)",
    r"\.douyin_upload_note\(\)",
    r"\.tencent_upload_video\(\)",
    r"\.tencent_upload_note\(\)",
    r"\.xiaohongshu_upload_video\(\)",
    r"\.xiaohongshu_upload_note\(\)",
]


def test_no_deprecated_alias_calls_in_examples():
    """扫描 examples/ 所有 .py 文件,确保没有调用已删除的别名方法。"""
    violations = []
    for py_file in EXAMPLES_DIR.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for pattern in DEPRECATED_CALL_PATTERNS:
            # 匹配 app.main() / app.douyin_upload_video() 等调用
            for match in re.finditer(pattern, content):
                line_num = content[:match.start()].count("\n") + 1
                violations.append(f"{py_file.name}:{line_num} -> {match.group()}")
    assert not violations, (
        f"examples/ 里有 {len(violations)} 处调用已删除的别名方法,改用 app.upload():\n"
        + "\n".join(violations)
    )


def test_examples_use_upload_method():
    """验证 examples/ 里的脚本调用了 app.upload()。"""
    py_files = list(EXAMPLES_DIR.rglob("*.py"))
    # 排除 __init__.py 等空文件
    upload_callers = []
    for py_file in py_files:
        content = py_file.read_text(encoding="utf-8")
        if "app.upload()" in content or "asyncio.run(app.upload()" in content:
            upload_callers.append(py_file.name)
    # 至少 6 个脚本应该调用 app.upload()
    assert len(upload_callers) >= 6, (
        f"期望至少 6 个 examples 脚本调用 app.upload(),实际 {len(upload_callers)} 个: "
        f"{upload_callers}"
    )
```

- [ ] **Step 2: 运行测试验证它失败(RED)**

Run:
```bash
.venv/bin/python -m pytest tests/test_examples_no_deprecated_calls.py -v
```
Expected: FAIL。`test_no_deprecated_alias_calls_in_examples` 应该报告 ~12 处违规(6 个脚本里的 12 个调用点)。`test_examples_use_upload_method` 应该报告 0 个调用者(因为还没改)。

- [ ] **Step 3: 修复 examples/upload_to_kuaishou.py(2 处)**

用 Edit 工具:

第一处(line 42),把:
```python
    asyncio.run(app.main())


def upload_note_to_kuaishou():
```
改为:
```python
    result = asyncio.run(app.upload())
    if result.get("success"):
        print(f"✅ 发布成功" + (f",链接: {result['result_url']}" if result.get("result_url") else ""))
    else:
        print(f"❌ 发布失败: {result.get('message')}")
        if result.get("account_issue"):
            print(f"   账号问题: {result.get('issue_type')}")


def upload_note_to_kuaishou():
```

第二处(line 67,现在是 73 左右因为前面加了几行),把:
```python
    asyncio.run(app.main())


if __name__ == '__main__':
```
改为:
```python
    result = asyncio.run(app.upload())
    if result.get("success"):
        print(f"✅ 发布成功" + (f",链接: {result['result_url']}" if result.get("result_url") else ""))
    else:
        print(f"❌ 发布失败: {result.get('message')}")
        if result.get("account_issue"):
            print(f"   账号问题: {result.get('issue_type')}")


if __name__ == '__main__':
```

- [ ] **Step 4: 修复 examples/upload_to_douyin.py(2 处)**

用 Edit 工具:

第一处(line 116),把:
```python
    asyncio.run(app.douyin_upload_video())
```
改为:
```python
    result = asyncio.run(app.upload())
    if result.get("success"):
        print(f"✅ 发布成功" + (f",链接: {result['result_url']}" if result.get("result_url") else ""))
    else:
        print(f"❌ 发布失败: {result.get('message')}")
        if result.get("account_issue"):
            print(f"   账号问题: {result.get('issue_type')}")
```

第二处(line 168),把:
```python
    asyncio.run(app.douyin_upload_note())
```
改为:
```python
    result = asyncio.run(app.upload())
    if result.get("success"):
        print(f"✅ 发布成功" + (f",链接: {result['result_url']}" if result.get("result_url") else ""))
    else:
        print(f"❌ 发布失败: {result.get('message')}")
        if result.get("account_issue"):
            print(f"   账号问题: {result.get('issue_type')}")
```

- [ ] **Step 5: 修复 examples/upload_video_to_baijiahao.py(1 处)**

用 Edit 工具,把(line 27):
```python
        asyncio.run(app.main(), debug=False)
```
改为:
```python
        result = asyncio.run(app.upload())
        if result.get("success"):
            print(f"✅ 发布成功" + (f",链接: {result['result_url']}" if result.get("result_url") else ""))
        else:
            print(f"❌ 发布失败: {result.get('message')}")
            if result.get("account_issue"):
                print(f"   账号问题: {result.get('issue_type')}")
```

注意:原代码在 for 循环里,缩进是 8 空格(2 级),保持缩进。

- [ ] **Step 6: 修复 examples/upload_video_to_tiktok.py(1 处)**

用 Edit 工具,把(line 30):
```python
        asyncio.run(app.main(), debug=False)
```
改为:
```python
        result = asyncio.run(app.upload())
        if result.get("success"):
            print(f"✅ 发布成功" + (f",链接: {result['result_url']}" if result.get("result_url") else ""))
        else:
            print(f"❌ 发布失败: {result.get('message')}")
            if result.get("account_issue"):
                print(f"   账号问题: {result.get('issue_type')}")
```

注意:原代码在 for 循环里,缩进是 8 空格(2 级),保持缩进。

- [ ] **Step 7: 修复 examples/upload_video_to_xiaohongshu.py(2 处)**

用 Edit 工具:

第一处(line 125),把:
```python
    result = asyncio.run(app.xiaohongshu_upload_video())
    print(f"\n上传结果: {result}")
```
改为:
```python
    result = asyncio.run(app.upload())
    if result.get("success"):
        print(f"✅ 发布成功" + (f",链接: {result['result_url']}" if result.get("result_url") else ""))
    else:
        print(f"❌ 发布失败: {result.get('message')}")
        if result.get("account_issue"):
            print(f"   账号问题: {result.get('issue_type')}")
```

第二处(line 181),把:
```python
    result = asyncio.run(app.xiaohongshu_upload_note())
    print(f"\n上传结果: {result}")
```
改为:
```python
    result = asyncio.run(app.upload())
    if result.get("success"):
        print(f"✅ 发布成功" + (f",链接: {result['result_url']}" if result.get("result_url") else ""))
    else:
        print(f"❌ 发布失败: {result.get('message')}")
        if result.get("account_issue"):
            print(f"   账号问题: {result.get('issue_type')}")
```

- [ ] **Step 8: 修复 examples/upload_video_to_tencent.py(4 处)**

用 Edit 工具。这个文件有 4 处调用,分两对:`upload_video` x2 和 `upload_note` x2。每对的两处上下文不同,需要分别 edit。

第一处(line 41,`upload_video_to_tencent` 函数末尾),把:
```python
    asyncio.run(app.tencent_upload_video())


def upload_video_to_tencent_scheduled():
```
改为:
```python
    result = asyncio.run(app.upload())
    if result.get("success"):
        print(f"✅ 发布成功" + (f",链接: {result['result_url']}" if result.get("result_url") else ""))
    else:
        print(f"❌ 发布失败: {result.get('message')}")
        if result.get("account_issue"):
            print(f"   账号问题: {result.get('issue_type')}")


def upload_video_to_tencent_scheduled():
```

第二处(line 61,`upload_video_to_tencent_scheduled` 函数末尾),把:
```python
    asyncio.run(app.tencent_upload_video())


def upload_note_to_tencent():
```
改为:
```python
    result = asyncio.run(app.upload())
    if result.get("success"):
        print(f"✅ 发布成功" + (f",链接: {result['result_url']}" if result.get("result_url") else ""))
    else:
        print(f"❌ 发布失败: {result.get('message')}")
        if result.get("account_issue"):
            print(f"   账号问题: {result.get('issue_type')}")


def upload_note_to_tencent():
```

第三处(line 81,`upload_note_to_tencent` 函数末尾),把:
```python
    asyncio.run(app.tencent_upload_note())


def upload_note_to_tencent_scheduled():
```
改为:
```python
    result = asyncio.run(app.upload())
    if result.get("success"):
        print(f"✅ 发布成功" + (f",链接: {result['result_url']}" if result.get("result_url") else ""))
    else:
        print(f"❌ 发布失败: {result.get('message')}")
        if result.get("account_issue"):
            print(f"   账号问题: {result.get('issue_type')}")


def upload_note_to_tencent_scheduled():
```

第四处(line 102,`upload_note_to_tencent_scheduled` 函数末尾),把:
```python
    asyncio.run(app.tencent_upload_note())


if __name__ == "__main__":
```
改为:
```python
    result = asyncio.run(app.upload())
    if result.get("success"):
        print(f"✅ 发布成功" + (f",链接: {result['result_url']}" if result.get("result_url") else ""))
    else:
        print(f"❌ 发布失败: {result.get('message')}")
        if result.get("account_issue"):
            print(f"   账号问题: {result.get('issue_type')}")


if __name__ == "__main__":
```

- [ ] **Step 9: 运行测试验证通过(GREEN)**

Run:
```bash
.venv/bin/python -m pytest tests/test_examples_no_deprecated_calls.py -v
```
Expected: `2 passed`。两个测试都通过:
- `test_no_deprecated_alias_calls_in_examples`: 0 处违规
- `test_examples_use_upload_method`: ≥6 个调用者

- [ ] **Step 10: 验证所有 examples 脚本语法正确**

Run:
```bash
for f in examples/upload_to_kuaishou.py examples/upload_to_douyin.py examples/upload_video_to_baijiahao.py examples/upload_video_to_tiktok.py examples/upload_video_to_xiaohongshu.py examples/upload_video_to_tencent.py; do
    .venv/bin/python -c "import ast; ast.parse(open('$f').read()); print('OK: $f')"
done
```
Expected: 6 行 `OK: ...`,无 SyntaxError。

- [ ] **Step 11: 验证 examples 脚本能 import(验证 upload() 方法存在)**

Run:
```bash
for f in examples/upload_to_kuaishou.py examples/upload_to_douyin.py examples/upload_video_to_baijiahao.py examples/upload_video_to_tiktok.py examples/upload_video_to_xiaohongshu.py examples/upload_video_to_tencent.py; do
    .venv/bin/python -c "import importlib.util; spec = importlib.util.spec_from_file_location('m', '$f'); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print('import OK: $f')" 2>&1 | tail -1
done
```
Expected: 6 行 `import OK: ...`,无 ImportError/AttributeError。

注意:这些脚本里有 `if __name__ == '__main__'` 守卫,import 时不会自动执行发布逻辑,只会定义函数。

- [ ] **Step 12: 运行完整回归测试套件**

Run:
```bash
.venv/bin/python -m pytest tests/test_publish_engine.py tests/test_publish_dispatch.py tests/test_publish_reporter.py tests/test_publish_cli.py tests/test_examples_no_deprecated_calls.py -v
```
Expected: `152 passed`(150 原有 + 2 新增),0 failed。

- [ ] **Step 13: 提交**

Run:
```bash
git add tests/test_examples_no_deprecated_calls.py examples/upload_to_kuaishou.py examples/upload_to_douyin.py examples/upload_video_to_baijiahao.py examples/upload_video_to_tiktok.py examples/upload_video_to_xiaohongshu.py examples/upload_video_to_tencent.py
git commit -m "$(cat <<'EOF'
fix(examples): replace deleted alias calls with app.upload() + result check

sub-project B Task 9 删除了各平台 uploader 的 main() / <platform>_upload_video()
/ <platform>_upload_note() 别名。修复 examples/ 里 6 个脚本共 12 处调用,改用
app.upload() 并检查 PlatformResultExtras 返回值(success/message/result_url/
account_issue/issue_type),向用户展示新返回契约的用法。

新增 tests/test_examples_no_deprecated_calls.py 扫描 examples/ 确保无残留的
已删除别名调用。
EOF
)"
```
Expected: commit 成功,工作树干净。

---

## 完成验证

所有 4 个 task 完成后,运行最终验证:

- [ ] **最终 Step 1: 完整测试套件**

Run:
```bash
.venv/bin/python -m pytest tests/ -v
```
Expected: 所有测试通过(152+ tests,0 failed)。

- [ ] **最终 Step 2: CLI 入口验证**

Run:
```bash
.venv/bin/python publish_all.py --help 2>&1 | head -5
```
Expected: 正常输出 help 信息,无 ImportError。

- [ ] **最终 Step 3: 无 web 残留**

Run:
```bash
grep -rn "myUtils\|hgsau_backend\|hgsau_frontend\|Flask\|flask-cors\|aiohttp-cors\|5409" --include="*.py" --include="*.md" --include="*.toml" --include="*.txt" . | grep -v ".venv" | grep -v "__pycache__" | grep -v ".git/"
```
Expected: 无输出(或只有 README line 237 作者 credits 里的"封装了 api 接口和 web 前端管理界面",这是历史贡献描述,保留)。

- [ ] **最终 Step 4: 提交历史检查**

Run:
```bash
git log --oneline sub-project-b/uploader-base-class..HEAD
```
Expected: 看到 4 个 task 的 commit(删废弃代码、清依赖、更文档、修 examples)+ 可能的 spec commit。
