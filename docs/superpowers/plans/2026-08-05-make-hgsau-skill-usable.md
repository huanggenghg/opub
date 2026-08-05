# hgsau skill 对齐 + 0.4.4 TestPyPI 发布 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `skills/hgsau-cli/SKILL.md` 里写的命令能真正跑通,并把本地最新代码发布到 TestPyPI as `0.4.4`。

**Architecture:** 不改功能代码。现有 `publish_all:main` 已经能跑(无子命令形式 `hgsau --platforms ...`),问题只在文档还写着 `hgsau publish`(commit `7377588` 删了子命令但没改文档)。把 9 个文档里的 `hgsau publish` 全部替换成 `hgsau`,bump 版本号到 `0.4.4`,然后构建发布到 TestPyPI。

**Tech Stack:** Python 3.9+, setuptools, twine, unittest(179 个测试)

## Global Constraints

- **不改功能代码** -- `publish/orchestrator.py`、`publish_all.py`、`tests/` 全部不动
- **不加发布脚本** -- 用户明确要求手动跑
- **不碰 `docs/superpowers/specs/*.md` 和 `docs/superpowers/plans/*.md`** -- 历史归档,不回溯修改
- **不发布到正式 PyPI** -- 只发 TestPyPI
- **不建 git tag** -- 项目无 tag 规范,不在此引入
- **不做 GitHub Actions CI** -- 项目无 CI,不在此引入
- **版本号 `0.4.4`** -- patch bump,写在 `pyproject.toml` 第 7 行
- **TestPyPI token** -- 在 `.secrets/testpypi.token`(已存在,gitignored),`TWINE_USERNAME=__token__`,不打印不提交
- **替换规则** -- `hgsau publish` -> `hgsau`(去掉 `publish` token),prose 和 code block 都改
- **替换范围** -- 只改 9 个文件(见 Task 1 文件列表),其他文件包括 `docs/superpowers/` 下的历史归档不动

## File Structure

**要修改的文件(10 个):**

| 文件 | 改动 | `hgsau publish` 出现次数 |
|---|---|---|
| `skills/hgsau-cli/SKILL.md` | `hgsau publish` -> `hgsau` | 10 |
| `CLAUDE.md` | 同上 | 3 |
| `AGENT.md` | 同上 | 8 |
| `README.md` | 同上 | 6 |
| `docs/CLI.md` | 同上 | 7 |
| `docs/install.md` | 同上 | 7 |
| `docs/update.md` | 同上 | 4 |
| `docs/skill-distribution.md` | 同上 | 4 |
| `docs/agent-bootstrap.md` | 同上 | 7 |
| `pyproject.toml` | `version = "0.4.3"` -> `version = "0.4.4"`(第 7 行) | N/A |

**不碰的文件:**
- `publish/orchestrator.py` -- 代码不改,已经是能跑的无子命令形式
- `publish_all.py` -- 薄壳,不改
- `tests/test_publish_cli.py` -- 测试已经是无子命令形式
- `docs/superpowers/specs/*.md`、`docs/superpowers/plans/*.md` -- 历史归档
- `pyproject.toml` 的 `hgsau = "publish_all:main"` 入口 -- 不改(entry point 定义,不是 `hgsau publish` 命令)

**构建产物(不提交):**
- `dist/hgsau-0.4.4-py3-none-any.whl`
- `dist/hgsau-0.4.4.tar.gz`

---

### Task 1: 文档对齐 -- `hgsau publish` -> `hgsau`

**Files:**
- Modify: `skills/hgsau-cli/SKILL.md`(10 处)
- Modify: `CLAUDE.md`(3 处)
- Modify: `AGENT.md`(8 处)
- Modify: `README.md`(6 处)
- Modify: `docs/CLI.md`(7 处)
- Modify: `docs/install.md`(7 处)
- Modify: `docs/update.md`(4 处)
- Modify: `docs/skill-distribution.md`(4 处)
- Modify: `docs/agent-bootstrap.md`(7 处)

**Interfaces:**
- Consumes: 无(第一个任务)
- Produces: 9 个文档里不再出现 `hgsau publish`,agent 按 SKILL.md 跑 `hgsau --platforms ...` 能成功

**共 56 处替换,全部是 `hgsau publish` -> `hgsau`(去掉 `publish` token)。**

