from __future__ import annotations

import hashlib
import hmac
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .models import Checkout, Payway


class RepositoryError(RuntimeError):
    """An order could not be persisted because of a business constraint."""


class Database:
    """Small SQLite repository for payment orders and device-bound licenses."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=5.0,
            isolation_level=None,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    session_id TEXT PRIMARY KEY NOT NULL,
                    provider_order_id TEXT NOT NULL UNIQUE,
                    device_hash TEXT NOT NULL,
                    product_id TEXT NOT NULL CHECK (product_id = 'opub-lifetime-v1'),
                    amount_fen INTEGER NOT NULL CHECK (amount_fen = 990),
                    status TEXT NOT NULL CHECK (status IN ('pending', 'paid', 'verification_failed', 'expired')),
                    poll_token_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    paid_at TEXT,
                    provider_charge_id TEXT UNIQUE,
                    payway TEXT NOT NULL CHECK (payway IN ('wechat', 'alipay')),
                    checkout_kind TEXT NOT NULL CHECK (checkout_kind IN ('url', 'html')),
                    checkout_value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS licenses (
                    license_id TEXT PRIMARY KEY NOT NULL,
                    session_id TEXT NOT NULL UNIQUE REFERENCES orders(session_id),
                    device_hash TEXT NOT NULL UNIQUE,
                    signed_payload TEXT NOT NULL,
                    issued_at TEXT NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS one_pending_order_per_device
                    ON orders(device_hash) WHERE status = 'pending';
                """
            )

    def row(self, query: str, values: Iterable[Any] = ()) -> sqlite3.Row | None:
        """Execute a repository/test query and return its first row, if any."""
        with self._connect() as connection:
            cursor = connection.execute(query, tuple(values))
            return cursor.fetchone()

    def insert_pending(
        self,
        *,
        session_id: str,
        provider_order_id: str,
        device_hash: str,
        poll_token_hash: str,
        created_at: str,
        expires_at: str,
        payway: Payway,
        checkout: Checkout,
    ) -> None:
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO orders (
                        session_id, provider_order_id, device_hash, product_id,
                        amount_fen, status, poll_token_hash, created_at, expires_at,
                        payway, checkout_kind, checkout_value
                    ) VALUES (?, ?, ?, 'opub-lifetime-v1', 990, 'pending', ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        provider_order_id,
                        device_hash,
                        poll_token_hash,
                        created_at,
                        expires_at,
                        payway,
                        checkout.kind,
                        checkout.value,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise RepositoryError(f"cannot create pending order: {exc}") from exc

    def license_for_device(self, device_hash: str) -> sqlite3.Row | None:
        return self.row(
            """
            SELECT license_id, session_id, device_hash, signed_payload, issued_at
            FROM licenses WHERE device_hash = ?
            """,
            (device_hash,),
        )

    def pending_for_device(self, device_hash: str) -> sqlite3.Row | None:
        return self.row(
            """
            SELECT session_id, provider_order_id, device_hash, product_id, amount_fen,
                   status, poll_token_hash, created_at, expires_at, paid_at,
                   provider_charge_id, payway, checkout_kind, checkout_value
            FROM orders WHERE device_hash = ? AND status = 'pending'
            """,
            (device_hash,),
        )

    def order_by_provider_id(self, provider_order_id: str) -> sqlite3.Row | None:
        return self.row(
            """
            SELECT session_id, provider_order_id, device_hash, product_id, amount_fen,
                   status, poll_token_hash, created_at, expires_at, paid_at,
                   provider_charge_id, payway, checkout_kind, checkout_value
            FROM orders WHERE provider_order_id = ?
            """,
            (provider_order_id,),
        )

    def order_by_session(self, session_id: str) -> sqlite3.Row | None:
        return self.row(
            """
            SELECT session_id, provider_order_id, device_hash, product_id, amount_fen,
                   status, poll_token_hash, created_at, expires_at, paid_at,
                   provider_charge_id, payway, checkout_kind, checkout_value
            FROM orders WHERE session_id = ?
            """,
            (session_id,),
        )

    def rotate_poll_token(self, session_id: str, poll_token_hash: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE orders SET poll_token_hash = ? WHERE session_id = ?",
                (poll_token_hash, session_id),
            )

    def poll_token_matches(self, session_id: str, poll_token_hash: str) -> bool:
        row = self.row(
            "SELECT poll_token_hash FROM orders WHERE session_id = ?",
            (session_id,),
        )
        stored = "" if row is None or row["poll_token_hash"] is None else row["poll_token_hash"]
        return hmac.compare_digest(
            hashlib.sha256(poll_token_hash.encode("utf-8")).digest(),
            hashlib.sha256(stored.encode("utf-8")).digest(),
        ) if row is not None else hmac.compare_digest(
            hashlib.sha256(poll_token_hash.encode("utf-8")).digest(),
            hashlib.sha256(b"__unknown_order_token__").digest(),
        )

    def expire_pending(self, device_hash: str, expired_at: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE orders SET status = 'expired', expires_at = ?
                WHERE device_hash = ? AND status = 'pending'
                """,
                (expired_at, device_hash),
            )

    def mark_verification_failed(self, session_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE orders SET status = 'verification_failed' WHERE session_id = ? AND status = 'pending'",
                (session_id,),
            )

    def issue_license(
        self,
        session_id: str,
        charge_id: str,
        signed_payload: str,
        license_id: str,
        issued_at: str,
    ) -> str:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            order = connection.execute(
                "SELECT device_hash, status FROM orders WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if order is None:
                raise RepositoryError(f"unknown order session: {session_id}")

            existing = connection.execute(
                "SELECT signed_payload FROM licenses WHERE device_hash = ?",
                (order["device_hash"],),
            ).fetchone()

            if order["status"] == "paid":
                if existing is None:
                    raise RepositoryError(f"paid order has no license: {session_id}")
                connection.commit()
                return str(existing["signed_payload"])

            if order["status"] not in {"pending", "expired", "verification_failed"}:
                raise RepositoryError(
                    f"cannot issue license for {order['status']} order: {session_id}"
                )

            connection.execute(
                """
                UPDATE orders
                SET status = 'paid', provider_charge_id = ?, paid_at = ?
                WHERE session_id = ? AND status IN ('pending', 'expired', 'verification_failed')
                """,
                (charge_id, issued_at, session_id),
            )

            if existing is not None:
                connection.commit()
                return str(existing["signed_payload"])

            connection.execute(
                """
                INSERT INTO licenses (license_id, session_id, device_hash, signed_payload, issued_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (license_id, session_id, order["device_hash"], signed_payload, issued_at),
            )
            connection.commit()
            return signed_payload
