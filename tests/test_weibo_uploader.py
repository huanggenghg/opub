import asyncio
import unittest

import uploader.weibo_uploader.main as weibo_main


class FakeLocator:
    def __init__(self, count=0, visible=False):
        self._count = count
        self._visible = visible

    @property
    def first(self):
        return self

    async def count(self):
        return self._count

    async def is_visible(self):
        return self._visible


class FakePage:
    def __init__(self, url, locators=None):
        self.url = url
        self._locators = locators or {}

    def locator(self, selector):
        return self._locators.get(selector, FakeLocator())


class WeiboCookieAuthTests(unittest.TestCase):
    def test_auth_page_is_invalid_when_redirected_to_login_without_visible_marker(self):
        page = FakePage("https://passport.weibo.com/sso/signin")

        valid = asyncio.run(weibo_main._is_weibo_auth_page_valid(page))

        self.assertFalse(valid)

    def test_auth_page_requires_visible_upload_entry(self):
        page = FakePage("https://weibo.com/upload/channel")

        valid = asyncio.run(weibo_main._is_weibo_auth_page_valid(page))

        self.assertFalse(valid)

    def test_auth_page_is_valid_when_upload_button_is_visible(self):
        page = FakePage(
            "https://weibo.com/upload/channel",
            {
                'button[id^="video_button_upload"], button._btn1_109u9_8': FakeLocator(
                    count=1,
                    visible=True,
                ),
            },
        )

        valid = asyncio.run(weibo_main._is_weibo_auth_page_valid(page))

        self.assertTrue(valid)


if __name__ == "__main__":
    unittest.main()
