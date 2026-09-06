"""Public activation-code parsing utilities."""

import re
from typing import Any


_ACTIVATION_CODE_PATTERN = re.compile(r"OPUB0[0123456789ABCDEFGHJKMNPQRSTVWXYZ]{30}")


class ActivationCodeFormatError(ValueError):
    """Raised when an activation code is not in its canonical format."""


def normalize_activation_code(value: Any) -> str:
    """Return a canonical activation code without display separators."""
    if not isinstance(value, str):
        raise ActivationCodeFormatError("invalid activation code")

    stripped = value.strip()
    if not stripped.isascii():
        raise ActivationCodeFormatError("invalid activation code")

    normalized = stripped.upper().replace("-", "")
    if _ACTIVATION_CODE_PATTERN.fullmatch(normalized) is None:
        raise ActivationCodeFormatError("invalid activation code")
    return normalized
