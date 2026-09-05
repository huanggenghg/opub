from __future__ import annotations

import copy
import hashlib
from html import escape
from html.parser import HTMLParser
import ipaddress
import re
from collections.abc import Mapping
from typing import Any, Dict, Mapping as TypingMapping, Optional
from urllib.parse import urlsplit

import requests

from .models import Checkout, ProviderOrder


WX_URL = "https://newapi.mbd.pub/release/wx/prepay"
ALIPAY_URL = "https://newapi.mbd.pub/release/alipay/pay"
QUERY_URL = "https://newapi.mbd.pub/release/main/search_order"

_TIMEOUT = (5, 15)
_MAX_CHECKOUT_HTML_BYTES = 256 * 1024
_DNS_LABEL_RE = re.compile(r"[A-Za-z0-9-]+\Z")
_VOID_TAGS = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"})
_REQUIRED_ALIPAY_FIELDS = ("method", "app_id", "biz_content", "sign")
_CHECKOUT_FORM_ID = "mianbaoduo-checkout"
_CANONICAL_DECIMAL_RE = re.compile(r"(?:0|[1-9][0-9]*)\Z")


class _AlipayFormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._stack: list[str] = []
        self._form_count = 0
        self._form_open = False
        self._action: str | None = None
        self._fields: dict[str, str] = {}

    @staticmethod
    def _attributes(attrs: list[tuple[str, str | None]]) -> dict[str, str | None]:
        result: dict[str, str | None] = {}
        for name, value in attrs:
            if name in result:
                raise ValueError("duplicate HTML attribute")
            result[name] = value
        return result

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attributes = self._attributes(attrs)
        if tag == "form":
            if self._form_open or self._form_count:
                raise ValueError("multiple or nested forms")
            method = attributes.get("method")
            action = attributes.get("action")
            if not isinstance(method, str) or method.strip().lower() != "post":
                raise ValueError("form method is not post")
            if not isinstance(action, str) or not _valid_alipay_action(action):
                raise ValueError("form action is invalid")
            self._form_count = 1
            self._form_open = True
            self._action = action
        elif self._form_open and tag == "input":
            name = attributes.get("name")
            value = attributes.get("value")
            if isinstance(name, str) and name.strip() and isinstance(value, str):
                if name in self._fields:
                    raise ValueError("duplicate input name")
                self._fields[name] = value
        if tag not in _VOID_TAGS:
            self._stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "form":
            raise ValueError("self-closing form")
        self.handle_starttag(tag, attrs)
        if tag not in _VOID_TAGS and self._stack and self._stack[-1] == tag:
            self._stack.pop()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _VOID_TAGS or not self._stack or self._stack[-1] != tag:
            raise ValueError("malformed HTML nesting")
        self._stack.pop()
        if tag == "form":
            if not self._form_open:
                raise ValueError("unexpected form close")
            self._form_open = False

    def result(self) -> tuple[str, dict[str, str]]:
        if self._form_count != 1 or self._form_open or self._stack or self._action is None:
            raise ValueError("incomplete HTML form")
        if any(field not in self._fields for field in _REQUIRED_ALIPAY_FIELDS):
            raise ValueError("required payment field is missing")
        return self._action, dict(self._fields)


class ProviderError(RuntimeError):
    """A safe, user-facing provider integration failure."""


def _is_scalar(value: object) -> bool:
    return isinstance(value, (str, int, float, bool))


def sign_parameters(values: TypingMapping[str, Any], app_key: str) -> str:
    """Create Mianbaoduo's sorted MD5 parameter signature without mutating values."""
    if not isinstance(values, Mapping):
        raise TypeError("values must be a mapping")
    if not isinstance(app_key, str):
        raise TypeError("app_key must be a string")

    parts: list[str] = []
    for key in sorted(values):
        if not isinstance(key, str):
            raise TypeError("parameter names must be strings")
        value = values[key]
        if value is None or value == "":
            continue
        if not _is_scalar(value):
            raise TypeError("nested parameter values are not supported")
        parts.append(f"{key}={value}")
    parts.append(f"key={app_key}")
    return hashlib.md5("&".join(parts).encode("utf-8")).hexdigest()


def _safe_int(value: object, field: str) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    if isinstance(value, str) and _CANONICAL_DECIMAL_RE.fullmatch(value):
        try:
            return int(value)
        except ValueError:
            pass
    raise ProviderError(f"Mianbaoduo order response has invalid {field}")


