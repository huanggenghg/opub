# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import inspect
import os
from datetime import datetime
from pathlib import Path

from patchright.async_api import Page
from patchright.async_api import Playwright
from patchright.async_api import async_playwright

from conf import BASE_DIR, DEBUG_MODE, LOCAL_CHROME_HEADLESS, LOCAL_CHROME_PATH
from uploader.base_video import BaseVideoUploader
from utils.base_social_media import set_init_script
from utils.log import weibo_logger

WEIBO_MAIN_URL = "https://weibo.com/"  # 微博主站，发布入口在首页
WEIBO_LOGIN_URL = "https://passport.weibo.com/sso/signin?entry=miniblog&source=miniblog&disp=popup&url=https%3A%2F%2Fweibo.com%2Fu%2F6569482075&from=weibopro"  # 登录页面
WEIBO_PUBLISH_URL = "https://weibo.com/"  # 发布入口在首页
WEIBO_PUBLISH_STRATEGY_IMMEDIATE = "immediate"
WEIBO_PUBLISH_STRATEGY_SCHEDULED = "scheduled"


def _msg(emoji: str, text: str) -> str:
    return f"{emoji} {text}"


def _resolve_account_file(account_file: str | Path) -> str:
    path = Path(account_file).expanduser()
    if path.is_absolute():
        return str(path)

    if len(path.parts) == 1:
        return str((Path(BASE_DIR) / "cookies" / "weibo_uploader" / path).resolve())

    return str(path.resolve())


async def _emit_qrcode_callback(qrcode_callback, payload: dict):
    if not qrcode_callback:
        return

    callback_result = qrcode_callback(payload)
    if inspect.isawaitable(callback_result):
        await callback_result


def _build_login_result(
    success: bool,
    status: str,
    message: str,
    account_file: str,
    qrcode: dict | None = None,
    current_url: str = "",
) -> dict:
    return {
        "success": success,
        "status": status,
        "message": message,
        "account_file": str(account_file),
        "qrcode": qrcode,
        "current_url": current_url,
    }


def _build_launch_kwargs(headless: bool) -> dict:
    launch_kwargs = {"headless": headless}
    if LOCAL_CHROME_PATH:
        launch_kwargs["executable_path"] = LOCAL_CHROME_PATH
    else:
        launch_kwargs["channel"] = "chrome"
    return launch_kwargs


def _get_qrcode_utils():
    from utils.login_qrcode import build_login_qrcode_path
    from utils.login_qrcode import decode_qrcode_from_path
    from utils.login_qrcode import print_terminal_qrcode
    from utils.login_qrcode import remove_qrcode_file
    from utils.login_qrcode import save_data_url_image

    return {
        "build_login_qrcode_path": build_login_qrcode_path,
        "decode_qrcode_from_path": decode_qrcode_from_path,
        "print_terminal_qrcode": print_terminal_qrcode,
        "remove_qrcode_file": remove_qrcode_file,
        "save_data_url_image": save_data_url_image,
    }


async def cookie_auth(account_file):
    """验证 cookie 是否有效"""
    account_file = _resolve_account_file(account_file)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(**_build_launch_kwargs(headless=True))
        try:
            context = await browser.new_context(storage_state=account_file)
            context = await set_init_script(context)
            page = await context.new_page()
            # 访问微博首页检查登录状态
            await page.goto(WEIBO_MAIN_URL)
            await page.wait_for_timeout(3000)

            # 检查是否有登录按钮（未登录状态）
            login_markers = [
                page.locator('text="登录"').first,
                page.locator('a[href*="login"]').first,
            ]

            for marker in login_markers:
                if await marker.count():
                    try:
                        if await marker.is_visible():
                            weibo_logger.info(_msg("🥹", "cookie 已失效，得重新登录一下"))
                            return False
                    except Exception:
                        continue

            weibo_logger.success(_msg("🥳", "cookie 有效"))
            return True
        except Exception as exc:
            weibo_logger.warning(_msg("😵", f"cookie 校验时出错，按失效处理: {exc}"))
            return False
        finally:
            await browser.close()


async def _is_weibo_login_completed(page: Page) -> bool:
    """检查微博登录是否完成"""
    # 检查 URL 是否跳转到微博主页（非登录页）
    if "passport.weibo.com" in page.url:
        return False

    # 检查是否还有登录相关元素
    login_markers = [
        page.locator('text="登录"').first,
        page.locator('text="扫码登录"').first,
    ]

    for marker in login_markers:
        if await marker.count():
            try:
                if await marker.is_visible():
                    return False
            except Exception:
                continue

    return True


