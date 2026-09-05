# opub License Client and Rollout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gate every `opub` CLI publish behind a permanent device-bound license, automate WeChat/Alipay activation through the three-endpoint service, and ship the updated Agent skill safely.

**Architecture:** The client derives a privacy-preserving device hash, verifies a locally stored Ed25519 document without network access, and only contacts the service during `--activate`. CLI command dispatch happens before publishing so help/version/status/activation remain free while publishing stops before preflight, cookies, browsers, and uploads.

**Tech Stack:** Python 3.9+, argparse, requests, cryptography, qrcode, unittest/pytest, setuptools, Twine.

---

## File map

- `publish/licensing/__init__.py`: public licensing exports.
- `publish/licensing/fingerprint.py`: platform-specific stable identifiers and SHA-256 device hash.
- `publish/licensing/storage.py`: `~/.opub` paths and mode-0600 atomic JSON writes.
- `publish/licensing/verifier.py`: schema/product/device/signature validation.
- `publish/licensing/api.py`: three-endpoint activation API client.
- `publish/licensing/activation.py`: session recovery, checkout opening, polling, and installation.
- `publish/licensing/deployment.py`: generated public service URL and trusted Ed25519 public key only.
- `publish/orchestrator.py`: licensing flags, free command dispatch, and publish gate.
- `publish/errors.py`: license exit code 13.
- `tests/test_license_*.py`: unit and simulated end-to-end coverage.
- `AGENT.md`, `skills/opub-cli/SKILL.md`, `README.md`, `docs/CLI.md`: user and Agent contract.

This plan starts only after the server completion gate in `2026-09-05-license-server-implementation.md` passes.

### Task 1: Stable cross-platform device fingerprint

**Files:**
- Create: `publish/licensing/__init__.py`
- Create: `publish/licensing/fingerprint.py`
- Create: `tests/test_license_fingerprint.py`

- [ ] **Step 1: Write failing platform and privacy tests**

```python
# tests/test_license_fingerprint.py
import hashlib

import pytest

from publish.licensing.fingerprint import DeviceFingerprintError, build_device_hash


def test_macos_uses_ioplatformuuid():
    run = lambda command: '"IOPlatformUUID" = "ABC-123"'
    actual = build_device_hash(system="Darwin", run=run, read=lambda path: "")
    expected = hashlib.sha256(b"opub-device-v1\nmacos\nabc-123").hexdigest()
    assert actual == expected


def test_windows_combines_smbios_and_machine_guid():
    values = iter(["SMBIOS-1", "GUID-2"])
    actual = build_device_hash(system="Windows", run=lambda command: next(values), read=lambda path: "")
    assert actual == hashlib.sha256(b"opub-device-v1\nwindows\nsmbios-1\nguid-2").hexdigest()


def test_linux_falls_back_to_machine_id():
    actual = build_device_hash(system="Linux", run=lambda command: "", read=lambda path: "" if "product_uuid" in path else "MID-1")
    assert actual == hashlib.sha256(b"opub-device-v1\nlinux\nmid-1").hexdigest()


def test_missing_stable_identifier_raises_lic004():
    with pytest.raises(DeviceFingerprintError) as exc:
        build_device_hash(system="Linux", run=lambda command: "", read=lambda path: "")
    assert exc.value.code == "LIC-004"
```

- [ ] **Step 2: Run and confirm failure**

Run: `python -m pytest tests/test_license_fingerprint.py -q`

Expected: FAIL because the licensing package does not exist.

- [ ] **Step 3: Implement normalization, readers, and hashing**

```python
# publish/licensing/__init__.py
"""Local device-license support for opub."""
```

