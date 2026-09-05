from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def canonical_json(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def sign_license(
    private_key_b64: str,
    key_id: str,
    license_id: str,
    device_hash: str,
    issued_at: str,
) -> dict[str, object]:
    private_seed = base64.b64decode(private_key_b64, validate=True)
    if len(private_seed) != 32:
        raise ValueError("private_key_b64 must be a base64-encoded 32-byte Ed25519 seed")

    payload = {
        "schema_version": 1,
        "key_id": key_id,
        "license_id": license_id,
        "product": "opub-lifetime-v1",
        "device_hash": device_hash,
        "issued_at": issued_at,
    }
    signature = Ed25519PrivateKey.from_private_bytes(private_seed).sign(
        canonical_json(payload)
    )
    return {
        "payload": payload,
        "signature": base64.b64encode(signature).decode("ascii"),
    }
