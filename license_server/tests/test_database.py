from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from typing import Literal, Optional, get_type_hints

import pytest

from license_server.database import Database, RedemptionResult


PRODUCT_ID = "opub-major-0"


def _database(tmp_path: Path) -> Database:
    database = Database(tmp_path / "licenses.sqlite3")
    database.initialize()
    return database


def _import(database: Database, code_hash: str = "code-1") -> None:
    database.import_activation_code(code_hash, PRODUCT_ID, "2026-09-06T00:00:00Z")


def test_initialize_creates_inventory_tables_wal_foreign_keys_and_legacy_tables(tmp_path: Path) -> None:
    database = _database(tmp_path)

    for table in ("orders", "licenses", "activation_codes", "code_licenses"):
        assert database.row(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        )[0] == table
    assert database.row("PRAGMA journal_mode")[0].lower() == "wal"
    assert database.row("PRAGMA foreign_keys")[0] == 1


def test_rows_returns_all_query_results(tmp_path: Path) -> None:
    database = _database(tmp_path)
    database.import_activation_codes(
        [("code-1", PRODUCT_ID, "created-1"), ("code-2", PRODUCT_ID, "created-2")]
    )

    assert [row["code_hash"] for row in database.rows(
        "SELECT code_hash FROM activation_codes ORDER BY code_hash"
    )] == ["code-1", "code-2"]


def test_redemption_result_is_frozen_with_exact_contract() -> None:
    assert get_type_hints(RedemptionResult) == {
        "status": Literal["created", "same_device", "used", "invalid", "existing_device"],
        "signed_payload": Optional[str],
    }
    assert [field.name for field in fields(RedemptionResult)] == ["status", "signed_payload"]
    result = RedemptionResult("invalid")
    with pytest.raises(FrozenInstanceError):
        result.status = "created"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("product_id", "other-product"),
        ("status", "invalid"),
        ("code_hash", None),
        ("product_id", None),
        ("status", None),
        ("created_at", None),
    ],
)
def test_activation_code_schema_rejects_invalid_values(
    tmp_path: Path, column: str, value: object
) -> None:
    database = _database(tmp_path)
    values = {
        "code_hash": "code-1",
        "product_id": PRODUCT_ID,
        "status": "available",
        "created_at": "created",
        "redeemed_at": None,
        "device_hash": None,
    }
    values[column] = value
    columns = ", ".join(values)
    with pytest.raises(sqlite3.IntegrityError):
        database.row(
            "INSERT INTO activation_codes ({}) VALUES ({})".format(
                columns, ", ".join("?" for _ in values)
            ),
            tuple(values.values()),
        )


