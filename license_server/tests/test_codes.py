from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from license_server.database import Database


ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _database(tmp_path: Path) -> Database:
    database = Database(tmp_path / "licenses.sqlite3")
    database.initialize()
    return database


def _choice_stream(monkeypatch: pytest.MonkeyPatch, symbols: str) -> None:
    iterator = iter(symbols)
    monkeypatch.setattr("license_server.codes.secrets.choice", lambda alphabet: next(iterator))


def _display_code(symbols: str) -> str:
    groups = [symbols[index : index + 5] for index in range(0, 30, 5)]
    return "OPUB0-" + "-".join(groups)


def _sqlite_artifacts(path: Path) -> list[Path]:
    return [path, Path(str(path) + "-wal"), Path(str(path) + "-shm")]


def _assert_plaintext_absent(path: Path, plaintext: str) -> None:
    needle = plaintext.encode("ascii")
    for artifact in _sqlite_artifacts(path):
        if artifact.exists():
            assert needle not in artifact.read_bytes()


def test_generate_inventory_writes_display_codes_and_hashes_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from license_server.codes import generate_inventory
    from publish.licensing.codes import normalize_activation_code

    database = _database(tmp_path)
    output = tmp_path / "inventory.txt"
    symbols = ALPHABET[:30]
    _choice_stream(monkeypatch, symbols)

    generated = generate_inventory(database, 1, output)

    assert generated == 1
    assert output.stat().st_mode & 0o777 == 0o600
    assert output.read_bytes().endswith(b"\n")

    line = output.read_text(encoding="utf-8").splitlines()
    assert line == [_display_code(symbols)]
    assert normalize_activation_code(line[0]) == "OPUB0" + symbols

    expected_hash = hashlib.sha256(
        b"opub-activation-code-v1\n" + normalize_activation_code(line[0]).encode("ascii")
    ).hexdigest()
    row = database.row("SELECT code_hash FROM activation_codes")
    assert row is not None
    assert row["code_hash"] == expected_hash
    assert len(row["code_hash"]) == 64
    assert database.code_stats() == {"available": 1, "redeemed": 0, "total": 1}
    _assert_plaintext_absent(database.path, line[0])
    _assert_plaintext_absent(database.path, normalize_activation_code(line[0]))
    database.row("PRAGMA wal_checkpoint(TRUNCATE)")
    _assert_plaintext_absent(database.path, line[0])
    _assert_plaintext_absent(database.path, normalize_activation_code(line[0]))


def test_generate_inventory_keeps_batch_codes_unique(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from license_server.codes import generate_inventory

    database = _database(tmp_path)
    output = tmp_path / "inventory.txt"
    first = ALPHABET[:30]
    second = ALPHABET[1:31]
    _choice_stream(monkeypatch, first + second)

    generated = generate_inventory(database, 2, output)

    lines = output.read_text(encoding="utf-8").splitlines()
    assert generated == 2
    assert len(lines) == 2
    assert len(set(lines)) == 2
    assert lines[0] == _display_code(first)
    assert lines[1] == _display_code(second)
    assert database.code_stats() == {"available": 2, "redeemed": 0, "total": 2}


def test_generate_inventory_refuses_existing_output_before_generation_or_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from license_server.codes import generate_inventory

    database = _database(tmp_path)
    output = tmp_path / "inventory.txt"
    output.write_text("already here\n", encoding="utf-8")
    called = {"import": False, "choice": False}

    def fail_choice(alphabet: str) -> str:  # pragma: no cover - defensive
        called["choice"] = True
        raise AssertionError("secrets.choice should not run when output exists")

    def fail_import(*args: object, **kwargs: object) -> None:
        called["import"] = True
        raise AssertionError("database import should not run when output exists")

    monkeypatch.setattr("license_server.codes.secrets.choice", fail_choice)
    monkeypatch.setattr(database, "import_activation_codes", fail_import)

    with pytest.raises(FileExistsError):
        generate_inventory(database, 1, output)

    assert output.read_text(encoding="utf-8") == "already here\n"
    assert called == {"import": False, "choice": False}


@pytest.mark.parametrize("count", [0, 10001])
def test_generate_inventory_rejects_invalid_count_bounds(
    tmp_path: Path, count: int
) -> None:
    from license_server.codes import generate_inventory

    database = _database(tmp_path)
    output = tmp_path / "inventory.txt"

    with pytest.raises(ValueError, match="count must be between 1 and 10000"):
        generate_inventory(database, count, output)


def test_generate_inventory_rolls_back_database_and_removes_output_on_import_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from license_server.codes import generate_inventory

    database = _database(tmp_path)
    output = tmp_path / "inventory.txt"
    symbols = ALPHABET[:30] * 2
    _choice_stream(monkeypatch, symbols)

    with pytest.raises(sqlite3.IntegrityError):
        generate_inventory(database, 2, output)

    assert not output.exists()
    assert database.code_stats() == {"available": 0, "redeemed": 0, "total": 0}
    assert database.row("SELECT COUNT(*) FROM activation_codes")[0] == 0


def test_main_generate_then_stats_reports_exact_last_line_without_printing_codes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from license_server.codes import main

    database_path = tmp_path / "licenses.sqlite3"
    output = tmp_path / "inventory.txt"
    monkeypatch.setenv("OPUB_LICENSE_DB_PATH", str(database_path))
    _choice_stream(monkeypatch, ALPHABET[:30] + ALPHABET[1:31])

    assert main(["generate", "--count", "2", "--output", str(output)]) == 0
    generate_stdout = capsys.readouterr().out
    assert generate_stdout == ""

    assert main(["stats"]) == 0
    stats_output = capsys.readouterr().out.strip().splitlines()
    assert stats_output[-1] == "available=2 redeemed=0 total=2"
    assert len(stats_output) == 1

    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute("SELECT code_hash FROM activation_codes ORDER BY code_hash")
        rows = cursor.fetchall()
    assert len(rows) == 2
    assert all(len(row[0]) == 64 for row in rows)
