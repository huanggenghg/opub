# Sub-project D: Cleanup + Test Coverage

## 背景

Sub-project B (uploader base class extraction) 和 Sub-project C (legacy web cleanup) 都已合并到 main。两个 sub-project 的 SDD review 过程中 deferred 了一批 minor findings 到 sub-project D。这些 findings 分 8 类,sub-project D 覆盖其中 1-4 类(安全清理 + 测试覆盖),5-8 类(debavioral risks、design tradeoffs、test tooling、benign)不在范围。

Sub-project B 和 C 的 deferred findings 记录在:
- `.superpowers/sdd/2026-08-03-uploader-base-class/progress.md`
- `.superpowers/sdd/2026-08-03-cleanup-legacy-web/progress.md`

## 目标

1. 删除 requirements.txt 里的 dead dependencies(Flask transitive + alembic/SQLAlchemy/Mako)
2. 清理 `uploader/base_video.py` 里的 cookie_gen 代码 duplication 和 dead pre-check branch
3. 清理平台 uploader 里的 unused imports/params/attributes(bilibili、ks、xiaohongshu 等)
4. 补测试覆盖:WeiboNote/KSNote/DouYinNote upload() 测试、storage_state-on-failure 行为测试、cookie_gen edge case 测试
5. 保持现有 152 tests 全绿,新增 ~8-10 tests

## 范围

### Task 1: 依赖清理(requirements.txt)

删除 9 个 dead packages:
- `alembic==1.16.1`(orphaned by db/ deletion in sub-project C)
- `SQLAlchemy==2.0.41`(orphaned by db/ deletion)
- `Mako==1.3.10`(alembic 的 template 依赖,orphaned by alembic)
- `blinker==1.9.0`(Flask transitive)
- `click==8.2.1`(Flask transitive)
- `itsdangerous==2.2.0`(Flask transitive)
- `Jinja2==3.1.6`(Flask transitive)
- `MarkupSafe`(Jinja2/Mako transitive,版本在 requirements.txt 里)
- `Werkzeug`(Flask transitive,版本在 requirements.txt 里)

**验证:**
- `grep -rn "import (alembic|sqlalchemy|mako|blinker|click|itsdangerous|jinja2|markupsafe|werkzeug)" --include="*.py" .` 返回空(已确认,见 brainstorming 阶段)
- `pip install -e .` 成功
- 152 tests 全绿
- requirements.txt 仍为 UTF-16 LE 编码(用 Python 修改,不用 Edit 工具,避免编码转换)

### Task 2: base_video.py cleanup

**2a. 提取 cookie_gen save+validate duplication:**

`base_video.py` cookie_gen 方法里,以下 block 出现两次(line 265-271 pre-check branch 和 line 279-285 QR flow branch):
```python
await page.wait_for_timeout(2000)
await context.storage_state(path=account_file)
if await cls.cookie_auth(account_file):
    result = _build_login_result(True, "success", f"{cls.PLATFORM_NAME}扫码登录成功", account_file, None, page.url)
else:
    result = _build_login_result(False, "cookie_invalid", f"{cls.PLATFORM_NAME}扫码完成但 cookie 校验失败", account_file, None, page.url)
```

提取为 helper(如 `_save_state_and_validate`),两处调用 helper。行为必须完全一致(同样的 wait_for_timeout、storage_state、cookie_auth、build_result 调用顺序和参数)。

**2b. 评估 pre-check branch(line 260-271):**

pre-check branch 是 sub-project B Task 1 implementer 添加的 deviation,用于让 plan 的 test 通过。comment 说明:"In real usage new_page() starts at about:blank so this branch is skipped and the QR flow runs normally."

评估选项:
- **Option A(推荐):** 保留 pre-check branch,但提取 duplication 后变得更简洁。pre-check 是 test-only 逻辑但不影响 production(production 里 about:blank 跳过),保留比删除更安全(删除需要修改 test)。
- **Option B:** 删除 pre-check branch,修复依赖它的 test。更干净但风险更高。

Plan 阶段决定具体选项,默认 Option A。

**2c. 清理 cosmetic issues:**

移除 base_video.py 里的 extra blank lines、dead 注释等(sub-project B 各 task review 里提到的)。

**验证:**
- `tests/test_base_uploader.py`、`tests/test_base_uploader_login.py`、`tests/test_base_uploader_session.py` 全绿
- 152 tests 全绿
- cookie_gen 行为不变(同样的 login flow、同样的 return values)

### Task 3: 平台 uploader 清理

**3a. bilibili(`uploader/bilibili_uploader/main.py`):**
- 移除 `return_detail` param(main.py:68-82)- 从未被传 True,docstring 未提及
- 移除 `publish_strategy` attribute storage(main.py:39)- biliup CLI 不支持 scheduling,stored 但 unused
- `raw_output` field:确认无 consumer 后,在 docstring 里注明 return 不含 raw_output(sub-project B 已 silently dropped,这里只是文档化)

**3b. ks/xiaohongshu `self.local_executable_path`:**
- `uploader/ks_uploader/main.py` 和 `uploader/xiaohongshu_uploader/main.py` 里 `self.local_executable_path` set 但 never read
- 移除 attribute 设置(注意:baijiahao 的 `local_executable_path` 在 `ai2video` 里用到,不能删 - sub-project B final fix 已确认保留)

