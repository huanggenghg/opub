import json
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from publish.licensing.activation import ActivationError, activate
from publish.licensing.api import ActivationServiceError, LicenseApi


VALID_CODE = "OPUB0-01234-56789-ABCDE-FGHJK-MNPQR-STVWX"
NORMALIZED_CODE = "OPUB00123456789ABCDEFGHJKMNPQRSTVWX"
DEVICE_HASH = "d" * 64
LICENSE_DOC = {
    "payload": {"device_hash": DEVICE_HASH, "product": "opub-major-0"},
    "signature": "signature",
}


class Response:
    def __init__(self, status: int = 200, payload=None):
        self.status_code = status
        self.payload = payload

    def json(self):
        if isinstance(self.payload, BaseException):
            raise self.payload
        return self.payload


class MockSession:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append(
            {"method": method, "url": url, "json": kwargs.get("json"), "kwargs": kwargs}
        )
        if self.error is not None:
            raise self.error
        return self.response


def test_license_api_posts_code_activation_once_with_exact_payload() -> None:
    session = MockSession(Response(200, {"status": "licensed", "license": LICENSE_DOC}))

    result = LicenseApi("https://license.test///", session=session).activate_code(
        DEVICE_HASH, "0.8.0", VALID_CODE
    )

    assert result == {"status": "licensed", "license": LICENSE_DOC}
    assert len(session.calls) == 1
    assert session.calls[0] == {
        "method": "POST",
        "url": "https://license.test/v1/code-activations",
        "json": {
            "device_hash": DEVICE_HASH,
            "client_version": "0.8.0",
            "activation_code": VALID_CODE,
        },
        "kwargs": {
            "timeout": (5, 20),
            "json": {
                "device_hash": DEVICE_HASH,
                "client_version": "0.8.0",
                "activation_code": VALID_CODE,
            },
        },
    }


@pytest.mark.parametrize(
    ("status", "body", "code"),
    [
        (400, {"detail": {"code": "LIC-013"}}, "LIC-013"),
        (409, {"detail": {"code": "LIC-014"}}, "LIC-014"),
        (422, {"detail": {"code": "LIC-015"}}, "LIC-015"),
    ],
)
def test_license_api_preserves_allowlisted_service_error(status, body, code) -> None:
    session = MockSession(Response(status, body))

    with pytest.raises(ActivationServiceError) as exc_info:
        LicenseApi("https://license.test", session=session).activate_code(
            DEVICE_HASH, "0.8.0", VALID_CODE
        )

    assert exc_info.value.code == code
    assert str(exc_info.value) == "activation service unavailable"


@pytest.mark.parametrize(
    ("response", "transport_error"),
    [
        (Response(200, None), None),
        (Response(200, []), None),
        (Response(200, "bad"), None),
        (Response(200, ValueError("response contained secret")), None),
        (Response(201, {"status": "licensed"}), None),
        (Response(302, {"detail": {"code": "LIC-013"}}), None),
        (Response(500, {"detail": {"code": "LIC-013"}}), None),
        (Response(400, {"code": "LIC-013"}), None),
        (Response(400, {"detail": "LIC-013"}), None),
        (Response(400, {"detail": {"code": "LIC-999"}}), None),
        (Response(400, {"detail": {"code": "LIC-013", "secret": "x"}}), None),
        (Response(400, {"detail": {"code": "LIC-013"}, "secret": "x"}), None),
        (None, requests.Timeout("timeout for secret activation code")),
        (None, requests.RequestException("request leaked device hash")),
    ],
)
def test_license_api_maps_untrusted_failures_to_safe_generic_error(
    response, transport_error
) -> None:
    session = MockSession(response, error=transport_error)

    with pytest.raises(ActivationServiceError) as exc_info:
        LicenseApi("https://license.test", session=session).activate_code(
            DEVICE_HASH, "0.8.0", VALID_CODE
        )

    assert exc_info.value.code == "LIC-011"
    assert str(exc_info.value) == "activation service unavailable"
    assert VALID_CODE not in str(exc_info.value)
    assert DEVICE_HASH not in str(exc_info.value)


