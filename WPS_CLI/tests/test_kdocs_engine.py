"""
kdocs_engine.is_content_readable 与 config.CONTENT_BACKUP_FORMATS 一致性测试 — TDD

Bug：config 宣称支持 .doc/.xls 内容备份，但 is_content_readable() 集合中缺失，
导致主引擎永远不会对这两种格式触发内容备份。
"""

import unittest

from wps_backup import config
from wps_backup.kdocs_engine import is_content_readable


class TestContentReadableFormats(unittest.TestCase):

    def test_all_config_formats_are_readable(self):
        """config.CONTENT_BACKUP_FORMATS 中的每种格式都应通过 is_content_readable"""
        for ext in sorted(config.CONTENT_BACKUP_FORMATS):
            with self.subTest(ext=ext):
                self.assertTrue(is_content_readable(ext),
                                f"config 声明支持 {ext}，但 is_content_readable 返回 False")

    def test_pptx_not_readable(self):
        """pptx 明确不支持（kdocs-cli read-file 限制）"""
        self.assertFalse(is_content_readable(".pptx"))


if __name__ == "__main__":
    unittest.main()
