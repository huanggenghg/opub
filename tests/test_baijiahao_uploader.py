import unittest

from uploader.baijiahao_uploader.main import _extract_bjh_public_url_from_preview_href


class ExtractBjhPublicUrlTests(unittest.TestCase):
    def test_extracts_id_from_preview_href(self):
        href = "http://baijiahao.baidu.com/builder/preview/s?id=1872396938046079637"
        self.assertEqual(
            _extract_bjh_public_url_from_preview_href(href),
            "https://baijiahao.baidu.com/s?id=1872396938046079637",
        )

    def test_returns_none_for_none_input(self):
        self.assertIsNone(_extract_bjh_public_url_from_preview_href(None))

    def test_returns_none_for_href_without_id(self):
        self.assertIsNone(_extract_bjh_public_url_from_preview_href("https://example.com/no-id"))

    def test_handles_https_and_extra_query_params(self):
        href = "https://baijiahao.baidu.com/builder/preview/s?id=123&other=456"
        self.assertEqual(
            _extract_bjh_public_url_from_preview_href(href),
            "https://baijiahao.baidu.com/s?id=123",
        )

    def test_returns_none_for_empty_string(self):
        self.assertIsNone(_extract_bjh_public_url_from_preview_href(""))


if __name__ == "__main__":
    unittest.main()
