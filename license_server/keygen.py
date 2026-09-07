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


def _normalize_https_url(value: str, field_name: str) -> str:
    trimmed = value.strip()
    if value != trimmed or any(ord(char) < 33 or ord(char) == 127 for char in value):
        raise ValueError(f"{field_name} must be a valid https URL")

    try:
        parts = urlsplit(trimmed)
    except ValueError:
        raise ValueError(f"{field_name} must be a valid https URL") from None
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.netloc.endswith(":")
        or parts.query
        or parts.fragment
    ):
        raise ValueError(f"{field_name} must be a valid https URL")

    try:
        _ = parts.port
    except ValueError:
        raise ValueError(f"{field_name} must be a valid https URL") from None

    if "@" in parts.netloc or parts.username is not None or parts.password is not None:
        raise ValueError(f"{field_name} must be a valid https URL")

    _validate_hostname(parts.hostname, field_name)
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _normalize_base_url(base_url: str) -> str:
    return _normalize_https_url(base_url, "base_url")


def _normalize_purchase_url(purchase_url: str) -> str:
    return _normalize_https_url(purchase_url, "purchase_url")


def _validate_hostname(hostname: str, field_name: str) -> None:
    if any(ord(char) < 33 or ord(char) == 127 for char in hostname):
        raise ValueError(f"{field_name} must be a valid https URL")

    try:
        hostname.encode("ascii")
    except UnicodeEncodeError:
        raise ValueError(f"{field_name} must be a valid https URL") from None

    try:
        ipaddress.ip_address(hostname)
        return
    except ValueError:
        pass

    if hostname == "localhost":
        return

    if hostname.endswith("."):
        raise ValueError(f"{field_name} must be a valid https URL")

    labels = hostname.split(".")
    if not labels or any(not label for label in labels):
        raise ValueError(f"{field_name} must be a valid https URL")

    for label in labels:
        if len(label) > 63 or label[0] == "-" or label[-1] == "-":
            raise ValueError(f"{field_name} must be a valid https URL")
        if not all(char.isalnum() or char == "-" for char in label):
            raise ValueError(f"{field_name} must be a valid https URL")


def _validate_key_id(key_id: str) -> str:
    normalized = key_id.strip()
    if not normalized:
        raise ValueError("key_id must be non-empty")
    return normalized


def _paths_alias(private_file: Path, client_file: Path) -> bool:
    private_resolved = private_file.resolve(strict=False)
    client_resolved = client_file.resolve(strict=False)
    if str(private_resolved).casefold() == str(client_resolved).casefold():
        return True

    try:
        return os.path.samefile(private_file, client_file)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise ValueError("private_file and client_file must be different paths") from exc


def _write_private_seed(
    private_file: Path,
    private_seed: bytes,
    temp_paths: list[Path],
) -> None:
    private_file.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        dir=str(private_file.parent),
        prefix=f".{private_file.name}.",
    )
    temp_path = Path(temp_path)
    temp_paths.append(temp_path)
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


def _write_client_module(
    private_file: Path,
    client_file: Path,
    base_url: str,
    purchase_url: str,
    key_id: str,
    public_key_b64: str,
    temp_paths: list[Path],
) -> None:
    client_file.parent.mkdir(parents=True, exist_ok=True)
    content = (
        f"LICENSE_API_BASE_URL={base_url!r}\n"
        f"LICENSE_PURCHASE_URL={purchase_url!r}\n"
        "LICENSE_PRODUCT_ID='opub-major-0'\n"
        f"TRUSTED_PUBLIC_KEYS={{{key_id!r}: {public_key_b64!r}}}\n"
    )
    fd, temp_path = tempfile.mkstemp(
        dir=str(client_file.parent),
        prefix=f".{client_file.name}.",
    )
    temp_path = Path(temp_path)
    temp_paths.append(temp_path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if _paths_alias(private_file, client_file):
            raise ValueError("private_file and client_file must be different paths")
        os.replace(temp_path, client_file)
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def _unlink_if_exists(path: Path) -> None:
    if not os.path.lexists(path):
        return
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def _cleanup_transaction(
    *,
    private_file: Path,
    private_published: bool,
    temp_paths: list[Path],
) -> BaseException | None:
    paths = ([private_file] if private_published else []) + list(temp_paths)
    failures: list[tuple[Path, BaseException]] = []
    for path in paths:
        try:
            _unlink_if_exists(path)
        except BaseException as exc:  # noqa: BLE001 - cleanup must continue independently
            failures.append((path, exc))

    # A transient unlink failure must not strand a transaction's files. Retry
    # each failed path once after all paths have received their first attempt.
    remaining_failures: list[BaseException] = []
    for path, _ in failures:
        try:
            _unlink_if_exists(path)
        except BaseException as exc:  # noqa: BLE001 - preserve cleanup progress
            remaining_failures.append(exc)
    return remaining_failures[0] if remaining_failures else None


def _unlink_private_temp_or_raise(temp_path: Path) -> None:
    try:
        _unlink_if_exists(temp_path)
    except BaseException as exc:  # noqa: BLE001 - expose cleanup as generation failure
        raise RuntimeError("license key generation cleanup failed") from exc


def generate(
    *,
    private_file: Path,
    client_file: Path,
    base_url: str,
    purchase_url: str,
    key_id: str,
) -> int:
    if _paths_alias(private_file, client_file):
        raise ValueError("private_file and client_file must be different paths")

    normalized_base_url = _normalize_base_url(base_url)
    normalized_purchase_url = _normalize_purchase_url(purchase_url)
    normalized_key_id = _validate_key_id(key_id)
    private_seed = secrets.token_bytes(32)
    public_key = Ed25519PrivateKey.from_private_bytes(private_seed).public_key()
    public_key_b64 = base64.b64encode(
        public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    ).decode("ascii")

    private_published = False
    temp_paths: list[Path] = []
    try:
        _write_private_seed(private_file, private_seed, temp_paths)
        private_published = True
        _unlink_private_temp_or_raise(temp_paths[0])
        temp_paths.pop(0)
        _write_client_module(
            private_file,
            client_file,
            normalized_base_url,
            normalized_purchase_url,
            normalized_key_id,
            public_key_b64,
            temp_paths,
        )
    except BaseException:
        _cleanup_transaction(
            private_file=private_file,
            private_published=private_published,
            temp_paths=temp_paths,
        )
        raise

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="keygen")
    parser.add_argument("--private-file", type=Path, required=True)
    parser.add_argument("--client-file", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--purchase-url", required=True)
    parser.add_argument("--key-id", required=True)
    args = parser.parse_args(argv)

    return generate(
        private_file=args.private_file,
        client_file=args.client_file,
        base_url=args.base_url,
        purchase_url=args.purchase_url,
        key_id=args.key_id,
    )


if __name__ == "__main__":
    raise SystemExit(main())
