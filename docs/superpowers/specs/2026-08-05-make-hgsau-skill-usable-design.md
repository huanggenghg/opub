# 让 hgsau-cli skill 可用 + 发布 0.4.4 到 TestPyPI

## 背景与问题

项目有一个 agent skill 文件 `skills/hgsau-cli/SKILL.md`,目的是让大模型直接调用 `hgsau` CLI 完成多平台发布。但当前这个 skill 是**坏的**,原因有两个断层:

### 断层 1:skill 文档与代码不一致

commit `7377588`(2026-08-02)以"redundant"为由删掉了 `hgsau publish` 的 `publish` 子命令,把所有参数直接挂在 `hgsau` 下。但这次改动**只改了代码,没改文档**:

- `skills/hgsau-cli/SKILL.md` 仍教 agent 跑 `hgsau publish`
- `CLAUDE.md`、`AGENT.md`、`README.md`、`docs/CLI.md`、`docs/install.md`、`docs/update.md`、`docs/skill-distribution.md`、`docs/agent-bootstrap.md` 全部仍写 `hgsau publish`

agent 按 skill 跑 `hgsau publish` 会报 `unrecognized arguments: publish`,技能实际不可用。

实际能跑的命令是 `hgsau --platforms douyin --video xxx.mp4 --title "标题"`(无子命令)。

### 断层 2:TestPyPI 包落后于本地代码

- `pyproject.toml` 版本号:`0.4.3`
- TestPyPI 最新版本:`0.4.3`(版本号相同,但是旧构建)
- 本地代码积累了大量 fix(baijiahao/tencent/kuaishou/xiaohongshu/runtime 等),这些都没发上去
- `dist/` 里还残留 `0.4.1` 的旧构建文件

即使把文档对齐,用户从 TestPyPI 装的 `0.4.3` 仍然是旧代码,skill 跑不通。

## 目标

1. 让 `skills/hgsau-cli/SKILL.md` 里写的命令能真正跑通
2. 把本地最新代码发布到 TestPyPI,用户装到的就是能跑的版本

## 方案

**不改功能代码。** 现有 `publish_all:main` 实现已经能跑,问题只在文档和发布。

### Part 1: 文档对齐(9 个文件)

把用户/agent 面向的文档里的 `hgsau publish` 全部替换成 `hgsau`(去掉 `publish` token),prose 和 code block 都改。

**要改的文件:**

| 文件 | 性质 |
|---|---|
| `skills/hgsau-cli/SKILL.md` | skill 本体,agent 直接读这个 |
| `CLAUDE.md` | 项目指令,Claude Code 自动加载 |
| `AGENT.md` | agent 指令,含 TestPyPI token 说明 |
| `README.md` | 项目说明 |
| `docs/CLI.md` | CLI 参考 |
| `docs/install.md` | 安装指南 |
| `docs/update.md` | 更新指南 |
| `docs/skill-distribution.md` | 技能分发说明 |
| `docs/agent-bootstrap.md` | agent 启动提示词 |

**替换规则:**

- `hgsau publish` -> `hgsau`
- 例:`hgsau publish --platforms douyin --video xxx.mp4 --title "标题"` -> `hgsau --platforms douyin --video xxx.mp4 --title "标题"`
- 例:`hgsau publish --help` -> `hgsau --help`
- 例:"`hgsau publish` 会自动完成..." -> "`hgsau` 会自动完成..."

**不改的文件:**

- `docs/superpowers/specs/*.md`、`docs/superpowers/plans/*.md` -- 历史设计归档,时间戳记录,不回溯修改
- `publish/orchestrator.py` -- 代码不动,已经是能跑的形式
- `tests/test_publish_cli.py` -- 测试已经是无子命令形式,不动
- `pyproject.toml` 入口 `hgsau = "publish_all:main"` -- 不动

### Part 2: 版本号 bump

`pyproject.toml`: `0.4.3` -> `0.4.4`

选 patch bump 的理由:本次产出是文档对齐 + 累积 bug fix 发布,没有新功能。`publish` 子命令删除的接口变更已经在 0.4.3 里发生了(只是文档没跟上),不算 0.4.4 的新变更。

