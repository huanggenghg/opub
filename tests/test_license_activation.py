import json
import stat
from unittest.mock import Mock

import pytest

from publish.licensing.activation import ActivationError, _atomic_bytes, activate, open_checkout
from publish.licensing.api import ActivationServiceError, LicenseApi


class Response:
    def __init__(self, payload=None, status=200, error=None):
        self.payload, self.status, self.error = payload, status, error

    def raise_for_status(self):
        if self.error:
            raise self.error
        if self.status >= 400:
            import requests
            raise requests.HTTPError("bad status")

    def json(self):
        if isinstance(self.payload, BaseException):
            raise self.payload
        return self.payload


def pending():
    return {"status": "pending", "session_id": "s1", "poll_token": "p1",
            "expires_at": "2099-01-01T00:00:00Z",
            "checkout": {"kind": "url", "value": "https://pay.test/1"}}


def test_license_api_contract_and_json_shape():
    session = Mock()
    session.request.side_effect = [Response({"status": "pending"}), Response({"status": "licensed"})]
    api = LicenseApi("https://license.test///", session=session)
    assert api.create_session("d" * 64, "1.2.3", "wechat", "nonce") == {"status": "pending"}
    assert api.get_session("a" * 32, "secret-token") == {"status": "licensed"}
    assert session.request.call_args_list[0].kwargs == {
        "timeout": (5, 20),
        "json": {"device_hash": "d" * 64, "client_nonce": "nonce", "client_version": "1.2.3", "payway": "wechat"},
    }
    assert session.request.call_args_list[1].kwargs == {
        "timeout": (5, 20), "headers": {"Authorization": "Bearer secret-token"}
    }


@pytest.mark.parametrize("response", [Response(None), Response([]), Response("bad"), Response(ValueError("bad"), error=ValueError("bad"))])
def test_license_api_maps_transport_http_and_json_errors(response):
    session = Mock()
    session.request.return_value = response
    with pytest.raises(ActivationServiceError) as exc:
        LicenseApi("https://license.test", session=session).get_session("s", "t")
    assert exc.value.code == "LIC-011"


def test_license_api_rejects_invalid_session_id_without_request():
    session = Mock()
    with pytest.raises(ActivationServiceError) as exc:
        LicenseApi("https://license.test", session=session).get_session("../secret", "token")
    assert exc.value.code == "LIC-011"
    session.request.assert_not_called()


def test_activation_opens_checkout_polls_verifies_then_writes(tmp_path):
    api = Mock()
    api.create_session.return_value = pending()
    api.get_session.side_effect = [{"status": "pending"}, {"status": "licensed", "license": {"payload": {}, "signature": "sig"}}]
    verify = Mock()
    opener = Mock()
    result = activate("wechat", "d" * 64, api, tmp_path, verify, opener, sleep=lambda _: None, monotonic=iter([0, 1, 2]).__next__)
    assert result == 0
    verify.assert_called_once_with({"payload": {}, "signature": "sig"}, "d" * 64)
    opener.assert_called_once()
    assert (tmp_path / "license.json").exists()
    assert not (tmp_path / "activation.json").exists()


def test_activation_timeout_keeps_session_file(tmp_path):
    api = Mock()
    api.create_session.return_value = pending()
    api.get_session.return_value = {"status": "pending"}
    with pytest.raises(ActivationError) as exc:
        activate("wechat", "d" * 64, api, tmp_path, Mock(), Mock(), timeout_seconds=1, sleep=lambda _: None, monotonic=iter([0, 2]).__next__)
    assert exc.value.code == "LIC-010"
    assert (tmp_path / "activation.json").exists()


def test_expired_and_verification_failed_are_safe(tmp_path):
    for status in ("expired", "verification_failed"):
        api = Mock(create_session=Mock(return_value=pending()), get_session=Mock(return_value={"status": status}))
        with pytest.raises(ActivationError) as exc:
            activate("wechat", "d" * 64, api, tmp_path, Mock(), Mock(), timeout_seconds=1, sleep=lambda _: None, monotonic=iter([0, 0]).__next__)
        assert exc.value.code == ("LIC-010" if status == "expired" else "LIC-012")
        assert not (tmp_path / "license.json").exists()
        if status == "expired":
            assert not (tmp_path / "activation.json").exists()


def test_corrupt_session_is_discarded_and_direct_license_is_verified(tmp_path):
    (tmp_path / "activation.json").write_text("{broken", encoding="utf-8")
    api = Mock()
    license_doc = {"payload": {"x": 1}, "signature": "secret"}
    api.create_session.return_value = {"status": "licensed", "license": license_doc}
    verify = Mock()
    assert activate("alipay", "d" * 64, api, tmp_path, verify, Mock()) == 0
    verify.assert_called_once_with(license_doc, "d" * 64)
    assert json.loads((tmp_path / "license.json").read_text()) == license_doc


