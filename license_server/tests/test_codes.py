from __future__ import annotations

import hashlib
import os
import sqlite3
import subprocess
import sys
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


def test_code_hash_uses_exact_domain_separator_and_normalized_value() -> None:
    from license_server.codes import code_hash

    normalized = "OPUB0" + ALPHABET[:30]
    assert code_hash(normalized) == hashlib.sha256(
        b"opub-activation-code-v1\n" + normalized.encode("ascii")
    ).hexdigest()


def test_generate_inventory_normalizes_before_hashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from license_server.codes import generate_inventory

    database = _database(tmp_path)
    output = tmp_path / "inventory.txt"
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr("license_server.codes.normalize_activation_code", lambda value: "OPUB0" + ALPHABET[:30])
    monkeypatch.setattr(
        "license_server.codes.code_hash",
        lambda normalized: calls.append(("code_hash", normalized)) or ("a" * 64),
    )

    _choice_stream(monkeypatch, ALPHABET[:30])
    generate_inventory(database, 1, output)

    assert calls == [("code_hash", "OPUB0" + ALPHABET[:30])]


def test_open_exclusive_removes_file_and_closes_fd_when_fchmod_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from license_server.codes import _open_exclusive

    path = tmp_path / "inventory.txt"
    closed: list[int] = []

    def fail_fchmod(fd: int, mode: int) -> None:
        raise OSError("fchmod failed")

    monkeypatch.setattr("license_server.codes.os.fchmod", fail_fchmod)
    monkeypatch.setattr("license_server.codes.os.close", lambda fd: closed.append(fd))

    with pytest.raises(OSError, match="fchmod failed"):
        _open_exclusive(path)

    assert not path.exists()
    assert closed


def test_generate_inventory_fsyncs_parent_directory_on_success_and_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from license_server.codes import generate_inventory

    database = _database(tmp_path)
    output = tmp_path / "inventory.txt"
    calls: list[Path] = []
    monkeypatch.setattr("license_server.codes._fsync_parent_directory", lambda path: calls.append(path))
    _choice_stream(monkeypatch, ALPHABET[:30])

    generate_inventory(database, 1, output)
    assert calls == [output]

    calls.clear()
    _choice_stream(monkeypatch, ALPHABET[1:31] * 2)
    with pytest.raises(sqlite3.IntegrityError):
        generate_inventory(database, 2, tmp_path / "inventory-2.txt")
    assert calls == [tmp_path / "inventory-2.txt", tmp_path / "inventory-2.txt"]


def test_generate_inventory_cleans_up_output_when_write_is_interrupted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from license_server.codes import generate_inventory

    database = _database(tmp_path)
    output = tmp_path / "inventory.txt"

    class InterruptingHandle:
        def __init__(self) -> None:
            self.closed = False

        def write(self, data: str) -> int:
            raise KeyboardInterrupt()

        def flush(self) -> None:
            pass

        def fileno(self) -> int:
            return 123

        def close(self) -> None:
            self.closed = True

    handle = InterruptingHandle()
    monkeypatch.setattr(
        "license_server.codes.os.fdopen",
        lambda fd, *args, **kwargs: handle,
    )
    _choice_stream(monkeypatch, ALPHABET[:30])

    with pytest.raises(KeyboardInterrupt):
        generate_inventory(database, 1, output)

    assert not output.exists()
    assert database.code_stats() == {"available": 0, "redeemed": 0, "total": 0}


def test_generate_inventory_fails_before_import_when_close_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from license_server.codes import generate_inventory

    database = _database(tmp_path)
    output = tmp_path / "inventory.txt"
    called = {"import": False}

    class ClosingHandle:
        def write(self, data: str) -> int:
            return len(data)

        def flush(self) -> None:
            pass

        def fileno(self) -> int:
            return 123

        def close(self) -> None:
            raise OSError("close failed")

    monkeypatch.setattr("license_server.codes.os.fdopen", lambda fd, *args, **kwargs: ClosingHandle())
    monkeypatch.setattr("license_server.codes.os.fsync", lambda fd: None)
    monkeypatch.setattr(
        database,
        "import_activation_codes",
        lambda *args, **kwargs: called.__setitem__("import", True),
    )
    _choice_stream(monkeypatch, ALPHABET[:30])

    with pytest.raises(OSError, match="close failed"):
        generate_inventory(database, 1, output)

    assert not output.exists()
    assert database.code_stats() == {"available": 0, "redeemed": 0, "total": 0}
    assert called == {"import": False}


def test_generate_inventory_retains_output_when_import_commits_then_interrupts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from license_server.codes import generate_inventory

    database = _database(tmp_path)
    output = tmp_path / "inventory.txt"
    _choice_stream(monkeypatch, ALPHABET[:30])
    real_import = database.import_activation_codes

    def commit_then_interrupt(activation_codes: object) -> None:
        real_import(activation_codes)
        raise KeyboardInterrupt()

    monkeypatch.setattr(database, "import_activation_codes", commit_then_interrupt)

    with pytest.raises(KeyboardInterrupt) as excinfo:
        generate_inventory(database, 1, output)

    assert output.exists()
    assert database.code_stats() == {"available": 1, "redeemed": 0, "total": 1}
    assert getattr(excinfo.value, "_inventory_reconciliation") == "all"
    assert getattr(excinfo.value, "_inventory_output_retained") is True


