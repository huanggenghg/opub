import base64
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from publish.licensing.verifier import LicenseValidationError, canonical_json, verify_license


def signed_document(device_hash="a" * 64, product="opub-major-0"):
    private = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    payload = {"schema_version": 1, "key_id": "test", "license_id": "lic-1", "product": product, "device_hash": device_hash, "issued_at": "2026-09-05T00:00:00Z"}
    signature = base64.b64encode(private.sign(canonical_json(payload))).decode("ascii")
    public = base64.b64encode(private.public_key().public_bytes_raw()).decode("ascii")
    return {"payload": payload, "signature": signature}, {"test": public}


def test_valid_license_passes_without_network(monkeypatch):
    document, keys = signed_document()
    import requests
    monkeypatch.setattr(requests.Session, "request", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
    verify_license(document, "a" * 64, keys)


def test_correctly_signed_legacy_product_is_rejected():
    document, keys = signed_document(product="opub-lifetime-v1")

    with pytest.raises(LicenseValidationError) as exc:
        verify_license(document, "a" * 64, keys)

    assert exc.value.code == "LIC-002"


@pytest.mark.parametrize("mutation,code", [
    (lambda d: d["payload"].update(product="other"), "LIC-002"),
    (lambda d: d["payload"].update(device_hash="b" * 64), "LIC-003"),
    (lambda d: d.update(signature="AAAA"), "LIC-002"),
    (lambda d: d["payload"].update(extra=True), "LIC-002"),
    (lambda d: d["payload"].pop("issued_at"), "LIC-002"),
    (lambda d: d["payload"].update(schema_version="1"), "LIC-002"),
])
def test_invalid_license_has_stable_code(mutation, code):
    document, keys = signed_document()
    mutation(document)
    with pytest.raises(LicenseValidationError) as exc:
        verify_license(document, "a" * 64, keys)
    assert exc.value.code == code


def test_canonical_json_is_server_compatible_ascii():
    assert canonical_json({"é": "值"}) == b'{"\\u00e9":"\\u503c"}'


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(signature=b"not-text"),
    lambda d: d["payload"].update(device_hash="A" * 64),
    lambda d: d["payload"].update(device_hash="short"),
])
def test_bad_signature_or_device_types_are_invalid(mutation):
    document, keys = signed_document()
    mutation(document)
    with pytest.raises(LicenseValidationError) as exc:
        verify_license(document, "a" * 64, keys)
    assert exc.value.code == "LIC-002"


@pytest.mark.parametrize("key_value", [b"not-text", "%%%", base64.b64encode(b"short").decode()])
def test_bad_trusted_public_key_is_invalid(key_value):
    document, keys = signed_document()
    keys["test"] = key_value
    with pytest.raises(LicenseValidationError) as exc:
        verify_license(document, "a" * 64, keys)
    assert exc.value.code == "LIC-002"
