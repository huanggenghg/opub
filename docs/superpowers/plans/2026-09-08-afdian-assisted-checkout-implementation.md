# Afdian Assisted Checkout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `opub --activate` explain that buyers do not need to pre-register Afdian, while keeping verification and credentials under the buyer's control.

**Architecture:** Keep the current Afdian product URL and activation-code exchange unchanged. Add one focused CLI guidance function called whenever the purchase page is opened, then align all public documentation and the Agent skill with the same account and privacy boundary.

**Tech Stack:** Python 3, argparse CLI, pytest, unittest.mock, Markdown contract tests

---

## File Structure

- `publish/orchestrator.py`: display purchase guidance when `--activate` opens the Afdian page.
- `tests/test_license_cli.py`: verify the runtime guidance for successful and failed browser opening.
- `tests/test_publish_cli.py`: enforce consistent wording across public documentation.
- `README.md`: describe the buyer-facing checkout accurately.
- `AGENT.md`: define the repository Agent contract for self-service Afdian verification.
- `docs/CLI.md`: document interactive and non-interactive activation behavior.
- `skills/opub-cli/SKILL.md`: tell installed Agents how to guide a buyer without handling credentials.

### Task 1: Add buyer-safe guidance to `opub --activate`

**Files:**
- Modify: `tests/test_license_cli.py:132-260`
- Modify: `publish/orchestrator.py:382-390`

- [ ] **Step 1: Write the failing runtime test**

Add this test after `test_noninteractive_activate_opens_purchase_page_and_exits_13`:

```python
def test_activate_explains_self_service_registration_and_private_credentials():
    stdout = io.StringIO()
    with patch("publish.orchestrator.sys.stdin.isatty", return_value=False), \
         patch("publish.orchestrator.webbrowser.open", return_value=True), \
         contextlib.redirect_stdout(stdout):
        assert publish_all.main(["--activate"]) == EXIT_LICENSE_ERROR

    output = stdout.getvalue()
    assert "无需提前注册爱发电" in output
    assert "你自己的手机号或邮箱" in output
    assert "爱发电会自动生成账号" in output
    assert "请勿向 Agent 提供验证码或账号密码" in output
```

- [ ] **Step 2: Run the new test and verify RED**

Run:

```bash
pytest -q tests/test_license_cli.py::test_activate_explains_self_service_registration_and_private_credentials
```

Expected: FAIL because `stdout` does not yet contain `无需提前注册爱发电`.

- [ ] **Step 3: Write the minimal guidance function**

Add this function immediately before `_open_license_purchase_page` and call it at the end of `_open_license_purchase_page`, whether or not the browser opened successfully:

```python
def _print_license_purchase_guidance() -> None:
    print(
        "[opub] 无需提前注册爱发电：请使用你自己的手机号或邮箱完成验证，"
        "首次购买时爱发电会自动生成账号。"
    )
    print(
        "[opub] 付款后复制爱发电发放的激活码；"
        "请勿向 Agent 提供验证码或账号密码。"
    )


def _open_license_purchase_page() -> None:
    try:
        opened = bool(webbrowser.open(LICENSE_PURCHASE_URL))
    except Exception:
        opened = False
    except KeyboardInterrupt:
        opened = False
    if not opened:
        print(f"[opub] 无法自动打开购买页，请手动打开: {LICENSE_PURCHASE_URL}")
    _print_license_purchase_guidance()
```

- [ ] **Step 4: Update exact-output assertions and verify GREEN**

In browser-failure tests that currently compare `stdout.getvalue()` to only the manual URL line, append these exact two lines to the expected string:

```python
"[opub] 无需提前注册爱发电：请使用你自己的手机号或邮箱完成验证，首次购买时爱发电会自动生成账号。\n"
"[opub] 付款后复制爱发电发放的激活码；请勿向 Agent 提供验证码或账号密码。\n"
```

Run:

```bash
pytest -q tests/test_license_cli.py
```

Expected: all tests in `tests/test_license_cli.py` PASS.

- [ ] **Step 5: Commit the runtime behavior**

```bash
git add publish/orchestrator.py tests/test_license_cli.py
git commit -m "feat: guide buyers through afdian activation"
```

### Task 2: Correct the public account contract

**Files:**
- Modify: `tests/test_publish_cli.py:223-366`
- Modify: `README.md:66-76`
- Modify: `AGENT.md:94-106`
- Modify: `docs/CLI.md:36-57`
- Modify: `skills/opub-cli/SKILL.md:78-83`

- [ ] **Step 1: Change documentation contract tests first**

In both paid-license fragment lists in `tests/test_publish_cli.py`, replace `"不需账号"` with:

```python
"opub 自身不设账号",
"无需提前注册爱发电",
"你自己的手机号或邮箱",
"爱发电会自动生成账号",
"请勿向 Agent 提供验证码或账号密码",
```

After each fragment loop, add:

```python
self.assertNotIn("不需账号", text)
```

- [ ] **Step 2: Run the documentation tests and verify RED**

Run:

```bash
pytest -q tests/test_publish_cli.py::SkillDocBlackboxTests::test_documents_paid_license_contract_and_agent_flow tests/test_publish_cli.py::PublicSingleAccountContractTests::test_public_docs_share_paid_license_contract
```

Expected: FAIL because the four public documents still contain `不需账号` and do not contain the new guidance.

- [ ] **Step 3: Update all four public documents**

Replace the inaccurate account sentence in each paid-license section with this shared wording, preserving the surrounding price, device-binding, version and DRM details:

```markdown
opub 自身不设账号。购买时无需提前注册爱发电；请使用你自己的手机号或邮箱完成验证，首次购买时爱发电会自动生成账号。付款后复制爱发电发放的激活码；请勿向 Agent 提供验证码或账号密码。
```

In `AGENT.md`, `docs/CLI.md`, and `skills/opub-cli/SKILL.md`, also make the activation flow explicit:

```markdown
Agent 只负责打开购买页和接收用户付款后提供的激活码，不得代填或索取手机号、邮箱验证码、爱发电账号或密码。
```

- [ ] **Step 4: Run the documentation tests and verify GREEN**

Run:

```bash
pytest -q tests/test_publish_cli.py
```

Expected: all tests in `tests/test_publish_cli.py` PASS.

- [ ] **Step 5: Commit the contract update**

```bash
git add README.md AGENT.md docs/CLI.md skills/opub-cli/SKILL.md tests/test_publish_cli.py
git commit -m "docs: clarify afdian assisted checkout"
```

### Task 3: Verify the complete change

**Files:**
- Verify only; no planned production file changes.

- [ ] **Step 1: Run focused license and documentation tests**

```bash
pytest -q tests/test_license_cli.py tests/test_publish_cli.py
```

Expected: all focused tests PASS with zero failures.

- [ ] **Step 2: Run the full repository test suite**

```bash
pytest -q
```

Expected: the complete test suite PASS with zero failures.

- [ ] **Step 3: Check formatting and accidental changes**

```bash
git diff --check HEAD~2..HEAD
git status --short
```

Expected: `git diff --check` produces no output. `git status --short` shows only the user's pre-existing untracked files, not modified tracked implementation files.

- [ ] **Step 4: Review the scope against the design**

Confirm all of the following from the diff and test output:

- The Afdian product URL and license API URL are unchanged.
- No phone number, email, verification code or password is collected or persisted.
- `--activate --code` still skips the browser and guidance.
- Interactive and non-interactive `--activate` both show guidance when opening the purchase page.
- No release, PyPI publish or production deployment is included in this change.
