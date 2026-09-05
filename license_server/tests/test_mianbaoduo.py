from __future__ import annotations

import copy

import pytest

from license_server.models import Checkout, ProviderOrder


class FakeResponse:
    def __init__(self, payload=None, *, json_error: Exception | None = None, text: str = ""):
        self.payload = payload
        self.json_error = json_error
        self.text = text

    def raise_for_status(self) -> None:
        return None

    def json(self):
        if self.json_error is not None:
            raise self.json_error
        return self.payload


class HTTPErrorResponse(FakeResponse):
    def raise_for_status(self) -> None:
        from requests import HTTPError

        raise HTTPError("raw HTTP details")


class FakeSession:
    def __init__(self, response: FakeResponse):
        self.response = response
        self.calls: list[tuple[str, dict, tuple[int, int]]] = []

    def post(self, url, *, json, timeout):
        self.calls.append((url, json, timeout))
        return self.response


class TransportErrorSession(FakeSession):
    def post(self, url, *, json, timeout):
        self.calls.append((url, json, timeout))
        from requests import Timeout

        raise Timeout("raw timeout details")


def test_sign_parameters_known_vector_and_omits_empty_values_without_mutating_input():
    from license_server.mianbaoduo import sign_parameters

    values = {"z": 2, "empty": "", "none": None, "a": 1}
    original = copy.deepcopy(values)

    assert sign_parameters(values, "key") == "4eaa812cecd6f7ebcda6d2baa3af89d8"
    assert values == original


def test_sign_parameters_is_deterministic_for_unicode_and_rejects_nested_values():
    from license_server.mianbaoduo import sign_parameters

    values = {"名称": "许可证", "a": "中"}
    first = sign_parameters(values, "密钥")
    second = sign_parameters(dict(reversed(list(values.items()))), "密钥")
    assert first == second
    assert len(first) == 32

    with pytest.raises((TypeError, ValueError)):
        sign_parameters({"nested": {"x": 1}}, "key")


def test_create_wechat_checkout_posts_signed_payload_and_returns_url():
    from license_server.mianbaoduo import WX_URL, MianbaoduoClient, sign_parameters

    response = FakeResponse({"h5_url": "https://pay.example/wechat/1"})
    session = FakeSession(response)
    client = MianbaoduoClient("app", "secret", "https://opub.test/done", session)

    checkout = client.create_checkout("wechat", "order-1", "opub", 990)

    expected = {"app_id": "app", "description": "opub", "out_trade_no": "order-1", "amount_total": 990, "channel": "h5"}
    expected["sign"] = sign_parameters(expected, "secret")
    assert checkout == Checkout("url", "https://pay.example/wechat/1")
    assert session.calls == [(WX_URL, expected, (5, 15))]


def test_create_alipay_checkout_posts_both_return_urls_and_returns_html():
    from license_server.mianbaoduo import ALIPAY_URL, MianbaoduoClient, sign_parameters

    body = "<html><form action='https://pay.example'></form></html>"
    response = FakeResponse({"body": body})
    session = FakeSession(response)
    client = MianbaoduoClient("app", "secret", "https://opub.test/done", session)

    checkout = client.create_checkout("alipay", "order-1", "opub", 990)

    expected = {
        "app_id": "app", "description": "opub", "out_trade_no": "order-1", "amount_total": 990,
        "url": "https://opub.test/done", "callback_url": "https://opub.test/done",
    }
    expected["sign"] = sign_parameters(expected, "secret")
    assert checkout == Checkout("html", body)
    assert session.calls == [(ALIPAY_URL, expected, (5, 15))]


def test_query_order_normalizes_numeric_strings_and_copies_raw_payload():
    from license_server.mianbaoduo import QUERY_URL, MianbaoduoClient, sign_parameters

    payload = {"state": "1", "amount": "990", "description": "opub", "charge_id": "charge-1", "payway": "2"}
    session = FakeSession(FakeResponse(payload))
    client = MianbaoduoClient("app", "secret", "https://opub.test/done", session)

    order = client.query_order("order-1")

    expected = {"app_id": "app", "out_trade_no": "order-1"}
    expected["sign"] = sign_parameters(expected, "secret")
    assert order == ProviderOrder(1, 990, "opub", "charge-1", 2, payload)
    assert order.raw is not payload
    assert session.calls == [(QUERY_URL, expected, (5, 15))]


@pytest.mark.parametrize("payway", ["stripe", "", None])
def test_unknown_payway_fails_before_network(payway):
    from license_server.mianbaoduo import MianbaoduoClient, ProviderError

    session = FakeSession(FakeResponse({}))
    client = MianbaoduoClient("app", "secret", "https://opub.test/done", session)
    with pytest.raises(ProviderError):
        client.create_checkout(payway, "order-1", "opub", 990)
    assert session.calls == []


@pytest.mark.parametrize("amount", [0, -1, 1.5, True, "990", None])
def test_invalid_amount_fails_before_network(amount):
    from license_server.mianbaoduo import MianbaoduoClient, ProviderError

    session = FakeSession(FakeResponse({}))
    client = MianbaoduoClient("app", "secret", "https://opub.test/done", session)
    with pytest.raises(ProviderError):
        client.create_checkout("wechat", "order-1", "opub", amount)
    assert session.calls == []


