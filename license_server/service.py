from __future__ import annotations

import base64
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from publish.licensing.codes import ActivationCodeFormatError, normalize_activation_code

from .codes import code_hash
from .config import Settings
from .database import Database
from .signing import canonical_json, sign_license


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


def _stored_license(
    signed_payload: str | None,
    *,
    private_key_b64: str,
    key_id: str,
    product_id: str,
    device_hash: str,
) -> dict[str, Any]:
    if signed_payload is None:
        raise RuntimeError("stored license is invalid")
    try:
        document = json.loads(signed_payload)
        if not isinstance(document, dict) or set(document) != {"payload", "signature"}:
            raise ValueError("invalid license document")
        payload = document["payload"]
        required_fields = {
            "schema_version",
            "key_id",
            "license_id",
            "product",
            "device_hash",
            "issued_at",
        }
        if not isinstance(payload, dict) or set(payload) != required_fields:
            raise ValueError("invalid license payload")
        if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
            raise ValueError("invalid schema version")
        text_fields = required_fields - {"schema_version"}
        if any(not isinstance(payload[name], str) for name in text_fields):
            raise ValueError("invalid license field type")
        if not payload["license_id"] or not payload["issued_at"]:
            raise ValueError("invalid license identity")
        if payload["key_id"] != key_id or payload["product"] != product_id:
            raise ValueError("invalid license identity")
        if payload["device_hash"] != device_hash or re.fullmatch(
            r"[0-9a-f]{64}", payload["device_hash"]
        ) is None:
            raise ValueError("invalid device identity")

        signature_text = document["signature"]
        if not isinstance(signature_text, str):
            raise ValueError("invalid signature")
        signature = base64.b64decode(signature_text, validate=True)
        if len(signature) != 64:
            raise ValueError("invalid signature")
        private_seed = base64.b64decode(private_key_b64, validate=True)
        if len(private_seed) != 32:
            raise ValueError("invalid signing key")
        public_key = Ed25519PrivateKey.from_private_bytes(private_seed).public_key()
        public_key.verify(signature, canonical_json(payload))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, InvalidSignature):
        raise RuntimeError("stored license is invalid") from None

    return {
        "payload": {name: payload[name] for name in required_fields},
        "signature": signature_text,
    }


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
        return {
            "status": "licensed",
            "license": _stored_license(
                result.signed_payload,
                private_key_b64=self.settings.license_private_key,
                key_id=self.settings.license_key_id,
                product_id=self.settings.product_id,
                device_hash=device_hash,
            ),
        }
