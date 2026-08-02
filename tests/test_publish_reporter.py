import io
import unittest
from contextlib import redirect_stdout

from publish.reporter import print_summary


class PrintSummaryTests(unittest.TestCase):
    def test_counts_success_and_failure(self):
        all_results = {
            "v1.mp4": {
                "douyin": {"success": True, "message": "ok"},
                "weibo": {"success": False, "message": "fail"},
            },
            "v2.mp4": {
                "douyin": {"success": True, "message": "ok"},
            },
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            print_summary(all_results)
        out = buf.getvalue()
        self.assertIn("成功: 2 次", out)
        self.assertIn("失败: 1 次", out)

    def test_aggregates_account_issues_deduped(self):
        all_results = {
            "v1.mp4": {
                "douyin": {"success": False, "message": "受限", "account_issue": True, "issue_type": "publish_restricted"},
            },
            "v2.mp4": {
                "douyin": {"success": False, "message": "受限", "account_issue": True, "issue_type": "publish_restricted"},
                "weibo": {"success": True, "message": "ok"},
            },
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            print_summary(all_results)
        out = buf.getvalue()
        self.assertIn("账号异常反馈", out)
        self.assertIn("抖音", out)
        # douyin 只出现一次(去重)
        self.assertEqual(out.count("[douyin]"), 1)

    def test_no_account_issues_section_when_all_success(self):
        all_results = {
            "v1.mp4": {"douyin": {"success": True, "message": "ok"}},
        }
        buf = io.StringIO()
        with redirect_stdout(buf):
            print_summary(all_results)
        out = buf.getvalue()
        self.assertNotIn("账号异常反馈", out)

    def test_empty_results(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            print_summary({})
        out = buf.getvalue()
        self.assertIn("成功: 0 次", out)
        self.assertIn("失败: 0 次", out)


if __name__ == "__main__":
    unittest.main()
