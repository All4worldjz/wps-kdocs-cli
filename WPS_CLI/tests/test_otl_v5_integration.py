"""
OTL v5 集成 — TDD
1. 产物级增量计划（plan_v5）：md / docx 独立判断，旧格式一次性升级，永久失败跳过
2. 主引擎一次遍历收集 .otl / .otl.link，OTL 引擎不再二次扫描（基线：二次扫描 75s/次）
3. OTL 阶段有界并发 + 状态写锁 + 扫描不完整不 prune
"""

import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from wps_backup import airpage_engine as ae
from wps_backup import config, engine, otl_engine
from wps_backup.app_contract import CANCEL


def _state():
    return otl_engine.OTLBackupState(state_file=Path(tempfile.mkdtemp()) / "s.json")


def _existing(tmp, name):
    p = Path(tmp) / name
    p.write_text("x")
    return str(p)


class TestPlanV5(unittest.TestCase):

    def setUp(self):
        self.st = _state()
        self.tmp = tempfile.mkdtemp()

    def test_new_file_needs_both(self):
        self.assertEqual(self.st.plan_v5("f", 10, want_docx=True), (True, True))

    def test_up_to_date_needs_nothing(self):
        self.st.records["f"] = {"mtime": 10, "format": 5, "content_path": _existing(self.tmp, "a.md"),
                                "docx_path": _existing(self.tmp, "a.docx")}
        self.assertEqual(self.st.plan_v5("f", 10, want_docx=True), (False, False))

    def test_legacy_format_upgrades_md_only(self):
        self.st.records["f"] = {"mtime": 10, "content_path": _existing(self.tmp, "a.md"),
                                "docx_path": _existing(self.tmp, "a.docx")}
        self.assertEqual(self.st.plan_v5("f", 10, want_docx=True), (True, False))

    def test_missing_docx_only(self):
        self.st.records["f"] = {"mtime": 10, "format": 5, "content_path": _existing(self.tmp, "a.md"),
                                "docx_path": ""}
        self.assertEqual(self.st.plan_v5("f", 10, want_docx=True), (False, True))
        self.assertEqual(self.st.plan_v5("f", 10, want_docx=False), (False, False))

    def test_changed_file_needs_both(self):
        self.st.records["f"] = {"mtime": 10, "format": 5, "content_path": _existing(self.tmp, "a.md"),
                                "docx_path": _existing(self.tmp, "a.docx")}
        self.assertEqual(self.st.plan_v5("f", 11, want_docx=True), (True, True))

    def test_permanent_skipped_until_changed(self):
        self.st.records["f"] = {"mtime": 10, "permanent": True, "error_msg": "OTL 内容为空"}
        self.assertEqual(self.st.plan_v5("f", 10, want_docx=True), (False, False))
        self.assertEqual(self.st.plan_v5("f", 11, want_docx=True), (True, True))

    def test_record_merges_partial_results(self):
        self.st.records["f"] = {"mtime": 10, "format": 5, "content_path": "/old.md", "docx_path": "",
                                "path": "/cache.otl"}
        res = ae.V5Result(file_id="f", version="8", docx_path="/new.docx", docx_ok=True)
        self.st.record_v5("f", 10, res, did_md=False, did_docx=True)
        rec = self.st.records["f"]
        self.assertEqual((rec["content_path"], rec["docx_path"], rec["path"]), ("/old.md", "/new.docx", "/cache.otl"))
        self.assertEqual(rec["airpage_version"], "8")

    def test_record_success_clears_legacy_error(self):
        self.st.records["f"] = {"mtime": 10, "error_msg": "x", "permanent": False}
        res = ae.V5Result(file_id="f", version="1", content_path="/a.md", md_ok=True)
        self.st.record_v5("f", 11, res, did_md=True, did_docx=False)
        rec = self.st.records["f"]
        self.assertEqual(rec["format"], 5)
        self.assertNotIn("error_msg", rec)
        self.assertFalse(rec["permanent"])