async def weibo_cookie_gen(
    account_file,
    qrcode_callback=None,
    poll_interval: int = 3,
    max_checks: int = 100,
    headless: bool = LOCAL_CHROME_HEADLESS,
):
    """生成微博登录 cookie"""
    account_file = _resolve_account_file(account_file)
    Path(account_file).parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(**_build_launch_kwargs(headless=headless))
        context = await browser.new_context()
        context = await set_init_script(context)
        result = _build_login_result(False, "failed", "微博登录失败", account_file)

        try:
            page = await context.new_page()
            weibo_logger.info(_msg("🧭", f"正在访问登录页面: {WEIBO_LOGIN_URL}"))
            await page.goto(WEIBO_LOGIN_URL)
            await page.wait_for_timeout(3000)

            weibo_logger.info(_msg("🔍", f"当前页面 URL: {page.url}"))
            weibo_logger.info(_msg("🧍", "请扫码，等待登录完成..."))

            # 等待登录完成
            for _ in range(max_checks):
                if await _is_weibo_login_completed(page):
                    weibo_logger.info(_msg("🥳", f"扫码成功，已跳转到: {page.url}"))
                    result = _build_login_result(True, "success", "微博扫码登录成功", account_file, None, page.url)
                    break

                await page.wait_for_timeout(poll_interval * 1000)
            else:
                result = _build_login_result(False, "timeout", "等待微博扫码登录超时", account_file, None, page.url)

            # 登录成功后保存 cookie
            if result["success"]:
                await page.wait_for_timeout(2000)
                await context.storage_state(path=account_file)
                # 验证 cookie
                if not await cookie_auth(account_file):
                    result = _build_login_result(
                        False,
                        "cookie_invalid",
                        "微博扫码流程结束，但 cookie 校验失败",
                        account_file,
                        None,
                        page.url,
                    )

        except Exception as exc:
            result = _build_login_result(False, "failed", str(exc), account_file, current_url=page.url if "page" in locals() else "")
        finally:
            if not result["success"]:
                weibo_logger.error(_msg("😢", f"登录失败: {result['message']}"))
            await context.close()
            await browser.close()

        return result


async def weibo_setup(
    account_file,
    handle=False,
    return_detail=False,
    qrcode_callback=None,
    headless: bool = LOCAL_CHROME_HEADLESS,
):
    """微博登录设置"""
    account_file = _resolve_account_file(account_file)

    if not os.path.exists(account_file) or not await cookie_auth(account_file):
        if not handle:
            result = _build_login_result(False, "cookie_invalid", "cookie文件不存在或已失效", account_file)
            return result if return_detail else False

        weibo_logger.info(_msg("🥹", "cookie 失效了，准备打开浏览器重新登录"))
        result = await weibo_cookie_gen(account_file, qrcode_callback=qrcode_callback, headless=headless)
        return result if return_detail else result["success"]

    result = _build_login_result(True, "cookie_valid", "cookie有效", account_file)
    return result if return_detail else True


class WeiboBaseUploader(BaseVideoUploader):
    """微博上传器基类"""

    def __init__(
        self,
        publish_date: datetime | int,
        account_file,
        publish_strategy: str = WEIBO_PUBLISH_STRATEGY_IMMEDIATE,
        debug: bool = DEBUG_MODE,
        headless: bool = LOCAL_CHROME_HEADLESS,
    ):
        self.publish_date = publish_date
        self.account_file = _resolve_account_file(account_file)
        self.publish_strategy = publish_strategy
        self.debug = debug
        self.date_format = "%Y年%m月%d日 %H:%M"
        self.headless = headless

    async def validate_base_args(self):
        if not os.path.exists(self.account_file):
            raise RuntimeError(f"cookie文件不存在，请先完成微博登录: {self.account_file}")
        if not await cookie_auth(self.account_file):
            raise RuntimeError(f"cookie文件已失效，请先完成微博登录: {self.account_file}")

        if self.publish_strategy not in {
            WEIBO_PUBLISH_STRATEGY_IMMEDIATE,
            WEIBO_PUBLISH_STRATEGY_SCHEDULED,
        }:
            raise ValueError(f"不支持的发布策略: {self.publish_strategy}")

        if self.publish_strategy == WEIBO_PUBLISH_STRATEGY_SCHEDULED:
            self.publish_date = self.validate_publish_date(self.publish_date)
        else:
            self.publish_date = 0

    async def fill_content(self, page: Page, content: str, tags: list = None):
        """填写微博正文和话题"""
        weibo_logger.info(_msg("✍️", "正在填写微博内容..."))

        # 找到正文输入框
        content_input = page.locator('textarea[placeholder*="有什么新鲜事"], textarea[placeholder*="分享"], div[contenteditable="true"]').first
        await content_input.wait_for(state="visible", timeout=10000)
        await content_input.click()

        # 构建完整内容
        full_content = content
        if tags:
            tags_text = " ".join([f"#{tag}#" for tag in tags])
            full_content = f"{content}\n{tags_text}"

        # 输入内容
        await page.keyboard.type(full_content, delay=30)
        weibo_logger.success(_msg("✅", "内容填写完成"))

    async def set_schedule_time(self, page: Page, publish_date: datetime):
        """设置定时发布"""
        weibo_logger.info(_msg("🕒", f"设置定时发布时间: {publish_date.strftime(self.date_format)}"))

        # 查找定时发布按钮
        schedule_btn = page.locator('text="定时发布", button:has-text("定时")').first
        if await schedule_btn.count():
            await schedule_btn.click()
            await page.wait_for_timeout(1000)

            # 设置日期时间
            # 具体选择器需要根据实际页面调整
            date_input = page.locator('input[type="date"], input[placeholder*="日期"]').first
            if await date_input.count():
                await date_input.fill(publish_date.strftime("%Y-%m-%d"))

            time_input = page.locator('input[type="time"], input[placeholder*="时间"]').first
            if await time_input.count():
                await time_input.fill(publish_date.strftime("%H:%M"))

            # 确认
            confirm_btn = page.locator('button:has-text("确定"), button:has-text("确认")').first
            if await confirm_btn.count():
                await confirm_btn.click()

            weibo_logger.success(_msg("✅", "定时发布设置完成"))
        else:
            weibo_logger.warning(_msg("⚠️", "未找到定时发布按钮，可能不支持定时发布"))


