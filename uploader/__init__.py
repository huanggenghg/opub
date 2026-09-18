from pathlib import Path

from conf import BASE_DIR
from utils.fs import ensure_dir

ensure_dir(Path(BASE_DIR / "cookies"))
