"""
运行卫生测试 — TDD

1. kdocs 企业账号探测：`kdocs-cli auth status` 显示已认证，但业务接口返回 403001
   （仅支持个人账号），导致每个下载的 docx/pdf/xlsx 都白跑 3 次 read-file。
   check_kdocs_cli_available() 需探测一次业务接口，403001 视为不可用。
2. OTL 永久失败跳过：.otl.link 快捷方式、空文档每次运行都重试（~23 个 × 数秒）。
   记录失败 + mtime，mtime 未变化时跳过；远程更新后重新尝试。
3. 单实例锁：launchd 与手动运行重叠时，两个进程整体重写同一状态 JSON。
"""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from wps_backup import config, kdocs_engine, otl_engine


def _proc(stdout="", rc=0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr="")


class TestKdocsEnterpriseProbe(unittest.TestCase):

    def _run(self, probe_payload):
        auth = _proc(json.dumps({"authenticated": True}))
        probe = _proc(json.dumps(probe_payload))
        with mock.patch("wps_backup.kdocs_engine.subprocess.run", side_effect=[auth, probe]):
            return kdocs_engine.check_kdocs_cli_available()

    def test_enterprise_account_403001_is_unavailable(self):
        self.assertFalse(self._run({"code": 403001, "message": "暂仅支持个人账号"}))

    def test_personal_account_not_found_is_available(self):
        self.assertTrue(self._run({"code": 404, "message": "file not found"}))

    def test_unauthenticated_skips_probe(self):
        auth = _proc(json.dumps({"authenticated": False}))
        with mock.patch("wps_backup.kdocs_engine.subprocess.run", side_effect=[auth]) as m:
            self.assertFalse(kdocs_engine.check_kdocs_cli_available())
        self.assertEqual(m.call_count, 1)


class TestOtlPermanentFailure(unittest.TestCase):

    def setUp(self):
        self.st = otl_engine.OTLBackupState(state_file=Path(tempfile.mkdtemp()) / "s.json")

    def test_permanent_failure_skipped_until_mtime_changes(self):
        self.st.mark_failed("f1", 100, "OTL 内容为空", name="未命名文档.otl")
        self.assertFalse(self.st.needs_update("f1", 100))
        self.assertTrue(self.st.needs_update("f1", 101))

    def test_link_shortcut_is_permanent(self):
        self.st.mark_failed("f2", 5, "airpage 无法读取 OTL 内容", name="x.otl.link")
        self.assertFalse(self.st.needs_update("f2", 5))

    def test_transient_failure_is_retried(self):
        self.st.mark_failed("f3", 5, "airpage 无法读取 OTL 内容", name="normal.otl")
        self.assertTrue(self.st.needs_update("f3", 5))

    def test_failure_preserves_previous_success_paths(self):
        self.st.mark_backed_up("f4", 1, content_path="/c.md", docx_path="/d.docx")
        self.st.mark_failed("f4", 2, "OTL 内容为空", name="a.otl")
        rec = self.st.records["f4"]
        self.assertEqual(rec["content_path"], "/c.md")
        self.assertEqual(rec["docx_path"], "/d.docx")

    def test_success_clears_failure(self):
        self.st.mark_failed("f5", 1, "OTL 内容为空", name="a.otl")
        self.st.mark_backed_up("f5", 2, content_path="/c.md")
        self.assertNotIn("error_msg", self.st.records["f5"])


class TestCacheDirTccGuard(unittest.TestCase):
    """WPS Office 缓存位于 ~/Library/Containers（macOS“App 数据”隐私保护）。
    launchd / 无终端环境下 opendir 会阻塞等待 TCC 授权弹窗，进程永久挂起。
    缓存探测必须在带超时的子进程中进行，失败则跳过缓存阶段。"""

    @staticmethod
    def _popen(rc=0, hang=False):
        proc = mock.Mock()
        if hang:
            proc.wait.side_effect = subprocess.TimeoutExpired(cmd="x", timeout=1)
        else:
            proc.wait.return_value = rc
        return mock.Mock(return_value=proc), proc

    def test_timeout_kills_without_waiting_again(self):
        """TCC 阻塞中的子进程可能不响应 SIGKILL；超时后 kill 且不得再次 wait"""
        popen, proc = self._popen(hang=True)
        self.assertFalse(otl_engine.cache_dir_accessible(Path("/x"), popen=popen))
        proc.kill.assert_called_once()
        self.assertEqual(proc.wait.call_count, 1)

    def test_nonzero_exit_means_inaccessible(self):
        popen, _ = self._popen(rc=1)
        self.assertFalse(otl_engine.cache_dir_accessible(Path("/x"), popen=popen))

    def test_ok(self):
        popen, _ = self._popen(rc=0)
        self.assertTrue(otl_engine.cache_dir_accessible(Path("/x"), popen=popen))

    def test_find_cache_root_skips_when_blocked(self):
        with mock.patch("wps_backup.otl_engine.cache_dir_accessible", return_value=False):
            self.assertIsNone(otl_engine.find_cache_root())

    def test_find_cache_root_disabled_by_config(self):
        with mock.patch.object(config, "OTL_CACHE_SCAN_ENABLED", False), \
             mock.patch("wps_backup.otl_engine.cache_dir_accessible") as m:
            self.assertIsNone(otl_engine.find_cache_root())
        m.assert_not_called()


class TestRunLock(unittest.TestCase):

    def test_second_acquire_fails_while_held(self):
        import wps_backup.lock as lock
        path = Path(tempfile.mkdtemp()) / ".run.lock"
        first = lock.acquire(path)
        self.assertIsNotNone(first)
        try:
            self.assertIsNone(lock.acquire(path))
        finally:
            lock.release(first)
        again = lock.acquire(path)
        self.assertIsNotNone(again)
        lock.release(again)

    def test_holder_pid_and_nonzero_exit_code(self):
        """被锁跳过必须以非零退出（不能伪装成功），并能报告持锁 PID"""
        import os
        import wps_backup.lock as lock
        path = Path(tempfile.mkdtemp()) / ".run.lock"
        fd = lock.acquire(path)
        try:
            self.assertEqual(lock.holder_pid(path), os.getpid())
        finally:
            lock.release(fd)
        self.assertNotEqual(lock.EXIT_LOCKED, 0)


if __name__ == "__main__":
    unittest.main()
