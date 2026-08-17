"""快手登录调试直连示例。

当前主线仅提供统一发布入口：
    opub publish

发布流程会按平台配置校验登录状态；这个脚本仅保留为 uploader 调试直连路径。
"""

import asyncio
from pathlib import Path

from conf import BASE_DIR
from uploader.ks_uploader.main import ks_setup


def login_to_kuaishou():
    account_file = Path(BASE_DIR / "cookies" / "kuaishou_creator.json")
    account_file.parent.mkdir(exist_ok=True)
    asyncio.run(ks_setup(str(account_file), handle=True))


if __name__ == '__main__':
    login_to_kuaishou()