```python
# publish/licensing/fingerprint.py
import hashlib
import platform
import re
import subprocess
from pathlib import Path
from typing import Callable, Optional, Sequence


class DeviceFingerprintError(RuntimeError):
    code = "LIC-004"


def _default_run(command: Sequence[str]) -> str:
    completed = subprocess.run(command, capture_output=True, text=True, timeout=8, check=False)
    return completed.stdout.strip()


def _default_read(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return ""


def _clean(value: str) -> str:
    return value.strip().strip('"').lower()


def build_device_hash(system: Optional[str] = None, run: Callable[[Sequence[str]], str] = _default_run, read: Callable[[str], str] = _default_read) -> str:
    system = system or platform.system()
    values: list[str]
    if system == "Darwin":
        output = run(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"])
        match = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', output)
        values = [match.group(1) if match else ""]
        platform_name = "macos"
    elif system == "Windows":
        smbios = run(["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_ComputerSystemProduct).UUID"])
        machine_guid = run(["powershell", "-NoProfile", "-Command", "(Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Cryptography').MachineGuid"])
        values = [smbios, machine_guid]
        platform_name = "windows"
    elif system == "Linux":
        dmi = read("/sys/class/dmi/id/product_uuid")
        values = [dmi or read("/etc/machine-id")]
        platform_name = "linux"
    else:
        raise DeviceFingerprintError("unsupported operating system")
    normalized = [_clean(value) for value in values if _clean(value)]
    if not normalized:
        raise DeviceFingerprintError("stable device identifier unavailable")
    material = "\n".join(["opub-device-v1", platform_name, *normalized]).encode("utf-8")
    return hashlib.sha256(material).hexdigest()
```

- [ ] **Step 4: Add logging/network privacy assertions**

Patch subprocess and file readers with markers such as `RAW-SECRET-UUID`, then assert captured stderr and the value returned by `build_device_hash()` never contain the marker and are exactly 64 lowercase hexadecimal characters.

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_license_fingerprint.py -q`

Expected: all fingerprint tests pass on any host OS because platform I/O is injected.

- [ ] **Step 6: Commit**

```bash
git add publish/licensing/__init__.py publish/licensing/fingerprint.py tests/test_license_fingerprint.py
git commit -m "feat: derive private device fingerprints"
```

### Task 2: Atomic license storage and Ed25519 verification

**Files:**
- Create: `publish/licensing/storage.py`
- Create: `publish/licensing/verifier.py`
- Create: `tests/test_license_storage.py`
- Create: `tests/test_license_verifier.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add the client verification dependency and failing tests**

Add `"cryptography>=45,<51"` to `[project].dependencies` in `pyproject.toml`.

```python
# tests/test_license_storage.py
import json
import stat

from publish.licensing.storage import atomic_write_json, license_path


def test_atomic_write_uses_mode_0600(tmp_path):
    target = license_path(tmp_path)
    atomic_write_json(target, {"ok": True})
    assert json.loads(target.read_text()) == {"ok": True}
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
```

```python
# tests/test_license_verifier.py
import base64

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from publish.licensing.verifier import LicenseValidationError, canonical_json, verify_license


def signed_document(device_hash="a" * 64):
    private = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    payload = {"schema_version": 1, "key_id": "test", "license_id": "lic-1", "product": "opub-lifetime-v1", "device_hash": device_hash, "issued_at": "2026-09-05T00:00:00Z"}
    signature = base64.b64encode(private.sign(canonical_json(payload))).decode("ascii")
    public = base64.b64encode(private.public_key().public_bytes_raw()).decode("ascii")
    return {"payload": payload, "signature": signature}, {"test": public}


def test_valid_license_passes():
    document, keys = signed_document()
    verify_license(document, "a" * 64, keys)


@pytest.mark.parametrize("mutation,code", [
    (lambda doc: doc["payload"].update(product="other"), "LIC-002"),
    (lambda doc: doc["payload"].update(device_hash="b" * 64), "LIC-003"),
    (lambda doc: doc.update(signature="AAAA"), "LIC-002"),
])
def test_invalid_license_has_stable_code(mutation, code):
    document, keys = signed_document()
    mutation(document)
    with pytest.raises(LicenseValidationError) as exc:
        verify_license(document, "a" * 64, keys)
    assert exc.value.code == code
```

- [ ] **Step 2: Run and confirm failure**

Run: `python -m pytest tests/test_license_storage.py tests/test_license_verifier.py -q`

Expected: FAIL because storage and verifier modules do not exist.

