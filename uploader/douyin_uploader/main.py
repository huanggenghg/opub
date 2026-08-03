# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime

import asyncio
import os
import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from patchright.async_api import Page
from patchright.async_api import async_playwright

from conf import DEBUG_MODE, LOCAL_CHROME_HEADLESS
from uploader.base_video import (
    BaseBrowserUploader,
    PlatformResultExtras,
    _build_launch_kwargs,
    _build_login_result,
    _emit_qrcode_callback,
    _get_qrcode_utils,
    _msg,
)
from utils.base_social_media import set_init_script
from utils.log import douyin_logger
from utils.excel_writer import write_video_link

DOUYIN_PUBLISH_STRATEGY_IMMEDIATE = "immediate"
DOUYIN_PUBLISH_STRATEGY_SCHEDULED = "scheduled"
DOUYIN_UPLOAD_URL = "https://creator.douyin.com/creator-micro/content/upload"
DOUYIN_LOGIN_URL = "https://creator.douyin.com/"
DOUYIN_LOGIN_URL_MARKERS = ("login", "passport")


def extract_video_id_from_url(url: str) -> str | None:
    """
    从URL中提取视频ID (modal_id)

    Args:
        url: URL字符串

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
        video_id: 视频ID

    Returns:
        str: 视频链接
    """
    return f"https://www.douyin.com/video/{video_id}"


class DouyinPublishRestrictedError(Exception):
    """抖音账号被限制发布(如健康分不足)时抛出。"""
    def __init__(self, toast_text: str):
        self.toast_text = toast_text
        super().__init__(f"账号被限制发布: {toast_text}")


async def _check_douyin_publish_restriction(page: Page, timeout_ms: int = 2000) -> str | None:
    """set_input_files 后检查是否出现限制 toast。返回 toast 文本,无则 None。"""
    toast = page.locator('.semi-toast-error').first
    try:
        await toast.wait_for(state="visible", timeout=timeout_ms)
        text = await toast.inner_text()
        return text.strip() or None
    except Exception:
        return None


async def _wait_for_douyin_publish_marker(page: Page, timeout_ms: int = 20000) -> None:
    """等上传页 publish 标记渲染。超时静默返回,由 _is_douyin_auth_page_valid 兜底判定。"""
    try:
        await page.get_by_text("发布视频", exact=True).first.wait_for(state="visible", timeout=timeout_ms)
    except Exception:
        pass


async def cookie_auth(account_file):
    """验证 cookie 是否有效 - 委托 DouYinBaseUploader.cookie_auth"""
    return await DouYinBaseUploader.cookie_auth(account_file)


async def _is_douyin_locator_visible(locator) -> bool:
    try:
        if not await locator.count():
            return False
        return await locator.is_visible()
    except Exception:
        return False


async def _is_douyin_auth_page_valid(page: Page) -> bool:
    current_url = (page.url or "").lower()
    if not current_url.startswith(DOUYIN_UPLOAD_URL):
        return False
    if any(marker in current_url for marker in DOUYIN_LOGIN_URL_MARKERS):
        return False

    login_markers = [
        page.get_by_text("手机号登录").first,
        page.get_by_text("扫码登录").first,
        page.get_by_role("img", name="二维码").first,
    ]
    for marker in login_markers:
        if await _is_douyin_locator_visible(marker):
            return False

    publish_markers = [
        page.get_by_text("发布视频", exact=True).first,
        page.get_by_text("发布图文", exact=True).first,
        page.locator('input[type="file"]').first,
    ]
    return any([await _is_douyin_locator_visible(marker) for marker in publish_markers])


async def douyin_setup(account_file, handle=False, return_detail=False, qrcode_callback=None, headless: bool = LOCAL_CHROME_HEADLESS):
    if not os.path.exists(account_file) or not await cookie_auth(account_file):
        if not handle:
            result = _build_login_result(False, "cookie_invalid", "cookie文件不存在或已失效", account_file)
            return result if return_detail else False
        douyin_logger.info(_msg("🥹", "cookie 失效了，准备打开浏览器重新登录"))
        result = await douyin_cookie_gen(account_file, qrcode_callback=qrcode_callback, headless=headless)
        return result if return_detail else result["success"]

    result = _build_login_result(True, "cookie_valid", "cookie有效", account_file)
    return result if return_detail else True


