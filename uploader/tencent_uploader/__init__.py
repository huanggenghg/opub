from pathlib import Path

from conf import BASE_DIR
from utils.fs import ensure_dir

ensure_dir(Path(BASE_DIR / "cookies" / "tencent_uploader"))

from uploader.tencent_uploader.main import TENCENT_PUBLISH_STRATEGY_IMMEDIATE
from uploader.tencent_uploader.main import TENCENT_PUBLISH_STRATEGY_SCHEDULED
from uploader.tencent_uploader.main import TencentBaseUploader
from uploader.tencent_uploader.main import TencentNote
from uploader.tencent_uploader.main import TencentVideo
from uploader.tencent_uploader.main import cookie_auth
from uploader.tencent_uploader.main import format_str_for_short_title
from uploader.tencent_uploader.main import get_tencent_cookie
from uploader.tencent_uploader.main import tencent_cookie_gen
from uploader.tencent_uploader.main import tencent_setup
from uploader.tencent_uploader.main import weixin_setup

__all__ = [
    "TENCENT_PUBLISH_STRATEGY_IMMEDIATE",
    "TENCENT_PUBLISH_STRATEGY_SCHEDULED",
    "TencentBaseUploader",
    "TencentNote",
    "TencentVideo",
    "cookie_auth",
    "format_str_for_short_title",
    "get_tencent_cookie",
    "tencent_cookie_gen",
    "tencent_setup",
    "weixin_setup",
]
