# Single Device Data Home Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every Agent running as the same operating-system user use `~/.opub` directly, without source-checkout routing or `SAU_HOME` snapshots.

**Architecture:** `conf.py` and the licensing storage helper both resolve the data root from `Path.home()`. Existing consumers continue using `BASE_DIR`; the Bilibili runtime already uses the same home directory. Tests assert that repository state and `SAU_HOME` cannot create a second data root.

**Tech Stack:** Python 3.9+, pathlib, pytest/unittest, setuptools/uv packaging

---

### Task 1: Lock the path contract with failing tests

**Files:**
- Modify: `tests/test_conf_pip_mode.py`
- Modify: `tests/test_license_storage.py`
- Modify: `tests/test_login_headed_defaults.py`
- Modify: `tests/test_license_e2e.py`

- [ ] Replace the `SAU_HOME` override assertions with an assertion that `conf.BASE_DIR == Path.home() / ".opub"` even when `SAU_HOME` points elsewhere.
- [ ] Assert that licensing `data_dir()` returns the same home path and ignores `SAU_HOME`.
- [ ] Remove test setup that depends on changing the production data root through the environment; use an explicit patched license path where isolation is needed.
- [ ] Run `.venv/bin/python -m pytest tests/test_conf_pip_mode.py tests/test_license_storage.py tests/test_login_headed_defaults.py tests/test_license_e2e.py -q` and confirm failures identify the old override/source behavior.

### Task 2: Use one home directory in production

**Files:**
- Modify: `conf.py`
- Modify: `publish/licensing/storage.py`

- [ ] Change `_detect_mode()` to return `(Path.home() / ".opub").resolve()` with no repository or environment branches.
- [ ] Change licensing `data_dir()` to use the same path while retaining the explicit `home` argument for isolated unit tests.
- [ ] Run the focused tests and confirm they pass.

### Task 3: Document the Agent contract and bump the package

**Files:**
- Modify: `README.md`
- Modify: `docs/CLI.md`
- Modify: `docs/issue-2026-09-19-tencent-ks-bili.md`
- Modify: `conf.example.py`
- Modify: `skills/opub-cli/SKILL.md`
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `tests/test_package_build.py`

- [ ] Document `~/.opub` as the only runtime data directory on all supported systems and remove `SAU_HOME` setup instructions.
- [ ] Record that the prior WorkBuddy workaround is retired after direct file and SQLite verification.
- [ ] Bump version `0.8.16` to `0.8.17` in package, lock file, skill metadata, and version consistency test.
- [ ] Run the focused tests, complete suite, package build, and wheel installation smoke test.

### Task 4: Consolidate this device and release

**Files:**
- Runtime data only: `~/.opub/cookies/`

- [ ] Compare canonical account files without printing credential contents; keep the currently verified/newer file per platform in `~/.opub/cookies/`.
- [ ] Back up both publish-history databases, merge non-conflicting runs and entries into `~/.opub/publish-history.sqlite3` in one transaction, and require `PRAGMA integrity_check` to return `ok`.
- [ ] Review the tracked diff, commit only task files, push `main`, wait for remote CI, publish `0.8.17` to PyPI, tag `v0.8.17`, and verify a clean installation reports the new version and home directory.