def test_activate_normalizes_verifies_then_writes_license(tmp_path: Path) -> None:
    events = []
    api = Mock()
    api.activate_code.side_effect = lambda *args: (
        events.append(("api", args))
        or {"status": "licensed", "license": LICENSE_DOC}
    )
    verify = Mock(side_effect=lambda *args: events.append(("verify", args)))

    assert activate(
        "  opub0-01234-56789-abcde-fghjk-mnpqr-stvwx  ",
        DEVICE_HASH,
        api,
        tmp_path,
        verify,
        client_version="0.8.0",
    ) == 0

    api.activate_code.assert_called_once_with(DEVICE_HASH, "0.8.0", NORMALIZED_CODE)
    verify.assert_called_once_with(LICENSE_DOC, DEVICE_HASH)
    assert [event[0] for event in events] == ["api", "verify"]
    assert json.loads((tmp_path / "license.json").read_text(encoding="utf-8")) == LICENSE_DOC


@pytest.mark.parametrize(
    "response",
    [
        None,
        [],
        {},
        {"status": "pending", "license": LICENSE_DOC},
        {"status": "LICENSED", "license": LICENSE_DOC},
        {"status": "licensed"},
        {"status": "licensed", "license": []},
    ],
)
def test_invalid_activation_response_preserves_existing_license(response, tmp_path: Path) -> None:
    target = tmp_path / "license.json"
    target.write_text('{"old":true}', encoding="utf-8")
    api = Mock(activate_code=Mock(return_value=response))

    with pytest.raises(ActivationServiceError) as exc_info:
        activate(VALID_CODE, DEVICE_HASH, api, tmp_path, Mock(), client_version="0.8.0")

    assert exc_info.value.code == "LIC-011"
    assert target.read_text(encoding="utf-8") == '{"old":true}'


def test_failed_verification_preserves_existing_license_and_creates_no_artifacts(
    tmp_path: Path,
) -> None:
    target = tmp_path / "license.json"
    target.write_text('{"old":true}', encoding="utf-8")
    api = Mock(
        activate_code=Mock(return_value={"status": "licensed", "license": LICENSE_DOC})
    )
    api.get_session.side_effect = AssertionError("polling is forbidden")
    verify = Mock(side_effect=RuntimeError("invalid secret license"))

    with pytest.raises(RuntimeError, match="invalid secret license"):
        activate(VALID_CODE, DEVICE_HASH, api, tmp_path, verify, client_version="0.8.0")

    assert target.read_text(encoding="utf-8") == '{"old":true}'
    api.activate_code.assert_called_once()
    api.get_session.assert_not_called()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["license.json"]


def test_invalid_local_code_maps_to_lic013_without_network_or_files(tmp_path: Path) -> None:
    api = Mock()

    with pytest.raises(ActivationError) as exc_info:
        activate("secret-invalid-code", DEVICE_HASH, api, tmp_path, Mock())

    assert exc_info.value.code == "LIC-013"
    assert "secret-invalid-code" not in str(exc_info.value)
    api.activate_code.assert_not_called()
    assert list(tmp_path.iterdir()) == []


def test_activation_creates_no_payment_session_checkout_or_polling_artifacts(
    tmp_path: Path,
) -> None:
    api = Mock(
        activate_code=Mock(return_value={"status": "licensed", "license": LICENSE_DOC})
    )
    api.create_session.side_effect = AssertionError("payment sessions are forbidden")
    api.get_session.side_effect = AssertionError("polling is forbidden")

    assert activate(VALID_CODE, DEVICE_HASH, api, tmp_path, Mock()) == 0

    api.create_session.assert_not_called()
    api.get_session.assert_not_called()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["license.json"]
    for name in ("activation.json", "payment-qr.png", "alipay-checkout.html"):
        assert not (tmp_path / name).exists()