def _valid_host(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass

    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError:
        return False
    if ascii_host.endswith("."):
        ascii_host = ascii_host[:-1]
    if not ascii_host or len(ascii_host) > 253:
        return False
    labels = ascii_host.split(".")
    return all(
        label
        and len(label) <= 63
        and _DNS_LABEL_RE.fullmatch(label) is not None
        and not label.startswith("-")
        and not label.endswith("-")
        for label in labels
    )


def _valid_h5_url(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    if any(char.isspace() or ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        return False
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() != "https" or not parsed.hostname:
            return False
        if "@" in parsed.netloc or parsed.username is not None or parsed.password is not None:
            return False
        if parsed.fragment or parsed.netloc.endswith(":"):
            return False
        port = parsed.port
        if port is not None and not 1 <= port <= 65535:
            return False
        return _valid_host(parsed.hostname)
    except (ValueError, UnicodeError):
        return False


def _valid_alipay_action(value: str) -> bool:
    if not _valid_h5_url(value):
        return False
    try:
        host = urlsplit(value).hostname
    except (ValueError, UnicodeError):
        return False
    if not host:
        return False
    normalized = host.rstrip(".").lower()
    return normalized == "alipay.com" or normalized.endswith(".alipay.com")


def _sanitize_alipay_html(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ProviderError("Mianbaoduo alipay checkout returned no usable form")
    try:
        if len(value.encode("utf-8")) > _MAX_CHECKOUT_HTML_BYTES:
            raise ProviderError("Mianbaoduo alipay checkout returned an invalid form")
    except UnicodeError:
        raise ProviderError("Mianbaoduo alipay checkout returned an invalid form") from None

    try:
        parser = _AlipayFormParser()
        parser.feed(value)
        parser.close()
        action, fields = parser.result()
        action.encode("utf-8")
        for name, field_value in fields.items():
            name.encode("utf-8")
            field_value.encode("utf-8")
    except ProviderError:
        raise
    except Exception:
        raise ProviderError("Mianbaoduo alipay checkout returned an invalid form") from None

    hidden_inputs = "".join(
        f'<input type="hidden" name="{escape(name, quote=True)}" value="{escape(field_value, quote=True)}">'
        for name, field_value in fields.items()
    )
    escaped_action = escape(action, quote=True)
    return (
        "<!doctype html><html><body>"
        f'<form id="{_CHECKOUT_FORM_ID}" method="post" action="{escaped_action}">'
        f"{hidden_inputs}"
        '<noscript><button type="submit">Continue to payment</button></noscript>'
        "</form>"
        f'<script>(function () {{ document.getElementById("{_CHECKOUT_FORM_ID}").submit(); }}());</script>'
        "</body></html>"
    )


class MianbaoduoClient:
    def __init__(
        self,
        app_id: str,
        app_key: str,
        return_url: str,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.app_id = app_id
        self.app_key = app_key
        self.return_url = return_url
        self.session = session if session is not None else requests.Session()

    def _post(self, operation: str, url: str, values: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(values)
        try:
            payload["sign"] = sign_parameters(payload, self.app_key)
        except (TypeError, ValueError):
            raise ProviderError(f"Mianbaoduo {operation} request could not be signed") from None

        try:
            response = self.session.post(url, json=payload, timeout=_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException:
            raise ProviderError(f"Mianbaoduo {operation} request failed") from None

        try:
            result = response.json()
        except (ValueError, TypeError):
            raise ProviderError(f"Mianbaoduo {operation} returned invalid JSON") from None
        if not isinstance(result, dict):
            raise ProviderError(f"Mianbaoduo {operation} returned an invalid response")
        if "error" in result:
            raise ProviderError(f"Mianbaoduo {operation} was rejected by the provider")
        return result

    def create_checkout(
        self,
        payway: str,
        order_id: str,
        description: str,
        amount_fen: int,
    ) -> Checkout:
        if payway not in ("wechat", "alipay"):
            raise ProviderError("Mianbaoduo checkout has an unsupported payment method")
        if type(amount_fen) is not int or amount_fen <= 0:
            raise ProviderError("Mianbaoduo checkout amount is invalid")

        values: Dict[str, Any] = {
            "app_id": self.app_id,
            "description": description,
            "out_trade_no": order_id,
            "amount_total": amount_fen,
        }
        if payway == "wechat":
            values["channel"] = "h5"
            result = self._post("wechat checkout", WX_URL, values)
            value = result.get("h5_url")
            if not _valid_h5_url(value):
                raise ProviderError("Mianbaoduo wechat checkout returned an invalid URL")
            return Checkout("url", value)

        values["url"] = self.return_url
        values["callback_url"] = self.return_url
        result = self._post("alipay checkout", ALIPAY_URL, values)
        return Checkout("html", _sanitize_alipay_html(result.get("body")))

    def query_order(self, order_id: str) -> ProviderOrder:
        values = {"app_id": self.app_id, "out_trade_no": order_id}
        result = self._post("order query", QUERY_URL, values)

        for field in ("state", "amount", "payway"):
            if field not in result:
                raise ProviderError(f"Mianbaoduo order response is missing {field}")
        for field in ("order_id", "description", "charge_id"):
            value = result.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ProviderError(f"Mianbaoduo order response has invalid {field}")

        return ProviderOrder(
            order_id=result["order_id"],
            state=_safe_int(result["state"], "state"),
            amount=_safe_int(result["amount"], "amount"),
            description=result["description"],
            charge_id=result["charge_id"],
            payway=_safe_int(result["payway"], "payway"),
            raw=copy.deepcopy(result),
        )
