from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from license_server.config import Settings
from license_server.database import Database
from license_server.mianbaoduo import ProviderError
from license_server.models import Checkout, ProviderOrder
from license_server.service import LicenseService, token_hash
from license_server.signing import canonical_json

DEVICE_HASH = "a" * 64
PRODUCT_NAME = "opub 永久设备许可证"


class FakeProvider:
    def __init__(self) -> None:
        self.create_calls: List[Dict[str, Any]] = []
        self.query_result: ProviderOrder = ProviderOrder(1, 990, PRODUCT_NAME, "charge-1", 1, {})

    def create_checkout(self, payway: str, order_id: str, description: str, amount_fen: int) -> Checkout:
        self.create_calls.append(
            {"payway": payway, "order_id": order_id, "description": description, "amount_fen": amount_fen}
        )
        if payway == "wechat":
            return Checkout("url", "https://pay.test/order")
        return Checkout("html", "<form></form>")

    def query_order(self, order_id: str) -> ProviderOrder:
        return self.query_result


def build_service(tmp_path: Path):
    settings = Settings.from_env(
        {
            "OPUB_PUBLIC_BASE_URL": "https://license.opub.test",
            "OPUB_PAYMENT_RETURN_URL": "https://opub.test/done",
            "OPUB_MBD_APP_ID": "app",
            "OPUB_MBD_APP_KEY": "key",
            "OPUB_LICENSE_PRIVATE_KEY": base64.b64encode(bytes(range(32))).decode("ascii"),
            "OPUB_LICENSE_KEY_ID": "test",
            "OPUB_LICENSE_DB_PATH": str(tmp_path / "db.sqlite3"),
        }
    )
    database = Database(settings.database_path)
    database.initialize()
    provider = FakeProvider()
    return LicenseService(settings, database, provider), database, provider


def provider_order_id_for(database: Database, session_id: str) -> str:
    return str(database.order_by_session(session_id)["provider_order_id"])


def make_stale(database: Database, session_id: str) -> None:
    stale = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    database.row("UPDATE orders SET expires_at = ? WHERE session_id = ?", (stale, session_id))


def test_fixed_price_reuse_token_rotation_and_payway_change(tmp_path: Path) -> None:
    service, database, provider = build_service(tmp_path)
    first = service.create_session(DEVICE_HASH, "wechat")
    same = service.create_session(DEVICE_HASH, "wechat")
    changed = service.create_session(DEVICE_HASH, "alipay")
    assert provider.create_calls[0]["amount_fen"] == 990
    assert provider.create_calls[0]["description"] == PRODUCT_NAME
    assert same["session_id"] == first["session_id"]
    assert same["poll_token"] != first["poll_token"]
    assert changed["session_id"] != first["session_id"]
    assert database.order_by_session(first["session_id"])["status"] == "expired"


def test_verified_webhook_is_idempotent_and_device_recovers_license(tmp_path: Path) -> None:
    service, database, provider = build_service(tmp_path)
    created = service.create_session(DEVICE_HASH, "wechat")
    order_id = provider_order_id_for(database, created["session_id"])
    assert service.handle_charge_succeeded(order_id)["status"] == "licensed"
    assert service.handle_charge_succeeded(order_id)["status"] == "licensed"
    assert database.row("SELECT COUNT(*) AS count FROM licenses")["count"] == 1
    recovered = service.create_session(DEVICE_HASH, "alipay")
    assert recovered["status"] == "licensed"
    assert len(provider.create_calls) == 1


@pytest.mark.parametrize(
    "result",
    [
        ProviderOrder(0, 990, PRODUCT_NAME, "charge-1", 1, {}),
        ProviderOrder(3, 990, PRODUCT_NAME, "charge-1", 1, {}),
        ProviderOrder(1, 991, PRODUCT_NAME, "charge-1", 1, {}),
        ProviderOrder(1, 990, "wrong product", "charge-1", 1, {}),
        ProviderOrder(1, 990, PRODUCT_NAME, "charge-1", 2, {}),
    ],
)
def test_unverified_provider_result_never_issues(tmp_path: Path, result: ProviderOrder) -> None:
    service, database, provider = build_service(tmp_path)
    created = service.create_session(DEVICE_HASH, "wechat")
    order_id = provider_order_id_for(database, created["session_id"])
    provider.query_result = result
    assert service.handle_charge_succeeded(order_id)["status"] == "verification_failed"
    assert database.row("SELECT COUNT(*) AS count FROM licenses")["count"] == 0


def test_unknown_webhook_is_ignored(tmp_path: Path) -> None:
    service, database, provider = build_service(tmp_path)
    assert service.handle_charge_succeeded("unknown") == {"status": "ignored"}
    assert database.row("SELECT COUNT(*) AS count FROM licenses")["count"] == 0