async def _extract_douyin_qrcode_src(page: Page) -> str:
    scan_login_tab = page.get_by_text("扫码登录", exact=True).first
    await scan_login_tab.wait_for(timeout=60000)  # 增加到60秒，页面加载慢

    qrcode_img = (
        scan_login_tab
        .locator("..")
        .locator("xpath=following-sibling::div[1]")
        .locator('img[aria-label="二维码"]')
        .first
    )

    if not await qrcode_img.count():
        qrcode_img = page.get_by_role("img", name="二维码").first

    await qrcode_img.wait_for(state="visible", timeout=30000)
    src = await qrcode_img.get_attribute("src")
    if not src:
        raise RuntimeError("未获取到抖音登录二维码地址")

    return src


async def _save_douyin_qrcode(page: Page, account_file: str, previous_qrcode_path: Path | None = None, qrcode_callback=None) -> dict:
    qrcode_utils = _get_qrcode_utils()
    qrcode_src = await _extract_douyin_qrcode_src(page)
    qrcode_path = qrcode_utils["save_data_url_image"](
        qrcode_src,
        qrcode_utils["build_login_qrcode_path"](account_file),
    )
    if previous_qrcode_path and previous_qrcode_path != qrcode_path:
        if qrcode_utils["remove_qrcode_file"](previous_qrcode_path):
            douyin_logger.info(_msg("🧹", f"临时二维码文件已清理: {previous_qrcode_path}"))
    douyin_logger.info(_msg("🖼️", f"二维码已经准备好啦，已保存到: {qrcode_path}"))
    qrcode_content = qrcode_utils["decode_qrcode_from_path"](qrcode_path)
    if qrcode_content:
        qrcode_utils["print_terminal_qrcode"](qrcode_content, qrcode_path, "抖音APP")
    else:
        douyin_logger.warning(_msg("😵", f"终端没法完整显示二维码，请打开 {qrcode_path} 扫码"))
    qrcode_info = {
        "image_path": str(qrcode_path),
        "image_data_url": qrcode_src,
    }
    await _emit_qrcode_callback(qrcode_callback, qrcode_info)
    return qrcode_info


async def _is_douyin_login_completed(page: Page) -> bool:
    if not page.url.startswith("https://creator.douyin.com/creator-micro/home"):
        return False

    login_markers = [
        page.get_by_text("扫码登录", exact=True).first,
        page.get_by_text("手机号登录", exact=True).first,
        page.get_by_text("二维码失效", exact=True).first,
        page.get_by_role("img", name="二维码").first,
    ]

    for marker in login_markers:
        if not await marker.count():
            continue
        try:
            if await marker.is_visible():
                return False
        except Exception:
            continue

    return True


async def _wait_for_douyin_login(page: Page, account_file: str, qrcode_info: dict, qrcode_callback=None, poll_interval: int = 3, max_checks: int = 100) -> dict:
    qrcode_path = Path(qrcode_info["image_path"])
    for _ in range(max_checks):
        if await _is_douyin_login_completed(page):
            douyin_logger.info(_msg("🥳", f"扫码成功，已经跳转到登录后页面: {page.url}"))
            return _build_login_result(True, "success", "抖音扫码登录成功", account_file, qrcode_info, page.url)

        expired_box = page.get_by_text("二维码失效", exact=True).locator("..").first
        if await expired_box.count() and await expired_box.is_visible():
            douyin_logger.warning(_msg("😵", "二维码失效了，小人马上去刷新"))
            await expired_box.click()
            await asyncio.sleep(1)
            qrcode_info = await _save_douyin_qrcode(page, account_file, qrcode_path, qrcode_callback=qrcode_callback)
            qrcode_path = Path(qrcode_info["image_path"])

        await asyncio.sleep(poll_interval)

    return _build_login_result(False, "timeout", "等待抖音扫码登录超时", account_file, qrcode_info, page.url)


