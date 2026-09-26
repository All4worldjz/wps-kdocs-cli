"""
扫描完整性防护测试 — TDD

风险：scan_remote_files / _recurse_otl 在某页 CLI 调用失败时静默 break，
返回“非空但不完整”的文件集；prune_stale 的空扫描防护不会触发，
其余盘/目录的增量记录被误删。OTL 扫描在盘列表失败时还会回退到硬编码默认盘。
另：OTL 子目录列表未分页，目录项 >200 时后续子文件夹不会被递归。
修复：扫描失败显式抛出；扫描不完整时跳过 prune_stale。
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from wps_backup import config, engine, otl_engine
from wps_backup.state import BackupState, FileSnapshot


def _page(items, token=""):
    return {"code": 0, "data": {"items": items, "next_page_token": token}}


def _file(fid, name="a.docx"):
    return {"id": fid, "name": name, "type": "file", "size": 1, "mtime": 1}


def _folder(fid):
    return {"id": fid, "name": fid, "type": "folder"}


class TestEngineScanFailure(unittest.TestCase):

    def test_page_failure_raises(self):
        responses = [_page([_file("f1")], token="p2"), None]
        with mock.patch("wps_backup.engine._cli", side_effect=responses):
            with self.assertRaises(RuntimeError):
                engine.scan_remote_files("d1", "盘A")

    def test_run_skips_prune_when_a_drive_scan_fails(self):
        tmp = Path(tempfile.mkdtemp())
        st = BackupState(state_file=tmp / "s.json")
        for d, f in (("d1", "keep1"), ("d2", "keep2")):
            st.mark_backed_up(FileSnapshot(
                file_id=f, drive_id=d, name=f, size=1, mtime=1, local_path="",
                local_hash="h", link_url="", drive_name=d, backed_up_at=""))

        def fake_scan(drive_id, drive_name, parent_id="0", otl_sink=None):
            if drive_id == "d2":
                raise RuntimeError("scan failed")
            return [engine.RemoteFile("keep1", "d1", "d1", "keep1", 1, 1, "", "0", "file")]

        with mock.patch("wps_backup.engine._get_auth_token", return_value="T"), \
             mock.patch("wps_backup.engine.kdocs_engine.check_kdocs_cli_available", return_value=False), \
             mock.patch("wps_backup.engine.BackupState", lambda: st), \
             mock.patch("wps_backup.engine.scan_remote_drives",
                        return_value=[{"id": "d1", "name": "d1"}, {"id": "d2", "name": "d2"}]), \
             mock.patch("wps_backup.engine.scan_remote_files", side_effect=fake_scan):
            result = engine.BackupEngine(workers=1).run(dry_run=True)

        self.assertIn("d2/keep2", st.snapshots, "扫描失败盘的记录不能被 prune")
        self.assertTrue(result.errors)


class TestOtlScanFailure(unittest.TestCase):

    def test_drive_list_failure_does_not_fall_back_to_default_drive(self):
        with mock.patch("wps_backup.otl_engine._cli", return_value=None), \
             mock.patch("wps_backup.otl_engine.list_otl_files") as m_default:
            with self.assertRaises(otl_engine.ScanIncompleteError):
                otl_engine.list_otl_files_all_drives()
        m_default.assert_not_called()

    def test_one_drive_failure_returns_partial_via_exception(self):
        drives = {"code": 0, "data": {"items": [{"id": "d1", "name": "A"}, {"id": "d2", "name": "B"}]}}
        good = otl_engine.OTLFileInfo("o1", "d1", "A", "x.otl", 1, 1, "", "")

        def fake_list(drive_id, drive_name="", parent_id="0"):
            if drive_id == "d2":
                raise RuntimeError("boom")
            return [good]

        with mock.patch("wps_backup.otl_engine._cli", return_value=drives), \
             mock.patch("wps_backup.otl_engine.list_otl_files", side_effect=fake_list):
            with self.assertRaises(otl_engine.ScanIncompleteError) as cm:
                otl_engine.list_otl_files_all_drives()
        self.assertEqual([f.file_id for f in cm.exception.partial], ["o1"])

    def test_recurse_raises_on_page_failure(self):
        with mock.patch("wps_backup.otl_engine._cli", return_value=None):
            with self.assertRaises(RuntimeError):
                otl_engine.list_otl_files("d1", "A")

    def test_recurse_paginates_folder_listing(self):
        """子目录列表必须分页：第二页中的文件夹也要递归"""
        calls = []

        def fake_cli(*args, **kw):
            args = list(args)
            parent = args[4]
            token = args[args.index("--page-token") + 1] if "--page-token" in args else ""
            is_otl = "--filter-exts" in args
            calls.append((parent, is_otl, token))
            if is_otl:
                return _page([_file("o_" + parent, "x.otl")] if parent == "sub2" else [])
            if parent == "0" and not token:
                return _page([_folder("sub1")], token="t2")
            if parent == "0" and token == "t2":
                return _page([_folder("sub2")])
            return _page([])

        with mock.patch("wps_backup.otl_engine._cli", side_effect=fake_cli):
            files = otl_engine.list_otl_files("d1", "A")
        self.assertEqual([f.file_id for f in files], ["o_sub2"])

    def test_run_uses_partial_and_skips_prune(self):
        tmp = Path(tempfile.mkdtemp())
        state_file = tmp / "_otl_state.json"
        st = otl_engine.OTLBackupState(state_file=state_file)
        st.mark_backed_up("keep_other_drive", 1)
        partial = [otl_engine.OTLFileInfo("o1", "d1", "A", "x.otl", 1, 1, "", "")]

        with mock.patch("wps_backup.otl_engine.OTL_STATE_FILE", state_file), \
             mock.patch("wps_backup.otl_engine.OTLBackupState",
                        lambda state_file=state_file, _cls=otl_engine.OTLBackupState: _cls(state_file)), \
             mock.patch("wps_backup.otl_engine.OTL_BACKUP_DIR", tmp / "f"), \
             mock.patch("wps_backup.otl_engine.OTL_CONTENT_DIR", tmp / "c"), \
             mock.patch("wps_backup.otl_engine.OTL_CONVERTED_DIR", tmp / "d"), \
             mock.patch("wps_backup.otl_engine.airpage_engine.check_airpage_available", return_value=False), \
             mock.patch("wps_backup.otl_engine.kdocs_engine.check_kdocs_cli_available", return_value=False), \
             mock.patch("wps_backup.otl_engine.find_cache_root", return_value=tmp), \
             mock.patch("wps_backup.otl_engine.parse_rectfile2", return_value=[]), \
             mock.patch("wps_backup.otl_engine.list_cache_otl_files", return_value={}), \
             mock.patch("wps_backup.otl_engine.list_otl_files_all_drives",
                        side_effect=otl_engine.ScanIncompleteError("d2 failed", partial)):
            result = otl_engine.OTLEngine().run()

        self.assertEqual(result.total, 1)
        self.assertTrue(result.errors)
        self.assertIn("keep_other_drive", otl_engine.OTLBackupState(state_file).records)


if __name__ == "__main__":
    unittest.main()
