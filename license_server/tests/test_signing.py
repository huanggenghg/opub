from __future__ import annotations

import base64
import importlib.util
import stat
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def _load_module(module_path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_canonical_json_sorts_keys_and_escapes_unicode() -> None:
    from license_server.signing import canonical_json

    assert canonical_json({"z": 1, "a": "中"}) == b'{"a":"\\u4e2d","z":1}'


def test_sign_license_creates_verifiable_license_payload() -> None:
    from license_server.signing import canonical_json, sign_license

    private_key_b64 = base64.b64encode(bytes(range(32))).decode("ascii")
    issued_at = "2026-09-05T00:00:00Z"
    signed = sign_license(
        private_key_b64=private_key_b64,
        key_id="kid-1",
        license_id="lic-1",
        device_hash="device-hash-1",
        issued_at=issued_at,
    )

    assert signed["payload"] == {
        "schema_version": 1,
        "key_id": "kid-1",
        "license_id": "lic-1",
        "product": "opub-lifetime-v1",
        "device_hash": "device-hash-1",
        "issued_at": issued_at,
    }
    assert isinstance(signed["payload"]["issued_at"], str)

    payload_bytes = canonical_json(signed["payload"])
    signature = base64.b64decode(signed["signature"])
    public_key = Ed25519PrivateKey.from_private_bytes(bytes(range(32))).public_key()
    public_key.verify(signature, payload_bytes)


def test_sign_license_rejects_tampered_payload() -> None:
    from license_server.signing import canonical_json, sign_license

    private_key_b64 = base64.b64encode(bytes(range(32))).decode("ascii")
    issued_at = "2026-09-05T00:00:00Z"
    signed = sign_license(
        private_key_b64=private_key_b64,
        key_id="kid-1",
        license_id="lic-1",
        device_hash="device-hash-1",
        issued_at=issued_at,
    )

    tampered_payload = dict(signed["payload"])
    tampered_payload["license_id"] = "lic-2"
    signature = base64.b64decode(signed["signature"])
    public_key = Ed25519PrivateKey.from_private_bytes(bytes(range(32))).public_key()

    with pytest.raises(InvalidSignature):
        public_key.verify(signature, canonical_json(tampered_payload))


def test_keygen_creates_private_seed_and_public_client_module(tmp_path: Path) -> None:
    from license_server import keygen

    private_file = tmp_path / "keys" / "license.private"
    client_file = tmp_path / "client" / "license_client.py"

    assert keygen.generate(
        private_file=private_file,
        client_file=client_file,
        base_url="https://example.com/license/",
        key_id="kid-1",
    ) == 0

    private_bytes = private_file.read_bytes()
    assert stat.S_IMODE(private_file.stat().st_mode) == 0o600
    assert private_bytes.endswith(b"\n")
    private_seed = base64.b64decode(private_bytes.strip(), validate=True)
    assert len(private_seed) == 32

    client_module_text = client_file.read_text(encoding="utf-8")
    assert client_module_text == (
        "LICENSE_API_BASE_URL='https://example.com/license'\n"
        "TRUSTED_PUBLIC_KEYS={'kid-1': '"
        + base64.b64encode(
            Ed25519PrivateKey.from_private_bytes(private_seed)
            .public_key()
            .public_bytes(Encoding.Raw, PublicFormat.Raw)
        ).decode("ascii")
        + "'}\n"
    )
    assert "PRIVATE" not in client_module_text

    client_module = _load_module(client_file, "generated_license_client")
    public_key_bytes = base64.b64decode(
        client_module.TRUSTED_PUBLIC_KEYS["kid-1"], validate=True
    )
    assert len(public_key_bytes) == 32

    from license_server.signing import canonical_json, sign_license

    signed = sign_license(
        private_key_b64=base64.b64encode(private_seed).decode("ascii"),
        key_id="kid-1",
        license_id="lic-1",
        device_hash="device-hash-1",
        issued_at="2026-09-05T00:00:00Z",
    )

    public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
    public_key.verify(
        base64.b64decode(signed["signature"]),
        canonical_json(signed["payload"]),
    )


def test_keygen_refuses_existing_private_before_touching_client(tmp_path: Path) -> None:
    from license_server import keygen

    private_file = tmp_path / "license.private"
    client_file = tmp_path / "client" / "license_client.py"
    private_file.parent.mkdir(parents=True, exist_ok=True)
    private_file.write_text("already-there\n", encoding="utf-8")
    client_file.parent.mkdir(parents=True, exist_ok=True)
    client_file.write_text("sentinel = True\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        keygen.generate(
            private_file=private_file,
            client_file=client_file,
            base_url="https://example.com/license",
            key_id="kid-1",
        )

    assert client_file.read_text(encoding="utf-8") == "sentinel = True\n"


def test_keygen_does_not_use_fchmod(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from license_server import keygen

    def _boom(*args, **kwargs):  # noqa: ANN001, ANN002
        raise AssertionError("os.fchmod must not be used")

    monkeypatch.setattr(keygen.os, "fchmod", _boom)

    assert (
        keygen.generate(
            private_file=tmp_path / "license.private",
            client_file=tmp_path / "license_client.py",
            base_url="https://example.com/license",
            key_id="kid-1",
        )
        == 0
    )


def _files_in(root: Path) -> set[Path]:
    return {path.relative_to(root) for path in root.rglob("*") if path.is_file()}


def _assert_no_temp_files(root: Path) -> None:
    temp_files = [path for path in root.rglob("*") if path.is_file() and path.name.startswith(".")]
    assert temp_files == []


def _assert_retryable_atomic_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    fail_attr: str,
    expected_exception: type[BaseException],
) -> None:
    from license_server import keygen

    private_file = tmp_path / "keys" / "license.private"
    client_file = tmp_path / "client" / "license_client.py"
    client_file.parent.mkdir(parents=True, exist_ok=True)
    client_file.write_text("sentinel = True\n", encoding="utf-8")

    real_func = getattr(keygen.os, fail_attr)
    calls = {"count": 0}

    def _fail_once(*args, **kwargs):  # noqa: ANN001, ANN002
        calls["count"] += 1
        if calls["count"] == 1:
            raise expected_exception(f"{fail_attr} boom")
        return real_func(*args, **kwargs)

    monkeypatch.setattr(keygen.os, fail_attr, _fail_once)

    with pytest.raises(expected_exception):
        keygen.generate(
            private_file=private_file,
            client_file=client_file,
            base_url="https://example.com:8443/license/",
            key_id="kid-1",
        )

    assert not private_file.exists()
    assert client_file.read_text(encoding="utf-8") == "sentinel = True\n"
    assert _files_in(tmp_path) == {client_file.relative_to(tmp_path)}
    _assert_no_temp_files(tmp_path)

    assert (
        keygen.generate(
            private_file=private_file,
            client_file=client_file,
            base_url="https://example.com:8443/license/",
            key_id="kid-1",
        )
        == 0
    )
    assert private_file.exists()
    assert client_file.read_text(encoding="utf-8").startswith("LICENSE_API_BASE_URL='https://example.com:8443/license'")
    _assert_no_temp_files(tmp_path)


def test_keygen_recovers_after_private_write_fsync_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from license_server import keygen

    _assert_retryable_atomic_failure(
        monkeypatch,
        tmp_path,
        fail_attr="fsync",
        expected_exception=OSError,
    )


def test_keygen_recovers_after_private_publication_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from license_server import keygen

    _assert_retryable_atomic_failure(
        monkeypatch,
        tmp_path,
        fail_attr="link",
        expected_exception=FileExistsError,
    )


def test_keygen_recovers_after_client_write_or_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from license_server import keygen

    private_file = tmp_path / "keys" / "license.private"
    client_file = tmp_path / "client" / "license_client.py"
    client_file.parent.mkdir(parents=True, exist_ok=True)
    client_file.write_text("sentinel = True\n", encoding="utf-8")

    real_replace = keygen.os.replace
    calls = {"count": 0}

    def _fail_once(src: str, dst: str) -> None:
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("replace boom")
        real_replace(src, dst)

    monkeypatch.setattr(keygen.os, "replace", _fail_once)

    with pytest.raises(OSError):
        keygen.generate(
            private_file=private_file,
            client_file=client_file,
            base_url="https://example.com:8443/license/",
            key_id="kid-1",
        )

    assert not private_file.exists()
    assert client_file.read_text(encoding="utf-8") == "sentinel = True\n"
    _assert_no_temp_files(tmp_path)

    assert (
        keygen.generate(
            private_file=private_file,
            client_file=client_file,
            base_url="https://example.com:8443/license/",
            key_id="kid-1",
        )
        == 0
    )
    assert private_file.exists()
    assert client_file.read_text(encoding="utf-8").startswith("LICENSE_API_BASE_URL='https://example.com:8443/license'")
    _assert_no_temp_files(tmp_path)


@pytest.mark.parametrize(
    "base_url",
    [
        "http://example.com/license",
        "https://",
        "https://user:pass@example.com/license",
        "https://example.com/license?x=1",
        "https://example.com/license#x",
    ],
)
def test_keygen_rejects_invalid_base_url(base_url: str, tmp_path: Path) -> None:
    from license_server import keygen

    with pytest.raises(ValueError):
        keygen.generate(
            private_file=tmp_path / "license.private",
            client_file=tmp_path / "license_client.py",
            base_url=base_url,
            key_id="kid-1",
        )


@pytest.mark.parametrize(
    "base_url",
    [
        "https://example.com:443/license",
        "https://127.0.0.1:8443/license",
        "https://[::1]:9443/license",
    ],
)
def test_keygen_accepts_valid_explicit_ports_and_paths(base_url: str, tmp_path: Path) -> None:
    from license_server import keygen

    assert (
        keygen.generate(
            private_file=tmp_path / "license.private",
            client_file=tmp_path / "license_client.py",
            base_url=base_url,
            key_id="kid-1",
        )
        == 0
    )


@pytest.mark.parametrize(
    "base_url",
    [
        "https://example.com:bad/license",
        "https://example.com:99999/license",
        "https://exa mple.com/license",
        "https://exa\nmple.com/license",
        "https://@example.com/license",
    ],
)
def test_keygen_rejects_malformed_host_and_ports(base_url: str, tmp_path: Path) -> None:
    from license_server import keygen

    with pytest.raises(ValueError):
        keygen.generate(
            private_file=tmp_path / "license.private",
            client_file=tmp_path / "license_client.py",
            base_url=base_url,
            key_id="kid-1",
        )


@pytest.mark.parametrize("key_id", ["", "   "])
def test_keygen_rejects_empty_key_id(key_id: str, tmp_path: Path) -> None:
    from license_server import keygen

    with pytest.raises(ValueError):
        keygen.generate(
            private_file=tmp_path / "license.private",
            client_file=tmp_path / "license_client.py",
            base_url="https://example.com/license",
            key_id=key_id,
        )


def test_keygen_rejects_same_private_and_client_path_without_touching_file(
    tmp_path: Path,
) -> None:
    from license_server import keygen

    target = tmp_path / "license_client.py"
    target.write_text("sentinel = True\n", encoding="utf-8")
    before_mode = stat.S_IMODE(target.stat().st_mode)

    with pytest.raises(ValueError):
        keygen.generate(
            private_file=target,
            client_file=target,
            base_url="https://example.com/license",
            key_id="kid-1",
        )

    assert target.read_text(encoding="utf-8") == "sentinel = True\n"
    assert stat.S_IMODE(target.stat().st_mode) == before_mode


def test_keygen_main_returns_zero(tmp_path: Path) -> None:
    from license_server import keygen

    private_file = tmp_path / "license.private"
    client_file = tmp_path / "license_client.py"
    argv = [
        "keygen",
        "--private-file",
        str(private_file),
        "--client-file",
        str(client_file),
        "--base-url",
        "https://example.com/license/",
        "--key-id",
        "kid-1",
    ]

    assert keygen.main(argv[1:]) == 0
