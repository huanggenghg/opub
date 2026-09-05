from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from license_server.database import Database, RepositoryError
from license_server.models import Checkout, ProviderOrder


def _database(tmp_path: Path) -> Database:
    database = Database(tmp_path / "licenses.sqlite3")
    database.initialize()
    return database


def _insert(database: Database, *, session_id: str = "session-1", device_hash: str = "device-1", provider_order_id: str = "provider-1", token_hash: str = "token-1", expires_at: str | None = None) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    database.insert_pending(
        session_id=session_id,
        provider_order_id=provider_order_id,
        device_hash=device_hash,
        poll_token_hash=token_hash,
        created_at=now.isoformat(),
        expires_at=expires_at or (now + timedelta(minutes=15)).isoformat(),
        payway="wechat",
        checkout=Checkout("url", "https://pay.example/order-1"),
    )


def test_initialize_creates_tables_wal_and_foreign_keys(tmp_path: Path) -> None:
    database = _database(tmp_path)

    assert database.row("SELECT name FROM sqlite_master WHERE type='table' AND name=?", ("orders",))[0] == "orders"
    assert database.row("SELECT name FROM sqlite_master WHERE type='table' AND name=?", ("licenses",))[0] == "licenses"
    assert database.row("PRAGMA journal_mode")[0].lower() == "wal"
    assert database.row("PRAGMA foreign_keys")[0] == 1

    with database._connect() as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_insert_pending_persists_fixed_product_amount_checkout_and_expiry(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _insert(database)

    row = database.order_by_session("session-1")
    assert row["product_id"] == "opub-lifetime-v1"
    assert row["amount_fen"] == 990
    assert row["status"] == "pending"
    assert row["checkout_kind"] == "url"
    assert row["checkout_value"] == "https://pay.example/order-1"
    assert row["expires_at"]


@pytest.mark.parametrize(
    ("column", "value"),
    [("product_id", "wrong"), ("amount_fen", 1), ("status", "unknown"), ("payway", "stripe"), ("checkout_kind", "json"), ("poll_token_hash", None)],
)
def test_sqlite_rejects_invalid_order_values(tmp_path: Path, column: str, value: object) -> None:
    database = _database(tmp_path)
    values = {
        "session_id": "session-1", "provider_order_id": "provider-1", "device_hash": "device-1",
        "product_id": "opub-lifetime-v1", "amount_fen": 990, "status": "pending", "poll_token_hash": "token",
        "created_at": "now", "expires_at": "later", "payway": "wechat", "checkout_kind": "url", "checkout_value": "x",
    }
    values[column] = value
    columns = ", ".join(values)
    with pytest.raises(sqlite3.IntegrityError):
        database.row(f"INSERT INTO orders ({columns}) VALUES ({','.join('?' for _ in values)})", tuple(values.values()))


def test_one_pending_per_device_and_expiring_allows_replacement(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _insert(database)
    with pytest.raises(RepositoryError):
        _insert(database, session_id="session-2", provider_order_id="provider-2")

    database.expire_pending("device-1", "expired-at")
    _insert(database, session_id="session-2", provider_order_id="provider-2")
    assert database.pending_for_device("device-1")["session_id"] == "session-2"


def test_token_rotation_invalidates_old_and_unknown_tokens_do_not_match(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _insert(database)
    assert database.poll_token_matches("session-1", "token-1")
    assert not database.poll_token_matches("session-1", "unknown")
    database.rotate_poll_token("session-1", "token-2")
    assert not database.poll_token_matches("session-1", "token-1")
    assert database.poll_token_matches("session-1", "token-2")


def test_issue_stores_paid_order_and_license_and_lookup(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _insert(database)
    payload = '{"license_id":"license-1"}'
    assert database.issue_license("session-1", "charge-1", payload, "license-1", "2026-09-05T00:00:00Z") == payload
    order = database.order_by_session("session-1")
    assert order["status"] == "paid"
    assert order["provider_charge_id"] == "charge-1"
    assert database.license_for_device("device-1")["signed_payload"] == payload


def test_verified_expired_order_becomes_paid_and_issues_license(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _insert(database)
    database.expire_pending("device-1", "expired-at")

    assert database.issue_license("session-1", "charge-1", "payload-1", "license-1", "time-1") == "payload-1"
    order = database.order_by_session("session-1")
    assert order["status"] == "paid"
    assert order["provider_charge_id"] == "charge-1"
    assert order["paid_at"] == "time-1"
    assert database.license_for_device("device-1")["signed_payload"] == "payload-1"


def test_verified_failed_order_becomes_paid_and_returns_original_license(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _insert(database)
    database.issue_license("session-1", "charge-1", "payload-1", "license-1", "time-1")
    _insert(database, session_id="session-2", provider_order_id="provider-2")
    database.mark_verification_failed("session-2")

    assert database.issue_license("session-2", "charge-2", "payload-2", "license-2", "time-2") == "payload-1"
    order = database.order_by_session("session-2")
    assert order["status"] == "paid"
    assert order["provider_charge_id"] == "charge-2"
    assert order["paid_at"] == "time-2"
    assert database.row("SELECT COUNT(*) FROM licenses")[0] == 1


def test_repeated_issue_for_paid_order_is_idempotent(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _insert(database)
    database.issue_license("session-1", "charge-1", "payload-1", "license-1", "time-1")

    assert database.issue_license("session-1", "charge-1", "payload-2", "license-2", "time-2") == "payload-1"
    order = database.order_by_session("session-1")
    assert order["status"] == "paid"
    assert order["provider_charge_id"] == "charge-1"
    assert order["paid_at"] == "time-1"


def test_second_order_for_paid_device_returns_original_license(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _insert(database)
    database.issue_license("session-1", "charge-1", "payload-1", "license-1", "time-1")
    _insert(database, session_id="session-2", provider_order_id="provider-2")
    assert database.issue_license("session-2", "charge-2", "payload-2", "license-2", "time-2") == "payload-1"
    assert database.row("SELECT COUNT(*) FROM licenses")[0] == 1


def test_concurrent_issuance_returns_stored_payload(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _insert(database)

    def issue(index: int) -> str:
        return database.issue_license("session-1", "charge-1", f"payload-{index}", f"license-{index}", "time")

    with ThreadPoolExecutor(max_workers=2) as pool:
        payloads = list(pool.map(issue, [1, 2]))
    assert payloads[0] == payloads[1]
    assert database.row("SELECT COUNT(*) FROM licenses")[0] == 1


def test_provider_charge_uniqueness_prevents_reuse(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _insert(database)
    database.issue_license("session-1", "charge-1", "payload-1", "license-1", "time-1")
    _insert(database, session_id="session-2", device_hash="device-2", provider_order_id="provider-2")
    with pytest.raises(sqlite3.IntegrityError):
        database.issue_license("session-2", "charge-1", "payload-2", "license-2", "time-2")
    assert database.order_by_session("session-2")["status"] == "pending"
    assert database.order_by_session("session-2")["provider_charge_id"] is None
    assert database.row("SELECT COUNT(*) FROM licenses")[0] == 1


def test_value_objects_are_frozen_with_exact_fields() -> None:
    assert [field.name for field in fields(Checkout)] == ["kind", "value"]
    assert [field.name for field in fields(ProviderOrder)] == [
        "state", "amount", "description", "charge_id", "payway", "raw"
    ]
    checkout = Checkout("url", "https://pay.example")
    provider_order = ProviderOrder(1, 990, "opub", "charge-1", 2, {"state": 1})
    with pytest.raises(FrozenInstanceError):
        checkout.kind = "html"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        provider_order.amount = 1  # type: ignore[misc]


def test_order_and_license_constraints_and_lookup_contract(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _insert(database)
    first = database.order_by_session("session-1")
    assert database.order_by_provider_id("provider-1") == first

    with pytest.raises(sqlite3.IntegrityError):
        database.row(
            "INSERT INTO orders (session_id, provider_order_id, device_hash, product_id, amount_fen, status, poll_token_hash, created_at, expires_at, payway, checkout_kind, checkout_value) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("session-1", "provider-2", "device-2", "opub-lifetime-v1", 990, "pending", "token-2", "now", "later", "wechat", "url", "x"),
        )
    with pytest.raises(sqlite3.IntegrityError):
        database.row(
            "INSERT INTO orders (session_id, provider_order_id, device_hash, product_id, amount_fen, status, poll_token_hash, created_at, expires_at, payway, checkout_kind, checkout_value) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("session-2", "provider-1", "device-2", "opub-lifetime-v1", 990, "pending", "token-2", "now", "later", "wechat", "url", "x"),
        )

    database.issue_license("session-1", "charge-1", "payload-1", "license-1", "time-1")
    with pytest.raises(sqlite3.IntegrityError):
        database.row(
            "INSERT INTO licenses (license_id, session_id, device_hash, signed_payload, issued_at) VALUES (?, ?, ?, ?, ?)",
            ("license-1", "session-1", "device-1", "payload-2", "time-2"),
        )
    with pytest.raises(sqlite3.IntegrityError):
        database.row(
            "INSERT INTO licenses (license_id, session_id, device_hash, signed_payload, issued_at) VALUES (?, ?, ?, ?, ?)",
            ("license-2", "session-1", "device-2", "payload-2", "time-2"),
        )
    with pytest.raises(sqlite3.IntegrityError):
        database.row(
            "INSERT INTO licenses (license_id, session_id, device_hash, signed_payload, issued_at) VALUES (?, ?, ?, ?, ?)",
            ("license-2", "session-2", "device-1", "payload-2", "time-2"),
        )
    with pytest.raises(sqlite3.IntegrityError):
        database.row(
            "INSERT INTO licenses (license_id, session_id, device_hash, signed_payload, issued_at) VALUES (?, ?, ?, ?, ?)",
            ("license-2", "missing", "device-2", "payload-2", "time-2"),
        )


@pytest.mark.parametrize("null_column", ["license_id", "session_id", "device_hash", "signed_payload", "issued_at"])
def test_license_columns_are_not_null(tmp_path: Path, null_column: str) -> None:
    database = _database(tmp_path)
    _insert(database)
    values = {
        "license_id": "license-1",
        "session_id": "session-1",
        "device_hash": "device-1",
        "signed_payload": "payload-1",
        "issued_at": "time-1",
    }
    values[null_column] = None
    with pytest.raises(sqlite3.IntegrityError):
        database.row(
            "INSERT INTO licenses (license_id, session_id, device_hash, signed_payload, issued_at) VALUES (?, ?, ?, ?, ?)",
            tuple(values.values()),
        )


def test_nullable_provider_charges_can_repeat(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _insert(database, device_hash="device-1")
    _insert(database, session_id="session-2", device_hash="device-2", provider_order_id="provider-2")
    assert database.row("SELECT COUNT(*) FROM orders WHERE provider_charge_id IS NULL")[0] == 2


def test_expire_and_verification_failed_only_affect_pending(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _insert(database)
    _insert(database, session_id="session-2", device_hash="device-2", provider_order_id="provider-2", token_hash="token-2")
    database.mark_verification_failed("session-1")
    database.expire_pending("device-2", "expired-at")
    assert database.order_by_session("session-1")["status"] == "verification_failed"
    assert database.order_by_session("session-2")["status"] == "expired"
    database.mark_verification_failed("session-1")
    database.expire_pending("device-1", "again")
    assert database.order_by_session("session-1")["status"] == "verification_failed"
