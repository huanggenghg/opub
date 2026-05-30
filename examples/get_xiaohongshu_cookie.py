"""
当前主线仅提供统一发布入口：

    hgsau publish

发布流程会按平台配置校验登录状态；这个脚本仅保留为小红书 uploader 的调试直连路径。
"""

import asyncio
from pathlib import Path

from conf import BASE_DIR
from uploader.xiaohongshu_uploader.main import xiaohongshu_setup

if __name__ == '__main__':
    account_file = Path(BASE_DIR / "cookies" / "xiaohongshu_uploader" / "account.json")
    account_file.parent.mkdir(exist_ok=True)
    result = asyncio.run(
        xiaohongshu_setup(
            str(account_file),
            handle=True,
            return_detail=True,
        )
    )
