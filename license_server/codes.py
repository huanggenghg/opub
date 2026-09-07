from __future__ import annotations

import argparse
import errno
import hashlib
import os
import secrets
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from license_server.database import Database
from publish.licensing.codes import normalize_activation_code


_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_HASH_PREFIX = b"opub-activation-code-v1\n"
_PRODUCT_ID = "opub-major-0"
_MIN_COUNT = 1
_MAX_COUNT = 10_000


def code_hash(normalized: str) -> str:
    return hashlib.sha256(_HASH_PREFIX + normalized.encode("ascii")).hexdigest()


def _validate_count(value: int) -> int:
    if value < _MIN_COUNT or value > _MAX_COUNT:
        raise ValueError("count must be between 1 and 10000")
    return value


def _count_argument(value: str) -> int:
    try:
        return _validate_count(int(value))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("count must be between 1 and 10000") from exc


def _generate_display_code() -> str:
    symbols = "".join(secrets.choice(_ALPHABET) for _ in range(30))
    groups = [symbols[index : index + 5] for index in range(0, 30, 5)]
    return "OPUB0-" + "-".join(groups)


def _created_at() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _path_matches_inode(path: Path, expected: os.stat_result) -> bool:
    try:
        current = os.lstat(path)
    except FileNotFoundError:
        return False
    return current.st_dev == expected.st_dev and current.st_ino == expected.st_ino


def _fsync_parent_directory(path: Path) -> None:
    parent = path.parent
    fd = os.open(parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    except OSError as exc:
        if exc.errno == errno.EINVAL:
            return
        raise
    finally:
        os.close(fd)


def _remove_created_output(path: Path, expected: os.stat_result) -> None:
    if not _path_matches_inode(path, expected):
        return
    try:
        os.unlink(path)
    except FileNotFoundError:
        return
    _fsync_parent_directory(path)


def _cleanup_created_output(path: Path, expected: os.stat_result) -> None:
    try:
        _remove_created_output(path, expected)
    except OSError:
        pass


def _open_exclusive(path: Path) -> int:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    created = os.fstat(fd)
    try:
        os.fchmod(fd, 0o600)
    except AttributeError:  # pragma: no cover - non-POSIX fallback
        pass
    except OSError:
        try:
            os.close(fd)
        finally:
            _cleanup_created_output(path, created)
        raise
    return fd


def generate_inventory(database: Database, count: int, output: str | Path) -> int:
    count = _validate_count(count)
    output_path = Path(output)
    if output_path.exists():
        raise FileExistsError(str(output_path))

    output_path.parent.mkdir(parents=True, exist_ok=True)

    display_codes = [_generate_display_code() for _ in range(count)]
    activation_codes = [
        (code_hash(normalize_activation_code(display_code)), _PRODUCT_ID, _created_at())
        for display_code in display_codes
    ]

    fd = _open_exclusive(output_path)
    created = os.fstat(fd)
    try:
        handle = os.fdopen(fd, "w", encoding="utf-8", newline="\n")
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        _remove_created_output(output_path, created)
        raise

    try:
        try:
            for display_code in display_codes:
                handle.write(display_code)
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            try:
                handle.close()
            except OSError:
                pass

        # The inventory file and SQLite catalog cannot commit atomically
        # together, so the export is made durable first; the runbook verifies
        # stats before upload in the follow-up task.
        _fsync_parent_directory(output_path)
        database.import_activation_codes(activation_codes)
    except BaseException:
        _cleanup_created_output(output_path, created)
        raise

    return count


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="license_server.codes")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="generate a plaintext inventory file")
    generate.add_argument("--count", type=_count_argument, required=True)
    generate.add_argument("--output", type=Path, required=True)

    subparsers.add_parser("stats", help="print inventory statistics")
    return parser


def _database_from_env() -> Database:
    database_path = os.environ["OPUB_LICENSE_DB_PATH"]
    database = Database(database_path)
    database.initialize()
    return database


def _print_stats(database: Database) -> None:
    stats = database.code_stats()
    print(f"available={stats['available']} redeemed={stats['redeemed']} total={stats['total']}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
        database = _database_from_env()

        if args.command == "generate":
            generate_inventory(database, args.count, args.output)
            return 0

        _print_stats(database)
        return 0
    except KeyError:
        print("OPUB_LICENSE_DB_PATH is required", file=sys.stderr)
        return 2
    except FileExistsError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (OSError, sqlite3.Error, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