async def douyin_cookie_gen(
    account_file,
    qrcode_callback=None,
    poll_interval: int = 3,
    max_checks: int = 100,
    headless: bool = LOCAL_CHROME_HEADLESS,
):
    qrcode_utils = _get_qrcode_utils()
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(**_build_launch_kwargs(headless))
        context = await browser.new_context()
        context = await set_init_script(context)
        qrcode_path = None
        result = _build_login_result(False, "failed", "抖音登录失败", account_file)
        try:
            page = await context.new_page()
            await page.goto(DOUYIN_LOGIN_URL)
            qrcode_info = await _save_douyin_qrcode(page, account_file, qrcode_callback=qrcode_callback)
            qrcode_path = Path(qrcode_info["image_path"])
            douyin_logger.info(_msg("🧍", "请扫码，小人正在耐心等待登录完成"))
            result = await _wait_for_douyin_login(
                page,
                account_file,
                qrcode_info,
                qrcode_callback=qrcode_callback,
                poll_interval=poll_interval,
                max_checks=max_checks,
            )
            if result["success"]:
                await asyncio.sleep(2)
                await context.storage_state(path=account_file)
                if not await cookie_auth(account_file):
                    result = _build_login_result(
                        False,
                        "cookie_invalid",
                        "抖音扫码流程结束，但 cookie 校验失败",
                        account_file,
                        qrcode_info,
                        page.url,
                    )
        except Exception as exc:
            result = _build_login_result(False, "failed", str(exc), account_file, current_url=page.url if "page" in locals() else "")
        finally:
            if qrcode_utils["remove_qrcode_file"](qrcode_path):
                douyin_logger.info(_msg("🧹", f"临时二维码文件已清理: {qrcode_path}"))
            if not result["success"]:
                douyin_logger.error(_msg("😢", f"登录失败: {result['message']}"))
            await context.close()
            await browser.close()
        return result


