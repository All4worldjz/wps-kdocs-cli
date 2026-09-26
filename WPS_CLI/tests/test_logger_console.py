"""
App agent 下 stderr 被重定向到 agent_runner.log（无轮转），控制台 handler 会把整份日志再写一遍。
WPS_BACKUP_NO_CONSOLE=1 时仅写入轮转的 backup.log。
"""

import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from wps_backup.logger import setup_logger


class TestConsoleHandlerToggle(unittest.TestCase):

    def _handlers(self, env):
        name = f"t_{os.urandom(4).hex()}"
        with mock.patch.dict(os.environ, env):
            lg = setup_logger(name, Path(tempfile.mkdtemp()) / "x.log")
        return [type(h).__name__ for h in lg.handlers]

    def test_console_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("WPS_BACKUP_NO_CONSOLE", None)
            self.assertIn("StreamHandler", self._handlers({}))

    def test_no_console_when_env_set(self):
        self.assertEqual(self._handlers({"WPS_BACKUP_NO_CONSOLE": "1"}), ["RotatingFileHandler"])


if __name__ == "__main__":
    unittest.main()
