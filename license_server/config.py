from __future__ import annotations

from base64 import b64decode
from dataclasses import dataclass
from binascii import Error as BinasciiError
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit, urlunsplit

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


@dataclass(frozen=True)
class Settings:
    public_base_url: str
    payment_return_url: str
    mbd_app_id: str
    mbd_app_key: str
    license_private_key: str
    license_key_id: str
    database_path: Path
    product_id: str = "opub-lifetime-v1"
    product_name: str = "opub 永久设备许可证"
    price_fen: int = 990

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Settings":
        required_names = (
            "OPUB_PUBLIC_BASE_URL",
            "OPUB_PAYMENT_RETURN_URL",
            "OPUB_MBD_APP_ID",
            "OPUB_MBD_APP_KEY",
            "OPUB_LICENSE_PRIVATE_KEY",
            "OPUB_LICENSE_KEY_ID",
            "OPUB_LICENSE_DB_PATH",
        )
        missing_names = [
            name
            for name in required_names
            if name not in env or not env[name].strip()
        ]
        if missing_names:
            missing = ", ".join(missing_names)
            raise ValueError(f"Missing required environment variables: {missing}")

        public_base_url = _normalize_url(
            env["OPUB_PUBLIC_BASE_URL"],
            field_name="OPUB_PUBLIC_BASE_URL",
            allow_query=False,
            strip_trailing_slash=True,
        )
        payment_return_url = _normalize_url(
            env["OPUB_PAYMENT_RETURN_URL"],
            field_name="OPUB_PAYMENT_RETURN_URL",
            allow_query=True,
            strip_trailing_slash=False,
        )
        license_private_key = env["OPUB_LICENSE_PRIVATE_KEY"]
        _validate_private_key(license_private_key)

        return cls(
            public_base_url=public_base_url,
            payment_return_url=payment_return_url,
            mbd_app_id=env["OPUB_MBD_APP_ID"].strip(),
            mbd_app_key=env["OPUB_MBD_APP_KEY"].strip(),
            license_private_key=license_private_key,
            license_key_id=env["OPUB_LICENSE_KEY_ID"].strip(),
            database_path=Path(env["OPUB_LICENSE_DB_PATH"].strip()),
        )


def _normalize_url(
    raw_value: str,
    *,
    field_name: str,
    allow_query: bool,
    strip_trailing_slash: bool,
) -> str:
    parts = urlsplit(raw_value.strip())
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.fragment
        or (not allow_query and parts.query)
    ):
        raise ValueError(f"{field_name} must be a valid https URL")

    path = parts.path.rstrip("/") if strip_trailing_slash else parts.path
    query = parts.query if allow_query else ""
    return urlunsplit((parts.scheme, parts.netloc, path, query, ""))


def _validate_private_key(raw_value: str) -> None:
    try:
        decoded = b64decode(raw_value, validate=True)
    except (BinasciiError, ValueError) as exc:
        raise ValueError(
            "OPUB_LICENSE_PRIVATE_KEY must be a valid base64-encoded 32-byte Ed25519 private key"
        ) from exc

    if len(decoded) != 32:
        raise ValueError(
            "OPUB_LICENSE_PRIVATE_KEY must be a valid base64-encoded 32-byte Ed25519 private key"
        )

    try:
        Ed25519PrivateKey.from_private_bytes(decoded)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "OPUB_LICENSE_PRIVATE_KEY must be a valid base64-encoded 32-byte Ed25519 private key"
        ) from exc