class DouYinBaseUploader(BaseBrowserUploader):
    """抖音上传器基类 - hook layer for BaseBrowserUploader."""

    PLATFORM_NAME = "douyin"
    UPLOAD_URL = DOUYIN_UPLOAD_URL
    LOGIN_URL = DOUYIN_LOGIN_URL
    LOGIN_MARKERS = list(DOUYIN_LOGIN_URL_MARKERS)
    PUBLISH_MARKERS = ["发布视频", "发布图文"]

    def __init__(
        self,
        publish_date: datetime | int,
        account_file,
        publish_strategy: str = DOUYIN_PUBLISH_STRATEGY_IMMEDIATE,
        debug: bool = DEBUG_MODE,
        headless: bool = LOCAL_CHROME_HEADLESS,
    ):
        self.publish_date = publish_date
        self.account_file = account_file
        self.publish_strategy = publish_strategy
        self.debug = debug
        self.date_format = "%Y年%m月%d日 %H:%M"
        self.headless = headless

    @classmethod
    async def cookie_auth(cls, account_file: str) -> bool:
        """Override: douyin cookie 校验需要等待 publish marker + DOM marker 检查。"""
        if not os.path.exists(account_file):
            return False
        async with async_playwright() as playwright:
            browser = await cls._launch_browser(playwright, headless=LOCAL_CHROME_HEADLESS)
            try:
                context = await cls._init_context(browser, account_file)
                page = await context.new_page()
                await page.goto(cls.UPLOAD_URL)
                try:
                    await page.wait_for_url(cls.UPLOAD_URL, timeout=5000)
                except Exception:
                    return False
                await _wait_for_douyin_publish_marker(page)
                return await _is_douyin_auth_page_valid(page)
            except Exception:
                return False
            finally:
                await browser.close()

    @classmethod
    async def is_login_completed(cls, page: Page) -> bool:
        """Override hook: douyin 登录完成判断(基于 URL + DOM marker)。"""
        return await _is_douyin_login_completed(page)

    @classmethod
    async def extract_qrcode_src(cls, page: Page):
        """Override hook: 从抖音登录页提取 QR 图片 src。"""
        return await _extract_douyin_qrcode_src(page)

    @classmethod
    async def _init_context(cls, browser, account_file=None):
        """Override: douyin 上传需要 geolocation 权限(用于 set_location)。"""
        permissions = ["geolocation"]
        if account_file and os.path.exists(account_file):
            context = await browser.new_context(permissions=permissions, storage_state=account_file)
        else:
            context = await browser.new_context(permissions=permissions)
        return await set_init_script(context)

    async def validate_login_and_strategy(self):
        """Renamed from `validate_base_args(self)` to avoid collision with
        `BasePlatformUploader.validate_base_args(params)` staticmethod (called by dispatch).
        Checks cookie existence/validity + publish_strategy + publish_date."""
        if not os.path.exists(self.account_file):
            raise RuntimeError(f"cookie文件不存在，请先完成抖音登录: {self.account_file}")
        if not await cookie_auth(self.account_file):
            raise RuntimeError(f"cookie文件已失效，请先完成抖音登录: {self.account_file}")
        if self.publish_strategy not in {DOUYIN_PUBLISH_STRATEGY_IMMEDIATE, DOUYIN_PUBLISH_STRATEGY_SCHEDULED}:
            raise ValueError(f"不支持的发布策略: {self.publish_strategy}")

        if self.publish_strategy == DOUYIN_PUBLISH_STRATEGY_SCHEDULED:
            self.publish_date = self.validate_publish_date(self.publish_date)
        else:
            self.publish_date = 0

    async def set_schedule_time_douyin(self, page, publish_date):
        label_element = page.locator("[class^='radio']:has-text('定时发布')")
        await label_element.click()
        await asyncio.sleep(1)
        publish_date_hour = publish_date.strftime("%Y-%m-%d %H:%M")

        await asyncio.sleep(1)
        await page.locator('.semi-input[placeholder="日期和时间"]').click()
        await page.keyboard.press("Control+KeyA")
        await page.keyboard.type(str(publish_date_hour))
        await page.keyboard.press("Enter")
        await asyncio.sleep(1)

    async def fill_title_and_description(self, page: Page, title: str, description: str, tags: list[str] | None = None):
        description_section = (
            page.get_by_text("作品描述", exact=True)
            .locator("xpath=ancestor::div[2]")
            .locator("xpath=following-sibling::div[1]")
        )

        title_input = description_section.locator('input[type="text"]').first
        await title_input.wait_for(state="visible", timeout=10000)
        await title_input.fill(title[:30])

        description_editor = description_section.locator('.zone-container[contenteditable="true"]').first
        await description_editor.wait_for(state="visible", timeout=10000)
        await description_editor.click()
        await page.keyboard.press("Control+KeyA")
        await page.keyboard.press("Delete")
        await page.keyboard.type(description)

        for tag in tags or []:
            await page.keyboard.type(" #" + tag)
            await page.keyboard.press("Space")

    async def set_location(self, page: Page, location: str = ""):
        if not location:
            return
        await page.locator('div.semi-select span:has-text("输入地理位置")').click()
        await page.keyboard.press("Backspace")
        await page.wait_for_timeout(2000)
        await page.keyboard.type(location)
        await page.wait_for_selector('div[role="listbox"] [role="option"]', timeout=5000)
        await page.locator('div[role="listbox"] [role="option"]').first.click()

    async def handle_product_dialog(self, page: Page, product_title: str):
        await page.wait_for_timeout(2000)
        await page.wait_for_selector('input[placeholder="请输入商品短标题"]', timeout=10000)
        short_title_input = page.locator('input[placeholder="请输入商品短标题"]')
        if not await short_title_input.count():
            douyin_logger.error(_msg("😵", "没找到商品短标题输入框"))
            return False

        product_title = product_title[:10]
        await short_title_input.fill(product_title)
        await page.wait_for_timeout(1000)

        finish_button = page.locator('button:has-text("完成编辑")')
        if "disabled" not in await finish_button.get_attribute("class"):
            await finish_button.click()
            douyin_logger.debug(_msg("🥳", "已点击“完成编辑”按钮"))
            await page.wait_for_selector(".semi-modal-content", state="hidden", timeout=5000)
            return True

        douyin_logger.error(_msg("😵", "“完成编辑”按钮是灰的，小人先把弹窗关掉"))
        cancel_button = page.locator('button:has-text("取消")')
        if await cancel_button.count():
            await cancel_button.click()
        else:
            close_button = page.locator(".semi-modal-close")
            await close_button.click()
        await page.wait_for_selector(".semi-modal-content", state="hidden", timeout=5000)
        return False

    async def set_product_link(self, page: Page, product_link: str, product_title: str):
        await page.wait_for_timeout(2000)
        try:
            await page.wait_for_selector("text=添加标签", timeout=10000)
            dropdown = page.get_by_text("添加标签").locator("..").locator("..").locator("..").locator(".semi-select").first
            if not await dropdown.count():
                douyin_logger.error(_msg("😵", "没找到标签下拉框"))
                return False
            douyin_logger.debug(_msg("🧍", "找到标签下拉框，小人准备选择“购物车”"))
            await dropdown.click()
            await page.wait_for_selector('[role="listbox"]', timeout=5000)
            await page.locator('[role="option"]:has-text("购物车")').click()
            douyin_logger.debug(_msg("🥳", "已经选中“购物车”"))

            await page.wait_for_selector('input[placeholder="粘贴商品链接"]', timeout=5000)
            input_field = page.locator('input[placeholder="粘贴商品链接"]')
            await input_field.fill(product_link)
            douyin_logger.debug(_msg("🔗", f"商品链接已经填好了: {product_link}"))

            add_button = page.locator('span:has-text("添加链接")')
            button_class = await add_button.get_attribute("class")
            if "disable" in button_class:
                douyin_logger.error(_msg("😵", "“添加链接”按钮现在点不了"))
                return False
            await add_button.click()
            douyin_logger.debug(_msg("🥳", "已点击“添加链接”按钮"))

            await page.wait_for_timeout(2000)
            error_modal = page.locator("text=未搜索到对应商品")
            if await error_modal.count():
                confirm_button = page.locator('button:has-text("确定")')
                await confirm_button.click()
                douyin_logger.error(_msg("😢", "这个商品链接无效"))
                return False

            if not await self.handle_product_dialog(page, product_title):
                return False

            douyin_logger.debug(_msg("🥳", "商品链接设置好了"))
            return True
        except Exception as e:
            douyin_logger.error(_msg("😢", f"设置商品链接时出错: {str(e)}"))
            return False