class WeiboVideo(WeiboBaseUploader):
    """微博视频发布器"""

    def __init__(
        self,
        title: str,
        file_path: str,
        tags: list = None,
        publish_date: datetime | int = 0,
        account_file: str = "",
        desc: str | None = None,
        publish_strategy: str = WEIBO_PUBLISH_STRATEGY_IMMEDIATE,
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
        self.tags = tags or []
        self.desc = desc or ""

    async def validate_upload_args(self):
        await self.validate_base_args()
        if not self.title or not str(self.title).strip():
            raise ValueError("视频发布需要提供标题")

        self.file_path = str(self.validate_video_file(self.file_path))

    async def upload_video_content(self, page: Page) -> None:
        """上传视频内容"""
        weibo_logger.info(_msg("🏃", f"开始上传视频: {self.title}"))
        weibo_logger.info(_msg("🧭", "正在访问微博首页..."))

        await page.goto(WEIBO_PUBLISH_URL)
        await page.wait_for_timeout(3000)

        # 在首页找到发布面板，点击"视频"按钮
        weibo_logger.info(_msg("🔍", "查找发布面板中的视频入口..."))

        # 点击视频按钮
        video_btn = page.locator('div[class*="publish"] >> text="视频"').first
        if await video_btn.count():
            await video_btn.click()
            await page.wait_for_timeout(2000)
            weibo_logger.info(_msg("✅", "已点击视频按钮"))
        else:
            weibo_logger.warning(_msg("⚠️", "未找到视频按钮，尝试直接上传"))

        # 查找视频上传入口
        video_upload_selectors = [
            'input[type="file"][accept*="video"]',
            'input[type="file"][accept*=".mp4"]',
            'input[type="file"]',
        ]

        upload_input = None
        for selector in video_upload_selectors:
            count = await page.locator(selector).count()
            weibo_logger.info(_msg("🔍", f"选择器 {selector}: 找到 {count} 个"))
            if count:
                upload_input = page.locator(selector).first
                break

        if not upload_input:
            raise RuntimeError("未找到视频上传入口")

        await upload_input.set_input_files(self.file_path)
        weibo_logger.info(_msg("📤", "视频文件已选择，等待上传..."))

        # 等待上传完成
        max_wait = 300  # 最多等待5分钟
        for i in range(max_wait // 5):
            await page.wait_for_timeout(5000)

            # 检查上传状态
            if await page.locator('text="上传成功", text="上传完成", text="100%"').count():
                weibo_logger.success(_msg("🥳", "视频上传完成"))
                break

            if await page.locator('text="上传失败"').count():
                raise RuntimeError("视频上传失败")

            weibo_logger.info(_msg("⏳", f"视频上传中... ({i+1}/{max_wait//5})"))

        # 填写内容
        content = f"{self.title}\n{self.desc}" if self.desc else self.title
        await self.fill_content(page, content, self.tags)

        # 设置定时发布
        if self.publish_strategy == WEIBO_PUBLISH_STRATEGY_SCHEDULED and self.publish_date != 0:
            await self.set_schedule_time(page, self.publish_date)

        # 点击发送按钮
        weibo_logger.info(_msg("🚀", "正在发布..."))
        send_btn = page.locator('div[class*="publish"] >> text="发送"').first
        if await send_btn.count():
            await send_btn.click()
            await page.wait_for_timeout(3000)
            weibo_logger.success(_msg("🥳", "视频发布成功"))
        else:
            weibo_logger.warning(_msg("⚠️", "未找到发送按钮"))

    async def upload(self, playwright: Playwright) -> None:
        weibo_logger.info(_msg("🧍", "检查 cookie 和视频文件..."))
        await self.validate_upload_args()
        weibo_logger.info(_msg("🥳", "上传前检查通过"))

        browser = await playwright.chromium.launch(**_build_launch_kwargs(headless=self.headless))
        context = await browser.new_context(storage_state=self.account_file)
        context = await set_init_script(context)

        try:
            page = await context.new_page()
            await self.upload_video_content(page)
            await context.storage_state(path=self.account_file)
            weibo_logger.success(_msg("🥳", "cookie 更新完毕"))
        finally:
            await context.close()
            await browser.close()

    async def main(self):
        async with async_playwright() as playwright:
            await self.upload(playwright)


class WeiboNote(WeiboBaseUploader):
    """微博图文发布器"""

    def __init__(
        self,
        image_paths: list,
        note: str,
        tags: list = None,
        publish_date: datetime | int = 0,
        account_file: str = "",
        title: str | None = None,
        publish_strategy: str = WEIBO_PUBLISH_STRATEGY_IMMEDIATE,
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
        self.note = note
        self.tags = tags or []
        self.title = title or note[:50] if note else ""

    async def validate_upload_args(self):
        await self.validate_base_args()
        if not self.image_paths:
            raise ValueError("图文发布需要提供图片")

        if isinstance(self.image_paths, (str, Path)):
            self.image_paths = [self.image_paths]

        normalized_paths = []
        for img_path in self.image_paths:
            normalized_paths.append(str(self.validate_image_file(img_path)))
        self.image_paths = normalized_paths[:9]  # 微博最多9张图

    async def upload_note_content(self, page: Page) -> None:
        """上传图文内容"""
        weibo_logger.info(_msg("🏃", f"开始上传图文，共 {len(self.image_paths)} 张图片"))
        weibo_logger.info(_msg("🧭", "正在访问微博创作者中心..."))

        await page.goto(WEIBO_PUBLISH_URL)
        await page.wait_for_timeout(2000)

        # 查找图片上传入口
        image_upload_selectors = [
            'input[type="file"][accept*="image"]',
            'input[type="file"][accept*=".jpg"]',
            'input[type="file"][accept*=".png"]',
        ]

        upload_input = None
        for selector in image_upload_selectors:
            if await page.locator(selector).count():
                upload_input = page.locator(selector).first
                break

        if not upload_input:
            raise RuntimeError("未找到图片上传入口")

        # 上传图片
        await upload_input.set_input_files(self.image_paths)
        weibo_logger.info(_msg("📤", f"已选择 {len(self.image_paths)} 张图片，等待上传..."))

        # 等待图片上传完成
        max_wait = 120
        for _ in range(max_wait // 3):
            await page.wait_for_timeout(3000)

            # 检查是否有上传成功的图片预览
            if await page.locator('img[src*="blob"], img[src*="http"]').count() >= len(self.image_paths):
                weibo_logger.success(_msg("🥳", "图片上传完成"))
                break

            weibo_logger.info(_msg("⏳", "图片上传中..."))

        # 填写内容
        await self.fill_content(page, self.note, self.tags)

        # 设置定时发布
        if self.publish_strategy == WEIBO_PUBLISH_STRATEGY_SCHEDULED and self.publish_date != 0:
            await self.set_schedule_time(page, self.publish_date)

        # 点击发布
        weibo_logger.info(_msg("🚀", "正在发布..."))
        publish_btn = page.locator('button:has-text("发布"), button:has-text("发送")').first
        await publish_btn.click()
        await page.wait_for_timeout(3000)

        # 检查发布结果
        if await page.locator('text="发布成功", text="已发布"').count():
            weibo_logger.success(_msg("🥳", "图文发布成功"))
        else:
            weibo_logger.info(_msg("✅", "发布请求已提交"))

    async def upload(self, playwright: Playwright) -> None:
        weibo_logger.info(_msg("🧍", "检查 cookie 和图片文件..."))
        await self.validate_upload_args()
        weibo_logger.info(_msg("🥳", "上传前检查通过"))

        browser = await playwright.chromium.launch(**_build_launch_kwargs(headless=self.headless))
        context = await browser.new_context(storage_state=self.account_file)
        context = await set_init_script(context)

        try:
            page = await context.new_page()
            await self.upload_note_content(page)
            await context.storage_state(path=self.account_file)
            weibo_logger.success(_msg("🥳", "cookie 更新完毕"))
        finally:
            await context.close()
            await browser.close()

    async def main(self):
        async with async_playwright() as playwright:
            await self.upload(playwright)
