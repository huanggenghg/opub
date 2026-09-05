from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from license_server.app import app_from_env, create_app
from license_server.config import Settings
from license_server.database import Database
from license_server.mianbaoduo import ProviderError
from license_server.models import Checkout, ProviderOrder

DEVICE_HASH = "a" * 64
PRODUCT_NAME = "opub 永久设备许可证"
VERIFIED_ORDER = ProviderOrder(1, 990, PRODUCT_NAME, "charge-x", 1, {})
CREATION_BODY = {
    "device_hash": DEVICE_HASH,
    "client_nonce": "b" * 32,
    "client_version": "0.7.0",
    "payway": "wechat",
}


@pytest.fixture()
def test_settings(tmp_path: Path) -> Settings:
    return Settings.from_env(
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


@pytest.fixture()
def database(test_settings: Settings) -> Database:
    return Database(test_settings.database_path)


@pytest.fixture()
def provider() -> Mock:
    """A Mianbaoduo-compatible mock: no network, tracks the created order id."""
    provider = Mock()
    provider.last_order_id = None

    def create_checkout(payway: str, order_id: str, description: str, amount_fen: int) -> Checkout:
        provider.last_order_id = order_id
        return Checkout("url", "https://pay.test/order")

    provider.create_checkout = Mock(side_effect=create_checkout)
    provider.query_order = Mock(return_value=VERIFIED_ORDER)
    return provider


@pytest.fixture()
def client(test_settings: Settings, database: Database, provider: Mock) -> TestClient:
    return TestClient(create_app(test_settings, database, provider))


def create_session(client: TestClient, body: dict[str, Any] | None = None) -> dict[str, Any]:
    response = client.post("/v1/activation-sessions", json=body or CREATION_BODY)
    assert response.status_code == 201
    return response.json()


def poll(client: TestClient, session: dict[str, Any]) -> Any:
    return client.get(
        f"/v1/activation-sessions/{session['session_id']}",
        headers={"Authorization": f"Bearer {session['poll_token']}"},
    )


def test_create_and_poll_pending_session(client: TestClient) -> None:
    created = client.post("/v1/activation-sessions", json=CREATION_BODY)
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "pending"
    assert body["session_id"]
    assert body["poll_token"]
    assert body["checkout"] == {"kind": "url", "value": "https://pay.test/order"}
    assert body["expires_at"]

    polled = poll(client, body)
    assert polled.status_code == 200
    assert polled.json() == {"status": "pending"}


@pytest.mark.parametrize(
    "overrides",
    [
        {"device_hash": "xyz"},
        {"device_hash": "A" * 64},
        {"device_hash": "a" * 63},
        {"client_nonce": "b" * 10},
        {"client_nonce": "b" * 257},
        {"client_version": ""},
        {"client_version": "x" * 65},
        {"payway": "paypal"},
    ],
)
def test_invalid_creation_payload_is_rejected(client: TestClient, overrides: dict[str, Any]) -> None:
    response = client.post("/v1/activation-sessions", json={**CREATION_BODY, **overrides})
    assert response.status_code == 422


def test_missing_creation_field_is_rejected(client: TestClient) -> None:
    body = {key: value for key, value in CREATION_BODY.items() if key != "client_version"}
    response = client.post("/v1/activation-sessions", json=body)
    assert response.status_code == 422


def test_validation_errors_do_not_echo_submitted_values(client: TestClient) -> None:
    response = client.post(
        "/v1/activation-sessions",
        json={
            "device_hash": "A" * 64,
            "client_nonce": "b" * 32,
            "client_version": "0.7.0",
            "payway": "paypal",
        },
    )
    assert response.status_code == 422
    assert "A" * 64 not in response.text
    assert "b" * 32 not in response.text


def test_poll_rejects_missing_and_wrong_bearer_token(client: TestClient) -> None:
    created = create_session(client)
    session_path = f"/v1/activation-sessions/{created['session_id']}"
    assert client.get(session_path).status_code == 401
    assert client.get(session_path, headers={"Authorization": "Basic abc"}).status_code == 401
    assert (
        client.get(session_path, headers={"Authorization": "Bearer wrong-token"}).status_code == 401
    )
    # Unknown sessions answer 401, not 404, to avoid session enumeration.
    assert (
        client.get("/v1/activation-sessions/missing", headers={"Authorization": "Bearer x"})
        .status_code
        == 401
    )


def test_charge_succeeded_webhook_licenses_and_poll_returns_license(
    client: TestClient, provider: Mock
) -> None:
    created = create_session(client)
    notified = client.post(
        "/v1/webhooks/mianbaoduo",
        json={"type": "charge_succeeded", "data": {"out_trade_no": provider.last_order_id}},
    )
    assert notified.status_code == 200
    assert notified.json() == {"status": "licensed"}

    polled = poll(client, created)
    assert polled.status_code == 200
    assert polled.json()["status"] == "licensed"
    assert polled.json()["license"]["payload"]["device_hash"] == DEVICE_HASH


def test_charge_succeeded_webhook_is_idempotent(client: TestClient, provider: Mock) -> None:
    create_session(client)
    for _ in range(2):
        notified = client.post(
            "/v1/webhooks/mianbaoduo",
            json={"type": "charge_succeeded", "data": {"out_trade_no": provider.last_order_id}},
        )
        assert notified.status_code == 200
        assert notified.json() == {"status": "licensed"}
    # The second delivery is answered from the database without a provider query.
    assert provider.query_order.call_count == 1


def test_unknown_webhook_type_is_acknowledged_without_issuance(
    client: TestClient, provider: Mock
) -> None:
    created = create_session(client)
    response = client.post(
        "/v1/webhooks/mianbaoduo",
        json={"type": "refund_succeeded", "data": {"out_trade_no": provider.last_order_id}},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}
    provider.query_order.assert_not_called()
    assert poll(client, created).json() == {"status": "pending"}


def test_charge_succeeded_for_unknown_order_is_ignored(client: TestClient, provider: Mock) -> None:
    response = client.post(
        "/v1/webhooks/mianbaoduo",
        json={"type": "charge_succeeded", "data": {"out_trade_no": "opub_missing"}},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}
    provider.query_order.assert_not_called()


def test_charge_succeeded_without_order_id_is_ignored(client: TestClient, provider: Mock) -> None:
    response = client.post(
        "/v1/webhooks/mianbaoduo", json={"type": "charge_succeeded", "data": {}}
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}
    provider.query_order.assert_not_called()


def test_complaint_webhook_is_acknowledged_without_issuance(
    client: TestClient, provider: Mock
) -> None:
    created = create_session(client)
    response = client.post(
        "/v1/webhooks/mianbaoduo",
        json={
            "type": "complaint",
            "data": {"out_trade_no": provider.last_order_id, "reason": "not as described"},
        },
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}
    provider.query_order.assert_not_called()
    assert poll(client, created).json() == {"status": "pending"}


def _complaint_records(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        record.getMessage()
        for record in caplog.records
        if "payment complaint" in record.getMessage()
    ]


def test_complaint_webhook_order_id_cannot_inject_log_lines(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="opub.license"):
        response = client.post(
            "/v1/webhooks/mianbaoduo",
            json={"type": "complaint", "data": {"out_trade_no": "evil\nFAKE-LOG ev\ril"}},
        )
    assert response.status_code == 200
    messages = _complaint_records(caplog)
    assert len(messages) == 1
    assert "\n" not in messages[0]
    assert "\r" not in messages[0]
    # The forged marker survives only inline, flattened onto the single line.
    assert "evil FAKE-LOG evil" in messages[0]


def test_complaint_webhook_order_id_is_truncated_in_logs(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="opub.license"):
        response = client.post(
            "/v1/webhooks/mianbaoduo",
            json={"type": "complaint", "data": {"out_trade_no": "x" * 200}},
        )
    assert response.status_code == 200
    messages = _complaint_records(caplog)
    assert len(messages) == 1
    assert "x" * 128 in messages[0]
    assert "x" * 129 not in messages[0]


def test_creation_rate_limited_after_sixty_requests(client: TestClient) -> None:
    for _ in range(60):
        assert client.post("/v1/activation-sessions", json=CREATION_BODY).status_code == 201
    assert client.post("/v1/activation-sessions", json=CREATION_BODY).status_code == 429
    # A different device from the same IP is a separate bucket.
    other_device = {**CREATION_BODY, "device_hash": "c" * 64}
    assert client.post("/v1/activation-sessions", json=other_device).status_code == 201


def test_polling_rate_limited_after_180_requests(client: TestClient) -> None:
    created = create_session(client)
    for _ in range(180):
        assert poll(client, created).status_code == 200
    assert poll(client, created).status_code == 429


def test_provider_failure_returns_redacted_503(client: TestClient, provider: Mock) -> None:
    provider.create_checkout.side_effect = RuntimeError(
        "secret-app-key device-hash checkout-html"
    )
    response = client.post("/v1/activation-sessions", json=CREATION_BODY)
    assert response.status_code == 503
    body = response.text
    assert "request_id" in body
    for secret in ("secret-app-key", "device-hash", "checkout-html", "a" * 64):
        assert secret not in body


def test_provider_error_returns_503(client: TestClient, provider: Mock) -> None:
    provider.create_checkout.side_effect = ProviderError(
        "Mianbaoduo wechat checkout request failed"
    )
    response = client.post("/v1/activation-sessions", json=CREATION_BODY)
    assert response.status_code == 503
    assert "request_id" in response.text


def test_database_failure_returns_redacted_503(client: TestClient, database: Database) -> None:
    database.row("DROP TABLE licenses")
    response = client.post("/v1/activation-sessions", json=CREATION_BODY)
    assert response.status_code == 503
    assert "request_id" in response.text


def test_provider_failure_logs_only_the_exception_class(
    client: TestClient, provider: Mock, caplog: pytest.LogCaptureFixture
) -> None:
    provider.create_checkout.side_effect = RuntimeError("secret-app-key")
    with caplog.at_level(logging.ERROR, logger="opub.license"):
        client.post("/v1/activation-sessions", json=CREATION_BODY)
    assert "RuntimeError" in caplog.text
    assert "secret-app-key" not in caplog.text


def test_documentation_routes_are_disabled(client: TestClient) -> None:
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_app_from_env_requires_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "OPUB_PUBLIC_BASE_URL",
        "OPUB_PAYMENT_RETURN_URL",
        "OPUB_MBD_APP_ID",
        "OPUB_MBD_APP_KEY",
        "OPUB_LICENSE_PRIVATE_KEY",
        "OPUB_LICENSE_KEY_ID",
        "OPUB_LICENSE_DB_PATH",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ValueError):
        app_from_env()