class DouYinVideo(DouYinBaseUploader):
    def __init__(
        self,
        title,
        file_path,
        tags,
        publish_date: datetime | int,
        account_file,
        thumbnail_landscape_path=None,
        productLink="",
        productTitle="",
        thumbnail_portrait_path=None,
        desc: str | None = None,
        publish_strategy: str = DOUYIN_PUBLISH_STRATEGY_IMMEDIATE,
        debug: bool = DEBUG_MODE,
        headless: bool = LOCAL_CHROME_HEADLESS,
    ):
        super().__init__(
            publish_date=publish_date,
            account_file=account_file,
            publish_strategy=publish_strategy,
            debug=debug,
            headless=headless,
        )
        self.title = title
        self.file_path = file_path
        self.tags = tags
        self.thumbnail_landscape_path = thumbnail_landscape_path
        self.thumbnail_portrait_path = thumbnail_portrait_path
        self.productLink = productLink
        self.productTitle = productTitle
        self.desc = desc or ""

    async def validate_upload_args(self):
        await self.validate_login_and_strategy()
        if not self.title or not str(self.title).strip():
            raise ValueError("视频模式下，title 是必须的")

        self.file_path = str(self.validate_video_file(self.file_path))
        if self.thumbnail_landscape_path:
            self.thumbnail_landscape_path = str(self.validate_image_file(self.thumbnail_landscape_path))
        if self.thumbnail_portrait_path:
            self.thumbnail_portrait_path = str(self.validate_image_file(self.thumbnail_portrait_path))

    async def handle_upload_error(self, page):
        douyin_logger.warning(_msg("😵", "视频上传摔了一跤，小人马上重新上传"))
        await page.locator('div.progress-div [class^="upload-btn-input"]').set_input_files(self.file_path)

    async def handle_auto_video_cover(self, page):
        if await page.get_by_text("请设置封面后再发布").first.is_visible():
            douyin_logger.info(_msg("🧍", "发布前还得先把封面弄好"))
            recommend_cover = page.locator('[class^="recommendCover-"]').first
            if await recommend_cover.count():
                douyin_logger.info(_msg("🏃", "小人去选第一个推荐封面"))
                try:
                    await recommend_cover.click()
                    await asyncio.sleep(1)
                    confirm_text = "是否确认应用此封面？"
                    if await page.get_by_text(confirm_text).first.is_visible():
                        douyin_logger.info(_msg("🪟", f"弹出确认框了: {confirm_text}"))
                        await page.get_by_role("button", name="确定").click()
                        douyin_logger.info(_msg("🥳", "推荐封面已经应用"))
                        await asyncio.sleep(1)
                    douyin_logger.info(_msg("🥳", "封面选择流程完成"))
                    return True
                except Exception as e:
                    douyin_logger.warning(_msg("😵", f"推荐封面没选成功: {e}"))
        return False

    async def set_thumbnail(self, page: Page):
        if not self.thumbnail_landscape_path and not self.thumbnail_portrait_path:
            return

        douyin_logger.info(_msg("🏃", "小人正在设置视频封面"))
        await page.click('text="选择封面"')
        cover_locator_str = 'div[id*="creator-content-modal"]'
        cover_locator = page.locator(cover_locator_str)
        await page.wait_for_selector(cover_locator_str)

        upload_input = cover_locator.locator("div[class^='semi-upload upload'] >> input.semi-upload-hidden-input")

        if self.thumbnail_landscape_path:
            await page.wait_for_timeout(1000)
            await upload_input.set_input_files(self.thumbnail_landscape_path)
            await page.wait_for_timeout(2000)
            douyin_logger.info(_msg("🖼️", "横版封面上传完成"))

        if self.thumbnail_portrait_path:
            await cover_locator.locator("div[class*='steps'] div").nth(1).click()
            await page.wait_for_timeout(1000)
            await upload_input.set_input_files(self.thumbnail_portrait_path)
            await page.wait_for_timeout(2000)
            douyin_logger.info(_msg("🖼️", "竖版封面上传完成"))

        await cover_locator.locator('button:visible:has-text("完成")').click()
        douyin_logger.info(_msg("🥳", "视频封面设置完成"))
        await page.wait_for_selector("div.extractFooter", state="detached")

    async def upload_video_content(self, page: Page) -> str | None:
        """上传视频内容(页面已通过 _browser_session 打开)。返回视频链接或 None。"""
        douyin_logger.info(_msg("🏃", f"小人开始搬运视频: {self.title}.mp4"))
        douyin_logger.info(_msg("🧭", "小人正在赶往上传主页"))
        await page.goto(DOUYIN_UPLOAD_URL)
        await page.wait_for_url(DOUYIN_UPLOAD_URL)
        await page.locator("div[class^='container'] input").set_input_files(self.file_path)

        restriction_text = await _check_douyin_publish_restriction(page)
        if restriction_text:
            raise DouyinPublishRestrictedError(restriction_text)

        while True:
            try:
                await page.wait_for_url(
                    "https://creator.douyin.com/creator-micro/content/publish?enter_from=publish_page",
                    timeout=3000,
                )
                douyin_logger.info(_msg("🥳", "已经进入 version_1 发布页面"))
                break
            except Exception:
                try:
                    await page.wait_for_url(
                        "https://creator.douyin.com/creator-micro/content/post/video?enter_from=publish_page",
                        timeout=3000,
                    )
                    douyin_logger.info(_msg("🥳", "已经进入 version_2 发布页面"))
                    break
                except Exception:
                    douyin_logger.debug(_msg("🧍", "还没进到视频发布页面，小人继续等一会"))
                    await asyncio.sleep(0.5)

        await asyncio.sleep(1)
        douyin_logger.info(_msg("✍️", "小人开始填标题、描述和话题"))
        await self.fill_title_and_description(page, self.title, self.desc or self.title, self.tags)
        douyin_logger.info(_msg("🏷️", f"小人一共贴了 {len(self.tags)} 个话题"))

        while True:
            try:
                number = await page.locator('[class^="long-card"] div:has-text("重新上传")').count()
                if number > 0:
                    douyin_logger.success(_msg("🥳", "视频已经传完啦"))
                    break
                douyin_logger.info(_msg("🏃", "小人正在努力上传视频"))
                await asyncio.sleep(2)
                if await page.locator('div.progress-div > div:has-text("上传失败")').count():
                    douyin_logger.error(_msg("😵", "检测到上传失败，小人准备重试"))
                    await self.handle_upload_error(page)
            except Exception:
                douyin_logger.debug(_msg("🧍", "小人还在等视频上传完成"))
                await asyncio.sleep(2)

        if self.productLink and self.productTitle:
            douyin_logger.info(_msg("🛒", "小人正在设置商品链接"))
            await self.set_product_link(page, self.productLink, self.productTitle)
            douyin_logger.info(_msg("🥳", "商品链接设置完成"))

        await self.set_thumbnail(page)

        third_part_element = '[class^="info"] > [class^="first-part"] div div.semi-switch'
        if await page.locator(third_part_element).count():
            if "semi-switch-checked" not in await page.eval_on_selector(third_part_element, "div => div.className"):
                await page.locator(third_part_element).locator("input.semi-switch-native-control").click()

        if self.publish_strategy == DOUYIN_PUBLISH_STRATEGY_SCHEDULED and self.publish_date != 0:
            await self.set_schedule_time_douyin(page, self.publish_date)

        while True:
            try:
                publish_button = page.get_by_role("button", name="发布", exact=True)
                if await publish_button.count():
                    await publish_button.click()
                await page.wait_for_url(
                    "https://creator.douyin.com/creator-micro/content/manage**",
                    timeout=3000,
                )
                douyin_logger.success(_msg("🥳", "视频发布成功，小人开心收工"))

                # 发布成功后获取视频链接并写入Excel
                video_link = await self._get_video_link(page)
                if video_link:
                    douyin_logger.info(_msg("🔗", f"视频链接: {video_link}"))
                    excel_result = write_video_link(video_link=video_link)
                    if excel_result["success"]:
                        douyin_logger.success(_msg("📝", f"已写入Excel: {excel_result['filepath']}"))
                    else:
                        douyin_logger.warning(_msg("⚠️", f"写入Excel失败: {excel_result['message']}"))
                else:
                    douyin_logger.warning(_msg("⚠️", "未能获取视频链接"))

                return video_link
            except Exception:
                await self.handle_auto_video_cover(page)
                douyin_logger.info(_msg("🏃", "小人正在冲刺发布视频"))
                if self.debug:
                    await page.screenshot(full_page=True)
                await asyncio.sleep(0.5)

    async def upload(self) -> PlatformResultExtras:
        """主入口，返回 PlatformResultExtras。捕获 DouyinPublishRestrictedError 映射为 account_issue。"""
        douyin_logger.info(_msg("🧍", "小人先检查 cookie、视频文件、封面和发布时间"))
        await self.validate_upload_args()
        douyin_logger.info(_msg("🥳", "上传前检查通过"))

        result: PlatformResultExtras = {"success": False, "message": ""}

        try:
            async with self._browser_session() as page:
                video_link = await self.upload_video_content(page)
                result["success"] = True
                if video_link:
                    result["result_url"] = video_link
                    result["message"] = f"发布成功，视频链接: {video_link}"
                else:
                    result["message"] = "发布成功"
            douyin_logger.success(_msg("🥳", "cookie 更新完毕"))
        except DouyinPublishRestrictedError as exc:
            result["message"] = f"账号被限制发布: {exc.toast_text}"
            result["account_issue"] = True
            result["issue_type"] = "publish_restricted"
            douyin_logger.error(_msg("😢", f"账号被限制发布: {exc.toast_text}"))
        except Exception as e:
            result["message"] = str(e)
            douyin_logger.error(_msg("❌", f"上传失败: {e}"))

        return result

    async def _get_video_link(self, page: Page) -> str | None:
        """
        发布成功后获取视频链接

        Args:
            page: Playwright页面对象

        Returns:
            str | None: 视频链接，如 "https://www.douyin.com/video/7637405747755732270"
        """
        try:
            # 导航到用户首页获取最新发布的视频链接
            douyin_logger.info(_msg("🧭", "正在导航到用户首页获取视频链接"))
            await page.goto("https://www.douyin.com/user/self?from_tab_name=main", timeout=30000)
            await page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(2)

            # 点击第一个视频
            first_video = page.locator("div[data-e2e='user-post-list'] a:first-child").first
            if await first_video.count():
                await first_video.click()
                await asyncio.sleep(2)

                # 从URL提取视频ID
                current_url = page.url
                video_id = extract_video_id_from_url(current_url)

                if video_id:
                    return build_video_link(video_id)

            return None
        except Exception as e:
            douyin_logger.warning(_msg("⚠️", f"获取视频链接失败: {e}"))
            return None


