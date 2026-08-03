# Sub-project C: 清理废弃 Web 版本 + 修复 examples 断链

## 背景

项目当前定位是 **CLI + 脚本实现为主,不涉及前后端页面**。但仓库里仍保留着 2025-06-03 一次性提交的完整 Web 管理系统(Flask backend + Vue.js frontend),以及配套的 `myUtils/` 桥接层。`docs/legacy-web.md` 已明确标注这部分为"历史遗留,不是主线维护方向"。

Sub-project B(Task 9)删除了各平台 uploader 的 `main()` / `<platform>_upload_video()` / `<platform>_upload_note()` 别名 wrapper,造成两处断链:
1. `myUtils/postVideo.py` 调用 `app.main()` / `app.douyin_upload_video()` - 但 myUtils/ 本身是废弃代码
2. `examples/` 里 6 个脚本调用同样的已删除别名 - 这些是 CLI 主线的参考脚本,**需要修复**

本 sub-project 彻底清理废弃 Web 版本,并修复 examples 断链。

## 目标

1. 删除所有废弃 Web 相关代码(myUtils/、hgsau_backend.py、hgsau_frontend/、Dockerfile、db/、hgsau_backend/、docs/legacy-web.md)
2. 清理依赖(requirements.txt、pyproject.toml 里的 web 依赖)
3. 更新文档(README.md、CLAUDE.md)反映 CLI-only 定位
4. 修复 examples/ 里 6 个脚本,改用 `app.upload()` 并展示 `PlatformResultExtras` 返回契约
5. 不破坏 CLI 主线(`python publish_all.py` 和 `hgsau publish` 仍正常工作)

## 范围

### 删除的文件/目录

| 路径 | 内容 | 删除理由 |
|---|---|---|
| `myUtils/` | postVideo.py(91 行)、auth.py(120 行)、login.py(320 行)、\_\_init\_\_.py | 只有 hgsau_backend.py 调用,且代码已废弃 |
| `hgsau_backend.py` | Flask backend(~718 行) | 废弃的 Web 服务器,缺 flask_cors 依赖无法运行 |
| `hgsau_backend/` | README.md 残留 | 旧 backend 目录残留 |
| `hgsau_frontend/` | 整个 Vue.js 前端(数千行) | 废弃的 Web 前端 |
| `Dockerfile` | 多阶段构建:Vue build + Flask serve | 纯 Web 部署用,CLI 不需要 |
| `db/createTable.py` | 建表脚本(36 行) | 建的 `user_info` / `file_records` 表只有 web backend 用 |
| `db/database.db` | 空文件(0 字节) | web backend 专用,CLI 不碰 sqlite |
| `docs/legacy-web.md` | legacy 说明(50 行) | 删除 legacy 代码后此文档无意义 |

### 修改的文件

#### `requirements.txt`
删除三行:
- `Flask[async]==3.1.1`
- `flask-cors==6.0.0`
- `aiohttp-cors==0.8.1`(代码里完全没用,顺手清掉)

#### `pyproject.toml`
删除 `[project.optional-dependencies]` 下的 `web = [...]` 段:
```toml
web = [
  "Flask[async]==3.1.1",
  "flask-cors==6.0.0",
]
```

#### `README.md`
删除 line 103:"历史 Web 说明请看:[历史 Web 版本说明](./docs/legacy-web.md)"(因为 docs/legacy-web.md 要删)

注:line 237 "封装了 api 接口和 web 前端管理界面" 在作者 credits 区,描述作者历史贡献,保留不动。

#### `CLAUDE.md`
重写以下两段,反映 CLI-only 定位:

**Project Overview 段**(当前 line 11-32):
- 删除"The project consists of a Python backend and a Vue.js frontend."
- 删除 Backend / Frontend 两个子段(Flask、RESTful API、SSE、Vue.js、Vite、Element Plus、Pinia、Vue Router 等)
- 保留 Command-line Interface 段(已经是 CLI 描述)

**Building and Running 段**(当前 line 67-89):
- 删除"Run the backend server: `python hgsau_backend.py`"步骤
- 删除"Frontend"整个子段(`cd hgsau_frontend`、`npm install`、`npm run dev`)

**Development Conventions 段**(当前 line 108-113):
- 删除"the `myUtils` and `uploader` directories"里的 `myUtils`
- 删除"the frontend code is located in the `hgsau_frontend` directory"
- 删除"the `package.json` file in the `hgsau_frontend` directory"

### 修复的文件(examples/)

