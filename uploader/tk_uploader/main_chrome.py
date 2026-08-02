# -*- coding: utf-8 -*-
"""Backward-compat shim: re-exports from main.py (now chromium+patchright).

The original main_chrome.py was an alternative chromium implementation using
playwright. After Task 9 migrated main.py to chromium+patchright, this file
became redundant. It now re-exports from main.py so legacy example scripts
that import from main_chrome continue to work.
"""
from uploader.tk_uploader.main import TiktokVideo, cookie_auth, tiktok_setup

__all__ = ["TiktokVideo", "cookie_auth", "tiktok_setup"]
