# opub License Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the three-endpoint FastAPI service that creates ¥9.90 device-bound payment sessions, verifies Mianbaoduo orders, and issues permanent Ed25519 licenses.

**Architecture:** A synchronous FastAPI application delegates persistence to SQLite, payment operations to a small Mianbaoduo adapter, and license creation to an Ed25519 signer. Webhooks never issue directly from callback data: they locate the local order, query Mianbaoduo with the merchant order number, validate the paid result, and commit the order/license atomically.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, SQLite WAL, requests, cryptography, pytest/TestClient, Caddy/systemd.

---

## File map

- `license_server/config.py`: validated environment configuration.
- `license_server/models.py`: request/response and provider value objects.
- `license_server/database.py`: schema and transaction-scoped order/license repository.
- `license_server/signing.py`: canonical JSON and Ed25519 signing.
- `license_server/mianbaoduo.py`: provider signature, checkout creation, and order lookup.
- `license_server/service.py`: activation-session and webhook business rules.
- `license_server/app.py`: the three HTTP routes and stable error mapping.
- `license_server/keygen.py`: generates the private key in `.secrets/` and the public client deployment module.
- `license_server/requirements.txt`: server-only runtime/test dependencies.
- `license_server/deploy/opub-license.service`: single-process service definition.
- `license_server/deploy/Caddyfile.example`: TLS reverse-proxy example.
- `license_server/README.md`: configuration, backup, and deployment runbook.
- `license_server/tests/`: isolated server tests.

### Task 1: Server package, configuration, and validated startup

**Files:**
- Create: `license_server/__init__.py`
- Create: `license_server/config.py`
- Create: `license_server/requirements.txt`
- Create: `license_server/tests/test_config.py`

- [ ] **Step 1: Write the failing configuration tests**

```python
# license_server/tests/test_config.py
import pytest

from license_server.config import Settings


BASE_ENV = {
    "OPUB_PUBLIC_BASE_URL": "https://license.opub.test",
    "OPUB_PAYMENT_RETURN_URL": "https://opub.test/payment-complete",
    "OPUB_MBD_APP_ID": "app-123",
    "OPUB_MBD_APP_KEY": "secret-123",
    "OPUB_LICENSE_PRIVATE_KEY": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
    "OPUB_LICENSE_KEY_ID": "2026-09",
    "OPUB_LICENSE_DB_PATH": "/tmp/opub-license-test.sqlite3",
}


def test_settings_fix_product_and_price_server_side():
    settings = Settings.from_env(BASE_ENV)
    assert settings.product_id == "opub-lifetime-v1"
    assert settings.product_name == "opub 永久设备许可证"
    assert settings.price_fen == 990


def test_settings_reject_non_https_public_url():
    with pytest.raises(ValueError, match="HTTPS"):
        Settings.from_env({**BASE_ENV, "OPUB_PUBLIC_BASE_URL": "http://localhost:8000"})


def test_settings_require_every_secret():
    env = dict(BASE_ENV)
    del env["OPUB_MBD_APP_KEY"]
    with pytest.raises(ValueError, match="OPUB_MBD_APP_KEY"):
        Settings.from_env(env)
```

- [ ] **Step 2: Run the tests and confirm the missing module failure**

Run: `python -m pytest license_server/tests/test_config.py -q`

Expected: FAIL because `license_server.config` does not exist.

- [ ] **Step 3: Add the package, dependency set, and complete settings object**

```python
# license_server/__init__.py
"""Private deployment package for the opub license service."""
```

```text
# license_server/requirements.txt
fastapi>=0.115,<1
uvicorn[standard]>=0.34,<1
requests>=2.32,<3
cryptography>=45,<51
pytest>=8,<10
httpx>=0.28,<1
```

```python
# license_server/config.py
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class Settings:
    public_base_url: str
    payment_return_url: str
    mbd_app_id: str
    mbd_app_key: str
    license_private_key: str
    license_key_id: str
    database_path: Path
    product_id: str = "opub-lifetime-v1"
    product_name: str = "opub 永久设备许可证"
    price_fen: int = 990

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Settings":
        names = (
            "OPUB_PUBLIC_BASE_URL",
            "OPUB_PAYMENT_RETURN_URL",
            "OPUB_MBD_APP_ID",
            "OPUB_MBD_APP_KEY",
            "OPUB_LICENSE_PRIVATE_KEY",
            "OPUB_LICENSE_KEY_ID",
            "OPUB_LICENSE_DB_PATH",
        )
        missing = [name for name in names if not env.get(name)]
        if missing:
            raise ValueError(f"missing required environment: {', '.join(missing)}")
        public_url = env["OPUB_PUBLIC_BASE_URL"].rstrip("/")
        return_url = env["OPUB_PAYMENT_RETURN_URL"]
        if not public_url.startswith("https://") or not return_url.startswith("https://"):
            raise ValueError("public and payment return URLs must use HTTPS")
        return cls(
            public_base_url=public_url,
            payment_return_url=return_url,
            mbd_app_id=env["OPUB_MBD_APP_ID"],
            mbd_app_key=env["OPUB_MBD_APP_KEY"],
            license_private_key=env["OPUB_LICENSE_PRIVATE_KEY"],
            license_key_id=env["OPUB_LICENSE_KEY_ID"],
            database_path=Path(env["OPUB_LICENSE_DB_PATH"]),
        )
```

