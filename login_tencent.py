"""微信视频号登录,cookie 直接存到 publish 流程期望的路径。

打开可见浏览器,用户扫码登录后,保存 storage_state 到
cookies/tencent_uploader/account.json。
"""
import asyncio
from pathlib import Path
from patchright.async_api import async_playwright

ACCOUNT_FILE = "cookies/tencent_uploader/account.json"
LOGIN_URL = "https://channels.weixin.qq.com"
MANAGE_URL = "https://channels.weixin.qq.com/platform/post/list"


async def main():
    Path(ACCOUNT_FILE).parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, channel="chrome")
        context = await browser.new_context()
        page = await context.new_page()

        print("=== 打开微信视频号登录页 ===")
        await page.goto(LOGIN_URL)
        print(f"  当前 URL: {page.url}")
        print("\n请在弹出的浏览器窗口里扫码登录微信视频号。")
        print("登录成功后脚本会自动检测并保存 cookie。\n")

        # 等待登录成功:URL 离开登录页即可
        logged_in = False
        last_url = ""
        for i in range(600):  # 最多等 5 分钟,每 0.5s 检查一次
            await asyncio.sleep(0.5)
            url = page.url
            if url != last_url:
                print(f"  [{i*0.5:.0f}s] URL: {url}")
                last_url = url

            # 只要不在登录页了,就算登录成功
            if "login.html" not in url and "channels.weixin.qq.com" in url:
                print(f"  ✅ 检测到离开登录页,视为登录成功")
                logged_in = True
                break

        if not logged_in:
            print("  ❌ 等待 5 分钟未检测到登录,退出")
            await browser.close()
            return

        # 关键:导航到上传页,等 publish marker 出现再存 cookie
        # 登录后直接存会漏 cookie(只存到 sessionid/wxuin 2 个),
        # 微信视频号需要更多 cookie 才能访问上传页
        print("\n=== 导航到上传页,等 publish marker 出现再存 cookie ===")
        await page.goto("https://channels.weixin.qq.com/platform/post/create", timeout=30000)

        if "login.html" in page.url:
            print(f"  ❌ 导航到上传页后被重定向回登录页,cookie 不完整")
            print(f"     当前 URL: {page.url}")
            await browser.close()
            return

        # 等待 publish marker 可见,确保页面完整加载(否则 cookie 不够)
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
            print(f"  ⚠️ 30s 内未检测到 publish marker,cookie 可能不完整")
            await asyncio.sleep(5)

        print(f"  上传页 URL: {page.url}")
        await context.storage_state(path=ACCOUNT_FILE)

        # 验证存了多少 cookie
        import json
        with open(ACCOUNT_FILE) as f:
            cookie_data = json.load(f)
        print(f"  存了 {len(cookie_data.get('cookies', []))} 个 cookie")
        for c in cookie_data.get("cookies", []):
            print(f"    - {c.get('name')} (domain={c.get('domain')})")

        print(f"\n✅ cookie 已保存到: {ACCOUNT_FILE}")
        print("现在可以运行 python publish_all.py 发布了。")

        await browser.close()


asyncio.run(main())
