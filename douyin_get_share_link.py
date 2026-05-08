# -*- coding: utf-8 -*-
"""
测试获取抖音分享链接的脚本
通过从URL提取modal_id生成视频链接
"""
import asyncio
import os
import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from patchright.async_api import async_playwright
from utils.base_social_media import set_init_script
from utils.log import douyin_logger


def _msg(emoji: str, text: str) -> str:
    return f"{emoji} {text}"


def extract_video_id_from_url(url: str) -> str | None:
    """
    从URL中提取视频ID (modal_id)

    URL格式: https://www.douyin.com/user/self?from_tab_name=main&modal_id=7637405747755732270

    Returns:
        str: 视频ID，如 "7637405747755732270"
    """
    # 方法1: 从URL参数中提取 modal_id
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)
    if 'modal_id' in query_params:
        return query_params['modal_id'][0]

    # 方法2: 从URL路径中提取 /video/{id}
    match = re.search(r'/video/(\d+)', url)
    if match:
        return match.group(1)

    return None


def build_video_link(video_id: str) -> str:
    """
    根据视频ID构建视频链接

    Args:
        video_id: 视频ID，如 "7637405747755732270"

    Returns:
        str: 视频链接，如 "https://www.douyin.com/video/7637405747755732270"
    """
    return f"https://www.douyin.com/video/{video_id}"


async def get_share_link(account_file: str) -> dict:
    """
    获取最新发布视频的分享链接

    流程：
    1. 打开用户首页 https://www.douyin.com/user/self?from_tab_name=main
    2. 点击第一个视频（最新发布的）
    3. 从URL中提取modal_id
    4. 拼接成视频链接

    Returns:
        dict: {"success": bool, "share_link": str, "video_id": str, "message": str}
    """
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        try:
            context = await browser.new_context(storage_state=account_file)
            context = await set_init_script(context)
            page = await context.new_page()

            # 1. 导航到用户首页
            douyin_logger.info(_msg("🧭", "正在导航到用户首页"))
            await page.goto("https://www.douyin.com/user/self?from_tab_name=main", timeout=60000)
            await page.wait_for_load_state("domcontentloaded")
            douyin_logger.info(_msg("✅", f"已进入用户首页: {page.url}"))

            await asyncio.sleep(2)

            # 2. 找到并点击第一个视频
            douyin_logger.info(_msg("🔍", "正在查找第一个视频"))

            video_selectors = [
                "div[data-e2e='user-post-list'] a:first-child",
                "ul[data-e2e='scroll-list'] li:first-child a",
                ".video-card a",
                "a[href*='/video/']",
            ]

            first_video = None
            for selector in video_selectors:
                try:
                    first_video = page.locator(selector).first
                    if await first_video.count():
                        douyin_logger.info(_msg("✅", f"找到视频元素: {selector}"))
                        break
                except Exception:
                    continue

            if not first_video or not await first_video.count():
                return {"success": False, "share_link": "", "video_id": "", "message": "未找到视频元素"}

            # 点击第一个视频
            await first_video.click()
            douyin_logger.info(_msg("👆", "已点击第一个视频"))
            await asyncio.sleep(2)

            # 3. 从URL中提取modal_id
            current_url = page.url
            douyin_logger.info(_msg("🔍", f"当前URL: {current_url}"))

            video_id = extract_video_id_from_url(current_url)

            if not video_id:
                return {"success": False, "share_link": "", "video_id": "", "message": f"无法从URL提取视频ID: {current_url}"}

            douyin_logger.info(_msg("✅", f"提取到视频ID: {video_id}"))

            # 4. 构建视频链接
            share_link = build_video_link(video_id)
            douyin_logger.info(_msg("✅", f"视频链接: {share_link}"))

            return {
                "success": True,
                "share_link": share_link,
                "video_id": video_id,
                "message": "成功获取分享链接"
            }

        except Exception as e:
            douyin_logger.error(_msg("❌", f"获取分享链接失败: {e}"))
            return {"success": False, "share_link": "", "video_id": "", "message": str(e)}
        finally:
            await browser.close()


async def main():
    """主函数"""
    account_file = "cookies/douyin_uploader/account.json"
    account_path = Path(__file__).parent / account_file

    if not account_path.exists():
        print(f"Cookie文件不存在: {account_path}")
        return

    print(f"使用cookie文件: {account_path}")
    result = await get_share_link(str(account_path))
    print(f"\n结果: {result}")


if __name__ == "__main__":
    asyncio.run(main())