- [ ] **Step 4: Install and run the configuration tests**

Run: `python -m pip install -r license_server/requirements.txt && python -m pytest license_server/tests/test_config.py -q`

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add license_server/__init__.py license_server/config.py license_server/requirements.txt license_server/tests/test_config.py
git commit -m "feat: add license server configuration"
```

### Task 2: Canonical license signing and safe key generation

**Files:**
- Create: `license_server/signing.py`
- Create: `license_server/keygen.py`
- Create: `license_server/tests/test_signing.py`

- [ ] **Step 1: Write signing tests with a deterministic test key**

```python
# license_server/tests/test_signing.py
import base64
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from license_server.signing import canonical_json, sign_license


def test_canonical_json_is_stable_and_compact():
    assert canonical_json({"z": 1, "a": "中"}) == b'{"a":"\\u4e2d","z":1}'


def test_signed_license_verifies_with_public_key():
    private = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    private_b64 = base64.b64encode(
        private.private_bytes_raw()
    ).decode("ascii")
    document = sign_license(private_b64, "test-key", "lic-1", "device-a", "2026-09-05T00:00:00Z")
    public = private.public_key()
    public.verify(base64.b64decode(document["signature"]), canonical_json(document["payload"]))
    assert document["payload"]["product"] == "opub-lifetime-v1"
    assert json.loads(json.dumps(document))["payload"]["license_id"] == "lic-1"
```

- [ ] **Step 2: Run and confirm failure**

Run: `python -m pytest license_server/tests/test_signing.py -q`

Expected: FAIL because `license_server.signing` does not exist.

- [ ] **Step 3: Implement canonical signing**

```python
# license_server/signing.py
import base64
import json
from typing import Any, Dict

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def canonical_json(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_license(private_key_b64: str, key_id: str, license_id: str, device_hash: str, issued_at: str) -> Dict[str, Any]:
    payload = {
        "schema_version": 1,
        "key_id": key_id,
        "license_id": license_id,
        "product": "opub-lifetime-v1",
        "device_hash": device_hash,
        "issued_at": issued_at,
    }
    key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_key_b64, validate=True))
    signature = base64.b64encode(key.sign(canonical_json(payload))).decode("ascii")
    return {"payload": payload, "signature": signature}
