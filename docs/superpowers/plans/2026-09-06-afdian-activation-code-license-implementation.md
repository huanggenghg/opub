# Afdian Activation Code License Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the unusable Mianbaoduo checkout flow with Afdian-delivered, one-time activation codes that bind one device and issue a permanent offline `opub-major-0` license.

**Architecture:** The private FastAPI service stores only hashes of pre-generated high-entropy codes. A single transactional redemption endpoint binds an available code to one device and returns an Ed25519-signed license; the public CLI opens the fixed Afdian item URL, accepts the delivered code, verifies the returned license locally, and writes it atomically. Existing Mianbaoduo tables stay in SQLite for safe migration, but the runtime no longer registers payment-session or webhook routes.

**Tech Stack:** Python 3.9+, FastAPI, Pydantic, SQLite WAL, Ed25519 via `cryptography`, Requests, pytest/unittest.

---

## File map

- Create `license_server/codes.py`: code generation, normalization/hash use, secure inventory export, and local `generate`/`stats` commands.
- Create `publish/licensing/codes.py`: public activation-code normalization and format validation shared by client and server.
- Modify `license_server/config.py`: remove Mianbaoduo/payment-return secrets and expose fixed `opub-major-0` metadata.
- Modify `license_server/database.py`: create activation-code tables and provide atomic import/redemption/statistics operations while retaining legacy tables.
- Modify `license_server/signing.py`: sign the configured major-version product instead of the legacy lifetime product.
- Modify `license_server/service.py`: replace checkout/webhook orchestration with activation-code redemption.
- Modify `license_server/app.py`: expose only `POST /v1/code-activations` and stable license error responses.
- Delete `license_server/mianbaoduo.py` and `license_server/models.py`: remove dead provider runtime code after replacement tests pass.
- Modify `publish/licensing/api.py`: call the redemption endpoint and safely map public service error codes.
- Replace `publish/licensing/activation.py`: remove checkout files, QR generation, saved sessions, and polling; perform one request and local verification.
- Modify `publish/licensing/__init__.py`: open the Afdian item, prompt/accept a code, and expose updated error guidance.
- Modify `publish/licensing/deployment.py`: include the public Afdian purchase URL and product id.
- Modify `publish/licensing/verifier.py`: accept only `opub-major-0` licenses.
- Modify `publish/orchestrator.py`: replace `--pay-with` with `--code` and keep licensing ahead of all publishing side effects.
- Modify `license_server/keygen.py`: preserve purchase URL and product id when regenerating client deployment data.
- Modify `pyproject.toml`: remove QR dependency and bump the changed CLI contract to `0.8.0`.
- Modify `AGENT.md`, `README.md`, `docs/CLI.md`, `skills/opub-cli/SKILL.md`, and `license_server/README.md`: document Afdian code activation and local inventory operations.
- Rewrite the related tests under `license_server/tests/` and `tests/`; keep package-isolation and Python 3.9 checks.

## Task 1: Product identity, configuration, signing, and verification

**Files:**
- Modify: `license_server/config.py`
- Modify: `license_server/signing.py`
- Modify: `license_server/tests/test_config.py`
- Modify: `license_server/tests/test_signing.py`
- Modify: `publish/licensing/deployment.py`
- Modify: `publish/licensing/verifier.py`
- Modify: `tests/test_license_verifier.py`

- [ ] **Step 1: Write failing configuration and signing tests**

Replace the payment-provider expectations in `license_server/tests/test_config.py` with the four required secrets/settings and the fixed product:

```python
def _valid_env() -> dict[str, str]:
    return {
        "OPUB_PUBLIC_BASE_URL": "https://example.com/license",
        "OPUB_LICENSE_PRIVATE_KEY": VALID_PRIVATE_KEY_B64,
        "OPUB_LICENSE_KEY_ID": "key-id",
        "OPUB_LICENSE_DB_PATH": "/tmp/licenses.db",
    }


def test_settings_defaults_are_fixed() -> None:
    settings = Settings.from_env(_valid_env())
    assert settings.product_id == "opub-major-0"
    assert settings.product_name == "opub 0.x 创始版"
    assert settings.price_fen == 990


def test_payment_provider_settings_are_not_required() -> None:
    settings = Settings.from_env(_valid_env())
    assert not hasattr(settings, "mbd_app_id")
    assert not hasattr(settings, "mbd_app_key")
    assert not hasattr(settings, "payment_return_url")
```

Update the signed payload assertion in `license_server/tests/test_signing.py` and all fixtures in `tests/test_license_verifier.py`:

```python
assert signed["payload"]["product"] == "opub-major-0"
```

Add a verifier regression:

```python
def test_legacy_lifetime_product_is_rejected() -> None:
    document = signed_document(product="opub-lifetime-v1")
    with pytest.raises(LicenseValidationError) as exc_info:
        verify_license(document, DEVICE_HASH, TRUSTED_KEYS)
    assert exc_info.value.code == "LIC-002"
```