- [ ] **Step 3: Implement data paths and atomic mode-0600 writes**

```python
# publish/licensing/storage.py
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Optional


def data_dir(home: Optional[Path] = None, environ: Optional[Mapping[str, str]] = None) -> Path:
    environ = environ or os.environ
    return Path(environ["SAU_HOME"]) if environ.get("SAU_HOME") else (home or Path.home()) / ".opub"


def license_path(base: Optional[Path] = None) -> Path:
    return (base or data_dir()) / "license.json"


def activation_path(base: Optional[Path] = None) -> Path:
    return (base or data_dir()) / "activation.json"


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        os.chmod(path, 0o600)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)
```

- [ ] **Step 4: Implement strict schema, product, device, and signature verification**

```python
# publish/licensing/verifier.py
import base64
import json
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


class LicenseValidationError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def canonical_json(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def verify_license(document: Mapping[str, Any], device_hash: str, trusted_keys: Mapping[str, str]) -> None:
    try:
        payload = document["payload"]
        signature = base64.b64decode(document["signature"], validate=True)
        required = {"schema_version", "key_id", "license_id", "product", "device_hash", "issued_at"}
        if set(payload) != required or payload["schema_version"] != 1 or payload["product"] != "opub-lifetime-v1":
            raise LicenseValidationError("LIC-002", "license schema or product is invalid")
        if payload["device_hash"] != device_hash:
            raise LicenseValidationError("LIC-003", "license belongs to another device")
        public_b64 = trusted_keys[payload["key_id"]]
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_b64, validate=True))
        key.verify(signature, canonical_json(payload))
    except LicenseValidationError:
        raise
    except (KeyError, TypeError, ValueError, InvalidSignature) as exc:
        raise LicenseValidationError("LIC-002", "license is damaged or signature is invalid") from exc
```

- [ ] **Step 5: Add offline and replacement-failure tests**

Mock every `requests` entry point to raise if called while verifying a valid local license. Patch `os.replace` to fail and assert the previous license remains byte-for-byte intact and the temporary file is removed.

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/test_license_storage.py tests/test_license_verifier.py -q`

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml publish/licensing/storage.py publish/licensing/verifier.py tests/test_license_storage.py tests/test_license_verifier.py
git commit -m "feat: verify and store offline licenses"
```

### Task 3: Activation API, checkout opening, and resumable polling

**Files:**
- Create: `publish/licensing/api.py`
- Create: `publish/licensing/activation.py`
- Create: `tests/test_license_activation.py`

- [ ] **Step 1: Write failing API and workflow tests**

```python
# tests/test_license_activation.py
from unittest.mock import Mock

import pytest

from publish.licensing.activation import ActivationError, activate


def test_activation_opens_checkout_polls_verifies_then_writes(tmp_path):
    api = Mock()
    api.create_session.return_value = {"status": "pending", "session_id": "s1", "poll_token": "p1", "expires_at": "2099-01-01T00:00:00Z", "checkout": {"kind": "url", "value": "https://pay.test/1"}}
    api.get_session.side_effect = [{"status": "pending"}, {"status": "licensed", "license": {"payload": {}, "signature": "sig"}}]
    verify = Mock()
    open_checkout = Mock()
    result = activate("wechat", "d" * 64, api, tmp_path, verify, open_checkout, sleep=lambda seconds: None, monotonic=iter([0, 1, 2]).__next__)
    assert result == 0
    verify.assert_called_once()
    open_checkout.assert_called_once()
    assert (tmp_path / "license.json").exists()


def test_activation_timeout_keeps_session_file(tmp_path):
    api = Mock()
    api.create_session.return_value = {"status": "pending", "session_id": "s1", "poll_token": "p1", "expires_at": "2099-01-01T00:00:00Z", "checkout": {"kind": "url", "value": "https://pay.test/1"}}
    api.get_session.return_value = {"status": "pending"}
    with pytest.raises(ActivationError) as exc:
        activate("wechat", "d" * 64, api, tmp_path, Mock(), Mock(), timeout_seconds=1, sleep=lambda seconds: None, monotonic=iter([0, 2]).__next__)
    assert exc.value.code == "LIC-010"
    assert (tmp_path / "activation.json").exists()
```