class TestCacheMarkMerges(unittest.TestCase):

    def test_mark_backed_up_preserves_v5_fields(self):
        st = _state()
        st.records["f"] = {"mtime": 5, "format": 5, "airpage_version": "7", "content_path": "/a.md",
                           "docx_path": "/a.docx", "permanent": False}
        st.mark_backed_up("f", 6, "/cache.otl", "/a.md", "/a.docx")
        rec = st.records["f"]
        self.assertEqual((rec["format"], rec["airpage_version"], rec["path"], rec["mtime"]),
                         (5, "7", "/cache.otl", 6))


class TestSingleWalk(unittest.TestCase):

    def test_scan_collects_otl_and_link_entries(self):
        page = {"code": 0, "data": {"next_page_token": "", "items": [
            {"id": "a", "name": "doc.otl", "type": "file", "size": 1, "mtime": 5, "link_id": "L", "link_url": "u"},
            {"id": "b", "name": "x.otl.link", "type": "shortcut", "size": 1, "mtime": 6},
            {"id": "c", "name": "p.docx", "type": "file", "size": 1, "mtime": 7},
        ]}}
        sink = []
        with mock.patch("wps_backup.engine._cli", return_value=page):
            files = engine.scan_remote_files("d1", "盘A", otl_sink=sink)
        self.assertEqual(sorted(f.file_id for f in sink), ["a", "b"])
        self.assertIsInstance(sink[0], otl_engine.OTLFileInfo)
        self.assertEqual(sink[0].drive_name, "盘A")
        self.assertNotIn("a", [f.file_id for f in files], ".otl 仍不进入实体下载")

    def test_otl_engine_uses_provided_files_without_scanning(self):
        tmp = Path(tempfile.mkdtemp())
        files = [otl_engine.OTLFileInfo("f1", "d", "D", "a.otl", 1, 5, "", "")]
        with self._engine_patches(tmp), \
             mock.patch("wps_backup.otl_engine.list_otl_files_all_drives") as scan, \
             mock.patch("wps_backup.otl_engine.airpage_engine.backup_otl_v5",
                        return_value=ae.V5Result("f1", "1", str(tmp / "a.md"), str(tmp / "a.docx"), True, True)):
            r = otl_engine.OTLEngine().run(api_files=files, scan_complete=True)
        scan.assert_not_called()
        self.assertEqual((r.total, r.content_backed_up, r.docx_exported), (1, 1, 1))

    def test_incomplete_scan_skips_prune(self):
        tmp = Path(tempfile.mkdtemp())
        with self._engine_patches(tmp):
            otl_engine.OTLBackupState().records.update({"other": {"mtime": 1}})
            st = otl_engine.OTLBackupState()
            st.records["other"] = {"mtime": 1, "format": 5}
            st._save()
            with mock.patch("wps_backup.otl_engine.airpage_engine.backup_otl_v5"):
                r = otl_engine.OTLEngine().run(api_files=[], scan_complete=False)
            self.assertIn("other", otl_engine.OTLBackupState().records)
            self.assertTrue(r.errors)

    def _engine_patches(self, tmp):
        from contextlib import ExitStack
        stack = ExitStack()
        sf = tmp / "_otl_state.json"
        for target, val in [
            ("wps_backup.otl_engine.OTL_STATE_FILE", sf),
            ("wps_backup.otl_engine.OTL_BACKUP_DIR", tmp / "f"),
            ("wps_backup.otl_engine.OTL_CONTENT_DIR", tmp / "c"),
            ("wps_backup.otl_engine.OTL_CONVERTED_DIR", tmp / "d"),
        ]:
            stack.enter_context(mock.patch(target, val))
        orig = otl_engine.OTLBackupState
        stack.enter_context(mock.patch("wps_backup.otl_engine.OTLBackupState",
                                       lambda state_file=sf, _c=orig: _c(state_file)))
        stack.enter_context(mock.patch("wps_backup.otl_engine.airpage_engine.check_airpage_available",
                                       return_value=True))
        stack.enter_context(mock.patch("wps_backup.otl_engine.kdocs_engine.check_kdocs_cli_available",
                                       return_value=False))
        stack.enter_context(mock.patch("wps_backup.otl_engine.find_cache_root", return_value=None))
        return stack


