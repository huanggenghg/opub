"""One-shot, device-bound activation-code redemption."""
from pathlib import Path
from typing import Any, Callable

from .api import ActivationServiceError
from .codes import ActivationCodeFormatError, normalize_activation_code
from .storage import atomic_write_json


class ActivationError(RuntimeError):
    def __init__(self, code: str, message: str = "activation failed") -> None:
        super().__init__(message)
        self.code = code


def activate(
    code: str,
    device_hash: str,
    api: Any,
    data_path: Path,
    verify: Callable[..., Any],
    client_version: str = "0.8.0.dev0",
) -> int:
    try:
        normalized_code = normalize_activation_code(code)
    except ActivationCodeFormatError:
        raise ActivationError("LIC-013") from None

    response = api.activate_code(device_hash, client_version, normalized_code)
    if (
        not isinstance(response, dict)
        or response.get("status") != "licensed"
        or not isinstance(response.get("license"), dict)
    ):
        raise ActivationServiceError()

    license_doc = response["license"]
    verify(license_doc, device_hash)
    atomic_write_json(Path(data_path) / "license.json", license_doc)
    return 0