- [ ] **Step 2: Run the focused tests and verify the old contract fails**

Run:

```bash
python -m pytest license_server/tests/test_config.py license_server/tests/test_signing.py tests/test_license_verifier.py -q
```

Expected: failures still show Mianbaoduo fields are required and the signed product is `opub-lifetime-v1`.

- [ ] **Step 3: Implement the fixed major-version contract**

Make `Settings` contain only:

```python
@dataclass(frozen=True)
class Settings:
    public_base_url: str
    license_private_key: str
    license_key_id: str
    database_path: Path
    product_id: str = "opub-major-0"
    product_name: str = "opub 0.x 创始版"
    price_fen: int = 990
```

`Settings.from_env()` must require exactly `OPUB_PUBLIC_BASE_URL`, `OPUB_LICENSE_PRIVATE_KEY`, `OPUB_LICENSE_KEY_ID`, and `OPUB_LICENSE_DB_PATH`, retaining existing HTTPS/private-key validation.

Change `sign_license()` to accept `product_id: str = "opub-major-0"` and write that value into the signed payload. Change the verifier product check to `opub-major-0`.

Set public deployment constants exactly:

```python
LICENSE_API_BASE_URL = "https://dachitech.xyz/license"
LICENSE_PURCHASE_URL = "https://afdian.com/item/69bf71f0a9f511f1bc065254001e7c00"
LICENSE_PRODUCT_ID = "opub-major-0"
TRUSTED_PUBLIC_KEYS = {"opub-license-2026-09": "z9RqPzxIN9C1HFTkgemN3Riwp58THCplDwlKFZhH9Ww="}
```

- [ ] **Step 4: Run focused tests**

Run the command from Step 2.

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add license_server/config.py license_server/signing.py license_server/tests/test_config.py license_server/tests/test_signing.py publish/licensing/deployment.py publish/licensing/verifier.py tests/test_license_verifier.py
git commit -m "refactor: define opub major version license"
```

## Task 2: Activation-code format and atomic database redemption

**Files:**
- Create: `publish/licensing/codes.py`
- Modify: `license_server/database.py`
- Rewrite: `license_server/tests/test_database.py`
- Create: `tests/test_activation_codes.py`

- [ ] **Step 1: Write failing code-format tests**

Create `tests/test_activation_codes.py`:

```python
import pytest

from publish.licensing.codes import ActivationCodeFormatError, normalize_activation_code


def test_normalizes_display_code() -> None:
    raw = "opub0-abcde-fghjk-mnpqr-stvwx-yz234-56789"
    assert normalize_activation_code(raw) == "OPUB0ABCDEFGHJKMNPQRSTVWXYZ23456789"


@pytest.mark.parametrize("value", ["", "OPUB1-ABCDE", "OPUB0-O0000", "OPUB0-../SECRET", "A" * 100])
def test_rejects_invalid_code(value: str) -> None:
    with pytest.raises(ActivationCodeFormatError):
        normalize_activation_code(value)