class DouYinNote(DouYinBaseUploader):
    def __init__(
        self,
        image_paths,
        note,
        tags,
        publish_date: datetime | int,
        account_file,
        title: str | None = None,
        publish_strategy: str = DOUYIN_PUBLISH_STRATEGY_IMMEDIATE,
        debug: bool = DEBUG_MODE,
        headless: bool = LOCAL_CHROME_HEADLESS,
    ):
        super().__init__(
            publish_date=publish_date,
            account_file=account_file,
            publish_strategy=publish_strategy,
            debug=debug,
            headless=headless,
        )
        self.image_paths = image_paths
        self.note = note or ""
        self.title = title or (self.note[:30] if self.note else "")
        self.tags = tags or []

    async def validate_upload_args(self):
        await self.validate_login_and_strategy()
        if not self.title or not str(self.title).strip():
            raise ValueError("图文模式下，title 是必须的")
        if not self.image_paths:
            raise ValueError("图文模式下，图片是必须的")

        if isinstance(self.image_paths, (str, Path)):
            self.image_paths = [self.image_paths]

        if len(self.image_paths) > 35:
            raise ValueError("图文模式下最多只支持上传 35 张图片")

        normalized_image_paths = []
        for image_path in self.image_paths:
            normalized_image_paths.append(str(self.validate_image_file(image_path)))
        self.image_paths = normalized_image_paths

    async def upload_note_content(self, page: Page) -> None:
        douyin_logger.info(_msg("🏃", f"小人开始搬运图文，共 {len(self.image_paths)} 张图片"))
        douyin_logger.info(_msg("🔀", "小人正在切换到图文发布"))
        await page.get_by_text("发布图文", exact=True).click()
        await page.wait_for_timeout(1000)

        douyin_logger.info(_msg("📤", "小人正在上传图片"))
        await page.locator("div[class^='container'] input[accept*='image']").set_input_files(self.image_paths)

        restriction_text = await _check_douyin_publish_restriction(page)
        if restriction_text:
            raise DouyinPublishRestrictedError(restriction_text)

        while True:
            try:
                await page.wait_for_url(
                    "**/creator-micro/content/post/image?**",
                    timeout=3000,
                )
                douyin_logger.info(_msg("🥳", "已经进入图文发布页面"))
                break
            except Exception:
                douyin_logger.debug(_msg("🧍", "小人还在等图片上传完成"))
                await asyncio.sleep(0.5)

        await asyncio.sleep(1)
        douyin_logger.info(_msg("✍️", "小人开始填标题、描述和话题"))
        await self.fill_title_and_description(page, self.title, self.note, self.tags)
        douyin_logger.info(_msg("🏷️", f"小人一共贴了 {len(self.tags)} 个话题"))

        if self.publish_strategy == DOUYIN_PUBLISH_STRATEGY_SCHEDULED and self.publish_date != 0:
            await self.set_schedule_time_douyin(page, self.publish_date)

        while True:
            try:
                publish_button = page.get_by_role("button", name="发布", exact=True)
                if await publish_button.count():
                    await publish_button.click()
                await page.wait_for_url(
                    "**/creator-micro/content/manage?enter_from=publish**",
                    timeout=3000,
                )
                douyin_logger.success(_msg("🥳", "图文发布成功，小人开心收工"))
                break
            except Exception:
                douyin_logger.info(_msg("🏃", "小人正在冲刺发布图文"))
                await asyncio.sleep(0.5)

    async def upload(self) -> PlatformResultExtras:
        """主入口，返回 PlatformResultExtras。捕获 DouyinPublishRestrictedError 映射为 account_issue。"""
        douyin_logger.info(_msg("🧍", "小人先检查 cookie、图片和发布时间"))
        await self.validate_upload_args()
        douyin_logger.info(_msg("🥳", "图文上传前检查通过"))

        result: PlatformResultExtras = {"success": False, "message": ""}

        try:
            async with self._browser_session() as page:
                await page.goto(DOUYIN_UPLOAD_URL)
                douyin_logger.info(_msg("🧭", "小人正在赶往图文发布页"))
                await page.wait_for_url(DOUYIN_UPLOAD_URL)

                await self.upload_note_content(page)
                result["success"] = True
                result["message"] = "发布成功"
            douyin_logger.success(_msg("🥳", "cookie 更新完毕"))
        except DouyinPublishRestrictedError as exc:
            result["message"] = f"账号被限制发布: {exc.toast_text}"
            result["account_issue"] = True
            result["issue_type"] = "publish_restricted"
            douyin_logger.error(_msg("😢", f"账号被限制发布: {exc.toast_text}"))
        except Exception as e:
            result["message"] = str(e)
            douyin_logger.error(_msg("❌", f"上传失败: {e}"))

        return result
