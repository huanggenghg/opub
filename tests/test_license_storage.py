import json
import os
import stat

import pytest

from publish.licensing.storage import (
    atomic_write_json,
    data_dir,
    license_path,
    read_json,
)


def test_paths_prefer_sau_home(tmp_path):
    assert data_dir(tmp_path / "home", {"SAU_HOME": str(tmp_path / "sau")}) == tmp_path / "sau"
    assert license_path(tmp_path) == tmp_path / "license.json"


def test_atomic_json_write_is_mode_0600_and_readable(tmp_path):
    target = tmp_path / "nested" / "license.json"
    atomic_write_json(target, {"z": "é", "ok": True})
    assert read_json(target) == {"z": "é", "ok": True}
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def test_failed_replace_keeps_old_file_and_removes_temp(tmp_path, monkeypatch):
    target = tmp_path / "license.json"
    atomic_write_json(target, {"old": True})
    before = target.read_bytes()
    real_replace = os.replace
    seen = []

    def fail_replace(source, destination):
        seen.append(source)
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError):
        atomic_write_json(target, {"new": True})
    assert target.read_bytes() == before
    assert seen and not os.path.exists(seen[0])


@pytest.mark.parametrize("failure", ["dump", "fsync"])
def test_write_failures_remove_temp_and_preserve_old_file(tmp_path, monkeypatch, failure):
    target = tmp_path / "license.json"
    atomic_write_json(target, {"old": True})
    before = target.read_bytes()
    if failure == "dump":
        monkeypatch.setattr("publish.licensing.storage.json.dump", lambda *a, **k: (_ for _ in ()).throw(OSError("dump")))
    else:
        monkeypatch.setattr("publish.licensing.storage.os.fsync", lambda fd: (_ for _ in ()).throw(OSError("fsync")))
    with pytest.raises(OSError):
        atomic_write_json(target, {"new": True})
    assert target.read_bytes() == before
    assert list(tmp_path.glob(".license.json.*")) == []