- [ ] **Step 1: 用 sed 批量替换 9 个文件**

macOS sed 语法(`-i ''` 表示无备份文件):

```bash
sed -i '' 's/hgsau publish/hgsau/g' \
  skills/hgsau-cli/SKILL.md \
  CLAUDE.md \
  AGENT.md \
  README.md \
  docs/CLI.md \
  docs/install.md \
  docs/update.md \
  docs/skill-distribution.md \
  docs/agent-bootstrap.md
```

- [ ] **Step 2: 验证 9 个文件里没有残留 `hgsau publish`**

Run:
```bash
grep -rn "hgsau publish" \
  skills/hgsau-cli/SKILL.md \
  CLAUDE.md \
  AGENT.md \
  README.md \
  docs/CLI.md \
  docs/install.md \
  docs/update.md \
  docs/skill-distribution.md \
  docs/agent-bootstrap.md
```

Expected: 无输出(所有 9 个文件都已清理干净)

- [ ] **Step 3: 验证历史归档未被误改**

Run:
```bash
grep -rl "hgsau publish" docs/superpowers/ | wc -l
```

Expected: `4`(specs + plans 里仍有 4 个文件含 `hgsau publish`,这些是历史归档,不动)

如果输出不是 4,说明 sed 误碰了 `docs/superpowers/`,需要 `git checkout docs/superpowers/` 恢复。

- [ ] **Step 4: 抽查 3 个文件确认替换读起来通顺**

Read 并确认以下文件里 `hgsau publish` 已变成 `hgsau`,且句子读得通:

1. `skills/hgsau-cli/SKILL.md` -- 检查"推荐流程"和"配置原则"两节
2. `docs/CLI.md` -- 检查"快速开始"和"运行时行为"两节
3. `CLAUDE.md` -- 检查"Command-line Interface"小节

重点确认:
- `hgsau publish --help` 变成了 `hgsau --help`
- `hgsau publish --platforms douyin,weibo --video videos/demo.mp4 --title "标题"` 变成了 `hgsau --platforms douyin,weibo --video videos/demo.mp4 --title "标题"`
- "`hgsau publish` 会自动完成..." 变成了 "`hgsau` 会自动完成..."

- [ ] **Step 5: Commit**

```bash
git add \
  skills/hgsau-cli/SKILL.md \
  CLAUDE.md \
  AGENT.md \
  README.md \
  docs/CLI.md \
  docs/install.md \
  docs/update.md \
  docs/skill-distribution.md \
  docs/agent-bootstrap.md
git commit -m "$(cat <<'EOF'
docs: align hgsau CLI references with actual no-subcommand interface

commit 7377588 dropped the 'publish' subcommand but docs never caught up.
Replace 'hgsau publish' with 'hgsau' across 9 user/agent-facing docs so
the skill and CLI contract match. No code changes.
EOF
)"
```

---

### Task 2: 版本号 bump 0.4.3 -> 0.4.4

**Files:**
- Modify: `pyproject.toml:7`(`version = "0.4.3"` -> `version = "0.4.4"`)

**Interfaces:**
- Consumes: 无(独立于 Task 1)
- Produces: `pyproject.toml` 版本号为 `0.4.4`,构建产物文件名含 `0.4.4`,TestPyPI 能接受上传(同版本号 `0.4.3` 已存在,不 bump 会被拒)

- [ ] **Step 1: 改 pyproject.toml 版本号**

把第 7 行的:
```toml
version = "0.4.3"
```
改成:
```toml
version = "0.4.4"
```

用 Edit 工具,`old_string` = `version = "0.4.3"`,`new_string` = `version = "0.4.4"`。

- [ ] **Step 2: 验证版本号**

Run:
```bash
grep '^version' pyproject.toml
```