- [ ] **Step 2: Run and confirm failure**

Run: `python -m pytest tests/test_license_activation.py -q`

Expected: FAIL because activation modules do not exist.

- [ ] **Step 3: Implement the narrow HTTP client**

```python
# publish/licensing/api.py
from typing import Any, Dict, Optional

import requests


class ActivationServiceError(RuntimeError):
    code = "LIC-011"


class LicenseApi:
    def __init__(self, base_url: str, session: Optional[requests.Session] = None):
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()

    def create_session(self, device_hash: str, client_version: str, payway: str, nonce: str) -> Dict[str, Any]:
        return self._json("POST", "/v1/activation-sessions", json={"device_hash": device_hash, "client_nonce": nonce, "client_version": client_version, "payway": payway})

    def get_session(self, session_id: str, poll_token: str) -> Dict[str, Any]:
        return self._json("GET", f"/v1/activation-sessions/{session_id}", headers={"Authorization": f"Bearer {poll_token}"})

    def _json(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        try:
            response = self.session.request(method, self.base_url + path, timeout=(5, 20), **kwargs)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            raise ActivationServiceError("activation service unavailable") from exc
```

- [ ] **Step 4: Implement local checkout handling without a fourth server route**

```python
# publish/licensing/activation.py (checkout portion)
import os
import secrets
import time
import webbrowser
from pathlib import Path

import qrcode

from publish.licensing.storage import activation_path, atomic_write_json, license_path, read_json


class ActivationError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def open_checkout(checkout: dict, data_path: Path) -> None:
    if checkout["kind"] == "url":
        qr_path = data_path / "payment-qr.png"
        fd = os.open(qr_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            qrcode.make(checkout["value"]).save(handle, format="PNG")
        webbrowser.open(checkout["value"])
        webbrowser.open(qr_path.resolve().as_uri())
        return
    if checkout["kind"] == "html":
        html_path = data_path / "alipay-checkout.html"
        fd = os.open(html_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(checkout["value"])
        webbrowser.open(html_path.resolve().as_uri())
        return
    raise ValueError("unsupported checkout kind")
```

- [ ] **Step 5: Implement resume, poll, local verification, and atomic installation**

```python
# publish/licensing/activation.py (workflow portion)
def activate(payway, device_hash, api, data_path, verify, checkout_opener=open_checkout, timeout_seconds=600, sleep=time.sleep, monotonic=time.monotonic, client_version="0.7.0") -> int:
    data_path.mkdir(parents=True, exist_ok=True)
    session_file = data_path / "activation.json"
    session = None
    if session_file.exists():
        try:
            candidate = read_json(session_file)
            if candidate.get("payway") == payway and candidate.get("device_hash") == device_hash and candidate.get("checkout", {}).get("kind") in ("url", "html"):
                session = candidate
        except (OSError, ValueError, TypeError):
            session_file.unlink(missing_ok=True)
    if session is None:
        response = api.create_session(device_hash, client_version, payway, secrets.token_urlsafe(24))
        if response["status"] == "licensed":
            verify(response["license"], device_hash)
            atomic_write_json(data_path / "license.json", response["license"])
            return 0
        session = {"session_id": response["session_id"], "poll_token": response["poll_token"], "payway": payway, "device_hash": device_hash, "expires_at": response["expires_at"], "checkout": response["checkout"]}
        atomic_write_json(session_file, session)
    checkout_opener(session["checkout"], data_path)
    started = monotonic()
    while monotonic() - started < timeout_seconds:
        response = api.get_session(session["session_id"], session["poll_token"])
        if response["status"] == "licensed":
            verify(response["license"], device_hash)
            atomic_write_json(data_path / "license.json", response["license"])
            session_file.unlink(missing_ok=True)
            return 0
        if response["status"] == "verification_failed":
            raise ActivationError("LIC-012", "payment verification failed")
        if response["status"] == "expired":
            session_file.unlink(missing_ok=True)
            raise ActivationError("LIC-010", "payment session expired")
        sleep(2)
    raise ActivationError("LIC-010", "payment wait timed out")
```

