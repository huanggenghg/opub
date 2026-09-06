from __future__ import annotations

import base64
import json
import shutil
import stat
from pathlib import Path
from unittest.mock import AsyncMock, patch
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

import publish_all
from license_server.app import create_app
from license_server.config import Settings
from license_server.database import Database
from license_server.models import Checkout, ProviderOrder
from publish.errors import EXIT_LICENSE_ERROR
from publish.licensing import require_valid_license
from publish.licensing.activation import activate
from publish.licensing.api import LicenseApi
from publish.licensing.verifier import LicenseValidationError, verify_license


DEVICE_HASH = "d" * 64
OTHER_DEVICE_HASH = "e" * 64
KEY_ID = "e2e-test"
PRODUCT_NAME = "opub 永久设备许可证"


class FastApiSessionAdapter:
    """Expose a requests.Session-shaped adapter around FastAPI TestClient."""

    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.requests: list[tuple[str, str]] = []

    def request(self, method: str, url: str, **kwargs):
        kwargs.pop("timeout", None)
        parsed = urlsplit(url)
        path = parsed.path + (("?" + parsed.query) if parsed.query else "")
        self.requests.append((method, path))
        return self.client.request(method, path, **kwargs)


class FakeProvider:
    """Deterministic Mianbaoduo protocol fake; it never performs network I/O."""

    def __init__(self) -> None:
        self.order_id: str | None = None
        self.created: list[tuple[str, str, str, int]] = []
        self.queried: list[str] = []

    def create_checkout(
        self, payway: str, order_id: str, description: str, amount_fen: int
    ) -> Checkout:
        self.order_id = order_id
        self.created.append((payway, order_id, description, amount_fen))
        return Checkout("url", "https://pay.test/e2e-order")

    def query_order(self, order_id: str) -> ProviderOrder:
        self.queried.append(order_id)
        return ProviderOrder(
            order_id=order_id,
            state=1,
            amount=990,
            description=PRODUCT_NAME,
            charge_id="charge-e2e",
            payway=1,
            raw={},
        )


def _test_signing_material() -> tuple[str, dict[str, str]]:
    private_key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    private_b64 = base64.b64encode(bytes(range(32))).decode("ascii")
    public_b64 = base64.b64encode(
        private_key.public_key().public_bytes_raw()
    ).decode("ascii")
    return private_b64, {KEY_ID: public_b64}


def _settings(tmp_path: Path, private_key: str) -> Settings:
    return Settings(
        public_base_url="https://license.test",
        payment_return_url="https://opub.test/payment-complete",
        mbd_app_id="test-app",
        mbd_app_key="test-key",
        license_private_key=private_key,
        license_key_id=KEY_ID,
        database_path=tmp_path / "server.sqlite3",
    )


def test_paid_activation_installs_device_bound_license_for_offline_use(tmp_path):
    private_key, trusted_keys = _test_signing_material()
    settings = _settings(tmp_path, private_key)
    database = Database(settings.database_path)
    provider = FakeProvider()
    server = TestClient(create_app(settings, database, provider))
    transport = FastApiSessionAdapter(server)
    api = LicenseApi(settings.public_base_url, session=transport)
    opened_checkouts = []
    webhook_responses = []
    clock = iter((0.0, 0.0, 1.0))

    def verify(document, device_hash):
        verify_license(document, device_hash, trusted_keys)

    def complete_payment(_seconds):
        webhook_responses.append(
            server.post(
                "/v1/webhooks/mianbaoduo",
                json={
                    "type": "charge_succeeded",
                    "data": {"out_trade_no": provider.order_id},
                },
            )
        )

    client_dir = tmp_path / "client"
    result = activate(
        "wechat",
        DEVICE_HASH,
        api,
        client_dir,
        verify,
        checkout_opener=lambda checkout, _path: opened_checkouts.append(checkout),
        sleep=complete_payment,
        monotonic=lambda: next(clock),
        client_version="0.7.0",
    )

    assert result == 0
    assert opened_checkouts == [{"kind": "url", "value": "https://pay.test/e2e-order"}]
    payway, order_id, description, amount_fen = provider.created[0]
    assert (payway, description, amount_fen) == ("wechat", PRODUCT_NAME, 990)
    assert order_id == provider.order_id
    assert provider.queried == [provider.order_id]
    assert [response.json() for response in webhook_responses] == [{"status": "licensed"}]
    assert [method for method, _path in transport.requests] == ["POST", "GET", "GET"]
    assert transport.requests[0][1] == "/v1/activation-sessions"
    assert len({path for _method, path in transport.requests[1:]}) == 1

    license_file = client_dir / "license.json"
    assert stat.S_IMODE(license_file.stat().st_mode) == 0o600
    installed = json.loads(license_file.read_text(encoding="utf-8"))
    verify_license(installed, DEVICE_HASH, trusted_keys)
    assert not (client_dir / "activation.json").exists()

    server.close()
    with patch("requests.Session.request", side_effect=AssertionError("network called")), patch(
        "publish.licensing.build_device_hash", return_value=DEVICE_HASH
    ):
        assert require_valid_license(client_dir, trusted_keys) == (True, None)
        verify_license(installed, DEVICE_HASH, trusted_keys)

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
