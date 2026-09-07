from __future__ import annotations

import base64
import json
import shutil
import stat
from pathlib import Path
from unittest.mock import AsyncMock, patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

import publish_all
from license_server.app import create_app
from license_server.codes import code_hash
from license_server.config import Settings
from license_server.database import Database
from publish.errors import EXIT_LICENSE_ERROR
from publish.licensing import require_valid_license
from publish.licensing.codes import normalize_activation_code
from publish.licensing.storage import atomic_write_json
from publish.licensing.verifier import LicenseValidationError, verify_license


ACTIVATION_CODE = "OPUB0-01234-56789-ABCDE-FGHJK-MNPQR-STVWX"
DEVICE_HASH = "d" * 64
OTHER_DEVICE_HASH = "e" * 64
KEY_ID = "e2e-test"


def _test_signing_material() -> tuple[str, dict[str, str]]:
    private_key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    private_b64 = base64.b64encode(bytes(range(32))).decode("ascii")
    public_b64 = base64.b64encode(
        private_key.public_key().public_bytes_raw()
    ).decode("ascii")
    return private_b64, {KEY_ID: public_b64}


def _settings(tmp_path: Path, private_key: str) -> Settings:
    return Settings.from_env(
        {
            "OPUB_PUBLIC_BASE_URL": "https://license.test",
            "OPUB_LICENSE_PRIVATE_KEY": private_key,
            "OPUB_LICENSE_KEY_ID": KEY_ID,
            "OPUB_LICENSE_DB_PATH": str(tmp_path / "server.sqlite3"),
        }
    )


def test_code_activation_returns_device_bound_license_for_offline_use(tmp_path):
    private_key, trusted_keys = _test_signing_material()
    settings = _settings(tmp_path, private_key)
    database = Database(settings.database_path)
    server = TestClient(create_app(settings, database))
    database.import_activation_code(
        code_hash(normalize_activation_code(ACTIVATION_CODE)),
        settings.product_id,
        "2026-09-06T00:00:00Z",
    )
    request_body = {
        "device_hash": DEVICE_HASH,
        "activation_code": ACTIVATION_CODE,
        "client_version": "0.8.0",
    }

    response = server.post("/v1/code-activations", json=request_body)

    assert response.status_code == 200
    assert response.json()["status"] == "licensed"
    installed = response.json()["license"]
    verify_license(installed, DEVICE_HASH, trusted_keys)

    repeated = server.post("/v1/code-activations", json=request_body)
    assert repeated.status_code == 200
    assert repeated.json() == response.json()
    used_elsewhere = server.post(
        "/v1/code-activations",
        json={**request_body, "device_hash": OTHER_DEVICE_HASH},
    )
    assert used_elsewhere.status_code == 409
    assert used_elsewhere.json() == {"detail": {"code": "LIC-014"}}

    client_dir = tmp_path / "client"
    license_file = client_dir / "license.json"
    atomic_write_json(license_file, installed)
    assert stat.S_IMODE(license_file.stat().st_mode) == 0o600
    assert json.loads(license_file.read_text(encoding="utf-8")) == installed
    assert not (client_dir / "activation.json").exists()

    server.close()
    with patch("requests.Session.request", side_effect=AssertionError("network called")), patch(
        "publish.licensing.build_device_hash", return_value=DEVICE_HASH
    ):
        assert require_valid_license(client_dir, trusted_keys) == (True, None)

    copied_dir = tmp_path / "copied-client"
    copied_dir.mkdir()
    shutil.copyfile(license_file, copied_dir / "license.json")
    with patch("publish.licensing.build_device_hash", return_value=OTHER_DEVICE_HASH):
        assert require_valid_license(copied_dir, trusted_keys) == (False, "LIC-003")
    try:
        verify_license(installed, OTHER_DEVICE_HASH, trusted_keys)
    except LicenseValidationError as exc:
        assert exc.code == "LIC-003"
    else:
        raise AssertionError("copied license unexpectedly verified for another device")


def test_unlicensed_cli_exits_before_cookies_assets_runtime_or_network(tmp_path, capsys):
    with patch.dict("os.environ", {"SAU_HOME": str(tmp_path / "unlicensed")}), patch(
        "publish.licensing.build_device_hash", return_value=DEVICE_HASH
    ), patch("publish.orchestrator._build_overrides") as overrides, patch(
        "publish.config._discover_account_files"
    ) as cookies, patch("publish.orchestrator.get_video_files") as assets, patch(
        "publish.orchestrator.runtime_preflight", new=AsyncMock()
    ) as runtime, patch(
        "requests.Session.request", side_effect=AssertionError("network called")
    ):
        result = publish_all.main(
            ["--platforms", "weibo", "--video", "/private/video.mp4", "--title", "t"]
        )

    assert result == EXIT_LICENSE_ERROR == 13
    assert "LIC-001" in capsys.readouterr().err
    overrides.assert_not_called()
    cookies.assert_not_called()
    assets.assert_not_called()
    runtime.assert_not_awaited()
