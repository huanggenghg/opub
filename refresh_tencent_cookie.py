"""刷新微信视频号 cookie:加载现有 cookie,导航到上传页,等 publish marker 出现后重存。

用于 login_tencent.py 只存到 2 个 cookie 的情况。如果现有 sessionid 还有效,
不需要重新扫码。纯 DOM 等待,不截图不发模型。
"""
import asyncio
import json
from pathlib import Path
from patchright.async_api import async_playwright

ACCOUNT_FILE = "cookies/tencent_uploader/account.json"
TENCENT_UPLOAD_URL = "https://channels.weixin.qq.com/platform/post/create"


async def main():
    if not Path(ACCOUNT_FILE).exists():
        print(f"❌ cookie 文件不存在: {ACCOUNT_FILE}")
        print("   请先运行 python login_tencent.py 扫码登录")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, channel="chrome")
        context = await browser.new_context(storage_state=ACCOUNT_FILE)
        page = await context.new_page()

        print("=== 加载现有 cookie,导航到上传页 ===")
        await page.goto(TENCENT_UPLOAD_URL, timeout=30000)
        await asyncio.sleep(2)
        print(f"  当前 URL: {page.url}")

        if "login.html" in page.url:
            print(f"  ❌ session 已失效,被重定向到登录页")
            print(f"     请重新运行 python login_tencent.py 扫码登录")
            await browser.close()
            return

        # 等 publish marker 出现,确保页面完整加载
        publish_markers = [
            'div:has-text("发表视频")',
            'button:has-text("发表")',
            'button:has-text("保存草稿")',
        ]
        marker_found = False
        for sel in publish_markers:
            try:
                loc = page.locator(sel).first
                await loc.wait_for(state="visible", timeout=30000)
                print(f"  ✅ 检测到 publish marker: {sel}")
                marker_found = True
                break
            except Exception:
                continue

        if not marker_found:
            print(f"  ⚠️ 30s 内未检测到 publish marker")
            body_text = await page.evaluate("document.body.innerText.slice(0, 300)")
            print(f"  body 文本前 300 字符: {body_text!r}")

        await context.storage_state(path=ACCOUNT_FILE)

        with open(ACCOUNT_FILE) as f:
            cookie_data = json.load(f)
        print(f"  存了 {len(cookie_data.get('cookies', []))} 个 cookie")
        for c in cookie_data.get("cookies", []):
            print(f"    - {c.get('name')} (domain={c.get('domain')})")

        if marker_found:
            print(f"\n✅ cookie 已刷新且 publish marker 已出现: {ACCOUNT_FILE}")
        else:
            print(f"\n⚠️ cookie 已保存但 marker 未出现,可能仍不完整")

        await browser.close()


asyncio.run(main())
