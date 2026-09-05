from __future__ import annotations

import hashlib
import json
import secrets
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import Settings
from .database import Database
from .models import Payway
from .signing import sign_license

_SESSION_TTL = timedelta(minutes=30)
_PROVIDER_PAYWAY = {"wechat": 1, "alipay": 2}
_VERIFIED_PROVIDER_STATES = (1, 2)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class LicenseService:
    """Activation-session and webhook business rules.

    ``provider`` is any Mianbaoduo-compatible client exposing
    ``create_checkout(payway, order_id, description, amount_fen) -> Checkout``
    and ``query_order(order_id) -> ProviderOrder``; provider failures
    (``ProviderError``) are deliberately propagated so the webhook layer can
    answer 503 and let the provider retry.
    """

    def __init__(self, settings: Settings, database: Database, provider: Any) -> None:
        self.settings = settings
        self.database = database
        self.provider = provider
        self.creation_lock = threading.Lock()

    def create_session(self, device_hash: str, payway: Payway) -> dict[str, Any]:
        with self.creation_lock:
            existing = self.database.license_for_device(device_hash)
            if existing:
                return {"status": "licensed", "license": json.loads(existing["signed_payload"])}
            pending = self.database.pending_for_device(device_hash)
            if pending is not None and _parse_timestamp(pending["expires_at"]) <= datetime.now(timezone.utc):
                self.database.expire_pending(device_hash, now_iso())
                pending = None
            if pending is not None and pending["payway"] == payway:
                token = secrets.token_urlsafe(32)
                self.database.rotate_poll_token(pending["session_id"], token_hash(token))
                return self._pending_response(pending, token)
            if pending is not None:
                self.database.expire_pending(device_hash, now_iso())
            session_id = uuid.uuid4().hex
            provider_order_id = f"opub_{uuid.uuid4().hex}"
            checkout = self.provider.create_checkout(
                payway, provider_order_id, self.settings.product_name, self.settings.price_fen
            )
            token = secrets.token_urlsafe(32)
            created_at = now_iso()
            expires_at = (datetime.now(timezone.utc) + _SESSION_TTL).isoformat().replace("+00:00", "Z")
            self.database.insert_pending(
                session_id=session_id,
                provider_order_id=provider_order_id,
                device_hash=device_hash,
                poll_token_hash=token_hash(token),
                created_at=created_at,
                expires_at=expires_at,
                payway=payway,
                checkout=checkout,
            )
            return self._pending_response(self.database.order_by_session(session_id), token)

    @staticmethod
    def _pending_response(order: Any, token: str) -> dict[str, Any]:
        return {
            "status": "pending",
            "session_id": order["session_id"],
            "poll_token": token,
            "checkout": {"kind": order["checkout_kind"], "value": order["checkout_value"]},
            "expires_at": order["expires_at"],
        }

    def get_session(self, session_id: str, token: str) -> dict[str, Any]:
        # The repository stores token_hash(token) and compares its argument
        # against the stored column, so the raw token is hashed here.
        if not self.database.poll_token_matches(session_id, token_hash(token)):
            raise PermissionError("invalid poll token")
        order = self.database.order_by_session(session_id)
        if order["status"] == "pending" and _parse_timestamp(order["expires_at"]) <= datetime.now(timezone.utc):
            self.database.expire_pending(order["device_hash"], now_iso())
            return {"status": "expired"}
        if order["status"] == "paid":
            license_row = self.database.license_for_device(order["device_hash"])
            return {"status": "licensed", "license": json.loads(license_row["signed_payload"])}
        return {"status": order["status"]}

    def handle_charge_succeeded(self, provider_order_id: str) -> dict[str, Any]:
        order = self.database.order_by_provider_id(provider_order_id)
        if order is None:
            return {"status": "ignored"}
        existing = self.database.row("SELECT * FROM licenses WHERE session_id = ?", (order["session_id"],))
        if existing:
            return {"status": "licensed"}
        verified = self.provider.query_order(provider_order_id)
        if (
            verified.order_id != provider_order_id
            or verified.state not in _VERIFIED_PROVIDER_STATES
            or verified.amount != self.settings.price_fen
            or verified.description != self.settings.product_name
            or verified.payway != _PROVIDER_PAYWAY[order["payway"]]
        ):
            self.database.mark_verification_failed(order["session_id"])
            return {"status": "verification_failed"}
        license_id = uuid.uuid4().hex
        issued_at = now_iso()
        document = sign_license(
            self.settings.license_private_key,
            self.settings.license_key_id,
            license_id,
            order["device_hash"],
            issued_at,
        )
        self.database.issue_license(
            order["session_id"],
            verified.charge_id,
            json.dumps(document, sort_keys=True, separators=(",", ":")),
            license_id,
            issued_at,
        )
        return {"status": "licensed"}
