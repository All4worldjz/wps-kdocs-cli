"""
config.py 环境变量覆盖测试 — TDD

Bug：环境变量覆盖（WPS_BACKUP_DIR / WPS_BACKUP_STATE_DIR）在文件底部执行，
但 CONTENT_BACKUP_DIR / STATE_FILE / LOG_FILE 已在上方用旧值计算，
导致覆盖只部分生效。
"""

import importlib
import os
import unittest
from unittest import mock

from wps_backup import config


class TestConfigEnvOverride(unittest.TestCase):

    def tearDown(self):
        importlib.reload(config)  # 恢复默认配置，避免影响其他测试

    def test_backup_dir_override_propagates_to_content_dir(self):
        with mock.patch.dict(os.environ, {"WPS_BACKUP_DIR": "/tmp/wps_test_root"}):
            importlib.reload(config)
            self.assertEqual(str(config.CONTENT_BACKUP_DIR),
                             "/tmp/wps_test_root/_content_backup")

    def test_state_dir_override_propagates_to_state_and_log(self):
        with mock.patch.dict(os.environ, {"WPS_BACKUP_STATE_DIR": "/tmp/wps_test_state"}):
            importlib.reload(config)
            self.assertEqual(str(config.STATE_FILE),
                             "/tmp/wps_test_state/backup_state.json")
            self.assertEqual(str(config.LOG_FILE),
                             "/tmp/wps_test_state/backup.log")


if __name__ == "__main__":
    unittest.main()
