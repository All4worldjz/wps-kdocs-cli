"""
prune_stale 防误清空保护测试 — TDD

事故背景：wps365-cli 接口漂移导致扫描返回 0 个文件时，
prune_stale(set()) 会清空全部增量状态记录，下次运行退化为全量重备。
规则：远程扫描结果为空但本地有记录时，视为扫描异常，跳过清理。
"""

import tempfile
import unittest
from pathlib import Path

from wps_backup.otl_engine import OTLBackupState
from wps_backup.state import BackupState, FileSnapshot


def _snapshot(file_id: str) -> FileSnapshot:
    return FileSnapshot(file_id=file_id, drive_id="d1", name=f"{file_id}.docx",
                        size=1, mtime=100, local_path="/x", local_hash="",
                        link_url="", drive_name="盘A", backed_up_at="")


class TestOTLPruneGuard(unittest.TestCase):
    def setUp(self):
        self.state_file = Path(tempfile.mkdtemp()) / "s.json"

    def test_empty_remote_scan_does_not_wipe_records(self):
        state = OTLBackupState(state_file=self.state_file)
        state.mark_backed_up("f1", 100, content_path="/a.md")
        state.prune_stale(set())
        self.assertIn("f1", state.records)

    def test_normal_prune_still_works(self):
        state = OTLBackupState(state_file=self.state_file)
        state.mark_backed_up("f1", 100)
        state.mark_backed_up("f2", 100)
        state.prune_stale({"f1"})
        self.assertIn("f1", state.records)
        self.assertNotIn("f2", state.records)


class TestMainStatePruneGuard(unittest.TestCase):
    def setUp(self):
        self.state_file = Path(tempfile.mkdtemp()) / "s.json"

    def test_empty_remote_scan_does_not_wipe_snapshots(self):
        state = BackupState(state_file=self.state_file)
        state.mark_backed_up(_snapshot("f1"))
        pruned = state.prune_stale(set())
        self.assertEqual(pruned, 0)
        self.assertTrue(state.is_backed_up("d1", "f1"))

    def test_normal_prune_still_works(self):
        state = BackupState(state_file=self.state_file)
        state.mark_backed_up(_snapshot("f1"))
        state.mark_backed_up(_snapshot("f2"))
        pruned = state.prune_stale({"d1/f1"})
        self.assertEqual(pruned, 1)
        self.assertTrue(state.is_backed_up("d1", "f1"))
        self.assertFalse(state.is_backed_up("d1", "f2"))


if __name__ == "__main__":
    unittest.main()
