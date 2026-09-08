import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Optional


def data_dir(home: Optional[Path] = None, environ: Optional[Mapping[str, str]] = None) -> Path:
    env = os.environ if environ is None else environ
    return Path(env["SAU_HOME"]) if env.get("SAU_HOME") else (home or Path.home()) / ".opub"


def license_path(base: Optional[Path] = None) -> Path:
    return (base or data_dir()) / "license.json"


def atomic_write_json(path: Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, str(path))
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def read_json(path: Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)