- [ ] **Step 6: Add corrupt-session, server-outage, invalid-license, HTML, and QR tests**

Assert corrupt `activation.json` is discarded safely, `ActivationServiceError` maps to `LIC-011`, verification failure never writes `license.json`, HTML is mode `0600`, QR contains only the checkout URL, and neither file contains the raw device identifier.

- [ ] **Step 7: Run activation tests**

Run: `python -m pytest tests/test_license_activation.py -q`

Expected: all tests pass with browser and HTTP fully mocked.

- [ ] **Step 8: Commit**

```bash
git add publish/licensing/api.py publish/licensing/activation.py tests/test_license_activation.py
git commit -m "feat: activate licenses through payment checkout"
```

### Task 4: CLI status, activation, and early publish gate

**Files:**
- Modify: `publish/errors.py`
- Modify: `publish/orchestrator.py`
- Modify: `publish/licensing/__init__.py`
- Modify: `tests/test_publish_errors.py`
- Create: `tests/test_license_cli.py`

- [ ] **Step 1: Add failing parser, free-command, and gate tests**

```python
# tests/test_license_cli.py
from unittest.mock import AsyncMock, Mock, patch

import publish_all
from publish.errors import EXIT_LICENSE_ERROR


def test_parser_exposes_license_commands():
    help_text = publish_all.build_parser().format_help()
    assert "--license-status" in help_text
    assert "--activate" in help_text
    assert "--pay-with {wechat,alipay}" in help_text


def test_license_status_does_not_run_publish():
    with patch("publish.orchestrator.show_license_status", return_value=0), patch("publish.orchestrator.run_publish", new=AsyncMock()) as publish:
        assert publish_all.main(["--license-status"]) == 0
        publish.assert_not_awaited()


def test_unlicensed_publish_stops_before_runtime_or_asset_access():
    with patch("publish.orchestrator.require_valid_license", return_value=(False, "LIC-001")), patch("publish.orchestrator.runtime_preflight", new=AsyncMock()) as preflight, patch("publish.orchestrator.get_video_files") as assets:
        code = publish_all.main(["--platforms", "weibo", "--video", "/secret/video.mp4", "--title", "t"])
    assert code == EXIT_LICENSE_ERROR
    preflight.assert_not_awaited()
    assets.assert_not_called()


def test_valid_license_publish_never_calls_license_network():
    with patch("publish.orchestrator.require_valid_license", return_value=(True, None)), patch("publish.orchestrator.run_publish", new=AsyncMock(return_value=0)), patch("requests.Session.request", side_effect=AssertionError("network called")):
        assert publish_all.main(["--platforms", "weibo", "--video", "v.mp4", "--title", "t"]) == 0
```

- [ ] **Step 2: Run and confirm failure**

Run: `python -m pytest tests/test_license_cli.py tests/test_publish_errors.py -q`

Expected: FAIL because licensing flags and exit code 13 do not exist.

- [ ] **Step 3: Add the license exit code and assertions**

```python
# publish/errors.py
EXIT_LICENSE_ERROR = 13
```

Extend `tests/test_publish_errors.py` imports and `test_exit_code_values()` with:

```python
self.assertEqual(EXIT_LICENSE_ERROR, 13)
```

- [ ] **Step 4: Add mutually exclusive free commands and constrained payment selection**

In `build_parser()`:

```python
license_group = parser.add_mutually_exclusive_group()
license_group.add_argument("--license-status", action="store_true", help="检查本机许可证状态")
license_group.add_argument("--activate", action="store_true", help="购买或恢复本机永久许可证")
parser.add_argument("--pay-with", choices=("wechat", "alipay"), help="激活支付渠道，仅与 --activate 一起使用")
```

After parsing and before `_build_overrides(args)`:

```python
if args.pay_with and not args.activate:
    parser.error("--pay-with 只能与 --activate 一起使用")
if args.license_status:
    return show_license_status()
if args.activate:
    payway = args.pay_with
    if payway is None and sys.stdin.isatty():
        payway = input("选择支付方式 [1=微信, 2=支付宝]: ").strip()
        payway = {"1": "wechat", "2": "alipay"}.get(payway)
    if payway not in ("wechat", "alipay"):
        print_error("LIC-001", "非交互激活必须指定支付方式", "使用 --activate --pay-with wechat 或 alipay")
        return EXIT_LICENSE_ERROR
    return run_activation(payway)
valid, code = require_valid_license()
if not valid:
    print_license_error(code)
    return EXIT_LICENSE_ERROR
```

Implement the command helpers in `publish/licensing/__init__.py`:

```python
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Mapping, Optional, Tuple

from publish.errors import EXIT_LICENSE_ERROR, EXIT_OK, print_error
from publish.licensing.activation import ActivationError, activate
from publish.licensing.api import ActivationServiceError, LicenseApi
from publish.licensing.fingerprint import DeviceFingerprintError, build_device_hash
from publish.licensing.storage import data_dir, license_path, read_json
from publish.licensing.verifier import LicenseValidationError, verify_license


LICENSE_ERRORS = {
    "LIC-001": ("尚未激活", "运行 opub --activate --pay-with wechat 或 alipay"),
    "LIC-002": ("许可证损坏或签名无效", "重新联网运行 opub --activate 恢复许可证"),
    "LIC-003": ("许可证属于其他设备", "当前电脑需要重新购买许可证"),
    "LIC-004": ("无法取得稳定设备标识", "确认系统允许读取设备 UUID 后重试"),
    "LIC-010": ("订单尚未支付或等待超时", "完成支付后重新运行同一激活命令"),
    "LIC-011": ("激活服务不可用", "检查网络后稍后重试"),
    "LIC-012": ("支付订单验证失败", "不要重复付款，联系发布者核查订单"),
}


def print_license_error(code: str) -> None:
    message, action = LICENSE_ERRORS.get(code, ("许可证验证失败", "重新运行 opub --license-status"))
    print_error(code, message, action)


def require_valid_license(base: Optional[Path] = None, trusted_keys: Optional[Mapping[str, str]] = None) -> Tuple[bool, Optional[str]]:
    try:
        device_hash = build_device_hash()
    except DeviceFingerprintError:
        return False, "LIC-004"
    target = license_path(base)
    if not target.exists():
        return False, "LIC-001"
    try:
        if trusted_keys is None:
            from publish.licensing.deployment import TRUSTED_PUBLIC_KEYS
            trusted_keys = TRUSTED_PUBLIC_KEYS
        verify_license(read_json(target), device_hash, trusted_keys)
        return True, None
    except LicenseValidationError as exc:
        return False, exc.code
    except (OSError, ValueError, TypeError):
        return False, "LIC-002"


def show_license_status() -> int:
    valid, code = require_valid_license()
    if valid:
        print("[opub] 许可证有效：当前设备已永久激活")
        return EXIT_OK
    print_license_error(code or "LIC-002")
    return EXIT_LICENSE_ERROR


def run_activation(payway: str) -> int:
    try:
        from publish.licensing.deployment import LICENSE_API_BASE_URL, TRUSTED_PUBLIC_KEYS
        device_hash = build_device_hash()
        try:
            client_version = version("opub")
        except PackageNotFoundError:
            client_version = "0.7.0.dev0"
        verify = lambda document, current_device: verify_license(document, current_device, TRUSTED_PUBLIC_KEYS)
        return activate(payway, device_hash, LicenseApi(LICENSE_API_BASE_URL), data_dir(), verify, client_version=client_version)
    except (DeviceFingerprintError, ActivationServiceError, ActivationError, LicenseValidationError) as exc:
        print_license_error(exc.code)
        return EXIT_LICENSE_ERROR
```

- [ ] **Step 5: Preserve the thin compatibility shell**

Do not add licensing logic to `publish_all.py`; its existing `from publish.orchestrator import main` export automatically receives the new behavior. Keep the console entry `publish_all:main` unchanged and assert that existing packaging test still passes.