```

- [ ] **Step 4: Add a generator that writes the secret separately from the public client module**

```python
# license_server/keygen.py
import argparse
import base64
import os
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-file", required=True, type=Path)
    parser.add_argument("--client-file", required=True, type=Path)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--key-id", required=True)
    args = parser.parse_args()
    if not args.base_url.startswith("https://"):
        parser.error("--base-url must use HTTPS")
    key = Ed25519PrivateKey.generate()
    private_b64 = base64.b64encode(key.private_bytes_raw()).decode("ascii")
    public_b64 = base64.b64encode(key.public_key().public_bytes_raw()).decode("ascii")
    args.private_file.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(args.private_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(private_b64 + "\n")
    args.client_file.parent.mkdir(parents=True, exist_ok=True)
    args.client_file.write_text(
        "LICENSE_API_BASE_URL = " + repr(args.base_url.rstrip("/")) + "\n"
        + "TRUSTED_PUBLIC_KEYS = {" + repr(args.key_id) + ": " + repr(public_b64) + "}\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run tests and generator safety check**

Run: `python -m pytest license_server/tests/test_signing.py -q`

Expected: `2 passed`.

Run: `tmpdir=$(mktemp -d) && python -m license_server.keygen --private-file "$tmpdir/private" --client-file "$tmpdir/deployment.py" --base-url https://license.opub.test --key-id test && test "$(stat -f '%Lp' "$tmpdir/private" 2>/dev/null || stat -c '%a' "$tmpdir/private")" = 600`

Expected: exit code 0 and no private key printed.

- [ ] **Step 6: Commit**

```bash
git add license_server/signing.py license_server/keygen.py license_server/tests/test_signing.py
git commit -m "feat: sign permanent device licenses"
```

### Task 3: SQLite schema and repository invariants

**Files:**
- Create: `license_server/models.py`
- Create: `license_server/database.py`
- Create: `license_server/tests/test_database.py`

- [ ] **Step 1: Write repository tests for uniqueness and token rotation**

```python
# license_server/tests/test_database.py
from license_server.database import Database


def test_schema_reuses_first_license_for_the_same_device(tmp_path):
    db = Database(tmp_path / "db.sqlite3")
    db.initialize()
    db.insert_pending("s1", "o1", "d1", "token-1", "wechat", "url", "https://pay/1", "2026-09-05T00:00:00Z", "2026-09-05T00:30:00Z")
    db.issue_license("s1", "charge-1", '{"payload":{},"signature":"a"}', "lic-1", "2026-09-05T00:01:00Z")
    db.insert_pending("s2", "o2", "d1", "token-2", "wechat", "url", "https://pay/2", "2026-09-05T00:02:00Z", "2026-09-05T00:32:00Z")
    original = db.issue_license("s2", "charge-2", '{"payload":{},"signature":"b"}', "lic-2", "2026-09-05T00:03:00Z")
    assert original == '{"payload":{},"signature":"a"}'
    assert db.row("SELECT COUNT(*) AS count FROM licenses")["count"] == 1


def test_rotate_poll_token_invalidates_old_token(tmp_path):
    db = Database(tmp_path / "db.sqlite3")
    db.initialize()
    db.insert_pending("s1", "o1", "d1", "old-hash", "wechat", "url", "https://pay/1", "2026-09-05T00:00:00Z", "2026-09-05T00:30:00Z")
    db.rotate_poll_token("s1", "new-hash")
    assert not db.poll_token_matches("s1", "old-hash")
    assert db.poll_token_matches("s1", "new-hash")
```

- [ ] **Step 2: Run and confirm failure**

Run: `python -m pytest license_server/tests/test_database.py -q`

Expected: FAIL because repository types do not exist.

- [ ] **Step 3: Define shared value objects**

```python
# license_server/models.py
from dataclasses import dataclass
from typing import Any, Dict, Literal


Payway = Literal["wechat", "alipay"]


@dataclass(frozen=True)
class Checkout:
    kind: Literal["url", "html"]
    value: str


@dataclass(frozen=True)
class ProviderOrder:
    state: int
    amount: int
    description: str
    charge_id: str
    payway: int
    raw: Dict[str, Any]
```

- [ ] **Step 4: Implement the schema and repository operations**

```python
# license_server/database.py
import hmac
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional


SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS orders (
  session_id TEXT PRIMARY KEY,
  provider_order_id TEXT UNIQUE NOT NULL,
  device_hash TEXT NOT NULL,
  product_id TEXT NOT NULL,
  amount_fen INTEGER NOT NULL CHECK(amount_fen = 990),
  status TEXT NOT NULL CHECK(status IN ('pending','paid','verification_failed','expired')),
  poll_token_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  paid_at TEXT,
  provider_charge_id TEXT UNIQUE,
  payway TEXT NOT NULL CHECK(payway IN ('wechat','alipay')),
  checkout_kind TEXT NOT NULL CHECK(checkout_kind IN ('url','html')),
  checkout_value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS licenses (
  license_id TEXT PRIMARY KEY,
  session_id TEXT UNIQUE NOT NULL REFERENCES orders(session_id),
  device_hash TEXT UNIQUE NOT NULL,
  signed_payload TEXT NOT NULL,
  issued_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS one_pending_per_device ON orders(device_hash) WHERE status='pending';
"""


class Database:
    def __init__(self, path: Path):
        self.path = path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def insert_pending(self, session_id: str, provider_order_id: str, device_hash: str, token_hash: str, payway: str, checkout_kind: str, checkout_value: str, created_at: str, expires_at: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO orders VALUES (?,?,?,?,990,'pending',?,?,?,NULL,NULL,?,?,?)",
                (session_id, provider_order_id, device_hash, "opub-lifetime-v1", token_hash, created_at, expires_at, payway, checkout_kind, checkout_value),
            )

    def row(self, sql: str, values: tuple = ()) -> Optional[Dict[str, Any]]:
        with self.connect() as connection:
            result = connection.execute(sql, values).fetchone()
            return dict(result) if result else None

    def license_for_device(self, device_hash: str) -> Optional[Dict[str, Any]]:
        return self.row("SELECT * FROM licenses WHERE device_hash=?", (device_hash,))

    def pending_for_device(self, device_hash: str) -> Optional[Dict[str, Any]]:
        return self.row("SELECT * FROM orders WHERE device_hash=? AND status='pending'", (device_hash,))

    def order_by_provider_id(self, provider_order_id: str) -> Optional[Dict[str, Any]]:
        return self.row("SELECT * FROM orders WHERE provider_order_id=?", (provider_order_id,))

    def order_by_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self.row("SELECT * FROM orders WHERE session_id=?", (session_id,))

    def rotate_poll_token(self, session_id: str, token_hash: str) -> None:
        with self.connect() as connection:
            connection.execute("UPDATE orders SET poll_token_hash=? WHERE session_id=?", (token_hash, session_id))

    def poll_token_matches(self, session_id: str, token_hash: str) -> bool:
        row = self.order_by_session(session_id)
        return bool(row and hmac.compare_digest(row["poll_token_hash"], token_hash))

    def expire(self, session_id: str) -> None:
        with self.connect() as connection:
            connection.execute("UPDATE orders SET status='expired' WHERE session_id=? AND status='pending'", (session_id,))

    def mark_verification_failed(self, session_id: str) -> None:
        with self.connect() as connection:
            connection.execute("UPDATE orders SET status='verification_failed' WHERE session_id=? AND status='pending'", (session_id,))

    def issue_license(self, session_id: str, charge_id: str, signed_payload: str, license_id: str, issued_at: str) -> str:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            order = connection.execute("SELECT * FROM orders WHERE session_id=?", (session_id,)).fetchone()
            if not order:
                raise ValueError("order not found")
            existing = connection.execute("SELECT license_id FROM licenses WHERE device_hash=?", (order["device_hash"],)).fetchone()
            connection.execute("UPDATE orders SET status='paid', paid_at=?, provider_charge_id=? WHERE session_id=?", (issued_at, charge_id, session_id))
            if existing:
                stored = connection.execute("SELECT signed_payload FROM licenses WHERE license_id=?", (existing["license_id"],)).fetchone()
                return stored["signed_payload"]
            connection.execute("INSERT OR IGNORE INTO licenses VALUES (?,?,?,?,?)", (license_id, session_id, order["device_hash"], signed_payload, issued_at))
            return signed_payload
```

- [ ] **Step 5: Run repository tests**

Run: `python -m pytest license_server/tests/test_database.py -q`

Expected: `2 passed`.

- [ ] **Step 6: Commit**

```bash
git add license_server/models.py license_server/database.py license_server/tests/test_database.py
git commit -m "feat: persist device-bound license orders"
```

### Task 4: Mianbaoduo payment adapter

**Files:**
- Create: `license_server/mianbaoduo.py`
- Create: `license_server/tests/test_mianbaoduo.py`

- [ ] **Step 1: Write contract tests for signing and both payment forms**

```python
# license_server/tests/test_mianbaoduo.py
from unittest.mock import Mock

from license_server.mianbaoduo import MianbaoduoClient, sign_parameters


def test_sign_parameters_sorts_keys_and_excludes_empty_values():
    assert sign_parameters({"z": "2", "a": "1", "empty": ""}, "key") == "4eaa812cecd6f7ebcda6d2baa3af89d8"


def test_wechat_checkout_returns_h5_url():
    session = Mock()
    session.post.return_value.json.return_value = {"h5_url": "https://wx.tenpay.test/pay"}
    session.post.return_value.raise_for_status.return_value = None
    client = MianbaoduoClient("app", "key", "https://opub.test/done", session)
    checkout = client.create_checkout("wechat", "order-1", "opub 永久设备许可证", 990)
    assert checkout.kind == "url"
    assert checkout.value == "https://wx.tenpay.test/pay"
    assert session.post.call_args.kwargs["json"]["amount_total"] == 990


def test_alipay_checkout_returns_form_html():
    session = Mock()
    session.post.return_value.json.return_value = {"body": "<form>pay</form>"}
    session.post.return_value.raise_for_status.return_value = None
    client = MianbaoduoClient("app", "key", "https://opub.test/done", session)
    checkout = client.create_checkout("alipay", "order-2", "opub 永久设备许可证", 990)
    assert checkout.kind == "html"
```

- [ ] **Step 2: Run and confirm failure**

Run: `python -m pytest license_server/tests/test_mianbaoduo.py -q`

Expected: FAIL because the adapter does not exist.

- [ ] **Step 3: Implement the provider adapter exactly against the documented endpoints**

```python
# license_server/mianbaoduo.py
import hashlib
from typing import Any, Dict

import requests

from license_server.models import Checkout, ProviderOrder


WX_URL = "https://newapi.mbd.pub/release/wx/prepay"
ALIPAY_URL = "https://newapi.mbd.pub/release/alipay/pay"
QUERY_URL = "https://newapi.mbd.pub/release/main/search_order"


def sign_parameters(values: Dict[str, Any], app_key: str) -> str:
    filtered = {key: value for key, value in values.items() if value not in (None, "")}
    source = "&".join(f"{key}={filtered[key]}" for key in sorted(filtered))
    return hashlib.md5(f"{source}&key={app_key}".encode("utf-8")).hexdigest()


class MianbaoduoClient:
    def __init__(self, app_id: str, app_key: str, return_url: str, session: requests.Session | None = None):
        self.app_id = app_id
        self.app_key = app_key
        self.return_url = return_url
        self.session = session or requests.Session()

    def _post(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        signed = {**payload, "sign": sign_parameters(payload, self.app_key)}
        response = self.session.post(url, json=signed, timeout=(5, 15))
        response.raise_for_status()
        result = response.json()
        if result.get("error"):
            raise RuntimeError(f"Mianbaoduo error: {result['error']}")
        return result

    def create_checkout(self, payway: str, order_id: str, description: str, amount_fen: int) -> Checkout:
        common = {"app_id": self.app_id, "description": description, "out_trade_no": order_id, "amount_total": amount_fen}
        if payway == "wechat":
            result = self._post(WX_URL, {**common, "channel": "h5"})
            return Checkout("url", result["h5_url"])
        result = self._post(ALIPAY_URL, {**common, "url": self.return_url, "callback_url": self.return_url})
        return Checkout("html", result["body"])

    def query_order(self, order_id: str) -> ProviderOrder:
        result = self._post(QUERY_URL, {"app_id": self.app_id, "out_trade_no": order_id})
        return ProviderOrder(int(result["state"]), int(result["amount"]), result["description"], result["charge_id"], int(result["payway"]), result)
```

- [ ] **Step 4: Add negative tests for provider errors and malformed responses**

```python
def test_provider_error_is_not_treated_as_checkout():
    session = Mock()
    session.post.return_value.json.return_value = {"error": "error sign"}
    session.post.return_value.raise_for_status.return_value = None
    client = MianbaoduoClient("app", "key", "https://opub.test/done", session)
    with pytest.raises(RuntimeError, match="error sign"):
        client.create_checkout("wechat", "order-1", "opub 永久设备许可证", 990)


def test_contract_drift_missing_h5_url_fails_closed():
    session = Mock()
    session.post.return_value.json.return_value = {"unexpected": True}
    session.post.return_value.raise_for_status.return_value = None
    client = MianbaoduoClient("app", "key", "https://opub.test/done", session)
    with pytest.raises(KeyError, match="h5_url"):
        client.create_checkout("wechat", "order-1", "opub 永久设备许可证", 990)
```

Add `import pytest` beside the existing `Mock` import.

- [ ] **Step 5: Run adapter tests**

Run: `python -m pytest license_server/tests/test_mianbaoduo.py -q`

Expected: all tests pass without network access.

- [ ] **Step 6: Commit**

```bash
git add license_server/mianbaoduo.py license_server/tests/test_mianbaoduo.py
git commit -m "feat: integrate mianbaoduo payment APIs"
```

### Task 5: Activation-session and webhook business rules

**Files:**
- Create: `license_server/service.py`
- Create: `license_server/tests/test_service.py`

- [ ] **Step 1: Write service tests for fixed pricing, recovery, payway changes, and idempotency**

```python
# license_server/tests/test_service.py
import base64

import pytest

from license_server.config import Settings
from license_server.database import Database
from license_server.models import Checkout, ProviderOrder
from license_server.service import LicenseService


class FakeProvider:
    def __init__(self):
        self.create_calls = []
        self.query_result = ProviderOrder(1, 990, "opub 永久设备许可证", "charge-1", 1, {})

    def create_checkout(self, payway, order_id, description, amount_fen):
        self.create_calls.append({"payway": payway, "order_id": order_id, "description": description, "amount_fen": amount_fen})
        return Checkout("url" if payway == "wechat" else "html", "https://pay.test" if payway == "wechat" else "<form></form>")

    def query_order(self, order_id):
        return self.query_result


def build_service(tmp_path):
    settings = Settings.from_env({
        "OPUB_PUBLIC_BASE_URL": "https://license.opub.test",
        "OPUB_PAYMENT_RETURN_URL": "https://opub.test/done",
        "OPUB_MBD_APP_ID": "app",
        "OPUB_MBD_APP_KEY": "key",
        "OPUB_LICENSE_PRIVATE_KEY": base64.b64encode(bytes(range(32))).decode("ascii"),
        "OPUB_LICENSE_KEY_ID": "test",
        "OPUB_LICENSE_DB_PATH": str(tmp_path / "db.sqlite3"),
    })
    database = Database(settings.database_path)
    database.initialize()
    provider = FakeProvider()
    return LicenseService(settings, database, provider), database, provider


def test_fixed_price_reuse_token_rotation_and_payway_change(tmp_path):
    service, database, provider = build_service(tmp_path)
    first = service.create_session("a" * 64, "wechat")
    same = service.create_session("a" * 64, "wechat")
    changed = service.create_session("a" * 64, "alipay")
    assert provider.create_calls[0]["amount_fen"] == 990
    assert same["session_id"] == first["session_id"]
    assert same["poll_token"] != first["poll_token"]
    assert changed["session_id"] != first["session_id"]
    assert database.order_by_session(first["session_id"])["status"] == "expired"


def test_verified_webhook_is_idempotent_and_device_recovers_license(tmp_path):
    service, database, provider = build_service(tmp_path)
    created = service.create_session("a" * 64, "wechat")
    order_id = database.order_by_session(created["session_id"])["provider_order_id"]
    assert service.handle_charge_succeeded(order_id)["status"] == "licensed"
    assert service.handle_charge_succeeded(order_id)["status"] == "licensed"
    assert database.row("SELECT COUNT(*) AS count FROM licenses")["count"] == 1
    recovered = service.create_session("a" * 64, "alipay")
    assert recovered["status"] == "licensed"
    assert len(provider.create_calls) == 1


@pytest.mark.parametrize("result", [
    ProviderOrder(0, 990, "opub 永久设备许可证", "charge-1", 1, {}),
    ProviderOrder(1, 991, "opub 永久设备许可证", "charge-1", 1, {}),
    ProviderOrder(1, 990, "wrong product", "charge-1", 1, {}),
    ProviderOrder(1, 990, "opub 永久设备许可证", "charge-1", 2, {}),
])
def test_unverified_provider_result_never_issues(tmp_path, result):
    service, database, provider = build_service(tmp_path)
    created = service.create_session("a" * 64, "wechat")
    order_id = database.order_by_session(created["session_id"])["provider_order_id"]
    provider.query_result = result
    assert service.handle_charge_succeeded(order_id)["status"] == "verification_failed"
    assert database.row("SELECT COUNT(*) AS count FROM licenses")["count"] == 0


def test_unknown_webhook_is_ignored(tmp_path):
    service, database, provider = build_service(tmp_path)
    assert service.handle_charge_succeeded("unknown") == {"status": "ignored"}
    assert database.row("SELECT COUNT(*) AS count FROM licenses")["count"] == 0


def test_concurrent_duplicate_webhooks_issue_once(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    service, database, provider = build_service(tmp_path)
    created = service.create_session("a" * 64, "wechat")
    order_id = database.order_by_session(created["session_id"])["provider_order_id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(service.handle_charge_succeeded, [order_id, order_id]))
    assert all(result["status"] == "licensed" for result in results)
    assert database.row("SELECT COUNT(*) AS count FROM licenses")["count"] == 1
```

- [ ] **Step 2: Run and confirm failure**

Run: `python -m pytest license_server/tests/test_service.py -q`

Expected: FAIL because `LicenseService` does not exist.

- [ ] **Step 3: Implement the service with a single-process creation lock**

```python
# license_server/service.py
import hashlib
import json
import secrets
import threading
import uuid
from datetime import datetime, timedelta, timezone

from license_server.signing import sign_license


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


class LicenseService:
    def __init__(self, settings, database, provider):
        self.settings = settings
        self.database = database
        self.provider = provider
        self.creation_lock = threading.Lock()

    def create_session(self, device_hash: str, payway: str) -> dict:
        with self.creation_lock:
            existing = self.database.license_for_device(device_hash)
            if existing:
                return {"status": "licensed", "license": json.loads(existing["signed_payload"])}
            pending = self.database.pending_for_device(device_hash)
            if pending and datetime.fromisoformat(pending["expires_at"].replace("Z", "+00:00")) <= datetime.now(timezone.utc):
                self.database.expire(pending["session_id"])
                pending = None
            if pending and pending["payway"] == payway:
                token = secrets.token_urlsafe(32)
                self.database.rotate_poll_token(pending["session_id"], token_hash(token))
                return self._pending_response(pending, token)
            if pending:
                self.database.expire(pending["session_id"])
            session_id = uuid.uuid4().hex
            provider_order_id = f"opub_{uuid.uuid4().hex}"
            checkout = self.provider.create_checkout(payway, provider_order_id, self.settings.product_name, self.settings.price_fen)
            token = secrets.token_urlsafe(32)
            created_at = now_iso()
            expires_at = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
            self.database.insert_pending(session_id, provider_order_id, device_hash, token_hash(token), payway, checkout.kind, checkout.value, created_at, expires_at)
            return self._pending_response(self.database.order_by_session(session_id), token)

    @staticmethod
    def _pending_response(order: dict, token: str) -> dict:
        return {"status": "pending", "session_id": order["session_id"], "poll_token": token, "checkout": {"kind": order["checkout_kind"], "value": order["checkout_value"]}, "expires_at": order["expires_at"]}

    def get_session(self, session_id: str, supplied_token_hash: str) -> dict:
        if not self.database.poll_token_matches(session_id, supplied_token_hash):
            raise PermissionError("invalid poll token")
        order = self.database.order_by_session(session_id)
        if order["status"] == "pending" and datetime.fromisoformat(order["expires_at"].replace("Z", "+00:00")) <= datetime.now(timezone.utc):
            self.database.expire(session_id)
            return {"status": "expired"}
        if order["status"] == "paid":
            license_row = self.database.license_for_device(order["device_hash"])
            return {"status": "licensed", "license": json.loads(license_row["signed_payload"])}
        return {"status": order["status"]}

    def handle_charge_succeeded(self, provider_order_id: str) -> dict:
        order = self.database.order_by_provider_id(provider_order_id)
        if not order:
            return {"status": "ignored"}
        existing = self.database.row("SELECT * FROM licenses WHERE session_id=?", (order["session_id"],))
        if existing:
            return {"status": "licensed"}
        verified = self.provider.query_order(provider_order_id)
        expected_payway = 1 if order["payway"] == "wechat" else 2
        if verified.state not in (1, 2) or verified.amount != 990 or verified.description != self.settings.product_name or verified.payway != expected_payway:
            self.database.mark_verification_failed(order["session_id"])
            return {"status": "verification_failed"}
        license_id = uuid.uuid4().hex
        issued_at = now_iso()
        document = sign_license(self.settings.license_private_key, self.settings.license_key_id, license_id, order["device_hash"], issued_at)
        self.database.issue_license(order["session_id"], verified.charge_id, json.dumps(document, sort_keys=True, separators=(",", ":")), license_id, issued_at)
        return {"status": "licensed"}
```

- [ ] **Step 4: Run service and repository tests together**

Run: `python -m pytest license_server/tests/test_service.py license_server/tests/test_database.py -q`

Expected: all tests pass, including repeated webhook calls producing one row.

- [ ] **Step 5: Commit**

```bash
git add license_server/service.py license_server/tests/test_service.py
git commit -m "feat: issue licenses from verified payments"
```

### Task 6: The three FastAPI routes and request throttling

**Files:**
- Create: `license_server/app.py`
- Create: `license_server/limiter.py`
- Create: `license_server/tests/test_api.py`

- [ ] **Step 1: Write HTTP contract tests**

Use `TestClient(create_app(settings, database, provider))` and assert these exact routes exist:

```python
created = client.post("/v1/activation-sessions", json={
    "device_hash": "a" * 64,
    "client_nonce": "b" * 32,
    "client_version": "0.7.0",
    "payway": "wechat",
})
assert created.status_code == 201
assert created.json()["status"] == "pending"

polled = client.get(
    f"/v1/activation-sessions/{created.json()['session_id']}",
    headers={"Authorization": f"Bearer {created.json()['poll_token']}"},
)
assert polled.json() == {"status": "pending"}

notified = client.post("/v1/webhooks/mianbaoduo", json={
    "type": "charge_succeeded",
    "data": {"out_trade_no": provider.last_order_id},
})
assert notified.status_code == 200
```

Also assert invalid hash/nonce/payway returns 422, missing or wrong bearer token returns 401, unknown webhook is acknowledged without issuance, complaint is acknowledged without issuance, and a 61st creation request from one IP returns 429.

- [ ] **Step 2: Run and confirm failure**

Run: `python -m pytest license_server/tests/test_api.py -q`

Expected: FAIL because the application factory does not exist.

- [ ] **Step 3: Implement a bounded in-memory limiter for the documented single worker**

```python
# license_server/limiter.py
import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window_seconds = window_seconds
        self.events = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            events = self.events[key]
            while events and events[0] <= now - self.window_seconds:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            return True
```

- [ ] **Step 4: Implement the application factory and only the three public routes**

```python
# license_server/app.py
import hashlib
import os
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from license_server.config import Settings
from license_server.database import Database
from license_server.limiter import RateLimiter
from license_server.mianbaoduo import MianbaoduoClient
from license_server.service import LicenseService, token_hash


class ActivationRequest(BaseModel):
    device_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    client_nonce: str = Field(min_length=22, max_length=256)
    client_version: str = Field(min_length=1, max_length=64)
    payway: Literal["wechat", "alipay"]


class WebhookRequest(BaseModel):
    type: str
    data: dict[str, Any]


def bearer_token(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing poll token")
    return authorization.removeprefix("Bearer ")


def create_app(settings: Settings, database: Database, provider: MianbaoduoClient) -> FastAPI:
    database.initialize()
    service = LicenseService(settings, database, provider)
    creation_limiter = RateLimiter(60, 3600)
    polling_limiter = RateLimiter(180, 600)
    app = FastAPI(title="opub License Service", docs_url=None, redoc_url=None, openapi_url=None)

    @app.post("/v1/activation-sessions", status_code=status.HTTP_201_CREATED)
    def create_activation(body: ActivationRequest, request: Request):
        client_ip = request.client.host if request.client else "unknown"
        if not creation_limiter.allow(f"{client_ip}:{body.device_hash}"):
            raise HTTPException(status_code=429, detail="rate limited")
        return service.create_session(body.device_hash, body.payway)

    @app.get("/v1/activation-sessions/{session_id}")
    def get_activation(session_id: str, request: Request, token: str = Depends(bearer_token)):
        client_ip = request.client.host if request.client else "unknown"
        if not polling_limiter.allow(f"{client_ip}:{session_id}"):
            raise HTTPException(status_code=429, detail="rate limited")
        try:
            return service.get_session(session_id, token_hash(token))
        except PermissionError:
            raise HTTPException(status_code=401, detail="invalid poll token")

    @app.post("/v1/webhooks/mianbaoduo")
    def webhook(body: WebhookRequest):
        if body.type == "complaint":
            logger.warning("payment complaint order=%s", str(body.data.get("out_trade_no", "unknown")))
            return {"status": "ignored"}
        if body.type != "charge_succeeded":
            return {"status": "ignored"}
        order_id = str(body.data.get("out_trade_no", ""))
        return service.handle_charge_succeeded(order_id)

    return app


def app_from_env() -> FastAPI:
    settings = Settings.from_env(os.environ)
    database = Database(settings.database_path)
    provider = MianbaoduoClient(settings.mbd_app_id, settings.mbd_app_key, settings.payment_return_url)
    return create_app(settings, database, provider)


```

Uvicorn must load `app_from_env` with `--factory`; importing the module in tests must not read
production environment variables.

- [ ] **Step 5: Prevent provider outages from becoming unstructured 500 responses**

Add imports `logging`, `secrets`, `sqlite3`, and `JSONResponse`, then register:

```python
logger = logging.getLogger("opub.license")


async def service_unavailable(request: Request, exc: Exception):
    request_id = secrets.token_hex(8)
    logger.error("license service failure request_id=%s route=%s error=%s", request_id, request.url.path, exc.__class__.__name__)
    return JSONResponse(status_code=503, content={"detail": "service unavailable", "request_id": request_id})


app.add_exception_handler(RuntimeError, service_unavailable)
app.add_exception_handler(sqlite3.Error, service_unavailable)
```

Add this test:

```python
def test_provider_failure_returns_redacted_503(client, provider):
    provider.create_checkout.side_effect = RuntimeError("secret-app-key device-hash checkout-html")
    response = client.post("/v1/activation-sessions", json={"device_hash": "a" * 64, "client_nonce": "b" * 32, "client_version": "0.7.0", "payway": "wechat"})
    assert response.status_code == 503
    body = response.text
    assert "request_id" in body
    for secret in ("secret-app-key", "device-hash", "checkout-html", "a" * 64):
        assert secret not in body
```

- [ ] **Step 6: Run the API suite**

Run: `python -m pytest license_server/tests -q`

Expected: all server tests pass and no test reaches `newapi.mbd.pub`.

- [ ] **Step 7: Commit**

```bash
git add license_server/app.py license_server/limiter.py license_server/tests/test_api.py
git commit -m "feat: expose license activation API"
```

### Task 7: Deployment, backup, and package-isolation checks

**Files:**
- Create: `license_server/deploy/opub-license.service`
- Create: `license_server/deploy/Caddyfile.example`
- Create: `license_server/README.md`
- Create: `MANIFEST.in`
- Modify: `.gitignore`
- Modify: `tests/test_package_build.py`

- [ ] **Step 1: Add failing build assertions that private server code is absent from distributions**

Extend `tests/test_package_build.py` to build both wheel and sdist, list their entries, and assert:

```python
for names in (wheel_names, sdist_names):
    self.assertFalse(any("license_server/" in name for name in names))
    self.assertFalse(any(".secrets/" in name for name in names))
    self.assertFalse(any(name.endswith(".sqlite3") for name in names))
```

- [ ] **Step 2: Run the build test and confirm it detects any leakage**

Run: `python -m pytest tests/test_package_build.py -q`

Expected: PASS after the explicit source-distribution prune is present.

Create:

```text
# MANIFEST.in
prune license_server
prune .secrets
global-exclude *.sqlite3 *.sqlite3-shm *.sqlite3-wal
```

- [ ] **Step 3: Add secret/database ignore rules**

Append exactly these rules to `.gitignore`:

```gitignore
# License service runtime state
license_server/data/
license_server/*.sqlite3
license_server/*.sqlite3-shm
license_server/*.sqlite3-wal
```

- [ ] **Step 4: Add the single-process systemd unit**

```ini
# license_server/deploy/opub-license.service
[Unit]
Description=opub license service
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/opub
EnvironmentFile=/etc/opub-license.env
ExecStart=/opt/opub/.venv/bin/uvicorn license_server.app:app_from_env --factory --host 127.0.0.1 --port 8013 --workers 1 --proxy-headers --forwarded-allow-ips=127.0.0.1
Restart=on-failure
User=opub-license
Group=opub-license
UMask=0077

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 5: Add the Caddy route**

```caddyfile
# license_server/deploy/Caddyfile.example
{$OPUB_LICENSE_HOST} {
    encode zstd gzip
    reverse_proxy 127.0.0.1:8013
}
```

The deployment runbook must set `OPUB_LICENSE_HOST` to the hostname portion of `OPUB_PUBLIC_BASE_URL`, configure the exact webhook URL `/v1/webhooks/mianbaoduo` in the provider console, and keep Uvicorn at one worker because creation locking and rate limiting are process-local.

- [ ] **Step 6: Write the runbook with exact backup and smoke commands**

Document:

```bash
python -m pip install -r license_server/requirements.txt
sudo systemctl enable --now opub-license
curl -fsS -o /dev/null -w '%{http_code}\n' "$OPUB_PUBLIC_BASE_URL/v1/activation-sessions/not-found"
sqlite3 "$OPUB_LICENSE_DB_PATH" '.backup /var/backups/opub-license/latest.sqlite3'
```

Expected smoke status is `401`; the route exists but requires a poll token. Document daily backup retention of 30 days and two offline copies of the private key.

- [ ] **Step 7: Run final server verification**

Run: `python -m pytest license_server/tests tests/test_package_build.py -q && git diff --check`

Expected: all tests pass and `git diff --check` prints nothing.

- [ ] **Step 8: Commit**

```bash
git add .gitignore MANIFEST.in license_server/deploy license_server/README.md tests/test_package_build.py
git commit -m "ops: add license service deployment"
```

## Server completion gate

Do not expose the client paywall yet. Before starting the client plan, confirm:

- The provider has approved the payment scene and both payment methods.
- A real HTTPS hostname is in `OPUB_PUBLIC_BASE_URL`.
- The webhook URL is configured with no query parameters.
- One internal ¥9.90 order reaches `licensed` exactly once.
- SQLite backup restoration is exercised on a disposable copy.
- The generated private key exists only in `.secrets/`, server secret storage, and offline backups.
