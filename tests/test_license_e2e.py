from __future__ import annotations

import base64
import json
import logging
import shutil
import stat
from pathlib import Path
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

import publish_all
from license_server.app import create_app
from license_server.codes import code_hash
from license_server.config import Settings
from license_server.database import Database
from publish.errors import EXIT_LICENSE_ERROR
from publish.licensing import require_valid_license
from publish.licensing.activation import activate
from publish.licensing.api import ActivationServiceError, LicenseApi
from publish.licensing.codes import normalize_activation_code
from publish.licensing.verifier import LicenseValidationError, verify_license


ACTIVATION_CODE = "OPUB0-01234-56789-ABCDE-FGHJK-MNPQR-STVWX"
USER_ACTIVATION_CODE = "  opub0-01234-56789-abcde-fghjk-mnpqr-stvwx  "
NORMALIZED_ACTIVATION_CODE = normalize_activation_code(ACTIVATION_CODE)
DEVICE_HASH = "d" * 64
OTHER_DEVICE_HASH = "e" * 64
KEY_ID = "e2e-test"


class TestClientSession:
    """Bridge the public requests-shaped client to an in-process FastAPI app."""

    __test__ = False

    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.calls: list[tuple[str, str]] = []

    def request(self, method: str, url: str, **kwargs):
        kwargs.pop("timeout", None)
        kwargs["follow_redirects"] = kwargs.pop("allow_redirects", True)
        parsed = urlsplit(url)
        path = parsed.path + (("?" + parsed.query) if parsed.query else "")
        self.calls.append((method, path))
        return self.client.request(method, path, **kwargs)


def test_deployment_runbook_limits_inventory_env_and_preserves_restore_rollback() -> None:
    readme = (
        Path(__file__).resolve().parents[1] / "license_server" / "README.md"
    ).read_text(encoding="utf-8")

    assert "set -a" not in readme
    assert "sudo -u opub-license env -i \\\n  OPUB_LICENSE_DB_PATH=" in readme
    assert "mktemp -d /var/backups/opub-license/pre-restore." in readme
    assert "mktemp /opt/opub/license_server/data/.license.sqlite3.restore." in readme
    assert "restore_stamp=" not in readme
    assert "license.sqlite3.before-restore" not in readme
    assert 'test "$backup_check" = "ok"' in readme
    assert 'test "$restore_check" = "ok"' in readme
    assert readme.index('test "$restore_check" = "ok"') < readme.index(
        "sudo systemctl stop opub-license"
    )
    assert "failed-restored.sqlite3" in readme
    assert "sqlite3 CLI" in readme


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


def test_code_activation_installs_device_bound_offline_license(tmp_path, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    private_key, trusted_keys = _test_signing_material()
    settings = _settings(tmp_path, private_key)
    database = Database(settings.database_path)
    application = create_app(settings, database)
    database.import_activation_code(
        code_hash(NORMALIZED_ACTIVATION_CODE),
        settings.product_id,
        "2026-09-06T00:00:00Z",
    )
    assert database.code_stats() == {"available": 1, "redeemed": 0, "total": 1}

    client_dir = tmp_path / "client"
    with TestClient(application) as server:
        transport = TestClientSession(server)
        api = LicenseApi(settings.public_base_url, session=transport)
        verify = lambda document, device_hash: verify_license(
            document, device_hash, trusted_keys
        )

        assert (
            activate(
                USER_ACTIVATION_CODE,
                DEVICE_HASH,
                api,
                client_dir,
                verify,
                client_version="0.8.0",
            )
            == 0
        )

        license_file = client_dir / "license.json"
        assert stat.S_IMODE(license_file.stat().st_mode) == 0o600
        installed = json.loads(license_file.read_text(encoding="utf-8"))
        verify_license(installed, DEVICE_HASH, trusted_keys)
        first_bytes = license_file.read_bytes()
        assert database.code_stats() == {"available": 0, "redeemed": 1, "total": 1}

        assert (
            activate(
                USER_ACTIVATION_CODE,
                DEVICE_HASH,
                api,
                client_dir,
                verify,
                client_version="0.8.0",
            )
            == 0
        )
        assert license_file.read_bytes() == first_bytes
        assert database.row("SELECT COUNT(*) FROM code_licenses")[0] == 1

        with pytest.raises(ActivationServiceError) as exc_info:
            api.activate_code(
                OTHER_DEVICE_HASH,
                "0.8.0",
                NORMALIZED_ACTIVATION_CODE,
            )
        assert exc_info.value.code == "LIC-014"

        assert transport.calls == [
            ("POST", "/v1/code-activations"),
            ("POST", "/v1/code-activations"),
            ("POST", "/v1/code-activations"),
        ]
        assert not (client_dir / "activation.json").exists()

    captured = capsys.readouterr()
    visible_output = captured.out + captured.err + caplog.text
    for secret in (
        USER_ACTIVATION_CODE,
        ACTIVATION_CODE,
        NORMALIZED_ACTIVATION_CODE,
        DEVICE_HASH,
        OTHER_DEVICE_HASH,
    ):
        assert secret not in visible_output

    with patch("requests.Session.request", side_effect=AssertionError("network called")), patch(
        "publish.licensing.build_device_hash", return_value=DEVICE_HASH
    ):
        assert require_valid_license(client_dir, trusted_keys) == (True, None)

    copied_dir = tmp_path / "copied-client"
    copied_dir.mkdir()
    shutil.copyfile(license_file, copied_dir / "license.json")
    with patch("publish.licensing.build_device_hash", return_value=OTHER_DEVICE_HASH):
        assert require_valid_license(copied_dir, trusted_keys) == (False, "LIC-003")
    with pytest.raises(LicenseValidationError) as exc_info:
        verify_license(installed, OTHER_DEVICE_HASH, trusted_keys)
    assert exc_info.value.code == "LIC-003"


def test_unlicensed_cli_exits_before_cookies_assets_runtime_or_network(tmp_path, capsys):
    with patch.dict("os.environ", {"SAU_HOME": str(tmp_path / "unlicensed")}), patch(
        "publish.licensing.build_device_hash", return_value=DEVICE_HASH
    ), patch("publish.orchestrator._build_overrides") as overrides, patch(
        "publish.orchestrator.default_params_from_overrides"
    ) as defaults, patch(
        "publish.config._discover_account_files"
    ) as cookies, patch("publish.orchestrator.get_video_files") as assets, patch(
        "publish.orchestrator.runtime_preflight", new=AsyncMock()
    ) as runtime, patch(
        "publish.orchestrator.ensure_account_login", new=AsyncMock()
    ) as browser, patch(
        "publish.orchestrator.publish_to_platform", new=AsyncMock()
    ) as upload, patch(
        "publish.orchestrator.webbrowser.open"
    ) as purchase_browser, patch(
        "requests.Session.request", side_effect=AssertionError("network called")
    ):
        result = publish_all.main(
            ["--platforms", "weibo", "--video", "/private/video.mp4", "--title", "t"]
        )

    assert result == EXIT_LICENSE_ERROR == 13
    assert "LIC-001" in capsys.readouterr().err
    overrides.assert_not_called()
    defaults.assert_not_called()
    cookies.assert_not_called()
    assets.assert_not_called()
    runtime.assert_not_awaited()
    browser.assert_not_awaited()
    upload.assert_not_awaited()
    purchase_browser.assert_not_called()
