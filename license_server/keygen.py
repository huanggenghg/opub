from __future__ import annotations

import argparse
import base64
import ipaddress
import os
import secrets
import tempfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def _normalize_base_url(base_url: str) -> str:
    trimmed = base_url.strip()
    if any(ord(char) < 33 or ord(char) == 127 for char in trimmed):
        raise ValueError("base_url must be a valid https URL")

    parts = urlsplit(trimmed)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.query
        or parts.fragment
    ):
        raise ValueError("base_url must be a valid https URL")

    try:
        _ = parts.port
    except ValueError as exc:
        raise ValueError("base_url must be a valid https URL") from exc

    if "@" in parts.netloc or parts.username is not None or parts.password is not None:
        raise ValueError("base_url must be a valid https URL")

    _validate_hostname(parts.hostname)
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _validate_hostname(hostname: str) -> None:
    if any(ord(char) < 33 or ord(char) == 127 for char in hostname):
        raise ValueError("base_url must be a valid https URL")

    try:
        hostname.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("base_url must be a valid https URL") from exc

    try:
        ipaddress.ip_address(hostname)
        return
    except ValueError:
        pass

    if hostname == "localhost":
        return

    if hostname.endswith("."):
        raise ValueError("base_url must be a valid https URL")

    labels = hostname.split(".")
    if not labels or any(not label for label in labels):
        raise ValueError("base_url must be a valid https URL")

    for label in labels:
        if len(label) > 63 or label[0] == "-" or label[-1] == "-":
            raise ValueError("base_url must be a valid https URL")
        if not all(char.isalnum() or char == "-" for char in label):
            raise ValueError("base_url must be a valid https URL")


def _validate_key_id(key_id: str) -> str:
    normalized = key_id.strip()
    if not normalized:
        raise ValueError("key_id must be non-empty")
    return normalized


def _write_private_seed(private_file: Path, private_seed: bytes) -> None:
    private_file.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        dir=str(private_file.parent),
        prefix=f".{private_file.name}.",
    )
    try:
        os.chmod(temp_path, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(base64.b64encode(private_seed))
            handle.write(b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temp_path, private_file)
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass


def _write_client_module(client_file: Path, base_url: str, key_id: str, public_key_b64: str) -> None:
    client_file.parent.mkdir(parents=True, exist_ok=True)
    content = (
        f"LICENSE_API_BASE_URL={base_url!r}\n"
        f"TRUSTED_PUBLIC_KEYS={{{key_id!r}: {public_key_b64!r}}}\n"
    )
    fd, temp_path = tempfile.mkstemp(
        dir=str(client_file.parent),
        prefix=f".{client_file.name}.",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, client_file)
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass


def generate(
    *,
    private_file: Path,
    client_file: Path,
    base_url: str,
    key_id: str,
) -> int:
    if private_file.resolve(strict=False) == client_file.resolve(strict=False):
        raise ValueError("private_file and client_file must be different paths")

    normalized_base_url = _normalize_base_url(base_url)
    normalized_key_id = _validate_key_id(key_id)
    private_seed = secrets.token_bytes(32)
    public_key = Ed25519PrivateKey.from_private_bytes(private_seed).public_key()
    public_key_b64 = base64.b64encode(
        public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    ).decode("ascii")

    private_published = False
    try:
        _write_private_seed(private_file, private_seed)
        private_published = True
        _write_client_module(client_file, normalized_base_url, normalized_key_id, public_key_b64)
    except Exception:
        if private_published:
            try:
                private_file.unlink()
            except FileNotFoundError:
                pass
        raise

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="keygen")
    parser.add_argument("--private-file", type=Path, required=True)
    parser.add_argument("--client-file", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--key-id", required=True)
    args = parser.parse_args(argv)

    return generate(
        private_file=args.private_file,
        client_file=args.client_file,
        base_url=args.base_url,
        key_id=args.key_id,
    )


if __name__ == "__main__":
    raise SystemExit(main())
