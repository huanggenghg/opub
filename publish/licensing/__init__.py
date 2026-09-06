# -*- coding: utf-8 -*-
"""许可证状态、离线校验与激活命令。"""

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
    message, action = LICENSE_ERRORS.get(
        code, ("许可证验证失败", "重新运行 opub --license-status")
    )
    print_error(code, message, action)


def require_valid_license(
    base: Optional[Path] = None,
    trusted_keys: Optional[Mapping[str, str]] = None,
) -> Tuple[bool, Optional[str]]:
    """Validate the local device-bound license without making network calls."""
    try:
        device_hash = build_device_hash()
    except DeviceFingerprintError:
        return False, "LIC-004"

    try:
        target = license_path(base)
        if not target.exists():
            return False, "LIC-001"
        if trusted_keys is None:
            from publish.licensing.deployment import TRUSTED_PUBLIC_KEYS

            trusted_keys = TRUSTED_PUBLIC_KEYS
        verify_license(read_json(target), device_hash, trusted_keys)
        return True, None
    except LicenseValidationError as exc:
        return False, exc.code if exc.code in LICENSE_ERRORS else "LIC-002"
    except (ImportError, AttributeError, OSError, TypeError, ValueError):
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
        from publish.licensing.deployment import (
            LICENSE_API_BASE_URL,
            TRUSTED_PUBLIC_KEYS,
        )

        device_hash = build_device_hash()
        try:
            client_version = version("opub")
        except PackageNotFoundError:
            client_version = "0.7.0.dev0"
        verify = lambda document, current_device: verify_license(
            document, current_device, TRUSTED_PUBLIC_KEYS
        )
        return activate(
            payway,
            device_hash,
            LicenseApi(LICENSE_API_BASE_URL),
            data_dir(),
            verify,
            client_version=client_version,
        )
    except DeviceFingerprintError:
        code = "LIC-004"
    except LicenseValidationError as exc:
        code = exc.code if exc.code in LICENSE_ERRORS else "LIC-002"
    except ActivationError as exc:
        code = exc.code if exc.code in LICENSE_ERRORS else "LIC-011"
    except (ActivationServiceError, ImportError, AttributeError, OSError, TypeError, ValueError):
        code = "LIC-011"
    except Exception:
        code = "LIC-011"

    print_license_error(code)
    return EXIT_LICENSE_ERROR


__all__ = [
    "DeviceFingerprintError",
    "LICENSE_ERRORS",
    "build_device_hash",
    "print_license_error",
    "require_valid_license",
    "run_activation",
    "show_license_status",
]