def test_generate_inventory_marks_partial_reconciliation_when_only_some_rows_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from license_server.codes import generate_inventory

    database = _database(tmp_path)
    output = tmp_path / "inventory.txt"
    _choice_stream(monkeypatch, ALPHABET[:30] + ALPHABET[1:31])
    real_import = database.import_activation_codes

    def commit_one_then_interrupt(activation_codes: object) -> None:
        rows = list(activation_codes)
        real_import((rows[0],))
        raise KeyboardInterrupt()

    monkeypatch.setattr(database, "import_activation_codes", commit_one_then_interrupt)

    with pytest.raises(KeyboardInterrupt) as excinfo:
        generate_inventory(database, 2, output)

    assert output.exists()
    assert database.code_stats() == {"available": 1, "redeemed": 0, "total": 1}
    assert getattr(excinfo.value, "_inventory_reconciliation") == "partial"
    assert getattr(excinfo.value, "_inventory_output_retained") is True


def test_generate_inventory_marks_unknown_reconciliation_when_query_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from license_server.codes import generate_inventory

    database = _database(tmp_path)
    output = tmp_path / "inventory.txt"
    _choice_stream(monkeypatch, ALPHABET[:30])
    real_import = database.import_activation_codes
    real_row = database.row

    def commit_then_interrupt(activation_codes: object) -> None:
        real_import(activation_codes)
        raise KeyboardInterrupt()

    def row_or_fail(query: str, values: object = ()) -> object:
        if query.startswith("SELECT 1 FROM activation_codes"):
            raise sqlite3.OperationalError("reconcile failed")
        return real_row(query, values)

    monkeypatch.setattr(database, "import_activation_codes", commit_then_interrupt)
    monkeypatch.setattr(database, "row", row_or_fail)

    with pytest.raises(KeyboardInterrupt) as excinfo:
        generate_inventory(database, 1, output)

    assert output.exists()
    assert getattr(excinfo.value, "_inventory_reconciliation") == "unknown"
    assert getattr(excinfo.value, "_inventory_output_retained") is True


def test_generate_inventory_does_not_delete_replacement_file_on_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from license_server.codes import generate_inventory

    database = _database(tmp_path)
    output = tmp_path / "inventory.txt"
    replacement = tmp_path / "replacement.txt"
    replacement.write_text("replacement\n", encoding="utf-8")
    _choice_stream(monkeypatch, ALPHABET[:30])

    def replace_then_fail(*args: object, **kwargs: object) -> None:
        if output.exists():
            output.unlink()
        replacement.replace(output)
        raise sqlite3.IntegrityError("forced failure")

    monkeypatch.setattr(database, "import_activation_codes", replace_then_fail)

    with pytest.raises(sqlite3.IntegrityError, match="forced failure"):
        generate_inventory(database, 1, output)

    assert output.exists()
    assert output.read_text(encoding="utf-8") == "replacement\n"
    assert database.code_stats() == {"available": 0, "redeemed": 0, "total": 0}


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
    wal_path = Path(str(database.path) + "-wal")
    assert wal_path.exists()
    assert wal_path.stat().st_size > 0

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
    _assert_plaintext_absent(database.path, symbols)
    _assert_plaintext_absent(database.path, line[0])
    _assert_plaintext_absent(database.path, normalize_activation_code(line[0]))
    database.row("PRAGMA wal_checkpoint(TRUNCATE)")
    assert not wal_path.exists() or wal_path.stat().st_size == 0
    _assert_plaintext_absent(database.path, symbols)
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


def test_main_reports_missing_env_without_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from license_server.codes import main

    monkeypatch.delenv("OPUB_LICENSE_DB_PATH", raising=False)

    assert main(["stats"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Traceback" not in captured.err
    assert "OPUB0" not in captured.err


def test_main_warns_when_import_commits_then_interrupts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from license_server.codes import main
    from license_server import codes

    monkeypatch.setenv("OPUB_LICENSE_DB_PATH", str(tmp_path / "licenses.sqlite3"))
    real_import = codes.Database.import_activation_codes

    def commit_then_interrupt(self: Database, activation_codes: object) -> None:
        real_import(self, activation_codes)
        raise KeyboardInterrupt()

    monkeypatch.setattr(codes.Database, "import_activation_codes", commit_then_interrupt)
    _choice_stream(monkeypatch, ALPHABET[:30])

    assert main(["generate", "--count", "1", "--output", str(tmp_path / "inventory.txt")]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "check stats before upload" in captured.err
    assert "Traceback" not in captured.err
    assert "OPUB0" not in captured.err
    assert codes.Database(tmp_path / "licenses.sqlite3").code_stats() == {"available": 1, "redeemed": 0, "total": 1}


def test_main_reports_existing_output_via_subprocess_without_traceback(
    tmp_path: Path
) -> None:
    database_path = tmp_path / "licenses.sqlite3"
    output = tmp_path / "inventory.txt"
    output.write_text("already here\n", encoding="utf-8")
    env = {**os.environ, "OPUB_LICENSE_DB_PATH": str(database_path)}

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "license_server.codes",
            "generate",
            "--count",
            "1",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(Path(__file__).resolve().parents[2]),
        check=False,
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert "Traceback" not in result.stderr
    assert "OPUB0" not in result.stderr
    assert "inventory output already exists" in result.stderr


def test_main_reports_database_error_without_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from license_server.codes import main
    from license_server import codes

    monkeypatch.setenv("OPUB_LICENSE_DB_PATH", str(tmp_path / "missing" / "licenses.sqlite3"))

    def fail_initialize(self: Database) -> None:
        raise sqlite3.OperationalError("database failed")

    monkeypatch.setattr(codes.Database, "initialize", fail_initialize)

    assert main(["stats"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Traceback" not in captured.err
    assert "OPUB0" not in captured.err
