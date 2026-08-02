# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
from datetime import datetime

from patchright.async_api import Page, Playwright, async_playwright

from conf import LOCAL_CHROME_HEADLESS
from uploader.base_video import (
    BaseBrowserUploader,
    PlatformResultExtras,
    PublishStrategy,
    _msg,
)
from uploader.tk_uploader.tk_config import Tk_Locator
from utils.base_social_media import set_init_script
from utils.log import tiktok_logger


class TiktokVideo(BaseBrowserUploader):
    """TikTok 视频上传器 - chromium + patchright"""

    PLATFORM_NAME = "tk"
    UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload"
    LOGIN_URL = "https://www.tiktok.com/login?lang=en"
    LOGIN_MARKERS = ["/login", "/signup"]
    PUBLISH_MARKERS = []

    def __init__(
        self,
        title: str,
        file_path: str,
        tags: list,
        publish_date,
        account_file: str,
        publish_strategy: PublishStrategy = PublishStrategy.IMMEDIATE,
        desc: str = "",
        headless: bool = LOCAL_CHROME_HEADLESS,
    ):
        self.title = title
        self.file_path = file_path
        self.tags = tags or []
        self.publish_date = publish_date
        self.account_file = account_file
        self.publish_strategy = publish_strategy
        self.desc = desc
        self.headless = headless
        self.locator_base = None

    @classmethod
    async def is_login_completed(cls, page: Page) -> bool:
        return await _is_tiktok_auth_page_valid(page)

    @classmethod
    async def cookie_gen(
        cls,
        account_file: str,
        qrcode_callback=None,
        headless: bool = LOCAL_CHROME_HEADLESS,
        return_detail: bool = False,
    ):
        """tk 用 page.pause 手动登录,qrcode_callback 被忽略。"""
        from pathlib import Path
        Path(account_file).parent.mkdir(parents=True, exist_ok=True)
        async with async_playwright() as playwright:
            browser = await cls._launch_browser(playwright, headless)
            context = await cls._init_context(browser, None)
            try:
                page = await context.new_page()
                await page.goto(cls.LOGIN_URL)
                tiktok_logger.info(_msg("🧭", "请在打开的浏览器中手动登录 TikTok,登录完成后在调试器中点继续"))
                await page.pause()
                await context.storage_state(path=account_file)
                return {"success": True, "status": "success", "message": "TikTok 手动登录完成", "account_file": account_file, "qrcode": None, "current_url": page.url}
            finally:
                await context.close()
                await browser.close()

    async def validate_upload_args(self):
        """上传前校验:title 非空 + 视频文件存在且格式支持。"""
        if not self.title or not str(self.title).strip():
            raise ValueError("视频模式下，title 是必须的")
        self.file_path = str(self.validate_video_file(self.file_path))

    async def upload(self) -> PlatformResultExtras:
        """主入口，返回 PlatformResultExtras。"""
        tiktok_logger.info(_msg("🧍", "先检查视频文件和发布参数"))
        await self.validate_upload_args()
        tiktok_logger.info(_msg("🥳", "上传前检查通过"))

        result: PlatformResultExtras = {"success": False, "message": ""}

        try:
            async with self._browser_session() as page:
                await self.upload_video_content(page)
                result["success"] = True
                result["message"] = "发布成功"
        except Exception as e:
            result["message"] = str(e)
            tiktok_logger.error(_msg("❌", f"上传失败: {e}"))

        return result

    async def upload_video_content(self, page: Page) -> None:
        """上传视频内容(页面已通过 _browser_session 打开)。"""
        await page.goto("https://www.tiktok.com/creator-center/upload")
        tiktok_logger.info(_msg("🏃", f"Uploading-------{self.title}.mp4"))

        try:
            await page.wait_for_url("https://www.tiktok.com/tiktokstudio/upload", timeout=10000)
        except Exception:
            pass

        try:
            await page.wait_for_selector('iframe[data-tt="Upload_index_iframe"], div.upload-container', timeout=10000)
        except Exception:
            tiktok_logger.error("Neither iframe nor div appeared within the timeout.")

        await self.choose_base_locator(page)

        upload_button = self.locator_base.locator('button:has-text("Select video"):visible')
        await upload_button.wait_for(state="visible")

        async with page.expect_file_chooser() as fc_info:
            await upload_button.click()
        file_chooser = await fc_info.value
        await file_chooser.set_files(self.file_path)

        await self.add_title_tags(page)
        await self.detect_upload_status(page)

        if self.publish_strategy == PublishStrategy.SCHEDULED and self.publish_date != 0:
            await self.set_schedule_time(page, self.publish_date)

        await self.click_publish(page)

    async def set_schedule_time(self, page, publish_date):
        schedule_input_element = self.locator_base.get_by_label('Schedule')
        await schedule_input_element.wait_for(state='visible')  # 确保按钮可见

        await schedule_input_element.click()
        scheduled_picker = self.locator_base.locator('div.scheduled-picker')
        await scheduled_picker.locator('div.TUXInputBox').nth(1).click()

        calendar_month = await self.locator_base.locator('div.calendar-wrapper span.month-title').inner_text()

        n_calendar_month = datetime.strptime(calendar_month, '%B').month

        schedule_month = publish_date.month

        if n_calendar_month != schedule_month:
            if n_calendar_month < schedule_month:
                arrow = self.locator_base.locator('div.calendar-wrapper span.arrow').nth(-1)
            else:
                arrow = self.locator_base.locator('div.calendar-wrapper span.arrow').nth(0)
            await arrow.click()

        # day set
        valid_days_locator = self.locator_base.locator(
            'div.calendar-wrapper span.day.valid')
        valid_days = await valid_days_locator.count()
        for i in range(valid_days):
            day_element = valid_days_locator.nth(i)
            text = await day_element.inner_text()
            if text.strip() == str(publish_date.day):
                await day_element.click()
                break
        # time set
        await scheduled_picker.locator('div.TUXInputBox').nth(0).click()

        hour_str = publish_date.strftime("%H")
        correct_minute = int(publish_date.minute / 5)
        minute_str = f"{correct_minute:02d}"

        hour_selector = f"span.tiktok-timepicker-left:has-text('{hour_str}')"
        minute_selector = f"span.tiktok-timepicker-right:has-text('{minute_str}')"

        # pick hour first
        await self.locator_base.locator(hour_selector).click()
        # click time button again
        # 等待某个特定的元素出现或状态变化，表明UI已更新
        await page.wait_for_timeout(1000)  # 等待500毫秒
        await scheduled_picker.locator('div.TUXInputBox').nth(0).click()
        # pick minutes after
        await self.locator_base.locator(minute_selector).click()

        # click title to remove the focus.
        await self.locator_base.locator("h1:has-text('Upload video')").click()

    async def handle_upload_error(self, page):
        tiktok_logger.info("video upload error retrying.")
        select_file_button = self.locator_base.locator('button[aria-label="Select file"]')
        async with page.expect_file_chooser() as fc_info:
            await select_file_button.click()
        file_chooser = await fc_info.value
        await file_chooser.set_files(self.file_path)

    async def add_title_tags(self, page):

        editor_locator = self.locator_base.locator('div.public-DraftEditor-content')
        await editor_locator.click()

        await page.keyboard.press("End")

        await page.keyboard.press("Control+A")

        await page.keyboard.press("Delete")

        await page.keyboard.press("End")

        await page.wait_for_timeout(1000)  # 等待1秒

        await page.keyboard.insert_text(self.title)
        await page.wait_for_timeout(1000)  # 等待1秒
        await page.keyboard.press("End")

        await page.keyboard.press("Enter")

        # tag part
        for index, tag in enumerate(self.tags, start=1):
            tiktok_logger.info("Setting the %s tag" % index)
            await page.keyboard.press("End")
            await page.wait_for_timeout(1000)  # 等待1秒
            await page.keyboard.insert_text("#" + tag + " ")
            await page.keyboard.press("Space")
            await page.wait_for_timeout(1000)  # 等待1秒

            await page.keyboard.press("Backspace")
            await page.keyboard.press("End")

    async def click_publish(self, page):
        success_flag_div = '#\\:r9\\:'
        while True:
            try:
                publish_button = self.locator_base.locator('div.btn-post')
                if await publish_button.count():
                    await publish_button.click()

                await self.locator_base.locator(success_flag_div).wait_for(state="visible", timeout=3000)
                tiktok_logger.success("  [-] video published success")
                break
            except Exception as e:
                if await self.locator_base.locator(success_flag_div).count():
                    tiktok_logger.success("  [-]video published success")
                    break
                else:
                    tiktok_logger.exception(f"  [-] Exception: {e}")
                    tiktok_logger.info("  [-] video publishing")
                    await page.screenshot(full_page=True)
                    await asyncio.sleep(0.5)

    async def detect_upload_status(self, page):
        while True:
            try:
                if await self.locator_base.locator('div.btn-post > button').get_attribute("disabled") is None:
                    tiktok_logger.info("  [-]video uploaded.")
                    break
                else:
                    tiktok_logger.info("  [-] video uploading...")
                    await asyncio.sleep(2)
                    if await self.locator_base.locator('button[aria-label="Select file"]').count():
                        tiktok_logger.info("  [-] found some error while uploading now retry...")
                        await self.handle_upload_error(page)
            except:
                tiktok_logger.info("  [-] video uploading...")
                await asyncio.sleep(2)

    async def choose_base_locator(self, page):
        # await page.wait_for_selector('div.upload-container')
        if await page.locator('iframe[data-tt="Upload_index_iframe"]').count():
            self.locator_base = self.locator_base
        else:
            self.locator_base = page.locator(Tk_Locator.default)