Expected:
```
version = "0.4.4"
```

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: bump version to 0.4.4 for testpypi release"
```

---

### Task 3: 发布前验证

**Files:** 无修改,纯验证。

**Interfaces:**
- Consumes: Task 1(文档对齐)+ Task 2(版本号 0.4.4)
- Produces: 确认本地代码 + 文档 + 版本号都就绪,可以安全发布到 TestPyPI

**这个任务不产生 commit,只做验证。任何一步失败都必须解决后才能进入 Task 4。**

- [ ] **Step 1: 跑测试套件(基线)**

Run:
```bash
python -m unittest discover -s tests --top-level-directory .
```

Expected: `Ran 179 tests in ...` 最后是 `OK`。

如果测试失败,**不要继续发布**。先排查失败原因,修好后再继续。因为本次不改代码,测试应该全部通过(跟改前一样)。

- [ ] **Step 2: 验证 `hgsau` CLI 能跑**

Run:
```bash
hgsau --help
```

Expected: 输出 argparse 帮助信息,包含 `--platforms`、`--video`、`--title`、`--config`、`--schedule`、`--start-from`、`--force` 等参数说明,`prog` 显示为 `hgsau`。

如果 `hgsau` 命令找不到,先跑 `uv pip install -e .` 重新安装。

- [ ] **Step 3: 验证文档无残留 `hgsau publish`(排除历史归档)**

Run:
```bash
grep -rn "hgsau publish" --include="*.md" . | grep -v "docs/superpowers/" | grep -v "node_modules" | grep -v ".egg-info"
```

Expected: 无输出。

如果有输出,说明 Task 1 漏了文件,回 Task 1 补上。

- [ ] **Step 4: 验证版本号一致**

Run:
```bash
grep '^version' pyproject.toml
```

Expected:
```
version = "0.4.4"
```

- [ ] **Step 5: 确认 `.secrets/testpypi.token` 存在**

Run:
```bash
test -f .secrets/testpypi.token && echo "token exists" || echo "token MISSING"
```

Expected: `token exists`

如果缺失,不要继续。问用户要 token,放到 `.secrets/testpypi.token`(单行,纯 token 字符串,无 `pypi-` 前缀也行,twine 都认)。

---

### Task 4: 构建 + 发布到 TestPyPI

**Files:** 无源码修改,产生构建产物(`dist/`,gitignored,不提交)。

**Interfaces:**
- Consumes: Task 1 + Task 2 + Task 3(全部验证通过)
- Produces: TestPyPI 上有 `hgsau==0.4.4` 包,用户 `pip install -i https://test.pypi.org/simple/ hgsau==0.4.4` 能装到含最新代码 + 对齐文档的版本

**这个任务不产生 commit。构建产物在 `dist/`(gitignored)。**

**前置条件:Task 3 所有步骤都通过。任何一项失败都不能开始本任务。**

- [ ] **Step 1: 清理旧构建产物**

`dist/` 里有 stale 的 `0.4.1` 构建文件,必须清掉避免误传:

Run:
```bash
rm -rf dist/ build/ *.egg-info
ls dist/ 2>/dev/null || echo "dist/ cleaned"
```

Expected: `dist/ cleaned`

- [ ] **Step 2: 构建 wheel + sdist**

Run:
```bash
python -m build
```

Expected: 输出 build 日志,最后类似:
```
Successfully built hgsau-0.4.4-py3-none-any.whl hgsau-0.4.4.tar.gz
```

- [ ] **Step 3: 验证构建产物**

Run:
```bash
ls -la dist/
```

Expected: 两个文件,文件名都含 `0.4.4`:
```
dist/hgsau-0.4.4-py3-none-any.whl
dist/hgsau-0.4.4.tar.gz
```

如果文件名是 `0.4.3` 或其他,说明 Task 2 没改对,回 Task 2 修。

- [ ] **Step 4: 上传到 TestPyPI**

Run:
```bash
TWINE_USERNAME=__token__ TWINE_PASSWORD=$(cat .secrets/testpypi.token) \
  twine upload --repository testpypi dist/*
```

Expected: 输出上传进度,最后类似:
```
Uploading hgsau-0.4.4-py3-none-any.whl
100%|██████████| ...
Uploading hgsau-0.4.4.tar.gz
100%|██████████| ...

View at:
https://test.pypi.org/project/hgsau/0.4.4/
```

**注意:**
- `TWINE_PASSWORD=$(cat .secrets/testpypi.token)` 会展开 token,但不会打印到终端
- 如果 twine 提示 `twine: command not found`,先 `pip install twine`
- 如果上传报 `400 File already exists`,说明 TestPyPI 上已有 `0.4.4`(可能之前传过),需要回 Task 2 bump 到 `0.4.5` 再重新构建上传

