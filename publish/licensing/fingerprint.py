# -*- coding: utf-8 -*-
"""跨平台设备指纹生成。"""

from __future__ import annotations

import hashlib
import platform
import subprocess
from pathlib import Path
from typing import Callable, Optional


class DeviceFingerprintError(Exception):
    code = "LIC-004"

    def __init__(self, message: str = "无法生成设备指纹"):
        super().__init__(message)


def _normalize(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    return text.strip().lower()


def _sha256_material(platform_name: str, value: str) -> str:
    material = "\n".join(("opub-device-v1", platform_name, value))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _safe_read(read: Callable[[str], str], path: str) -> str:
    try:
        return read(path) or ""
    except Exception:
        return ""


def _default_read(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _safe_run(run: Callable[..., object], command: list[str]) -> str:
    try:
        result = run(
            command,
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except Exception as exc:
        raise DeviceFingerprintError() from None

    stdout = getattr(result, "stdout", "") or ""
    return stdout


def _extract_ioreg_uuid(stdout: str) -> str:
    for line in stdout.splitlines():
        if "IOPlatformUUID" not in line:
            continue
        if "=" not in line:
            continue
        candidate = line.split("=", 1)[1]
        return _normalize(candidate)
    return ""


def _windows_uuid(run: Callable[..., object]) -> str:
    stdout = _safe_run(
        run,
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-CimInstance -ClassName Win32_ComputerSystemProduct).UUID",
        ],
    )
    return _normalize(stdout)


def _windows_machine_guid(run: Callable[..., object]) -> str:
    stdout = _safe_run(
        run,
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-ItemProperty -Path 'HKLM:\\SOFTWARE\\Microsoft\\Cryptography' -Name MachineGuid).MachineGuid",
        ],
    )
    return _normalize(stdout)


def build_device_hash(
    system: Optional[str] = None,
    run: Callable[..., object] = subprocess.run,
    read: Callable[[str], str] = _default_read,
) -> str:
    system_name = system or platform.system()

    if system_name == "Darwin":
        stdout = _safe_run(
            run,
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
        )
        value = _extract_ioreg_uuid(stdout)
        platform_name = "macos"
    elif system_name == "Windows":
        uuid = _windows_uuid(run)
        machine_guid = _windows_machine_guid(run)
        value = "\n".join(item for item in (uuid, machine_guid) if item)
        platform_name = "windows"
    elif system_name == "Linux":
        value = _normalize(_safe_read(read, "/sys/class/dmi/id/product_uuid"))
        if not value:
            value = _normalize(_safe_read(read, "/etc/machine-id"))
        platform_name = "linux"
    else:
        raise DeviceFingerprintError()

    if not value:
        raise DeviceFingerprintError()

    return _sha256_material(platform_name, value)
