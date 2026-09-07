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
_RECONCILIATION_WARNING = (
    "inventory may have been committed to the database; check stats before upload"
)


class MissingLicenseDatabasePathError(RuntimeError):
    pass


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
    # The output directory is trusted for this narrow lstat/unlink window.
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
        except OSError:
            pass
        _cleanup_created_output(path, created)
        raise
    return fd


def _activation_code_hashes(display_codes: Sequence[str]) -> list[str]:
    return [code_hash(normalize_activation_code(display_code)) for display_code in display_codes]


def _reconcile_activation_code_import(database: Database, code_hashes: Sequence[str]) -> str:
    present = 0
    try:
        for code_hash_value in code_hashes:
            if database.row(
                "SELECT 1 FROM activation_codes WHERE code_hash = ?",
                (code_hash_value,),
            ) is not None:
                present += 1
    except sqlite3.Error:
        return "unknown"
    if present == 0:
        return "none"
    if present == len(code_hashes):
        return "all"
    return "partial"


def _mark_reconciliation(exception: BaseException, outcome: str) -> None:
    setattr(exception, "_inventory_output_retained", outcome != "none")
    setattr(exception, "_inventory_reconciliation", outcome)


def _inventory_warning(exception: BaseException) -> bool:
    return bool(getattr(exception, "_inventory_output_retained", False))


def _inventory_warning_text(exception: BaseException) -> str:
    outcome = getattr(exception, "_inventory_reconciliation", "unknown")
    if outcome in {"all", "partial", "unknown"}:
        return _RECONCILIATION_WARNING
    return "inventory generation failed; check stats before upload"


def generate_inventory(database: Database, count: int, output: str | Path) -> int:
    count = _validate_count(count)
    output_path = Path(output)
    if output_path.exists():
        raise FileExistsError(str(output_path))

    output_path.parent.mkdir(parents=True, exist_ok=True)

    display_codes = [_generate_display_code() for _ in range(count)]
    activation_hashes = _activation_code_hashes(display_codes)
    activation_codes = [
        (code_hash_value, _PRODUCT_ID, _created_at())
        for code_hash_value in activation_hashes
    ]

    fd = _open_exclusive(output_path)
    created = os.fstat(fd)
    try:
        _fsync_parent_directory(output_path)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        _cleanup_created_output(output_path, created)
        raise

    try:
        handle = os.fdopen(fd, "w", encoding="utf-8", newline="\n")
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        _remove_created_output(output_path, created)
        raise

    write_error: BaseException | None = None
    close_error: BaseException | None = None
    try:
        try:
            for display_code in display_codes:
                handle.write(display_code)
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException as exc:
            write_error = exc
        finally:
            try:
                handle.close()
            except BaseException as exc:
                close_error = exc
    except BaseException:
        _cleanup_created_output(output_path, created)
        raise

    if write_error is not None:
        _cleanup_created_output(output_path, created)
        raise write_error
    if close_error is not None:
        _cleanup_created_output(output_path, created)
        raise close_error

    try:
        database.import_activation_codes(activation_codes)
    except BaseException as exc:
        # The inventory file and SQLite catalog cannot commit atomically
        # together, so the export is made durable first; the runbook verifies
        # stats before upload in the follow-up task.
        outcome = _reconcile_activation_code_import(database, activation_hashes)
        _mark_reconciliation(exc, outcome)
        if outcome == "none":
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
    try:
        database_path = os.environ["OPUB_LICENSE_DB_PATH"]
    except KeyError as exc:
        raise MissingLicenseDatabasePathError from exc
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
    except MissingLicenseDatabasePathError:
        print("OPUB_LICENSE_DB_PATH is required", file=sys.stderr)
        return 2
    except sqlite3.Error:
        print("inventory database unavailable", file=sys.stderr)
        return 1

    if args.command == "generate":
        try:
            generate_inventory(database, args.count, args.output)
            return 0
        except BaseException as exc:
            if _inventory_warning(exc):
                print(_inventory_warning_text(exc), file=sys.stderr)
                return 1
            if isinstance(exc, FileExistsError):
                print("inventory output already exists", file=sys.stderr)
                return 1
            if isinstance(exc, (OSError, sqlite3.Error, RuntimeError, KeyboardInterrupt)):
                print("inventory generation failed", file=sys.stderr)
                return 1
            raise

    try:
        _print_stats(database)
        return 0
    except sqlite3.Error:
        print("inventory database unavailable", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