- [ ] **Step 5: 验证 TestPyPI 上的版本**

Run:
```bash
curl -s "https://test.pypi.org/pypi/hgsau/json" | python3 -c "import sys,json; d=json.load(sys.stdin); print('latest:', d['info']['version'])"
```

Expected:
```
latest: 0.4.4
```

- [ ] **Step 6: 从 TestPyPI 安装并验证 CLI 可跑**

在干净环境(新 venv 或系统 Python)里:

Run:
```bash
pip install -i https://test.pypi.org/simple/ hgsau==0.4.4
hgsau --help
```

Expected:
- `pip install` 成功
- `hgsau --help` 输出跟 Step 2 一样的帮助信息

**注意:** 如果在项目根目录跑,`pip install -e .` 的本地安装可能覆盖 TestPyPI 包。建议在项目目录外跑,或用新 venv:
```bash
python -m venv /tmp/hgsau-verify
source /tmp/hgsau-verify/bin/activate
pip install -i https://test.pypi.org/simple/ hgsau==0.4.4
hgsau --help
deactivate
rm -rf /tmp/hgsau-verify
```

- [ ] **Step 7: 验证安装的包里文档已对齐**

Run(在 TestPyPI 安装的环境里):
```bash
python -c "import skills.hgsau_cli; print(open('skills/hgsau-cli/SKILL.md').read())" 2>/dev/null || \
pip show -f hgsau | grep -i skill
```

或者直接确认 TestPyPI 上的 SKILL.md 不含 `hgsau publish`:

Run:
```bash
curl -s "https://test.pypi.org/packages/source/h/hgsau/hgsau-0.4.4.tar.gz" | \
  tar -xzf - -O hgsau-0.4.4/skills/hgsau-cli/SKILL.md 2>/dev/null | \
  grep -c "hgsau publish" || echo "0"
```

Expected: `0`(SKILL.md 里无 `hgsau publish`)

**注意:** 如果包结构里没有 `skills/` 目录(因为 `pyproject.toml` 的 `tool.setuptools.packages.find` 只 `include = ["uploader*", "utils*", "publish*"]`),这步可能取不到 SKILL.md。这种情况下,SKILL.md 本来就不会随包安装,agent 是从仓库读的,不是从包读的。这没关系 -- 确认仓库里的 SKILL.md 已对齐(Task 1 已做)就够。

---

## Self-Review

### 1. Spec coverage

| Spec 要求 | 对应任务 |
|---|---|
| Part 1: 9 个文档 `hgsau publish` -> `hgsau` | Task 1 |
| Part 2: 版本号 0.4.3 -> 0.4.4 | Task 2 |
| Part 3: 构建 + 发布到 TestPyPI(手动,无脚本) | Task 4 |
| Part 4: 发布前验证(测试/CLI/文档/版本) | Task 3 |
| 不改功能代码 | Global Constraints + 全部任务不碰 `publish/`、`tests/` |
| 不加发布脚本 | Global Constraints + Task 4 是手动命令 |
| 不碰历史 specs/plans | Global Constraints + Task 1 Step 3 验证 |
| 不发正式 PyPI | Global Constraints + Task 4 用 `--repository testpypi` |
| 不建 git tag | Global Constraints(无建 tag 步骤) |
| 不做 CI | Global Constraints(无 CI 步骤) |

无遗漏。

### 2. Placeholder scan

- 无 TBD/TODO/"implement later"
- 所有步骤都有具体命令和 expected output
- sed 命令列出全部 9 个文件,不用通配符(避免误碰 `docs/superpowers/`)
- 替换规则有具体例子(`hgsau publish --help` -> `hgsau --help` 等)

### 3. Type consistency

- 版本号 `0.4.4` 在 Task 2、Task 3 Step 4、Task 4 Step 3/4/5/6 全部一致
- 文件列表在 Task 1 和 File Structure 一致(9 个文件)
- 测试命令 `python -m unittest discover -s tests --top-level-directory .` 在 Task 3 Step 1 用,跟探索阶段确认的命令一致
- token 路径 `.secrets/testpypi.token` 在 Global Constraints、Task 3 Step 5、Task 4 Step 4 一致

无不一致。