- [ ] **Step 6: Run all CLI and publish-engine tests**

Run: `python -m pytest tests/test_license_cli.py tests/test_publish_cli.py tests/test_publish_engine.py tests/test_publish_errors.py -q`

Expected: all tests pass; existing publish-engine tests inject a valid-license fixture at their CLI boundary rather than writing a real license into the developer home directory.

- [ ] **Step 7: Commit**

```bash
git add publish/errors.py publish/orchestrator.py publish/licensing/__init__.py tests/test_publish_errors.py tests/test_license_cli.py tests/test_publish_cli.py tests/test_publish_engine.py
git commit -m "feat: gate opub publishing behind a license"
```

### Task 5: Agent skill and public documentation contract

**Files:**
- Modify: `AGENT.md`
- Modify: `skills/opub-cli/SKILL.md`
- Modify: `README.md`
- Modify: `docs/CLI.md`
- Modify: `tests/test_publish_cli.py`

- [ ] **Step 1: Add failing documentation contract tests**

Extend `SkillDocBlackboxTests`:

```python
def test_documents_paid_activation_contract(self):
    text = self.SKILL_PATH.read_text(encoding="utf-8")
    for fragment in ["opub --license-status", "opub --activate --pay-with", "LIC-", "13", "微信", "支付宝", "9.90"]:
        self.assertIn(fragment, text)
    self.assertIn("激活成功后继续原发布任务", text)
    self.assertNotIn("设备哈希", text.split("## Agent 用户反馈", 1)[1])
    self.assertNotIn("轮询令牌", text.split("## Agent 用户反馈", 1)[1])
```

- [ ] **Step 2: Run and confirm failure**

Run: `python -m pytest tests/test_publish_cli.py::SkillDocBlackboxTests -q`

Expected: FAIL because the installed skill does not document licensing.

- [ ] **Step 3: Update Agent behavior**

Add an activation section to `AGENT.md` and `skills/opub-cli/SKILL.md` with this exact flow:

```text
1. 保留用户已确认的素材、标题、描述、标签、平台和发布时间。
2. 发布前运行 opub --license-status，并隐藏原始 stdout/stderr。
3. 退出码为 13 时询问用户选择微信或支付宝。
4. 微信运行 opub --activate --pay-with wechat；支付宝运行 opub --activate --pay-with alipay。
5. 只告诉用户付款窗口已打开；不展示设备哈希、轮询令牌、支付表单或内部日志。
6. 激活成功后继续原发布任务，不要求用户重新提供参数。
```

Add exit code `13` and `LIC-001` through `LIC-012` to the existing error table.

- [ ] **Step 4: Update public pricing and device-bound terms**

Document in `README.md` and `docs/CLI.md`: ¥9.90 one-time payment, one device, permanent offline use after activation, no account, no transfer/unbind/replacement reset, a new computer requires a new purchase, and a public Python package is honest-user enforcement rather than strong DRM.

- [ ] **Step 5: Run documentation contract tests**

Run: `python -m pytest tests/test_publish_cli.py -q`

Expected: all tests pass and the previous one-account-per-platform contract remains unchanged.

- [ ] **Step 6: Commit**

```bash
git add AGENT.md skills/opub-cli/SKILL.md README.md docs/CLI.md tests/test_publish_cli.py
git commit -m "docs: add paid activation workflow"
```

### Task 6: Production public key, simulated end-to-end flow, and release gate

**Files:**
- Create: `publish/licensing/deployment.py` using `license_server.keygen`
- Create: `tests/test_license_e2e.py`
- Modify: `tests/test_package_build.py`
- Modify: `pyproject.toml`
- Modify: `skills/opub-cli/SKILL.md`

- [ ] **Step 1: Generate the production key pair without printing the private key**

Run:

```bash
test -n "$OPUB_PUBLIC_BASE_URL"
python -m license_server.keygen \
  --private-file .secrets/opub-license-ed25519.key \
  --client-file publish/licensing/deployment.py \
  --base-url "$OPUB_PUBLIC_BASE_URL" \
  --key-id 2026-09
```

