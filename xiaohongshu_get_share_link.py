# -*- coding: utf-8 -*-
"""
获取小红书分享链接的脚本
通过点击分享按钮和链接图标，从剪贴板获取分享链接
"""
import asyncio
import re
from pathlib import Path

from patchright.async_api import async_playwright
from utils.base_social_media import set_init_script
from utils.log import xiaohongshu_logger


def _msg(emoji: str, text: str) -> str:
    return f"{emoji} {text}"


XHS_USER_PROFILE_URL = "https://www.xiaohongshu.com/user/profile/678a98cc000000000d00891b"


async def get_share_link(account_file: str) -> dict:
    """
    获取最新发布笔记的分享链接

    流程：
    1. 先访问主站验证登录状态
    2. 打开用户首页
    3. 点击第一个笔记进入详情页
    4. 点击分享按钮
    5. 点击链接图标
    6. 从剪贴板获取链接

    Returns:
        dict: {"success": bool, "share_link": str, "note_id": str, "message": str}
    """
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        try:
            # 授予剪贴板读写权限，避免每次都需要用户确认
            context = await browser.new_context(
                storage_state=account_file,
                permissions=["clipboard-read", "clipboard-write"]
            )
            context = await set_init_script(context)
            page = await context.new_page()

            # 1. 先访问主站验证登录状态
            xiaohongshu_logger.info(_msg("🔍", "正在验证登录状态"))
            await page.goto("https://www.xiaohongshu.com/explore", timeout=60000)
            await page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(2)

            # 检查是否跳转到登录页
            if "login" in page.url:
                xiaohongshu_logger.error(_msg("❌", "Cookie已失效，请重新登录小红书"))
                return {"success": False, "share_link": "", "note_id": "", "message": "Cookie已失效，请重新登录小红书"}

            xiaohongshu_logger.success(_msg("✅", "登录状态有效"))

            # 2. 导航到用户首页
            xiaohongshu_logger.info(_msg("🧭", "正在导航到用户首页"))
            await page.goto(XHS_USER_PROFILE_URL, timeout=60000)
            await page.wait_for_load_state("domcontentloaded")
            xiaohongshu_logger.info(_msg("✅", f"已进入用户首页: {page.url}"))

            await asyncio.sleep(3)

            # 3. 找到并点击第一个笔记
            xiaohongshu_logger.info(_msg("🔍", "正在查找第一个笔记"))

            first_note = page.locator("section.note-item").first
            if await first_note.count() == 0:
                xiaohongshu_logger.warning(_msg("⚠️", "未找到笔记元素"))
                return {"success": False, "share_link": "", "note_id": "", "message": "未找到笔记元素"}

            xiaohongshu_logger.info(_msg("✅", "找到笔记元素: section.note-item"))

            # 点击第一个笔记进入详情页
            await first_note.click()
            xiaohongshu_logger.info(_msg("👆", "已点击第一个笔记"))
            await asyncio.sleep(3)

            current_url = page.url
            xiaohongshu_logger.info(_msg("🔍", f"当前URL: {current_url}"))

            # 4. 点击分享按钮
            xiaohongshu_logger.info(_msg("🔍", "正在查找分享按钮"))

            await asyncio.sleep(2)

            share_button = page.locator('button.reds-button-new.share-icon').first

            if await share_button.count() == 0:
                xiaohongshu_logger.warning(_msg("⚠️", "未找到分享按钮"))
                await page.screenshot(path="debug_xhs_detail.png")
                return {"success": False, "share_link": "", "note_id": "", "message": "未找到分享按钮"}

            xiaohongshu_logger.info(_msg("✅", "找到分享按钮"))

            # 用 JavaScript 点击（绕过 viewport 检查）
            await share_button.evaluate('el => el.click()')
            xiaohongshu_logger.info(_msg("👆", "已点击分享按钮"))
            await asyncio.sleep(2)

            # 5. 点击链接图标
            xiaohongshu_logger.info(_msg("🔍", "正在查找链接图标"))

            link_container = page.locator('.share-icon-container').first

            if await link_container.count() == 0:
                xiaohongshu_logger.warning(_msg("⚠️", "未找到链接图标"))
                await page.screenshot(path="debug_share_panel.png")
                return {"success": False, "share_link": "", "note_id": "", "message": "未找到链接图标"}

            xiaohongshu_logger.info(_msg("✅", "找到链接图标"))

            # 点击链接图标
            await link_container.click()
            xiaohongshu_logger.info(_msg("👆", "已点击链接图标"))
            await asyncio.sleep(1)

            # 6. 从剪贴板获取链接
            xiaohongshu_logger.info(_msg("📋", "正在从剪贴板获取链接"))

            try:
                clipboard_text = await page.evaluate('navigator.clipboard.readText()')

                if clipboard_text:
                    # 从剪贴板文本中提取URL（格式：标题 😆 口令 😆 URL）
                    share_link = clipboard_text
                    note_id = ""

                    # 尝试提取URL
                    url_match = re.search(r'https://[^\s]+', clipboard_text)
                    if url_match:
                        share_link = url_match.group(0)
                        # 提取笔记ID
                        match = re.search(r'/item/([a-f0-9]+)', share_link)
                        if match:
                            note_id = match.group(1)

                    xiaohongshu_logger.success(_msg("✅", f"获取到分享链接: {share_link}"))

                    return {
                        "success": True,
                        "share_link": share_link,
                        "note_id": note_id,
                        "message": "成功获取分享链接"
                    }
                else:
                    xiaohongshu_logger.warning(_msg("⚠️", "剪贴板内容为空"))
                    return {"success": False, "share_link": "", "note_id": "", "message": "剪贴板内容为空"}

            except Exception as e:
                xiaohongshu_logger.error(_msg("❌", f"读取剪贴板失败: {e}"))
                return {"success": False, "share_link": "", "note_id": "", "message": f"读取剪贴板失败: {e}"}

        except Exception as e:
            xiaohongshu_logger.error(_msg("❌", f"获取分享链接失败: {e}"))
            return {"success": False, "share_link": "", "note_id": "", "message": str(e)}
        finally:
            await browser.close()


async def main():
    """主函数"""
    account_file = "cookies/xiaohongshu_uploader/account.json"
    account_path = Path(__file__).parent / account_file

    if not account_path.exists():
        print(f"Cookie文件不存在: {account_path}")
        return

    print(f"使用cookie文件: {account_path}")
    result = await get_share_link(str(account_path))
    print(f"\n结果: {result}")


if __name__ == "__main__":
    asyncio.run(main())