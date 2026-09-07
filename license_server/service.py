from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from publish.licensing.codes import ActivationCodeFormatError, normalize_activation_code

from .codes import code_hash
from .config import Settings
from .database import Database
from .signing import sign_license


_MAJOR_ZERO_VERSION = re.compile(
    r"0\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:(?:a|b|rc)(?:0|[1-9][0-9]*))?"
    r"(?:\.post(?:0|[1-9][0-9]*))?"
    r"(?:\.dev(?:0|[1-9][0-9]*))?"
    r"(?:\+[a-z0-9]+(?:[.-][a-z0-9]+)*)?"
)


class InvalidActivationCode(ValueError):
    code = "LIC-013"


class ActivationCodeUsed(ValueError):
    code = "LIC-014"


class ClientVersionMismatch(ValueError):
    code = "LIC-015"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _stored_license(signed_payload: str | None) -> dict[str, Any]:
    if signed_payload is None:
        raise RuntimeError("stored license is invalid")
    try:
        document = json.loads(signed_payload)
    except (TypeError, json.JSONDecodeError):
        raise RuntimeError("stored license is invalid") from None
    if not isinstance(document, dict):
        raise RuntimeError("stored license is invalid")
    return document


class LicenseService:
    """Redeem activation-code inventory into signed, device-bound licenses."""

    def __init__(self, settings: Settings, database: Database) -> None:
        self.settings = settings
        self.database = database

    def redeem(
        self,
        activation_code: str,
        device_hash: str,
        client_version: str,
    ) -> dict[str, Any]:
        if _MAJOR_ZERO_VERSION.fullmatch(client_version) is None:
            raise ClientVersionMismatch()

        try:
            normalized = normalize_activation_code(activation_code)
        except ActivationCodeFormatError:
            raise InvalidActivationCode() from None

        license_id = uuid.uuid4().hex
        issued_at = _now_iso()
        document = sign_license(
            private_key_b64=self.settings.license_private_key,
            key_id=self.settings.license_key_id,
            license_id=license_id,
            device_hash=device_hash,
            issued_at=issued_at,
            product_id=self.settings.product_id,
        )
        signed_payload = json.dumps(document, sort_keys=True, separators=(",", ":"))
        result = self.database.redeem_activation_code(
            code_hash(normalized),
            device_hash,
            license_id,
            signed_payload,
            issued_at,
        )

        if result.status == "invalid":
            raise InvalidActivationCode()
        if result.status == "used":
            raise ActivationCodeUsed()
        if result.status not in {"created", "same_device", "existing_device"}:
            raise RuntimeError("unexpected redemption state")
        return {"status": "licensed", "license": _stored_license(result.signed_payload)}
