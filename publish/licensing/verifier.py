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
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def verify_license(document: Mapping[str, Any], device_hash: str, trusted_keys: Mapping[str, str]) -> None:
    try:
        if not isinstance(document, Mapping) or set(document) != {"payload", "signature"}:
            raise LicenseValidationError("LIC-002", "license is damaged or signature is invalid")
        payload = document["payload"]
        if not isinstance(payload, Mapping):
            raise LicenseValidationError("LIC-002", "license schema or product is invalid")
        required = {"schema_version", "key_id", "license_id", "product", "device_hash", "issued_at"}
        if set(payload) != required or type(payload["schema_version"]) is not int or payload["schema_version"] != 1 or payload["product"] != "opub-lifetime-v1":
            raise LicenseValidationError("LIC-002", "license schema or product is invalid")
        if any(not isinstance(payload[name], str) for name in required - {"schema_version"}):
            raise LicenseValidationError("LIC-002", "license schema or product is invalid")
        if not payload["key_id"] or not payload["license_id"] or not payload["issued_at"]:
            raise LicenseValidationError("LIC-002", "license schema or product is invalid")
        if len(payload["device_hash"]) != 64:
            raise LicenseValidationError("LIC-002", "license schema or product is invalid")
        if not isinstance(document["signature"], str) or not isinstance(device_hash, str):
            raise LicenseValidationError("LIC-002", "license is damaged or signature is invalid")
        import re
        if not re.fullmatch(r"[0-9a-f]{64}", payload["device_hash"]) or not re.fullmatch(r"[0-9a-f]{64}", device_hash):
            raise LicenseValidationError("LIC-002", "license schema or product is invalid")
        if payload["device_hash"] != device_hash:
            raise LicenseValidationError("LIC-003", "license belongs to another device")
        signature = base64.b64decode(document["signature"], validate=True)
        if len(signature) != 64:
            raise ValueError("invalid signature length")
        public_b64 = trusted_keys[payload["key_id"]]
        if not isinstance(public_b64, str):
            raise ValueError("invalid public key type")
        public = base64.b64decode(public_b64, validate=True)
        if len(public) != 32:
            raise ValueError("invalid public key length")
        Ed25519PublicKey.from_public_bytes(public).verify(signature, canonical_json(payload))
    except LicenseValidationError:
        raise
    except (KeyError, TypeError, ValueError, InvalidSignature):
        raise LicenseValidationError("LIC-002", "license is damaged or signature is invalid")
