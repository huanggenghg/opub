from __future__ import annotations

import base64
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from license_server.app import app_from_env, create_app
from license_server.codes import code_hash
from license_server.config import Settings
from license_server.database import Database
from license_server.service import (
    ActivationCodeUsed,
    ClientVersionMismatch,
    InvalidActivationCode,
    LicenseService,
)
from publish.licensing.codes import normalize_activation_code


VALID_CODE = "OPUB0-01234-56789-ABCDE-FGHJK-MNPQR-STVWX"
DEVICE_HASH = "a" * 64
ACTIVATION_BODY = {
    "device_hash": DEVICE_HASH,
    "activation_code": VALID_CODE,
    "client_version": "0.8.0",
}


@pytest.fixture()
def test_settings(tmp_path: Path) -> Settings:
    return Settings.from_env(
        {
            "OPUB_PUBLIC_BASE_URL": "https://license.opub.test",
            "OPUB_LICENSE_PRIVATE_KEY": base64.b64encode(bytes(range(32))).decode("ascii"),
            "OPUB_LICENSE_KEY_ID": "test-key",
            "OPUB_LICENSE_DB_PATH": str(tmp_path / "db.sqlite3"),
        }
    )


@pytest.fixture()
def database(test_settings: Settings) -> Database:
    return Database(test_settings.database_path)


@pytest.fixture()
def client(test_settings: Settings, database: Database) -> TestClient:
    return TestClient(create_app(test_settings, database))


@pytest.fixture()
def seeded_code(database: Database) -> str:
    database.import_activation_code(
        code_hash(normalize_activation_code(VALID_CODE)),
        "opub-major-0",
        "2026-09-06T00:00:00Z",
    )
    return VALID_CODE


def test_app_exposes_only_code_activation(client: TestClient) -> None:
    paths = {
        route.path
        for route in client.app.routes
        if getattr(route, "path", "").startswith("/v1/")
    }
    assert paths == {"/v1/code-activations"}


def test_code_activation_returns_real_license(
    client: TestClient, seeded_code: str
) -> None:
    response = client.post(
        "/v1/code-activations",
        json={**ACTIVATION_BODY, "activation_code": seeded_code},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "licensed"
    assert response.json()["license"]["payload"]["device_hash"] == DEVICE_HASH
    assert response.json()["license"]["payload"]["product"] == "opub-major-0"


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (InvalidActivationCode, 400, "LIC-013"),
        (ActivationCodeUsed, 409, "LIC-014"),
        (ClientVersionMismatch, 422, "LIC-015"),
    ],
)
def test_public_errors_are_stable(
    error: type[ValueError],
    status_code: int,
    code: str,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args, **_kwargs):
        raise error()

    monkeypatch.setattr(LicenseService, "redeem", fail)
    response = client.post("/v1/code-activations", json=ACTIVATION_BODY)

    assert response.status_code == status_code
    assert response.json() == {"detail": {"code": code}}


@pytest.mark.parametrize(
    "overrides",
    [
        {"device_hash": "xyz"},
        {"device_hash": "A" * 64},
        {"device_hash": "a" * 63},
        {"activation_code": ""},
        {"activation_code": "x" * 65},
        {"client_version": ""},
        {"client_version": "x" * 65},
    ],
)
def test_invalid_request_is_rejected_without_echoing_values(
    client: TestClient, overrides: dict[str, str]
) -> None:
    body = {**ACTIVATION_BODY, **overrides}
    response = client.post("/v1/code-activations", json=body)

    assert response.status_code == 422
    for submitted in body.values():
        if submitted:
            assert submitted not in response.text


def test_missing_request_field_is_rejected(client: TestClient) -> None:
    body = {key: value for key, value in ACTIVATION_BODY.items() if key != "client_version"}

    response = client.post("/v1/code-activations", json=body)

    assert response.status_code == 422
    assert DEVICE_HASH not in response.text
    assert VALID_CODE not in response.text


def test_per_device_rate_limit_allows_sixty_requests_then_rejects(
    client: TestClient, seeded_code: str
) -> None:
    for _ in range(60):
        assert client.post("/v1/code-activations", json=ACTIVATION_BODY).status_code == 200

    assert client.post("/v1/code-activations", json=ACTIVATION_BODY).status_code == 429
    other_device = {**ACTIVATION_BODY, "device_hash": "b" * 64}
    assert client.post("/v1/code-activations", json=other_device).status_code == 409


def test_per_ip_rate_limit_prevents_bypass_by_rotating_devices(client: TestClient) -> None:
    for index in range(120):
        rotating = {**ACTIVATION_BODY, "device_hash": f"{index:064x}"}
        assert client.post("/v1/code-activations", json=rotating).status_code == 400

    fresh_device = {**ACTIVATION_BODY, "device_hash": "f" * 64}
    assert client.post("/v1/code-activations", json=fresh_device).status_code == 429


def test_runtime_failure_returns_opaque_503_and_safe_log(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_message = f"failure {VALID_CODE} {DEVICE_HASH}"

    def fail(*_args, **_kwargs):
        raise RuntimeError(secret_message)

    monkeypatch.setattr(LicenseService, "redeem", fail)
    with caplog.at_level(logging.ERROR, logger="opub.license"):
        response = client.post("/v1/code-activations", json=ACTIVATION_BODY)

    assert response.status_code == 503
    assert response.json()["detail"] == "service unavailable"
    assert response.json()["request_id"]
    assert "RuntimeError" in caplog.text
    assert "/v1/code-activations" in caplog.text
    for secret in (secret_message, VALID_CODE, DEVICE_HASH):
        assert secret not in response.text
        assert secret not in caplog.text


def test_sqlite_failure_returns_opaque_503(
    client: TestClient, database: Database, seeded_code: str
) -> None:
    database.row("DROP TABLE activation_codes")

    response = client.post("/v1/code-activations", json=ACTIVATION_BODY)

    assert response.status_code == 503
    assert response.json()["detail"] == "service unavailable"
    assert response.json()["request_id"]
    assert VALID_CODE not in response.text
    assert DEVICE_HASH not in response.text


def test_documentation_routes_are_disabled(client: TestClient) -> None:
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_app_from_env_starts_with_only_four_required_variables(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    names = (
        "OPUB_PUBLIC_BASE_URL",
        "OPUB_LICENSE_PRIVATE_KEY",
        "OPUB_LICENSE_KEY_ID",
        "OPUB_LICENSE_DB_PATH",
        "OPUB_PAYMENT_RETURN_URL",
        "OPUB_MBD_APP_ID",
        "OPUB_MBD_APP_KEY",
    )
    for name in names:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPUB_PUBLIC_BASE_URL", "https://license.opub.test")
    monkeypatch.setenv(
        "OPUB_LICENSE_PRIVATE_KEY",
        base64.b64encode(bytes(range(32))).decode("ascii"),
    )
    monkeypatch.setenv("OPUB_LICENSE_KEY_ID", "test-key")
    monkeypatch.setenv("OPUB_LICENSE_DB_PATH", str(tmp_path / "env.sqlite3"))

    application = app_from_env()

    client = TestClient(application)
    assert client.get("/docs").status_code == 404
    assert Path(tmp_path / "env.sqlite3").exists()
