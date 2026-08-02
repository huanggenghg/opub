# -*- coding: utf-8 -*-
"""publish_all.py -- 向后兼容薄壳

实际代码在 publish/ 包内。此文件保留用于:
- python publish_all.py 入口
- hgsau 控制台脚本(publish_all:main)
- 测试 import 兼容(publish_all.X)
"""
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).resolve().parent))

from publish.config import (
    PublishOverrides,
    apply_overrides,
    default_params_from_overrides,
    parse_config,
    read_config,
    reset_publish_task_fields,
)
from publish.content import (
    fill_empty_content,
    get_video_content,
    get_video_files,
    load_content_templates,
    resolve_path,
    truncate_title,
)
from publish.constants import (
    PLATFORM_NAMES,
    PUBLISH_TASK_FIELD_DEFAULTS,
    TITLE_LIMITS,
)
from publish.dispatch import (
    ensure_account_login,
    ensure_login,
    platform_requires_account_login,
    publish_to_baijiahao,
    publish_to_bilibili,
    publish_to_douyin,
    publish_to_kuaishou,
    publish_to_platform,
    publish_to_tencent,
    publish_to_weibo,
    publish_to_xiaohongshu,
)
from publish.orchestrator import (
    build_parser,
    main,
    publish_one_item,
    run_publish,
    run_publish_sync,
    run_publish_with_params,
)
from publish.reporter import print_header, print_results
from publish.runtime import (
    install_patchright_chromium,
    patchright_available,
    patchright_chromium_installed,
    playwright_browser_cache_dirs,
    run_async_for_test,
    runtime_preflight,
)

if __name__ == "__main__":
    raise SystemExit(main())
