from __future__ import annotations

import copy
import hashlib
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
_FORM_RE = re.compile(r"<form\b[^>]*>.*?</form\s*>", re.IGNORECASE | re.DOTALL)
_DNS_LABEL_RE = re.compile(r"[A-Za-z0-9-]+\Z")


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
    if isinstance(value, bool):
        raise ProviderError(f"Mianbaoduo order response has invalid {field}")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
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
        value = result.get("body")
        if not isinstance(value, str) or not value:
            raise ProviderError("Mianbaoduo alipay checkout returned no usable form")
        try:
            body_size = len(value.encode("utf-8"))
        except UnicodeError:
            raise ProviderError("Mianbaoduo alipay checkout returned an invalid form") from None
        if body_size > _MAX_CHECKOUT_HTML_BYTES or not _FORM_RE.search(value):
            raise ProviderError("Mianbaoduo alipay checkout returned an invalid form")
        return Checkout("html", value)

    def query_order(self, order_id: str) -> ProviderOrder:
        values = {"app_id": self.app_id, "out_trade_no": order_id}
        result = self._post("order query", QUERY_URL, values)

        for field in ("state", "amount", "payway"):
            if field not in result:
                raise ProviderError(f"Mianbaoduo order response is missing {field}")
        for field in ("description", "charge_id"):
            value = result.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ProviderError(f"Mianbaoduo order response has invalid {field}")

        return ProviderOrder(
            state=_safe_int(result["state"], "state"),
            amount=_safe_int(result["amount"], "amount"),
            description=result["description"],
            charge_id=result["charge_id"],
            payway=_safe_int(result["payway"], "payway"),
            raw=copy.deepcopy(result),
        )