```

- [ ] **Step 2: Write failing database tests**

Rewrite `license_server/tests/test_database.py` around the new tables while retaining one migration assertion for legacy tables. Cover import, lookup, same-device idempotency, other-device rejection, existing-device/non-consumption, and concurrency:

```python
def test_initialize_preserves_legacy_and_adds_code_tables(tmp_path: Path) -> None:
    database = _database(tmp_path)
    names = {
        row[0]
        for row in database.rows("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"orders", "licenses", "activation_codes", "code_licenses"} <= names


def test_redeem_available_code_binds_device_once(tmp_path: Path) -> None:
    database = _database(tmp_path)
    database.import_activation_code(CODE_HASH, "opub-major-0", "created")
    result = database.redeem_activation_code(
        CODE_HASH, DEVICE_HASH, "lic-1", '{"payload":1}', "issued"
    )
    assert result.status == "created"
    assert result.signed_payload == '{"payload":1}'
    assert database.code_stats() == {"available": 0, "redeemed": 1, "total": 1}


def test_redeem_same_code_same_device_is_idempotent(tmp_path: Path) -> None:
    database = _database(tmp_path)
    database.import_activation_code(CODE_HASH, "opub-major-0", "created")
    first = database.redeem_activation_code(CODE_HASH, DEVICE_HASH, "lic-1", "payload-1", "time-1")
    second = database.redeem_activation_code(CODE_HASH, DEVICE_HASH, "lic-2", "payload-2", "time-2")
    assert first.signed_payload == second.signed_payload == "payload-1"


def test_redeem_same_code_other_device_is_rejected(tmp_path: Path) -> None:
    database = _database(tmp_path)
    database.import_activation_code(CODE_HASH, "opub-major-0", "created")
    database.redeem_activation_code(CODE_HASH, DEVICE_HASH, "lic-1", "payload-1", "time-1")
    assert database.redeem_activation_code(CODE_HASH, OTHER_DEVICE, "lic-2", "payload-2", "time-2").status == "used"


def test_existing_device_does_not_consume_second_code(tmp_path: Path) -> None:
    database = _database(tmp_path)
    database.import_activation_code(CODE_HASH, "opub-major-0", "created")
    database.import_activation_code(SECOND_CODE_HASH, "opub-major-0", "created")
    database.redeem_activation_code(CODE_HASH, DEVICE_HASH, "lic-1", "payload-1", "time-1")
    result = database.redeem_activation_code(SECOND_CODE_HASH, DEVICE_HASH, "lic-2", "payload-2", "time-2")
    assert result.status == "existing_device"
    assert database.code_stats()["available"] == 1
```

For concurrency, run two `redeem_activation_code` calls for the same code on different device hashes with `ThreadPoolExecutor`; assert exactly one `created` and one `used` result and one `code_licenses` row.

- [ ] **Step 3: Run the new tests and verify they fail**

Run:

```bash
python -m pytest tests/test_activation_codes.py license_server/tests/test_database.py -q
```

Expected: collection/import failures because the code parser, tables, and redemption API do not exist.

- [ ] **Step 4: Implement shared normalization**

Create `publish/licensing/codes.py` with one canonical representation:

```python
import re

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_NORMALIZED = re.compile(r"OPUB0[" + _ALPHABET + r"]{30}\Z")


class ActivationCodeFormatError(ValueError):
    pass


def normalize_activation_code(value: str) -> str:
    if not isinstance(value, str):
        raise ActivationCodeFormatError("invalid activation code")
    normalized = value.strip().upper().replace("-", "")
    if _NORMALIZED.fullmatch(normalized) is None:
        raise ActivationCodeFormatError("invalid activation code")
    return normalized
```

- [ ] **Step 5: Add code tables and transactional methods**

Add to `Database.initialize()` without changing the legacy schema:

```sql
CREATE TABLE IF NOT EXISTS activation_codes (
    code_hash TEXT PRIMARY KEY NOT NULL,
    product_id TEXT NOT NULL CHECK (product_id = 'opub-major-0'),
    status TEXT NOT NULL CHECK (status IN ('available', 'redeemed')),
    created_at TEXT NOT NULL,
    redeemed_at TEXT,
    device_hash TEXT
);

CREATE TABLE IF NOT EXISTS code_licenses (
    license_id TEXT PRIMARY KEY NOT NULL,
    code_hash TEXT NOT NULL UNIQUE REFERENCES activation_codes(code_hash),
    device_hash TEXT NOT NULL UNIQUE,
    signed_payload TEXT NOT NULL,
    issued_at TEXT NOT NULL
);
```

Add a frozen result object in `database.py`:

```python
@dataclass(frozen=True)
class RedemptionResult:
    status: Literal["created", "same_device", "used", "invalid", "existing_device"]
    signed_payload: str | None = None
```

Implement `rows()`, `import_activation_code()`, `import_activation_codes()`, `code_stats()`, and `redeem_activation_code()`. `import_activation_codes()` accepts an iterable of `(code_hash, product_id, created_at)` tuples and inserts the whole batch in one transaction. The redemption method must use `BEGIN IMMEDIATE`, compare bound devices inside the transaction, update the code and insert `code_licenses` together, and roll back on every exception.

- [ ] **Step 6: Run focused tests**

Run the command from Step 3.

Expected: all selected tests pass, including concurrency.

- [ ] **Step 7: Commit**

```bash
git add publish/licensing/codes.py tests/test_activation_codes.py license_server/database.py license_server/tests/test_database.py
git commit -m "feat: add atomic activation code inventory"
```

## Task 3: Secure inventory generator and local statistics

**Files:**
- Create: `license_server/codes.py`
- Create: `license_server/tests/test_codes.py`
- Modify: `.gitignore`

- [ ] **Step 1: Write failing generator tests**

Create `license_server/tests/test_codes.py` covering format, uniqueness, hashes-only persistence, mode `0600`, no overwrite, and stats:

```python
def test_generate_exports_unique_codes_and_stores_only_hashes(tmp_path: Path) -> None:
    database = _database(tmp_path)
    output = tmp_path / "inventory.txt"
    assert generate_inventory(database, 3, output) == 3
    codes = output.read_text(encoding="utf-8").splitlines()
    assert len(codes) == len(set(codes)) == 3
    assert all(code.startswith("OPUB0-") for code in codes)
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    database_bytes = database.path.read_bytes()
    assert all(code.encode("ascii") not in database_bytes for code in codes)
    assert database.code_stats() == {"available": 3, "redeemed": 0, "total": 3}


def test_generate_refuses_existing_output_before_import(tmp_path: Path) -> None:
    database = _database(tmp_path)
    output = tmp_path / "inventory.txt"
    output.write_text("sentinel", encoding="utf-8")
    with pytest.raises(FileExistsError):
        generate_inventory(database, 2, output)
    assert output.read_text(encoding="utf-8") == "sentinel"
    assert database.code_stats()["total"] == 0
```

Add exact CLI coverage:

```python
def test_cli_generate_and_stats(tmp_path: Path, monkeypatch, capsys) -> None:
    database_path = tmp_path / "codes.sqlite3"
    output = tmp_path / "inventory.txt"
    monkeypatch.setenv("OPUB_LICENSE_DB_PATH", str(database_path))
    assert codes.main(["generate", "--count", "2", "--output", str(output)]) == 0
    assert len(output.read_text(encoding="utf-8").splitlines()) == 2
    assert codes.main(["stats"]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == "available=2 redeemed=0 total=2"
```

- [ ] **Step 2: Run and verify failure**

```bash
python -m pytest license_server/tests/test_codes.py -q
```

Expected: import failure because `license_server.codes` does not exist.

- [ ] **Step 3: Implement generator and CLI**

Generate 30 random symbols from the 32-character alphabet with `secrets.choice`, format them in six groups of five after `OPUB0-`, normalize through the shared parser, and hash exactly:

```python
def code_hash(normalized: str) -> str:
    return hashlib.sha256(
        b"opub-activation-code-v1\n" + normalized.encode("ascii")
    ).hexdigest()
```

`generate_inventory()` must reserve the target with exclusive creation, set mode `0600`, write and fsync the plaintext list, import all hashes inside one database transaction, and remove the newly created output if importing fails. `main()` must read only `OPUB_LICENSE_DB_PATH`, initialize the database, and support:

```text
python -m license_server.codes generate --count 100 --output .secrets/opub-afdian-codes.txt
python -m license_server.codes stats
```

Reject counts outside `1..10000`. Add `.secrets/*codes*.txt` to `.gitignore` even though `.secrets/` is already ignored, documenting the inventory boundary explicitly.

- [ ] **Step 4: Run focused tests**

```bash
python -m pytest license_server/tests/test_codes.py tests/test_activation_codes.py license_server/tests/test_database.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add .gitignore license_server/codes.py license_server/tests/test_codes.py
git commit -m "feat: generate afdian activation code inventory"
```

## Task 4: Redemption service and one-route FastAPI application

**Files:**
- Rewrite: `license_server/service.py`
- Rewrite: `license_server/app.py`
- Modify: `license_server/database.py`
- Rewrite: `license_server/tests/test_service.py`
- Rewrite: `license_server/tests/test_api.py`
- Delete: `license_server/mianbaoduo.py`
- Delete: `license_server/models.py`
- Delete: `license_server/tests/test_mianbaoduo.py`
- Modify: `license_server/requirements.txt`

- [ ] **Step 1: Write failing service tests**

Build `LicenseService(settings, database)` without a provider. Import known code hashes, then cover success, invalid code, used code, version mismatch, idempotent recovery, and concurrent devices:

```python
def test_redeem_signs_major_zero_license(tmp_path: Path) -> None:
    service, database = build_service(tmp_path)
    import_code(database, CODE)
    response = service.redeem(CODE, DEVICE_HASH, "0.8.0")
    assert response["status"] == "licensed"
    assert response["license"]["payload"]["product"] == "opub-major-0"
    assert response["license"]["payload"]["device_hash"] == DEVICE_HASH


@pytest.mark.parametrize("version", ["1.0.0", "garbage", "", "00.8.0"])
def test_redeem_rejects_non_zero_major(version: str, tmp_path: Path) -> None:
    service, database = build_service(tmp_path)
    import_code(database, CODE)
    with pytest.raises(ClientVersionMismatch):
        service.redeem(CODE, DEVICE_HASH, version)
```

Assert invalid format and unknown inventory both raise `InvalidActivationCode`; assert a code bound to another device raises `ActivationCodeUsed` without changing database rows.

- [ ] **Step 2: Write failing API tests**

Replace the three-route assertions with:

```python
def test_app_exposes_only_code_activation() -> None:
    paths = {route.path for route in app.routes if getattr(route, "path", "").startswith("/v1/")}
    assert paths == {"/v1/code-activations"}


def test_code_activation_returns_license(client, seeded_code) -> None:
    response = client.post("/v1/code-activations", json={
        "device_hash": "a" * 64,
        "activation_code": seeded_code,
        "client_version": "0.8.0",
    })
    assert response.status_code == 200
    assert response.json()["status"] == "licensed"


@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [(InvalidActivationCode, 400, "LIC-013"), (ActivationCodeUsed, 409, "LIC-014"), (ClientVersionMismatch, 422, "LIC-015")],
)
def test_public_errors_are_stable(error, status_code, code, client, monkeypatch):
    def fail(*_args, **_kwargs):
        raise error()

    monkeypatch.setattr(LicenseService, "redeem", fail)
    response = client.post("/v1/code-activations", json={
        "device_hash": "a" * 64,
        "activation_code": VALID_CODE,
        "client_version": "0.8.0",
    })
    assert response.status_code == status_code
    assert response.json() == {"detail": {"code": code}}
```

The parameterized test uses the existing `client` and `monkeypatch` fixtures and must not assert exception messages.

- [ ] **Step 3: Run and verify failures**

```bash
python -m pytest license_server/tests/test_service.py license_server/tests/test_api.py -q
```

Expected: failures because the old provider constructor and three routes still exist.

- [ ] **Step 4: Implement service errors and redemption**

Define:

```python
class InvalidActivationCode(ValueError):
    code = "LIC-013"

class ActivationCodeUsed(ValueError):
    code = "LIC-014"

class ClientVersionMismatch(ValueError):
    code = "LIC-015"
```

`LicenseService.redeem()` must normalize/hash the code, require a syntactically valid major-zero client version, create a candidate license with `sign_license()`, call the transactional database method, map its statuses to the three public errors, and parse the stored signed payload for idempotent responses.

- [ ] **Step 5: Replace FastAPI routes**

Define the request with bounded fields:

```python
class CodeActivationRequest(BaseModel):
    device_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    activation_code: str = Field(min_length=1, max_length=64)
    client_version: str = Field(min_length=1, max_length=64)
```

Register only `POST /v1/code-activations`, keep the sanitized Pydantic handler and opaque 503 handler, and apply both per-IP and per-`IP:device_hash` rate limits before redemption. Map service errors to `{"detail":{"code":"LIC-xxx"}}` with 400/409/422.

Change `app_from_env()` to instantiate only `Settings`, `Database`, and `LicenseService`. Remove `requests` from server requirements if no remaining server module imports it.

- [ ] **Step 6: Delete provider runtime and run server tests**

Delete the three Mianbaoduo files listed above. In `license_server/database.py`, remove the
`Checkout`/`Payway` import and the unused legacy order repository methods while preserving the
legacy `orders` and `licenses` DDL exactly for rollback/audit. Then run:

```bash
python -m pytest license_server/tests -q
```

Expected: all server tests pass; test collection contains no Mianbaoduo test module.

- [ ] **Step 7: Commit**

```bash
git add -A license_server
git commit -m "feat: expose activation code redemption service"
```

## Task 5: One-shot client activation

**Files:**
- Rewrite: `publish/licensing/api.py`
- Rewrite: `publish/licensing/activation.py`
- Modify: `publish/licensing/__init__.py`
- Rewrite: `tests/test_license_activation.py`
- Modify: `tests/test_license_cli.py`

- [ ] **Step 1: Write failing API and activation tests**

Replace session/polling tests with:

```python
def test_license_api_posts_code_activation() -> None:
    session = MockSession(Response(200, {"status": "licensed", "license": LICENSE_DOC}))
    result = LicenseApi("https://license.test///", session=session).activate_code(
        "a" * 64, "0.8.0", "OPUB0-ABCDE-FGHJK-MNPQR-STVWX-YZ234-56789"
    )
    assert result["status"] == "licensed"
    assert session.calls[0].url == "https://license.test/v1/code-activations"
    assert session.calls[0].json["activation_code"].startswith("OPUB0-")


@pytest.mark.parametrize(
    ("status", "body", "code"),
    [(400, {"detail": {"code": "LIC-013"}}, "LIC-013"),
     (409, {"detail": {"code": "LIC-014"}}, "LIC-014"),
     (422, {"detail": {"code": "LIC-015"}}, "LIC-015")],
)
def test_license_api_preserves_allowlisted_service_error(status, body, code):
    with pytest.raises(ActivationServiceError) as exc_info:
        LicenseApi("https://license.test", session=MockSession(Response(status, body))).activate_code(
            "a" * 64, "0.8.0", VALID_CODE
        )
    assert exc_info.value.code == code


def test_activate_verifies_then_writes_license(tmp_path: Path) -> None:
    api = Mock(activate_code=Mock(return_value={"status": "licensed", "license": LICENSE_DOC}))
    verify = Mock()
    assert activate(VALID_CODE, DEVICE_HASH, api, tmp_path, verify, client_version="0.8.0") == 0
    verify.assert_called_once_with(LICENSE_DOC, DEVICE_HASH)
    assert json.loads((tmp_path / "license.json").read_text()) == LICENSE_DOC
```

Add tests proving an invalid response or failed verification never writes `license.json`, no `activation.json`, QR, or HTML file is created, and no sleep/poll method is called.

- [ ] **Step 2: Run and verify failures**

```bash
python -m pytest tests/test_license_activation.py tests/test_license_cli.py -q
```

Expected: failures because the client still creates and polls payment sessions.

- [ ] **Step 3: Implement the safe client API**

`LicenseApi.activate_code()` must send one POST. `_json()` may preserve only `LIC-013`, `LIC-014`, and `LIC-015` from the exact nested error shape; all transport, timeout, malformed JSON, unexpected status, and other remote values map to `LIC-011`. Never include response/request text in exceptions.

Use:

```python
class ActivationServiceError(RuntimeError):
    def __init__(self, code: str = "LIC-011") -> None:
        super().__init__("activation service unavailable")
        self.code = code
```

- [ ] **Step 4: Replace activation polling with one-shot redemption**

Reduce `activate()` to: normalize code, call `api.activate_code`, require exact `status == "licensed"` and a dictionary license, verify it, then use `atomic_write_json(data_path / "license.json", license_doc)`. Map local format failures to `ActivationError("LIC-013")`. Remove QR, temporary HTML, saved sessions, polling, nonce, sleep, and timeout code.

Update `run_activation(code)` to pass the installed package version and preserve the explicit public code carried by `ActivationServiceError`.

- [ ] **Step 5: Run focused tests**

```bash
python -m pytest tests/test_license_activation.py tests/test_license_cli.py tests/test_license_storage.py tests/test_license_verifier.py -q
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit**

```bash
git add publish/licensing/api.py publish/licensing/activation.py publish/licensing/__init__.py tests/test_license_activation.py tests/test_license_cli.py
git commit -m "feat: activate opub with one-time codes"
```

## Task 6: CLI, Agent contract, and user-facing documentation

**Files:**
- Modify: `publish/orchestrator.py`
- Modify: `AGENT.md`
- Modify: `README.md`
- Modify: `docs/CLI.md`
- Modify: `skills/opub-cli/SKILL.md`
- Modify: `tests/test_license_cli.py`
- Modify: `tests/test_publish_cli.py`

- [ ] **Step 1: Write failing parser and behavior tests**

Add exact CLI contract tests:

```python
def test_parser_exposes_code_activation_and_removes_payment_method() -> None:
    help_text = build_parser().format_help()
    assert "--activate" in help_text
    assert "--code" in help_text
    assert "--pay-with" not in help_text


def test_code_requires_activate() -> None:
    with pytest.raises(SystemExit):
        main(["--code", VALID_CODE])


def test_explicit_code_activates_without_prompt_or_purchase_page() -> None:
    with patch("publish.orchestrator.run_activation", return_value=0) as run, patch(
        "publish.orchestrator.webbrowser.open"
    ) as open_page:
        assert main(["--activate", "--code", VALID_CODE]) == 0
    run.assert_called_once_with(VALID_CODE)
    open_page.assert_not_called()


def test_noninteractive_activate_opens_purchase_page_and_exits_13() -> None:
    with patch("sys.stdin.isatty", return_value=False), patch(
        "publish.orchestrator.webbrowser.open", return_value=True
    ) as open_page:
        assert main(["--activate"]) == 13
    open_page.assert_called_once_with(LICENSE_PURCHASE_URL)
```

Keep tests asserting help/version/status bypass the license gate and unlicensed publishing stops before Cookie, asset, dependency, browser, or network access.

- [ ] **Step 2: Run and verify failures**

```bash
python -m pytest tests/test_license_cli.py tests/test_publish_cli.py -q
```

Expected: failures because `--pay-with` still exists and `--code` does not.

- [ ] **Step 3: Implement CLI behavior**

Add `--code` to the parser and reject it unless `--activate` is present. Remove `--pay-with` completely.

When `--activate --code` is used, call `run_activation(code)` without opening a page. When interactive `--activate` has no code, open `LICENSE_PURCHASE_URL`, prompt `请输入爱发电发放的激活码: `, and redeem non-empty input. When non-interactive `--activate` has no code, open the purchase URL once, print `LIC-001` with the suggestion `付款取得激活码后运行 opub --activate --code OPUB0-你的激活码`, and exit 13.

Never print the code and never place it in exceptions.

- [ ] **Step 4: Update all public documentation**

Use one consistent contract everywhere:

```text
opub --license-status
opub --activate
opub --activate --code OPUB0-ABCDE-FGHJK-MNPQR-STVWX-YZ234-56789
```

State that payment is on the Afdian item, the delivered code binds one device, the license covers `0.x`, the installed version continues offline permanently, future major versions are separate purchases, and payment method is selected on Afdian. Remove Mianbaoduo, payment polling, `--pay-with`, `LIC-010`, and `LIC-012` guidance. Add `LIC-013` through `LIC-015`.

The Agent contract must retain confirmed publishing inputs across activation and continue the same publish automatically after a successful code redemption.

- [ ] **Step 5: Run documentation contract tests**

```bash
python -m pytest tests/test_license_cli.py tests/test_publish_cli.py -q
```

Expected: all selected tests pass and no public contract test finds `--pay-with`.

- [ ] **Step 6: Commit**

```bash
git add publish/orchestrator.py AGENT.md README.md docs/CLI.md skills/opub-cli/SKILL.md tests/test_license_cli.py tests/test_publish_cli.py
git commit -m "docs: switch agent activation to afdian codes"
```

## Task 7: Key generation, packaging, and version bump

**Files:**
- Modify: `license_server/keygen.py`
- Modify: `license_server/tests/test_signing.py`
- Modify: `pyproject.toml`
- Modify: `skills/opub-cli/SKILL.md`
- Modify: `tests/test_package_build.py`
- Modify: `tests/test_python_compatibility.py`
- Modify: `MANIFEST.in`

- [ ] **Step 1: Write failing deployment-generation and package tests**

Update the key-generation test to pass the purchase URL and expect all public constants:

```python
assert keygen.generate(
    private_file=private_file,
    client_file=client_file,
    base_url="https://example.com/license/",
    purchase_url="https://afdian.com/item/test-item",
    key_id="kid-1",
) == 0
assert "LICENSE_PURCHASE_URL='https://afdian.com/item/test-item'" in client_file.read_text()
assert "LICENSE_PRODUCT_ID='opub-major-0'" in client_file.read_text()
```

Update `CLIENT_LICENSE_FILES` in `tests/test_package_build.py` to include `publish/licensing/codes.py`; extend private filename/payload checks to reject `*codes*.txt`; remove `OPUB_MBD_APP_KEY` from `PRIVATE_KEY_ENV_NAMES`. Change version assertions to `0.8.0` in both `pyproject.toml` and the skill. Add `publish/licensing/codes.py` to the Python 3.9 compile/import list in `tests/test_python_compatibility.py`.

- [ ] **Step 2: Run and verify failures**

```bash
python -m pytest license_server/tests/test_signing.py tests/test_package_build.py tests/test_python_compatibility.py -q
```

Expected: failures because keygen lacks the purchase URL, the new client module is not in package expectations, and version remains `0.7.0`.

- [ ] **Step 3: Implement safe deployment generation and packaging**

Add required `--purchase-url` to `license_server.keygen`, validate it as HTTPS, and emit `LICENSE_API_BASE_URL`, `LICENSE_PURCHASE_URL`, `LICENSE_PRODUCT_ID`, then `TRUSTED_PUBLIC_KEYS`. Preserve exclusive private-file creation and atomic client-file replacement.

Remove `qrcode` from `pyproject.toml`, because no QR is generated. Bump the package and skill to `0.8.0`. Explicitly prune activation inventories in `MANIFEST.in`:

```text
global-exclude *codes*.txt
```

- [ ] **Step 4: Run build and compatibility tests**

```bash
python -m pytest license_server/tests/test_signing.py tests/test_package_build.py tests/test_python_compatibility.py -q
```

Expected: all selected tests pass; wheel/sdist contain the client code parser but no server source, SQLite file, secrets, or activation inventory.

- [ ] **Step 5: Commit**

```bash
git add license_server/keygen.py license_server/tests/test_signing.py pyproject.toml skills/opub-cli/SKILL.md tests/test_package_build.py tests/test_python_compatibility.py MANIFEST.in
git commit -m "chore: prepare activation code client release"
```

## Task 8: End-to-end flow and deployment runbook

**Files:**
- Rewrite: `tests/test_license_e2e.py`
- Rewrite: `license_server/README.md`
- Modify: `license_server/deploy/opub-license.service`
- Modify: `license_server/deploy/Caddyfile.example`

- [ ] **Step 1: Write the failing end-to-end test**

Build a real temporary FastAPI app and database, import one known code hash, bridge the public `LicenseApi` to `TestClient`, and exercise the actual public activation function:

```python
def test_code_activation_installs_device_bound_offline_license(tmp_path: Path) -> None:
    app, database, trusted_keys = build_real_app(tmp_path)
    import_plain_code(database, VALID_CODE)
    api = LicenseApi("https://license.test", session=TestClientSession(TestClient(app)))
    client_dir = tmp_path / "client"

    assert activate(VALID_CODE, DEVICE_HASH, api, client_dir, verifier(trusted_keys), client_version="0.8.0") == 0
    installed = json.loads((client_dir / "license.json").read_text())
    verify_license(installed, DEVICE_HASH, trusted_keys)
    assert require_valid_license(client_dir, trusted_keys) == (True, None)
    assert database.code_stats() == {"available": 0, "redeemed": 1, "total": 1}

    with pytest.raises(ActivationServiceError) as exc_info:
        api.activate_code(OTHER_DEVICE_HASH, "0.8.0", VALID_CODE)
    assert exc_info.value.code == "LIC-014"
```

Retain an end-to-end test proving unlicensed CLI publication exits 13 before Cookie, asset, dependency, runtime, and network calls.

- [ ] **Step 2: Run and verify failure**

```bash
python -m pytest tests/test_license_e2e.py -q
```

Expected: failure while the test still targets payment sessions or before the new test helpers exist.

- [ ] **Step 3: Complete the E2E test and deployment docs**

Rewrite `license_server/README.md` to document exactly four environment values, one public route, inventory generation/statistics, uploading plaintext inventory to Afdian, backup/restore, and this smoke test:

```bash
curl -sS -o /dev/null -w '%{http_code}\n' \
  -X POST https://dachitech.xyz/license/v1/code-activations \
  -H 'content-type: application/json' \
  --data '{}'
```

Expected HTTP status is `422`, proving TLS, proxy, route, and request validation are active without transmitting an activation code.

Confirm the systemd unit still uses one worker and the reverse-proxy path preserves `/license/v1/code-activations`. Remove all provider/webhook setup sections. Do not generate production codes in this task.

- [ ] **Step 4: Run E2E and server suites**

```bash
python -m pytest tests/test_license_e2e.py license_server/tests -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/test_license_e2e.py license_server/README.md license_server/deploy/opub-license.service license_server/deploy/Caddyfile.example
git commit -m "test: verify activation code license flow end to end"
```

## Task 9: Full verification and local test inventory

**Files:**
- Modify only if verification exposes a defect in files already listed above.
- Generate ignored test artifact: `.secrets/opub-afdian-test-codes.txt`

- [ ] **Step 1: Run formatting and stale-contract scans**

```bash
git diff --check
rg -n "Mianbaoduo|mianbaoduo|OPUB_MBD|--pay-with|LIC-010|LIC-012" publish license_server README.md AGENT.md docs/CLI.md skills/opub-cli/SKILL.md tests
```

Expected: `git diff --check` is silent; the scan returns no active runtime, public documentation, or test references. Historical design/plan documents are intentionally outside the scan.

- [ ] **Step 2: Run the full supported test suites**

```bash
python -m pytest -q -k 'not test_uploading_video_raises_on_timeout and not test_interactive_login_opens_new_console_when_stdio_is_redirected'
python3.9 -m pytest tests/test_python_compatibility.py tests/test_license_activation.py tests/test_license_cli.py tests/test_license_e2e.py license_server/tests -q
```

Expected: all selected tests pass. The two exclusions are the previously documented unrelated environment-sensitive tests.

- [ ] **Step 3: Build and inspect release artifacts**

```bash
python -m build
python -m twine check dist/opub-0.8.0*
```

Expected: wheel and sdist build successfully and Twine reports `PASSED` for both.

- [ ] **Step 4: Generate a local test inventory**

Use a disposable database, not the production path:

```bash
OPUB_LICENSE_DB_PATH=.secrets/opub-code-test.sqlite3 \
python -m license_server.codes generate \
  --count 3 \
  --output .secrets/opub-afdian-test-codes.txt
```

Expected: exactly three codes are written with file mode `0600`; `stats` reports three available. Do not paste the codes into chat, logs, Git, or the final response.

- [ ] **Step 5: Exercise one local redemption without real payment**

Run this against the disposable inventory without printing the code or private key:

```bash
python - <<'PY'
from pathlib import Path

from license_server.config import Settings
from license_server.database import Database
from license_server.service import ActivationCodeUsed, LicenseService

database_path = Path(".secrets/opub-code-test.sqlite3")
private_key = Path(".secrets/opub-license-ed25519.key").read_text(encoding="utf-8").strip()
code = Path(".secrets/opub-afdian-test-codes.txt").read_text(encoding="utf-8").splitlines()[0]
settings = Settings(
    public_base_url="https://dachitech.xyz/license",
    license_private_key=private_key,
    license_key_id="opub-license-2026-09",
    database_path=database_path,
)
database = Database(database_path)
service = LicenseService(settings, database)
first = service.redeem(code, "a" * 64, "0.8.0")
second = service.redeem(code, "a" * 64, "0.8.0")
assert first == second
try:
    service.redeem(code, "b" * 64, "0.8.0")
except ActivationCodeUsed:
    pass
else:
    raise AssertionError("another device unexpectedly redeemed the same code")
assert database.code_stats() == {"available": 2, "redeemed": 1, "total": 3}
print("local activation-code redemption: PASS")
PY
```

Expected: `local activation-code redemption: PASS` and no secret values in output.

- [ ] **Step 6: Review repository state and commit verification fixes**

```bash
git status --short
git log --oneline -10
```

Expected: only the user's pre-existing unrelated untracked files and ignored `.secrets/` artifacts remain. If Step 1–5 required corrections, commit only the affected implementation files from this plan with:

```bash
git add publish/licensing license_server AGENT.md README.md docs/CLI.md skills/opub-cli/SKILL.md pyproject.toml MANIFEST.in tests/test_activation_codes.py tests/test_license_activation.py tests/test_license_cli.py tests/test_license_e2e.py tests/test_license_verifier.py tests/test_package_build.py tests/test_publish_cli.py tests/test_python_compatibility.py
git commit -m "fix: complete activation code release checks"
```

Do not push, publish to PyPI, deploy to Alibaba Cloud, generate production inventory, or upload codes to Afdian in this plan; each is an external release action requiring a separate explicit instruction after local verification.
