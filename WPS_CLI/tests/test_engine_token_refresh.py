"""
engine 下载 403 token 刷新重试测试 — TDD

事故背景：hwc-bj.ag.wps.cn 等存储域名的下载地址要求 Bearer token。
access token 仅 2 小时有效，长跑备份（>2h）中 token 过期后，
下载返回 HTTP 403 被归类为"不可重试"，文件被永久标记失败。
修复：下载遇 401/403 时刷新 token 重试一次；仍失败才判定为权限问题。
"""

import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from wps_backup import config
from wps_backup.engine import (
    AtomicCounter,
    BackupEngine,
    BackupResult,
    RemoteFile,
)
from wps_backup.state import BackupState


def _rf() -> RemoteFile:
    return RemoteFile(file_id="f_001", drive_id="d1", drive_name="盘A",
                      name="a.docx", size=4, mtime=1, link_url="",
                      parent_id="0", type="file")


def _engine(tmp: Path) -> BackupEngine:
    """构造 BackupEngine，状态与备份目录重定向到临时目录，不触真实 CLI"""
    with mock.patch("wps_backup.engine._get_auth_token", return_value="T0"), \
         mock.patch("wps_backup.engine.kdocs_engine.check_kdocs_cli_available",
                    return_value=False), \
         mock.patch("wps_backup.engine.BackupState",
                    lambda: BackupState(state_file=tmp / "s.json")), \
         mock.patch.object(config, "BACKUP_DIR", tmp):
        return BackupEngine(workers=1)


class TestDownload403TokenRefresh(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.eng = _engine(self.tmp)

    def _run_worker(self, fake_download, token_sequence):
        result = BackupResult()
        with mock.patch.object(self.eng, "_get_download_url_throttled",
                               return_value="http://x"), \
             mock.patch.object(config, "BACKUP_DIR", self.tmp), \
             mock.patch("wps_backup.engine._simple_download",
                        side_effect=fake_download), \
             mock.patch("wps_backup.engine._get_auth_token",
                        side_effect=token_sequence) as m_tok:
            self.eng._download_worker(_rf(), 1, 1, result,
                                      AtomicCounter(), time.time())
        return result, m_tok

    def test_403_refreshes_token_and_retries(self):
        """首次 403（token 过期）→ 刷新 token → 重试成功"""
        calls = []

        def fake_simple(url, dest, token):
            calls.append(token)
            if token == "T0":
                return (False, 0, "HTTP 403 (不可重试)")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"data")
            return (True, 4, "hash123")

        result, m_tok = self._run_worker(fake_simple, ["T1"])
        self.assertEqual(result.new, 1, f"应下载成功: errors={result.errors}")
        self.assertEqual(result.failed, 0)
        self.assertEqual(calls, ["T0", "T1"], "第二次下载应使用刷新后的 token")
        m_tok.assert_called()

    def test_403_after_refresh_stays_failed(self):
        """刷新 token 后仍 403（真实权限不足）→ 标记失败"""
        def fake_simple(url, dest, token):
            return (False, 0, "HTTP 403 (不可重试)")

        result, m_tok = self._run_worker(fake_simple, ["T1", "T2"])
        self.assertEqual(result.failed, 1)
        self.assertEqual(result.new, 0)
        snap = self.eng.state.get_snapshot("d1", "f_001")
        self.assertIn("403", snap.error_msg)

    def test_non_auth_failure_does_not_refresh_token(self):
        """非 401/403 失败不触发 token 刷新"""
        def fake_simple(url, dest, token):
            return (False, 0, "HTTP 500")

        result, m_tok = self._run_worker(fake_simple, ["T1"])
        self.assertEqual(result.failed, 1)
        m_tok.assert_not_called()


if __name__ == "__main__":
    unittest.main()