def test_code_license_constraints_reject_orphan_duplicate_code_and_duplicate_device(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _import(database)
    database.redeem_activation_code("code-1", "device-1", "license-1", "payload-1", "issued-1")

    with pytest.raises(sqlite3.IntegrityError):
        database.row(
            "INSERT INTO code_licenses VALUES (?, ?, ?, ?, ?)",
            ("license-2", "missing", "device-2", "payload-2", "issued-2"),
        )
    with pytest.raises(sqlite3.IntegrityError):
        database.row(
            "INSERT INTO code_licenses VALUES (?, ?, ?, ?, ?)",
            ("license-2", "code-1", "device-2", "payload-2", "issued-2"),
        )
    database.import_activation_code("code-2", PRODUCT_ID, "created-2")
    with pytest.raises(sqlite3.IntegrityError):
        database.row(
            "INSERT INTO code_licenses VALUES (?, ?, ?, ?, ?)",
            ("license-2", "code-2", "device-1", "payload-2", "issued-2"),
        )


def test_batch_import_is_atomic_and_enforces_unique_code_hashes(tmp_path: Path) -> None:
    database = _database(tmp_path)
    database.import_activation_codes(
        [("code-1", PRODUCT_ID, "created-1"), ("code-2", PRODUCT_ID, "created-2")]
    )
    assert database.code_stats() == {"available": 2, "redeemed": 0, "total": 2}

    with pytest.raises(sqlite3.IntegrityError):
        database.import_activation_codes(
            [("code-3", PRODUCT_ID, "created-3"), ("code-1", PRODUCT_ID, "created-4")]
        )
    assert database.code_stats() == {"available": 2, "redeemed": 0, "total": 2}


def test_redeem_unknown_code_returns_invalid_without_mutation(tmp_path: Path) -> None:
    database = _database(tmp_path)

    assert database.redeem_activation_code(
        "missing", "device-1", "license-1", "payload-1", "issued-1"
    ) == RedemptionResult("invalid")
    assert database.code_stats() == {"available": 0, "redeemed": 0, "total": 0}


def test_redeem_available_code_creates_license_and_preserves_exact_payload(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _import(database)
    payload = '{"license_id":"license-1","signature":"exact"}'

    assert database.redeem_activation_code(
        "code-1", "device-1", "license-1", payload, "issued-1"
    ) == RedemptionResult("created", payload)
    assert database.code_stats() == {"available": 0, "redeemed": 1, "total": 1}
    assert database.row("SELECT signed_payload FROM code_licenses WHERE code_hash = ?", ("code-1",))[0] == payload
    row = database.row(
        "SELECT redeemed_at, device_hash FROM activation_codes WHERE code_hash = ?", ("code-1",)
    )
    assert tuple(row) == ("issued-1", "device-1")


def test_redeem_same_device_returns_stored_payload(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _import(database)
    database.redeem_activation_code("code-1", "device-1", "license-1", "payload-1", "issued-1")

    assert database.redeem_activation_code(
        "code-1", "device-1", "license-2", "payload-2", "issued-2"
    ) == RedemptionResult("same_device", "payload-1")
    assert database.row("SELECT COUNT(*) FROM code_licenses")[0] == 1


def test_redeem_other_device_returns_used_without_mutation(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _import(database)
    database.redeem_activation_code("code-1", "device-1", "license-1", "payload-1", "issued-1")

    assert database.redeem_activation_code(
        "code-1", "device-2", "license-2", "payload-2", "issued-2"
    ) == RedemptionResult("used")
    assert database.row("SELECT device_hash FROM activation_codes WHERE code_hash = ?", ("code-1",))[0] == "device-1"
    assert database.row("SELECT COUNT(*) FROM code_licenses")[0] == 1


def test_redeem_new_code_for_existing_device_preserves_available_code(tmp_path: Path) -> None:
    database = _database(tmp_path)
    database.import_activation_codes(
        [("code-1", PRODUCT_ID, "created-1"), ("code-2", PRODUCT_ID, "created-2")]
    )
    database.redeem_activation_code("code-1", "device-1", "license-1", "payload-1", "issued-1")

    assert database.redeem_activation_code(
        "code-2", "device-1", "license-2", "payload-2", "issued-2"
    ) == RedemptionResult("existing_device", "payload-1")
    assert database.code_stats() == {"available": 1, "redeemed": 1, "total": 2}
    assert database.row("SELECT status FROM activation_codes WHERE code_hash = ?", ("code-2",))[0] == "available"


def test_redeem_rolls_back_code_update_when_license_insert_fails(tmp_path: Path) -> None:
    database = _database(tmp_path)
    database.import_activation_codes(
        [("code-1", PRODUCT_ID, "created-1"), ("code-2", PRODUCT_ID, "created-2")]
    )
    database.redeem_activation_code("code-1", "device-1", "license-1", "payload-1", "issued-1")

    with pytest.raises(sqlite3.IntegrityError):
        database.redeem_activation_code(
            "code-2", "device-2", "license-1", "payload-2", "issued-2"
        )

    row = database.row(
        "SELECT status, redeemed_at, device_hash FROM activation_codes WHERE code_hash = ?", ("code-2",)
    )
    assert tuple(row) == ("available", None, None)
    assert database.row("SELECT COUNT(*) FROM code_licenses WHERE code_hash = ?", ("code-2",))[0] == 0


def test_concurrent_redemption_of_one_code_allows_one_created_and_one_used(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _import(database)

    def redeem(index: int) -> RedemptionResult:
        return database.redeem_activation_code(
            "code-1", "device-{}".format(index), "license-{}".format(index),
            "payload-{}".format(index), "issued-{}".format(index),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(redeem, [1, 2]))

    assert sorted(result.status for result in results) == ["created", "used"]
    assert database.row("SELECT COUNT(*) FROM code_licenses")[0] == 1