async def _is_tiktok_auth_page_valid(page: Page) -> bool:
    """tk 登录页检测 - 保留原逻辑"""
    current_url = (page.url or "").lower()
    if any(marker in current_url for marker in TiktokVideo.LOGIN_MARKERS):
        return False

    login_markers = [
        page.locator('select[class*="SelectFormContainer"]').first,
        page.locator('a[href*="/login"]').first,
    ]
    for marker in login_markers:
        if await _is_tiktok_locator_visible(marker):
            return False

    upload_markers = [
        page.locator('button:has-text("Select video")').first,
        page.locator('button[aria-label="Select file"]').first,
        page.locator("div.upload-container").first,
    ]
    return any([await _is_tiktok_locator_visible(marker) for marker in upload_markers])


async def _is_tiktok_locator_visible(locator) -> bool:
    try:
        if not await locator.count():
            return False
        return await locator.is_visible()
    except Exception:
        return False


# Module-level wrappers for dispatch.py compatibility
async def cookie_auth(account_file):
    return await TiktokVideo.cookie_auth(account_file)


async def tiktok_setup(account_file, handle=False, return_detail=False, qrcode_callback=None, headless=LOCAL_CHROME_HEADLESS):
    return await TiktokVideo.setup(account_file, handle, return_detail, qrcode_callback, headless)