6 个脚本,共约 12 处调用。修复模式:`app.<deprecated_alias>()` -> `result = app.upload()`,并检查返回值。

| 脚本 | 当前调用 | 修复后 |
|---|---|---|
| `examples/upload_to_kuaishou.py` | `asyncio.run(app.main())` x2 | `result = asyncio.run(app.upload())` + 结果检查 |
| `examples/upload_to_douyin.py` | `app.douyin_upload_video()`、`app.douyin_upload_note()` | `app.upload()` + 结果检查 |
| `examples/upload_video_to_baijiahao.py` | `asyncio.run(app.main())` | `app.upload()` + 结果检查 |
| `examples/upload_video_to_tiktok.py` | `asyncio.run(app.main())` | `app.upload()` + 结果检查 |
| `examples/upload_video_to_xiaohongshu.py` | `app.xiaohongshu_upload_video()`、`app.xiaohongshu_upload_note()` | `app.upload()` + 结果检查 |
| `examples/upload_video_to_tencent.py` | `app.tencent_upload_video()` x2、`app.tencent_upload_note()` x2 | `app.upload()` + 结果检查 |

**examples 修复模板**(展示 PlatformResultExtras 契约):

```python
result = asyncio.run(app.upload())
if result.get("success"):
    print(f"✅ 发布成功" + (f",链接: {result['result_url']}" if result.get("result_url") else ""))
else:
    print(f"❌ 发布失败: {result.get('message')}")
    if result.get("account_issue"):
        print(f"   账号问题: {result.get('issue_type')}")
```

每个脚本在调用 `app.upload()` 后,用这个模板处理返回值。这样 examples 既修复了断链,又向用户展示了新返回契约的用法(success / message / result_url / account_issue / issue_type)。

## 分支策略

- sub-project C 从 `sub-project-b/uploader-base-class` 分支拉出新分支(不是 main),因为 examples 修复依赖 sub-project B 的新 `upload()` 方法
- 新分支名:`sub-project-c/cleanup-legacy-web`
- 最终 sub-project B + C 一起合并到 main(顺序:C 合并到 B 的分支,然后 B 的分支合并到 main;或者 C 直接基于 B rebase 后一起 PR)

## 测试策略

### 回归测试(CLI 主线不破坏)
- `tests/test_publish_engine.py` / `tests/test_publish_dispatch.py` / `tests/test_publish_reporter.py` / `tests/test_publish_cli.py` 全绿(150 tests,sub-project B 最终状态)
- `python publish_all.py --help` 正常输出
- examples 脚本能 import 成功(不需要真跑发布,只验证 `app.upload()` 方法存在且可调用)

### examples 修复验证
- 每个 examples 脚本 `python -c "import ast; ast.parse(open('examples/<script>.py').read())"` 语法通过
- `grep -rn "app.main()\|douyin_upload_video()\|tencent_upload_video()\|tencent_upload_note()\|xiaohongshu_upload_video()\|xiaohongshu_upload_note()" examples/` 返回空

### 删除验证
- `grep -rn "myUtils\|hgsau_backend\|hgsau_frontend" --include="*.py" --include="*.md" --include="*.toml"` 除了 git 历史外无残留
- `python -c "import publish_all"` 仍能成功(CLI 入口不依赖任何已删代码)

## 不在范围

- `uploader/` 目录的进一步重构(sub-project B 已完成)
- `publish/` 包的重构(sub-project A 已完成)
- sub-project D 的 deferred minor findings 清理(独立的清理子项目)
- 真实平台发布测试(需要网络和账号,不在 CI 范围)
- 保留任何 Web 版本的迁移路径(彻底删除,不保留向后兼容)

## 迁移顺序(给 writing-plans 的提示)

建议拆成 4 个 task:

1. **Task 1: 删除废弃代码** - 删 myUtils/、hgsau_backend.py、hgsau_backend/、hgsau_frontend/、Dockerfile、db/、docs/legacy-web.md。验证 CLI 回归网全绿。
2. **Task 2: 清理依赖** - 改 requirements.txt、pyproject.toml。验证 `pip install -e .` 仍成功,CLI 回归网全绿。
3. **Task 3: 更新文档** - 改 README.md、CLAUDE.md。纯文档改动,无代码影响。
4. **Task 4: 修复 examples** - 改 6 个脚本的 ~12 处调用,用 `app.upload()` + 结果检查模板。验证语法和 import。

Task 1-3 互相独立,Task 4 依赖 sub-project B 的 `upload()` 方法存在(已满足)。每个 task 保持 CLI 回归网全绿。