class TestConcurrency(unittest.TestCase):

    def tearDown(self):
        CANCEL.clear()

    def test_parallel_workers_and_state_consistency(self):
        tmp = Path(tempfile.mkdtemp())
        files = [otl_engine.OTLFileInfo(f"f{i}", "d", "D", f"{i}.otl", 1, 5, "", "") for i in range(12)]
        active, peak = [0], [0]
        lock = threading.Lock()

        def slow(file_id, **kw):
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(0.05)
            with lock:
                active[0] -= 1
            return ae.V5Result(file_id, "1", str(tmp / f"{file_id}.md"), str(tmp / f"{file_id}.docx"), True, True)

        with TestSingleWalk()._engine_patches(tmp), \
             mock.patch.object(config, "OTL_WORKERS", 4), \
             mock.patch("wps_backup.otl_engine.airpage_engine.backup_otl_v5", side_effect=slow):
            r = otl_engine.OTLEngine().run(api_files=files, scan_complete=True)
            recs = otl_engine.OTLBackupState().records
        self.assertEqual(r.content_backed_up, 12)
        self.assertGreater(peak[0], 1, "应并发执行")
        self.assertLessEqual(peak[0], 4)
        self.assertEqual(len([k for k in recs if k.startswith("f")]), 12, "并发写状态不得丢记录")

    def test_transient_failures_surface_as_errors(self):
        """临时失败必须进入 result.errors → run 以非零退出，App 显示、定时任务每小时重试"""
        tmp = Path(tempfile.mkdtemp())
        files = [otl_engine.OTLFileInfo("f1", "d", "D", "a.otl", 1, 5, "", ""),
                 otl_engine.OTLFileInfo("f2", "d", "D", "b.otl", 1, 5, "", "")]
        results = {"f1": ae.V5Result("f1", "1", str(tmp / "a.md"), None, True, False, "", "docx 下载失败"),
                   "f2": ae.V5Result("f2", None, None, None, False, False, "获取文档版本失败（HTTP 403）",
                                     "获取文档版本失败（HTTP 403）")}
        with TestSingleWalk()._engine_patches(tmp), \
             mock.patch("wps_backup.otl_engine.airpage_engine.backup_otl_v5",
                        side_effect=lambda file_id, **kw: results[file_id]), \
             mock.patch("wps_backup.otl_engine.airpage_engine.backup_otl_via_airpage", return_value=None):
            r = otl_engine.OTLEngine().run(api_files=files, scan_complete=True)
        self.assertTrue(r.errors, "临时失败不能以 0 退出")

    def test_permanent_failures_do_not_error(self):
        tmp = Path(tempfile.mkdtemp())
        files = [otl_engine.OTLFileInfo("f1", "d", "D", "x.otl.link", 1, 5, "", "")]
        perm = ae.V5Result("f1", None, None, None, False, False, "无权限", "无权限", permanent=True)
        with TestSingleWalk()._engine_patches(tmp), \
             mock.patch("wps_backup.otl_engine.airpage_engine.backup_otl_v5", return_value=perm):
            r = otl_engine.OTLEngine().run(api_files=files, scan_complete=True)
        self.assertEqual(r.errors, [])

    def test_cancel_stops_submitting(self):
        tmp = Path(tempfile.mkdtemp())
        files = [otl_engine.OTLFileInfo(f"f{i}", "d", "D", f"{i}.otl", 1, 5, "", "") for i in range(5)]
        CANCEL.set()
        with TestSingleWalk()._engine_patches(tmp), \
             mock.patch("wps_backup.otl_engine.airpage_engine.backup_otl_v5") as b:
            r = otl_engine.OTLEngine().run(api_files=files, scan_complete=True)
        b.assert_not_called()
        self.assertTrue(r.errors)


if __name__ == "__main__":
    unittest.main()