Expected: `.secrets/opub-license-ed25519.key` has mode `0600`; `publish/licensing/deployment.py` contains only the HTTPS base URL and one base64 public key. Copy the private value into server secret storage without placing it in shell history or Git.

- [ ] **Step 2: Write a simulated end-to-end test across real server and client modules**

```python
# tests/test_license_e2e.py
def test_paid_activation_then_permanent_offline_publish(tmp_path, test_settings, fake_provider):
    database = Database(tmp_path / "server.sqlite3")
    server = TestClient(create_app(test_settings, database, fake_provider))
    api = TestClientLicenseApi(server)
    checkout_opened = []
    fake_provider.order_state = 1
    result = activate("wechat", "d" * 64, api, tmp_path / "client", verify_with_test_key, lambda checkout, path: checkout_opened.append(checkout), sleep=trigger_webhook_then_return, monotonic=fake_clock)
    assert result == 0
    assert len(checkout_opened) == 1
    server.close()
    with patch("requests.Session.request", side_effect=AssertionError("offline verification used network")):
        verify_installed_license(tmp_path / "client", "d" * 64, test_public_keys)
```

The test helper `trigger_webhook_then_return` posts one `charge_succeeded` callback before the second poll; `TestClientLicenseApi` adapts FastAPI `TestClient` to the client `LicenseApi` protocol.

- [ ] **Step 3: Strengthen distribution scanning**

Extend the package test to assert wheel contents include:

```python
self.assertIn("publish/licensing/deployment.py", names)
self.assertIn("publish/licensing/verifier.py", names)
self.assertFalse(any("license_server/" in name for name in names))
```

Scan wheel and sdist bytes for the exact Mianbaoduo app key and private key loaded from local secret files; fail if either byte sequence occurs. Do not print the matching bytes.

- [ ] **Step 4: Bump the release version consistently**

Set `[project].version` and the skill frontmatter `version` to `0.7.0` because licensing changes the product contract. Add this build assertion:

```python
pyproject_text = Path("pyproject.toml").read_text(encoding="utf-8")
skill_text = Path("skills/opub-cli/SKILL.md").read_text(encoding="utf-8")
self.assertIn('version = "0.7.0"', pyproject_text)
self.assertIn('version: "0.7.0"', skill_text)
```

- [ ] **Step 5: Run the full release verification**

Run:

```bash
python -m pytest -q
python -m build
python -m twine check dist/*
git diff --check
```

Expected: all tests pass, wheel/sdist build succeeds, Twine reports both artifacts `PASSED`, and diff check prints nothing.

- [ ] **Step 6: Perform a real internal ¥9.90 activation before publishing the package**

Run the built wheel in a clean temporary virtual environment, call `opub --activate --pay-with wechat` or `alipay`, pay ¥9.90, confirm `opub --license-status` exits 0, disconnect the network, and run a non-destructive mocked publish smoke test. Then use a second machine or an injected different fingerprint to confirm the copied license returns exit code 13 with `LIC-003`.

- [ ] **Step 7: Commit the production-safe client**

```bash
git add publish/licensing/deployment.py tests/test_license_e2e.py tests/test_package_build.py pyproject.toml skills/opub-cli/SKILL.md
git commit -m "chore: prepare licensed opub release"
```

- [ ] **Step 8: Publish only after explicit release approval**

Run `git push` and `python -m twine upload dist/*` only after the owner confirms the real-payment evidence, provider approval, final version, and target PyPI repository. Never print the PyPI token or payment secrets.

## Client completion gate

- `opub --help`, `--version`, `--license-status`, and `--activate` work without a license.
- Every publish command returns exit 13 before runtime preflight or asset access when unlicensed.
- Valid licenses publish offline without any HTTP call.
- Copied, modified, wrong-device, wrong-product, and unknown-key licenses fail with stable `LIC-*` codes.
- Both payment methods complete using only the three server endpoints.
- Agent instructions preserve the original publish inputs while activation happens.
- Wheel and sdist contain the public key but no server code, private key, app key, database, or `.env`.
