import unittest
from pathlib import Path


class NoExcelLinkWritesTests(unittest.TestCase):
    PRODUCTION_FILES = (
        Path("publish/dispatch.py"),
        Path("uploader/douyin_uploader/main.py"),
        Path("uploader/xiaohongshu_uploader/main.py"),
        Path("uploader/ks_uploader/main.py"),
    )

    def test_excel_writer_module_does_not_exist(self):
        self.assertFalse(Path("utils/excel_writer.py").exists())

    def test_production_files_have_no_excel_link_write_references(self):
        for production_file in self.PRODUCTION_FILES:
            contents = production_file.read_text(encoding="utf-8")
            self.assertNotIn("excel_writer", contents, production_file)
            self.assertNotIn("write_video_link", contents, production_file)


if __name__ == "__main__":
    unittest.main()