def test_concurrent_duplicate_webhooks_issue_once(tmp_path: Path) -> None:
    service, database, provider = build_service(tmp_path)
    created = service.create_session(DEVICE_HASH, "wechat")
    order_id = provider_order_id_for(database, created["session_id"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(service.handle_charge_succeeded, [order_id, order_id]))
    assert all(result["status"] == "licensed" for result in results)
    assert database.row("SELECT COUNT(*) AS count FROM licenses")["count"] == 1


def test_get_session_accepts_raw_poll_token_and_stores_only_its_hash(tmp_path: Path) -> None:
    service, database, provider = build_service(tmp_path)
    created = service.create_session(DEVICE_HASH, "wechat")
    assert service.get_session(created["session_id"], created["poll_token"]) == {"status": "pending"}
    stored = database.order_by_session(created["session_id"])["poll_token_hash"]
    assert stored == token_hash(created["poll_token"])
    assert stored != created["poll_token"]
    with pytest.raises(PermissionError):
        service.get_session(created["session_id"], "wrong-token")
    with pytest.raises(PermissionError):
        service.get_session("missing-session", "any-token")
    with pytest.raises(PermissionError):
        service.get_session(created["session_id"], "非ASCII令牌")


def test_get_session_rejects_rotated_poll_token(tmp_path: Path) -> None:
    service, database, provider = build_service(tmp_path)
    first = service.create_session(DEVICE_HASH, "wechat")
    second = service.create_session(DEVICE_HASH, "wechat")
    assert second["session_id"] == first["session_id"]
    with pytest.raises(PermissionError):
        service.get_session(first["session_id"], first["poll_token"])
    assert service.get_session(second["session_id"], second["poll_token"]) == {"status": "pending"}


def test_get_session_expires_stale_pending_order(tmp_path: Path) -> None:
    service, database, provider = build_service(tmp_path)
    created = service.create_session(DEVICE_HASH, "wechat")
    make_stale(database, created["session_id"])
    assert service.get_session(created["session_id"], created["poll_token"]) == {"status": "expired"}
    assert database.order_by_session(created["session_id"])["status"] == "expired"


def test_stale_pending_session_is_replaced_with_new_checkout(tmp_path: Path) -> None:
    service, database, provider = build_service(tmp_path)
    first = service.create_session(DEVICE_HASH, "wechat")
    make_stale(database, first["session_id"])
    second = service.create_session(DEVICE_HASH, "wechat")
    assert second["session_id"] != first["session_id"]
    assert database.order_by_session(first["session_id"])["status"] == "expired"
    assert len(provider.create_calls) == 2


def test_get_session_returns_signed_license_after_verified_webhook(tmp_path: Path) -> None:
    service, database, provider = build_service(tmp_path)
    created = service.create_session(DEVICE_HASH, "wechat")
    order_id = provider_order_id_for(database, created["session_id"])
    assert service.handle_charge_succeeded(order_id)["status"] == "licensed"
    response = service.get_session(created["session_id"], created["poll_token"])
    assert response["status"] == "licensed"
    document = response["license"]
    assert document["payload"]["device_hash"] == DEVICE_HASH
    assert document["payload"]["product"] == "opub-lifetime-v1"
    assert document["payload"]["key_id"] == "test"
    public_key = Ed25519PrivateKey.from_private_bytes(bytes(range(32))).public_key()
    public_key.verify(base64.b64decode(document["signature"]), canonical_json(document["payload"]))


def test_provider_failure_propagates_and_order_stays_pending(tmp_path: Path) -> None:
    service, database, provider = build_service(tmp_path)
    created = service.create_session(DEVICE_HASH, "wechat")
    order_id = provider_order_id_for(database, created["session_id"])

    def failing_query(order_id: str) -> ProviderOrder:
        raise ProviderError("Mianbaoduo order query request failed")

    provider.query_order = failing_query  # type: ignore[method-assign]
    with pytest.raises(ProviderError):
        service.handle_charge_succeeded(order_id)
    assert database.order_by_session(created["session_id"])["status"] == "pending"
    assert database.row("SELECT COUNT(*) AS count FROM licenses")["count"] == 0


def test_verification_failed_order_recovers_when_provider_confirms_payment(tmp_path: Path) -> None:
    service, database, provider = build_service(tmp_path)
    created = service.create_session(DEVICE_HASH, "wechat")
    order_id = provider_order_id_for(database, created["session_id"])
    provider.query_result = ProviderOrder(0, 990, PRODUCT_NAME, "charge-1", 1, {})
    assert service.handle_charge_succeeded(order_id)["status"] == "verification_failed"
    provider.query_result = ProviderOrder(1, 990, PRODUCT_NAME, "charge-1", 1, {})
    assert service.handle_charge_succeeded(order_id)["status"] == "licensed"
    assert service.get_session(created["session_id"], created["poll_token"])["status"] == "licensed"