**3c. 残留 unused imports:**
- 扫描所有 platform uploader main.py 文件,移除残留的 unused imports
- sub-project B final fix 清了大部分,但 review 里提到一些可能残留(如 weibo 的 `_build_launch_kwargs`、`_get_qrcode_utils` 等 - 需 plan 阶段 grep 确认)

**验证:**
- `tests/test_*_uploader_base.py` 全绿
- 152 tests 全绿
- `grep -rn "local_executable_path" uploader/ks_uploader/ uploader/xiaohongshu_uploader/` 返回空
- bilibili `return_detail` 和 `publish_strategy` 不再出现

### Task 4: 测试覆盖

**4a. Note upload() 测试:**

为 3 个 Note 类添加 upload() 测试,parallel to existing Video 测试:
- `tests/test_weibo_uploader_base.py`:添加 `test_weibo_note_upload_returns_unified_dict`(parallel to existing WeiboVideo upload test)
- `tests/test_ks_uploader_base.py`:添加 `test_ks_note_upload_returns_unified_dict`
- `tests/test_douyin_uploader_base.py`:添加 `test_douyin_note_upload_returns_unified_dict`

每个测试验证:upload() 返回 PlatformResultExtras dict,包含 `success` 和 `message` 字段,success=True 时有 `result_url`。

**4b. storage_state-on-failure 行为测试:**

在 `tests/test_base_uploader_session.py` 添加测试,验证 `_browser_session` 的 finally block 行为:
- `test_browser_session_saves_storage_state_on_success`:upload 成功后,storage_state 被保存
- `test_browser_session_saves_storage_state_on_failure`:upload 抛异常后,storage_state 仍被保存(这是 sub-project B 的 deliberate design,测试文档化此行为)

**关键设计决策:** 测试 CURRENT 行为(saves on failure),NOT desired behavior。不添加 `save_on_success_only` flag,不改变行为。sub-project B 的 deferred finding 明确说这是 deliberate design,"add save_on_success_only flag if issues arise" - sub-project D 只测试,不改行为。

**4c. cookie_gen edge case 测试:**

在 `tests/test_base_uploader_login.py` 添加测试:
- `test_cookie_gen_returns_timeout_when_login_never_completes`:mock is_login_completed 始终返回 False,验证 100 次轮询后返回 `timeout` result
- `test_cookie_gen_invokes_qrcode_callback`:mock extract_qrcode_src 返回 QR URL,验证 qrcode_callback 被调用
- `test_cookie_gen_handles_exception`:mock page.goto 抛异常,验证 cookie_gen 捕获异常并返回 `failed` result

**验证:**
- 新增 ~8-10 tests
- 总测试数 ~160-162
- 全绿

## 分支策略

- 新分支:`sub-project-d/cleanup-test-coverage`,从 `main`(已含 A+B+C)拉出
- 这是第一个直接从 main 分支的 sub-project(B 从 A 的 main state 分,C 从 B 分)
- 合并回 main 后删除 feature branch

## 测试策略

### 回归测试(每个 task 都要保持)
- `pytest tests/ -v` 全绿
- Task 1-3:152 tests
- Task 4:~160-162 tests(152 + ~8-10 new)

### 删除验证(Task 1)
- `grep -rn "import (alembic|sqlalchemy|mako|blinker|click|itsdangerous|jinja2|markupsafe|werkzeug)" --include="*.py" .` 返回空
- `pip install -e .` 成功

### 行为不变验证(Task 2-3)
- cookie_gen return values 不变(test_base_uploader_login.py 全绿)
- 平台 upload() return contract 不变(test_*_uploader_base.py 全绿)

## 不在范围

- **Category 5(production behavior risks):** storage_state-on-failure fix、premature "cookie 更新完毕" log、headless inconsistency - 需 production 观察,独立 sub-project
- **Category 6(design tradeoffs):** tk anti-crawl risk、*_setup wrappers、douyin navigation inconsistency - track only,无 code 改动
- **Category 7(test tooling):** test_examples_no_deprecated_calls.py AST-based scanning - nice-to-have,低优先级
- **Category 8(benign):** CLAUDE.md commit hygiene - 无需 action
- 任何新 feature 或超出 cleanup+test 的 refactoring

## 迁移顺序(给 writing-plans 的提示)

建议拆 4 个 task,顺序执行(Task 4 依赖 Task 2-3 代码稳定):

1. **Task 1: 依赖清理** - 删 requirements.txt 9 个 dead packages。独立,无 code 改动。
2. **Task 2: base_video.py cleanup** - 提取 cookie_gen duplication,评估 pre-check branch,清理 cosmetic。
3. **Task 3: 平台 uploader 清理** - bilibili params、ks/xiaohongshu attribute、残留 imports。
4. **Task 4: 测试覆盖** - Note upload() 测试、storage_state-on-failure 测试、cookie_gen edge case 测试。

Task 1 独立。Task 2-3 触不同文件但都影响 uploader 层。Task 4 依赖 Task 2-3 完成(代码稳定后再加测试)。
