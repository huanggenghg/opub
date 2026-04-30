# -*- coding: utf-8 -*-
"""微博登录脚本"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from uploader.weibo_uploader.main import weibo_setup


async def main():
    account_file = "cookies/weibo_uploader/account.json"
    print("正在打开微博登录页面，请扫码登录...")
    result = await weibo_setup(account_file, handle=True, return_detail=True)
    if result["success"]:
        print(f"登录成功！Cookie 已保存到: {account_file}")
    else:
        print(f"登录失败: {result['message']}")


if __name__ == "__main__":
    asyncio.run(main())