### Part 3: 构建 + 发布到 TestPyPI(手动)

不加固化脚本(用户偏好手动跑)。流程:

```bash
# 0. 前置:确认测试通过、hgsau --help 能跑、文档无残留 hgsau publish
grep -rn "hgsau publish" --include="*.md" . | grep -v "docs/superpowers/"
# 期望:无输出

# 1. 清理旧构建产物(dist/ 里有 stale 的 0.4.1 文件)
rm -rf dist/ build/ *.egg-info

# 2. 构建
python -m build

# 3. 发布到 TestPyPI
TWINE_USERNAME=__token__ TWINE_PASSWORD=$(cat .secrets/testpypi.token) \
  twine upload --repository testpypi dist/*

# 4. 验证(在干净环境或 venv 里)
pip install -i https://test.pypi.org/simple/ hgsau==0.4.4
hgsau --help
hgsau --platforms douyin --video videos/demo.mp4 --title "测试"
```

**token 处理**(已在 AGENT.md 记录):
- token 文件:`.secrets/testpypi.token`(已存在,gitignored)
- `TWINE_USERNAME=__token__`
- 不打印、不提交 token

### Part 4: 发布前验证

发布前必须确认:

1. **测试套件通过**:`python -m pytest tests/`(或项目惯用的测试命令)
2. **CLI 能跑**:`hgsau --help` 正常输出、`hgsau --platforms ...` 不报错
3. **文档无残留**:`grep -rn "hgsau publish" --include="*.md" . | grep -v "docs/superpowers/"` 无输出
4. **版本号一致**:`pyproject.toml` 里是 `0.4.4`,构建产物文件名也是 `0.4.4`

## 影响分析

| 项目 | 改前 | 改后 |
|---|---|---|
| `hgsau publish` | 报错 `unrecognized arguments: publish` | 仍报错(代码不改,这个形式本来就不支持) |
| `hgsau --platforms ...` | 能跑 | 能跑(不变) |
| `hgsau --help` | 能跑 | 能跑(不变) |
| `hgsau`(无参数) | 读 config 发布 | 读 config 发布(不变) |
| SKILL.md 文档命令 | 跟代码不一致(agent 跑会报错) | 跟代码一致(agent 能跑) |
| TestPyPI `0.4.4` | 不存在 | 存在,含最新代码 + 对齐文档 |
| `python publish_all.py` | 能跑(无子命令) | 能跑(不变) |

**注意:** `hgsau publish` 这个形式在改后仍然报错。这不是回归,因为代码不改,只是文档不再承诺这个形式。用户/agent 应该用 `hgsau --platforms ...` 或 `hgsau`(无参数)。

## 不在范围内

- **不恢复 `publish` 子命令** -- 用户明确要求"利用现有 publish_all 实现"
- **不加发布脚本** -- 用户明确要求手动跑
- **不改 `publish/orchestrator.py` 代码** -- 现有实现已经能跑
- **不改测试** -- 测试已经是无子命令形式
- **不碰历史 specs/plans** -- 归档文件不回溯修改
- **不发布到正式 PyPI** -- 只发 TestPyPI
- **不建 git tag** -- 项目目前没有 tag 规范,不在这件事里引入
- **不做 GitHub Actions CI** -- 项目目前无 CI,不在这件事里引入

## 验证清单

- [ ] 9 个文档里 `hgsau publish` 全部替换成 `hgsau`
- [ ] `grep -rn "hgsau publish" --include="*.md" . | grep -v "docs/superpowers/"` 无输出
- [ ] `pyproject.toml` 版本号是 `0.4.4`
- [ ] 测试套件通过
- [ ] `hgsau --help` 正常
- [ ] `dist/` 清理后重新构建,产物文件名含 `0.4.4`
- [ ] `twine upload --repository testpypi` 成功
- [ ] `pip install -i https://test.pypi.org/simple/ hgsau==0.4.4` 成功
- [ ] 装好的 `hgsau --help` 正常
