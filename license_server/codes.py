from __future__ import annotations

import argparse
import hashlib
import os
import secrets
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


def _activation_code_hash(display_code: str) -> str:
    normalized = normalize_activation_code(display_code)
    return hashlib.sha256(_HASH_PREFIX + normalized.encode("ascii")).hexdigest()


def _created_at() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _open_exclusive(path: Path) -> int:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.fchmod(fd, 0o600)
    except AttributeError:  # pragma: no cover - non-POSIX fallback
        pass
    return fd


def generate_inventory(database: Database, count: int, output: str | Path) -> int:
    count = _validate_count(count)
    output_path = Path(output)
    if output_path.exists():
        raise FileExistsError(str(output_path))

    output_path.parent.mkdir(parents=True, exist_ok=True)

    display_codes = [_generate_display_code() for _ in range(count)]
    activation_codes = [
        (_activation_code_hash(display_code), _PRODUCT_ID, _created_at())
        for display_code in display_codes
    ]

    fd = _open_exclusive(output_path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            for display_code in display_codes:
                handle.write(display_code)
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        database.import_activation_codes(activation_codes)
    except Exception:
        try:
            output_path.unlink()
        except FileNotFoundError:
            pass
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
    args = parser.parse_args(list(argv) if argv is not None else None)
    database = _database_from_env()

    if args.command == "generate":
        generate_inventory(database, args.count, args.output)
        return 0

    _print_stats(database)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
