from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from license_server.codes import code_hash
from license_server.config import Settings
from license_server.database import Database
from license_server.service import (
    ActivationCodeUsed,
    ClientVersionMismatch,
    InvalidActivationCode,
    LicenseService,
)
from license_server.signing import canonical_json
from publish.licensing.codes import normalize_activation_code


CODE = "OPUB0-01234-56789-ABCDE-FGHJK-MNPQR-STVWX"
OTHER_CODE = "OPUB0-ZYXWV-TSRQP-NMKJH-GFEDC-BA987-65432"
DEVICE_HASH = "a" * 64
OTHER_DEVICE_HASH = "b" * 64


def build_service(tmp_path: Path, *, product_id: str = "opub-major-0") -> tuple[LicenseService, Database]:
    settings = Settings.from_env(
        {
            "OPUB_PUBLIC_BASE_URL": "https://license.opub.test",
            "OPUB_LICENSE_PRIVATE_KEY": base64.b64encode(bytes(range(32))).decode("ascii"),
            "OPUB_LICENSE_KEY_ID": "test-key",
            "OPUB_LICENSE_DB_PATH": str(tmp_path / "db.sqlite3"),
        }
    )
    settings = replace(settings, product_id=product_id)
    database = Database(settings.database_path)
    database.initialize()
    return LicenseService(settings, database), database


def import_code(database: Database, activation_code: str) -> None:
    normalized = normalize_activation_code(activation_code)
    database.import_activation_code(
        code_hash(normalized),
        "opub-major-0",
        "2026-09-06T00:00:00Z",
    )


def test_redeem_signs_verifiable_major_zero_license(tmp_path: Path) -> None:
    service, database = build_service(tmp_path)
    import_code(database, CODE)

    response = service.redeem(CODE, DEVICE_HASH, "0.8.0")

    assert response["status"] == "licensed"
    document = response["license"]
    assert document["payload"]["product"] == "opub-major-0"
    assert document["payload"]["device_hash"] == DEVICE_HASH
    assert document["payload"]["key_id"] == "test-key"
    public_key = Ed25519PrivateKey.from_private_bytes(bytes(range(32))).public_key()
    public_key.verify(
        base64.b64decode(document["signature"]),
        canonical_json(document["payload"]),
    )


def test_redeem_passes_configured_product_id_to_signing(tmp_path: Path) -> None:
    service, database = build_service(tmp_path, product_id="custom-major-zero")
    import_code(database, CODE)

    response = service.redeem(CODE, DEVICE_HASH, "0.8.0.dev0")

    assert response["license"]["payload"]["product"] == "custom-major-zero"


@pytest.mark.parametrize("version", ["0.8.0", "0.8.0.dev0"])
def test_redeem_accepts_real_major_zero_versions(version: str, tmp_path: Path) -> None:
    service, database = build_service(tmp_path)
    import_code(database, CODE)

    assert service.redeem(CODE, DEVICE_HASH, version)["status"] == "licensed"


@pytest.mark.parametrize("version", ["1.0.0", "garbage", "", "00.8.0", "0.8٨.0"])
def test_redeem_rejects_invalid_or_non_zero_major_versions(version: str, tmp_path: Path) -> None:
    service, database = build_service(tmp_path)
    import_code(database, CODE)

    with pytest.raises(ClientVersionMismatch) as exc_info:
        service.redeem(CODE, DEVICE_HASH, version)

    if version:
        assert version not in str(exc_info.value)
    assert database.code_stats() == {"available": 1, "redeemed": 0, "total": 1}


@pytest.mark.parametrize("activation_code", ["not-a-code", "OPUB0-OOOOO-OOOOO-OOOOO-OOOOO-OOOOO-OOOOO"])
def test_redeem_maps_invalid_format_to_public_error(
    activation_code: str, tmp_path: Path
) -> None:
    service, _database = build_service(tmp_path)

    with pytest.raises(InvalidActivationCode) as exc_info:
        service.redeem(activation_code, DEVICE_HASH, "0.8.0")

    assert activation_code not in str(exc_info.value)
    assert DEVICE_HASH not in str(exc_info.value)


