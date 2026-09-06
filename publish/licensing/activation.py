"""Interactive payment checkout and resumable license activation."""
from __future__ import annotations

import os
import secrets
import tempfile
import time
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

import qrcode

from .api import ActivationServiceError
from .storage import atomic_write_json, read_json


class ActivationError(RuntimeError):
    def __init__(self, code: str, message: str = "activation failed"):
        super().__init__(message)
        self.code = code


def _atomic_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="." + path.name + ".", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, str(path))
    except BaseException:
        try:
            os.unlink(name)
        except OSError:
            pass
        raise


def _atomic_text(path: Path, value: str) -> None:
    _atomic_bytes(path, value.encode("utf-8"))


def _validate_checkout(checkout: Any) -> bool:
    if not isinstance(checkout, Mapping):
        return False
    kind, value = checkout.get("kind"), checkout.get("value")
    if not isinstance(kind, str) or not isinstance(value, str) or not value:
        return False
    if kind == "html":
        return True
    if kind != "url":
        return False
    parsed = urllib.parse.urlparse(value)
    return (
        parsed.scheme == "https" and bool(parsed.hostname) and
        not parsed.username and not parsed.password and
        not any(ord(char) < 32 or ord(char) == 127 for char in value)
    )


def open_checkout(checkout: Mapping[str, Any], data_path: Path) -> None:
    if not isinstance(checkout, Mapping):
        raise ActivationError("LIC-011", "invalid checkout")
    kind, value = checkout.get("kind"), checkout.get("value")
    if not isinstance(kind, str) or not isinstance(value, str) or not value:
        raise ActivationError("LIC-011", "invalid checkout")
    data_path = Path(data_path)
    if kind == "url":
        parsed = urllib.parse.urlparse(value)
        if not _validate_checkout(checkout):
            raise ActivationError("LIC-011", "invalid checkout")
        try:
            image = qrcode.make(value)
            with tempfile.NamedTemporaryFile() as tmp:
                image.save(tmp, format="PNG")
                tmp.flush()
                tmp.seek(0)
                _atomic_bytes(data_path / "payment-qr.png", tmp.read())
        except Exception:
            try:
                (data_path / "payment-qr.png").unlink()
            except OSError:
                pass
            raise ActivationError("LIC-011", "unable to save checkout") from None
        webbrowser.open(value)
        webbrowser.open((data_path / "payment-qr.png").resolve().as_uri())
        return
    if kind == "html":
        try:
            path = data_path / "alipay-checkout.html"
            _atomic_text(path, value)
        except Exception:
            try:
                path.unlink()
            except OSError:
                pass
            raise ActivationError("LIC-011", "unable to save checkout") from None
        webbrowser.open(path.resolve().as_uri())
        return
    raise ActivationError("LIC-011", "unsupported checkout")


def _valid_saved_session(candidate: Any, payway: str, device_hash: str) -> bool:
    if not isinstance(candidate, dict):
        return False
    required = {"session_id", "poll_token", "payway", "device_hash", "expires_at", "checkout"}
    if set(candidate) != required or candidate["payway"] != payway or candidate["device_hash"] != device_hash:
        return False
    if any(not isinstance(candidate[key], str) or not candidate[key] for key in required - {"checkout"}):
        return False
    checkout = candidate["checkout"]
    if not isinstance(checkout, dict) or set(checkout) != {"kind", "value"}:
        return False
    return _validate_checkout(checkout)


def _response_status(response: Any) -> str:
    if not isinstance(response, dict) or not isinstance(response.get("status"), str):
        raise ActivationServiceError("activation service unavailable")
    return response["status"]


def activate(
    payway: str, device_hash: str, api: Any, data_path: Path, verify: Callable[..., Any],
    checkout_opener: Callable[[Mapping[str, Any], Path], None] = open_checkout,
    timeout_seconds: float = 600, sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic, client_version: str = "0.7.0",
) -> int:
    if payway not in {"wechat", "alipay"}:
        raise ActivationError("LIC-011", "unsupported payment method")
    data_path = Path(data_path)
    data_path.mkdir(parents=True, exist_ok=True)
    session_file = data_path / "activation.json"
    session: Optional[dict] = None
    if session_file.exists():
        try:
            candidate = read_json(session_file)
            if _valid_saved_session(candidate, payway, device_hash):
                session = candidate
            else:
                session_file.unlink()
        except Exception:
            try:
                session_file.unlink()
            except OSError:
                pass
    # A persisted checkout is untrusted. Always ask the service to refresh the
    # session and checkout; only its current response may be opened.
    response = api.create_session(device_hash, client_version, payway, secrets.token_urlsafe(24))
    status = _response_status(response)
    if status == "licensed":
        license_doc = response.get("license")
        if not isinstance(license_doc, dict):
            raise ActivationServiceError("activation service unavailable")
        verify(license_doc, device_hash)
        atomic_write_json(data_path / "license.json", license_doc)
        try:
            session_file.unlink()
        except FileNotFoundError:
            pass
        return 0
    if status != "pending" or not all(isinstance(response.get(k), str) and response.get(k) for k in ("session_id", "poll_token", "expires_at")):
        raise ActivationError("LIC-011", "invalid activation response")
    checkout = response.get("checkout")
    if not _validate_checkout(checkout):
        raise ActivationError("LIC-011", "invalid activation response")
    session = {"session_id": response["session_id"], "poll_token": response["poll_token"], "payway": payway, "device_hash": device_hash, "expires_at": response["expires_at"], "checkout": {"kind": checkout["kind"], "value": checkout["value"]}}
    atomic_write_json(session_file, session)
    checkout_opener(session["checkout"], data_path)
    started = monotonic()
    while monotonic() - started < timeout_seconds:
        response = api.get_session(session["session_id"], session["poll_token"])
        status = _response_status(response)
        if status == "licensed":
            license_doc = response.get("license")
            if not isinstance(license_doc, dict):
                raise ActivationServiceError("activation service unavailable")
            verify(license_doc, device_hash)
            atomic_write_json(data_path / "license.json", license_doc)
            try:
                session_file.unlink()
            except FileNotFoundError:
                pass
            return 0
        if status == "verification_failed":
            raise ActivationError("LIC-012", "payment verification failed")
        if status == "expired":
            try:
                session_file.unlink()
            except FileNotFoundError:
                pass
            raise ActivationError("LIC-010", "payment session expired")
        if status != "pending":
            raise ActivationServiceError("activation service unavailable")
        sleep(2)
    raise ActivationError("LIC-010", "payment wait timed out")
