from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


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
        missing_names = [name for name in required_names if name not in env]
        if missing_names:
            missing = ", ".join(missing_names)
            raise ValueError(f"Missing required environment variables: {missing}")

        public_base_url = env["OPUB_PUBLIC_BASE_URL"].rstrip("/")
        payment_return_url = env["OPUB_PAYMENT_RETURN_URL"]
        if not public_base_url.startswith("https://"):
            raise ValueError("OPUB_PUBLIC_BASE_URL must start with https://")
        if not payment_return_url.startswith("https://"):
            raise ValueError("OPUB_PAYMENT_RETURN_URL must start with https://")

        return cls(
            public_base_url=public_base_url,
            payment_return_url=payment_return_url,
            mbd_app_id=env["OPUB_MBD_APP_ID"],
            mbd_app_key=env["OPUB_MBD_APP_KEY"],
            license_private_key=env["OPUB_LICENSE_PRIVATE_KEY"],
            license_key_id=env["OPUB_LICENSE_KEY_ID"],
            database_path=Path(env["OPUB_LICENSE_DB_PATH"]),
        )