def test_provider_and_transport_failures_are_redacted():
    from license_server.mianbaoduo import MianbaoduoClient, ProviderError

    secret = "TOP-SECRET-APP-KEY"
    for response in [
        FakeResponse({"error": "raw provider secret"}),
        FakeResponse(json_error=ValueError("raw json secret")),
    ]:
        client = MianbaoduoClient("app", secret, "https://opub.test/done", FakeSession(response))
        with pytest.raises(ProviderError) as exc_info:
            client.create_checkout("wechat", "order-1", "opub", 990)
        assert secret not in str(exc_info.value)
        assert "raw" not in str(exc_info.value)

    client = MianbaoduoClient("app", secret, "https://opub.test/done", TransportErrorSession(FakeResponse()))
    with pytest.raises(ProviderError) as exc_info:
        client.create_checkout("wechat", "order-1", "opub", 990)
    assert secret not in str(exc_info.value)
    assert "raw timeout" not in str(exc_info.value)

    client = MianbaoduoClient("app", secret, "https://opub.test/done", FakeSession(HTTPErrorResponse({})))
    with pytest.raises(ProviderError) as exc_info:
        client.create_checkout("wechat", "order-1", "opub", 990)
    assert secret not in str(exc_info.value)
    assert "raw HTTP details" not in str(exc_info.value)


@pytest.mark.parametrize(
    "payload",
    [None, [], {}, {"h5_url": "http://insecure.example"}, {"h5_url": "https:///missing-host"}],
)
def test_invalid_wechat_payload_fails_closed(payload):
    from license_server.mianbaoduo import MianbaoduoClient, ProviderError

    client = MianbaoduoClient("app", "secret", "https://opub.test/done", FakeSession(FakeResponse(payload)))
    with pytest.raises(ProviderError):
        client.create_checkout("wechat", "order-1", "opub", 990)


@pytest.mark.parametrize(
    "url",
    [
        "https://pay.example:not-a-port/path",
        "https://pay.example:99999/path",
        "https://pay. example/path",
        "https://[",
        "https://user:password@pay.example/path",
        "https://user@pay.example/path",
        "https://pay.example/path#fragment",
        "https://-pay.example/path",
        "https://pay-.example/path",
        "https://pay..example/path",
        "https://pay_example/path",
    ],
)
def test_invalid_wechat_url_structure_fails_closed(url):
    from license_server.mianbaoduo import MianbaoduoClient, ProviderError

    client = MianbaoduoClient("app", "secret", "https://opub.test/done", FakeSession(FakeResponse({"h5_url": url})))
    with pytest.raises(ProviderError):
        client.create_checkout("wechat", "order-1", "opub", 990)


@pytest.mark.parametrize(
    "url",
    [
        "https://pay.example:443/path?checkout=1",
        "https://192.0.2.10/pay",
        "https://[2001:db8::1]:8443/pay",
    ],
)
def test_valid_wechat_url_structure_is_returned(url):
    from license_server.mianbaoduo import MianbaoduoClient

    client = MianbaoduoClient("app", "secret", "https://opub.test/done", FakeSession(FakeResponse({"h5_url": url})))
    assert client.create_checkout("wechat", "order-1", "opub", 990) == Checkout("url", url)


@pytest.mark.parametrize("body", ["", "not html", "<form>" + ("x" * (256 * 1024)) + "</form>"])
def test_invalid_alipay_html_fails_closed(body):
    from license_server.mianbaoduo import MianbaoduoClient, ProviderError

    client = MianbaoduoClient("app", "secret", "https://opub.test/done", FakeSession(FakeResponse({"body": body})))
    with pytest.raises(ProviderError):
        client.create_checkout("alipay", "order-1", "opub", 990)


def test_alipay_html_at_size_limit_is_allowed():
    from license_server.mianbaoduo import _MAX_CHECKOUT_HTML_BYTES, MianbaoduoClient

    prefix = "<form>"
    suffix = "</form>"
    body = prefix + ("x" * (_MAX_CHECKOUT_HTML_BYTES - len(prefix.encode("utf-8")) - len(suffix.encode("utf-8")))) + suffix
    client = MianbaoduoClient("app", "secret", "https://opub.test/done", FakeSession(FakeResponse({"body": body})))
    assert client.create_checkout("alipay", "order-1", "opub", 990) == Checkout("html", body)


def test_alipay_html_unicode_encoding_failure_is_redacted():
    from license_server.mianbaoduo import MianbaoduoClient, ProviderError

    secret = "TOP-SECRET-APP-KEY"
    body = "<form>" + "\ud800" + "</form>"
    client = MianbaoduoClient("app", secret, "https://opub.test/done", FakeSession(FakeResponse({"body": body})))
    with pytest.raises(ProviderError) as exc_info:
        client.create_checkout("alipay", "order-1", "opub", 990)
    assert secret not in str(exc_info.value)
    assert "\ud800" not in str(exc_info.value)


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"state": "done", "amount": 990, "description": "opub", "charge_id": "id", "payway": 1},
        {"state": 1, "amount": 990, "description": "", "charge_id": "id", "payway": 1},
        {"state": 1, "amount": 990, "description": "opub", "charge_id": "id", "payway": 1.5},
        {"state": 1, "description": "opub", "charge_id": "id", "payway": 1},
        {"state": 1, "amount": "not-a-number", "description": "opub", "charge_id": "id", "payway": 1},
        {"state": 1, "amount": 990, "description": "opub", "payway": 1},
        {"state": 1, "amount": 990, "description": "opub", "charge_id": 123, "payway": 1},
        {"state": 1, "amount": 990, "description": "opub", "charge_id": " ", "payway": 1},
        {"state": 1, "amount": 990, "description": "opub", "charge_id": "id", "payway": "no"},
        {"state": "no", "amount": 990, "description": "opub", "charge_id": "id", "payway": 1},
    ],
)
def test_invalid_query_payload_fails_closed(payload):
    from license_server.mianbaoduo import MianbaoduoClient, ProviderError

    client = MianbaoduoClient("app", "secret", "https://opub.test/done", FakeSession(FakeResponse(payload)))
    with pytest.raises(ProviderError):
        client.query_order("order-1")