def test_direct_license_removes_stale_activation_session(tmp_path):
    stale = pending()
    stale.update({"payway": "wechat", "device_hash": "d" * 64})
    (tmp_path / "activation.json").write_text(json.dumps(stale), encoding="utf-8")
    license_doc = {"payload": {"x": 1}, "signature": "sig"}
    api = Mock(create_session=Mock(return_value={"status": "licensed", "license": license_doc}))
    assert activate("wechat", "d" * 64, api, tmp_path, Mock()) == 0
    assert not (tmp_path / "activation.json").exists()


def test_invalid_license_never_writes_license(tmp_path):
    api = Mock(create_session=Mock(return_value={"status": "licensed", "license": {"x": 1}}))
    def reject(*_):
        raise ActivationError("LIC-002", "invalid")
    with pytest.raises(ActivationError):
        activate("wechat", "d" * 64, api, tmp_path, reject, Mock())
    assert not (tmp_path / "license.json").exists()


def test_open_checkout_secure_files_and_privacy(tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr("publish.licensing.activation.webbrowser.open", opened.append)
    encoded = []
    class FakeImage:
        def save(self, handle, format):
            handle.write(b"PNG:" + encoded[0].encode())
    monkeypatch.setattr("publish.licensing.activation.qrcode.make", lambda value: (encoded.append(value) or FakeImage()))
    open_checkout({"kind": "url", "value": "https://pay.test/token"}, tmp_path)
    qr = tmp_path / "payment-qr.png"
    assert stat.S_IMODE(qr.stat().st_mode) == 0o600
    assert encoded == ["https://pay.test/token"]
    assert opened[0] == "https://pay.test/token"
    assert str(qr.resolve().as_uri()) == opened[1]
    opened.clear()
    html = "<form>private-checkout</form>"
    open_checkout({"kind": "html", "value": html}, tmp_path)
    page = tmp_path / "alipay-checkout.html"
    assert stat.S_IMODE(page.stat().st_mode) == 0o600
    assert page.read_text() == html
    assert opened == [page.resolve().as_uri()]


def test_open_checkout_rejects_non_https_or_unknown_kind(tmp_path):
    with pytest.raises(ActivationError):
        open_checkout({"kind": "url", "value": "http://bad.test"}, tmp_path)
    with pytest.raises(ActivationError):
        open_checkout({"kind": "other", "value": "x"}, tmp_path)


def test_recovered_session_refreshes_checkout_before_opening(tmp_path):
    saved = pending()
    saved.update({"payway": "wechat", "device_hash": "d" * 64})
    (tmp_path / "activation.json").write_text(json.dumps(saved), encoding="utf-8")
    api = Mock()
    refreshed = pending()
    refreshed["checkout"] = {"kind": "url", "value": "https://authoritative.test/new"}
    api.create_session.return_value = refreshed
    api.get_session.return_value = {"status": "verification_failed"}
    opener = Mock()
    with pytest.raises(ActivationError):
        activate("wechat", "d" * 64, api, tmp_path, Mock(), opener, timeout_seconds=1, sleep=lambda _: None, monotonic=iter([0, 0]).__next__)
    assert opener.call_args[0][0]["value"] == "https://authoritative.test/new"
    assert api.create_session.call_count == 1


def test_server_http_checkout_is_rejected_before_opening_or_persisting(tmp_path):
    response = pending()
    response["checkout"] = {"kind": "url", "value": "http://evil.test/pay"}
    api = Mock(create_session=Mock(return_value=response))
    with pytest.raises(ActivationError) as exc:
        activate("wechat", "d" * 64, api, tmp_path, Mock(), Mock())
    assert exc.value.code == "LIC-011"
    assert not (tmp_path / "activation.json").exists()


def test_atomic_checkout_does_not_chmod_after_successful_replace(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("publish.licensing.activation.os.chmod", lambda *args: calls.append(args))
    _atomic_bytes(tmp_path / "artifact", b"safe")
    assert (tmp_path / "artifact").read_bytes() == b"safe"
    assert calls == []


def test_atomic_checkout_replace_failure_preserves_old_and_cleans_temp(tmp_path, monkeypatch):
    target = tmp_path / "artifact"
    target.write_bytes(b"old")
    monkeypatch.setattr("publish.licensing.activation.os.replace", lambda *_: (_ for _ in ()).throw(OSError("replace failed")))
    with pytest.raises(OSError):
        _atomic_bytes(target, b"new")
    assert target.read_bytes() == b"old"
    assert list(tmp_path.glob(".artifact.*")) == []