def test_redeem_maps_unknown_inventory_code_to_same_public_error(tmp_path: Path) -> None:
    service, _database = build_service(tmp_path)

    with pytest.raises(InvalidActivationCode) as exc_info:
        service.redeem(CODE, DEVICE_HASH, "0.8.0")

    assert CODE not in str(exc_info.value)
    assert code_hash(normalize_activation_code(CODE)) not in str(exc_info.value)
    assert DEVICE_HASH not in str(exc_info.value)


def test_redeem_same_code_on_same_device_returns_identical_license(tmp_path: Path) -> None:
    service, database = build_service(tmp_path)
    import_code(database, CODE)

    first = service.redeem(CODE, DEVICE_HASH, "0.8.0")
    second = service.redeem(CODE.lower(), DEVICE_HASH, "0.8.0.dev0")

    assert second == first
    assert database.row("SELECT COUNT(*) FROM code_licenses")[0] == 1


def test_redeem_used_code_on_other_device_is_rejected_without_mutation(tmp_path: Path) -> None:
    service, database = build_service(tmp_path)
    import_code(database, CODE)
    first = service.redeem(CODE, DEVICE_HASH, "0.8.0")
    before_code = tuple(
        database.row(
            "SELECT status, redeemed_at, device_hash FROM activation_codes WHERE code_hash = ?",
            (code_hash(normalize_activation_code(CODE)),),
        )
    )

    with pytest.raises(ActivationCodeUsed) as exc_info:
        service.redeem(CODE, OTHER_DEVICE_HASH, "0.8.0")

    after_code = tuple(
        database.row(
            "SELECT status, redeemed_at, device_hash FROM activation_codes WHERE code_hash = ?",
            (code_hash(normalize_activation_code(CODE)),),
        )
    )
    assert before_code == after_code
    assert database.row("SELECT COUNT(*) FROM code_licenses")[0] == 1
    assert database.row("SELECT signed_payload FROM code_licenses")[0]
    assert first["license"]["payload"]["device_hash"] == DEVICE_HASH
    assert CODE not in str(exc_info.value)
    assert OTHER_DEVICE_HASH not in str(exc_info.value)


def test_available_new_code_for_licensed_device_returns_existing_without_consuming(
    tmp_path: Path,
) -> None:
    service, database = build_service(tmp_path)
    import_code(database, CODE)
    import_code(database, OTHER_CODE)
    first = service.redeem(CODE, DEVICE_HASH, "0.8.0")

    second = service.redeem(OTHER_CODE, DEVICE_HASH, "0.8.0")

    assert second == first
    assert database.code_stats() == {"available": 1, "redeemed": 1, "total": 2}
    assert database.row(
        "SELECT status FROM activation_codes WHERE code_hash = ?",
        (code_hash(normalize_activation_code(OTHER_CODE)),),
    )[0] == "available"


def test_malformed_stored_license_is_an_opaque_runtime_error(tmp_path: Path) -> None:
    service, database = build_service(tmp_path)
    import_code(database, CODE)
    service.redeem(CODE, DEVICE_HASH, "0.8.0")
    malformed = "secret-code secret-device {"
    database.row(
        "UPDATE code_licenses SET signed_payload = ?",
        (malformed,),
    )

    with pytest.raises(RuntimeError) as exc_info:
        service.redeem(CODE, DEVICE_HASH, "0.8.0")

    assert malformed not in str(exc_info.value)
    assert CODE not in str(exc_info.value)
    assert DEVICE_HASH not in str(exc_info.value)


def test_concurrent_devices_cannot_both_redeem_one_code(tmp_path: Path) -> None:
    service, database = build_service(tmp_path)
    import_code(database, CODE)

    def redeem(device_hash: str) -> tuple[str, str | None]:
        try:
            response = service.redeem(CODE, device_hash, "0.8.0")
            return response["status"], response["license"]["payload"]["device_hash"]
        except ActivationCodeUsed:
            return "used", None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(redeem, (DEVICE_HASH, OTHER_DEVICE_HASH)))

    assert sorted(status for status, _device in results) == ["licensed", "used"]
    assert database.row("SELECT COUNT(*) FROM code_licenses")[0] == 1


def test_public_service_error_contract_is_stable() -> None:
    assert InvalidActivationCode.code == "LIC-013"
    assert ActivationCodeUsed.code == "LIC-014"
    assert ClientVersionMismatch.code == "LIC-015"
