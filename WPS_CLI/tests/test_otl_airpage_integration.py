"""
otl_engine × airpage 集成测试 — TDD
后端选择（airpage 优先，kdocs-cli 回退）、状态记录 docx_path、Phase 2 分发
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from wps_backup import config
from wps_backup.kdocs_engine import ContentBackupResult
from wps_backup.otl_engine import (
    OTLBackupState,
    OTLEngine,
    OTLFileInfo,
    select_content_backend,
)


class TestSelectContentBackend(unittest.TestCase):
    """OTL 内容备份后端选择：airpage 优先，kdocs-cli 回退"""

    def test_airpage_preferred_when_available(self):
        with mock.patch.object(config, "AIRPAGE_OTL_CONTENT_ENABLED", True):
            self.assertEqual(select_content_backend(True, True), "airpage")

    def test_kdocs_fallback_when_airpage_unavailable(self):
        with mock.patch.object(config, "AIRPAGE_OTL_CONTENT_ENABLED", True):
            self.assertEqual(select_content_backend(False, True), "kdocs")

    def test_kdocs_when_airpage_disabled_by_config(self):
        with mock.patch.object(config, "AIRPAGE_OTL_CONTENT_ENABLED", False):
            self.assertEqual(select_content_backend(True, True), "kdocs")

    def test_none_when_no_backend(self):
        with mock.patch.object(config, "AIRPAGE_OTL_CONTENT_ENABLED", True):
            self.assertIsNone(select_content_backend(False, False))


class TestOTLStateDocxPath(unittest.TestCase):
    """OTL 状态记录应持久化 docx 导出路径"""

    def test_mark_backed_up_with_docx_path(self):
        tmp = Path(tempfile.mkdtemp()) / "state.json"
        state = OTLBackupState(state_file=tmp)
        state.mark_backed_up("f1", 100, local_path="/a.otl",
                             content_path="/a.md", docx_path="/a.docx")

        reloaded = OTLBackupState(state_file=tmp)
        rec = reloaded.records["f1"]
        self.assertEqual(rec["docx_path"], "/a.docx")
        self.assertEqual(rec["content_path"], "/a.md")

    def test_docx_path_defaults_empty(self):
        tmp = Path(tempfile.mkdtemp()) / "state.json"
        state = OTLBackupState(state_file=tmp)
        state.mark_backed_up("f1", 100, local_path="/a.otl", content_path="/a.md")
        self.assertEqual(state.records["f1"]["docx_path"], "")


def _engine(airpage: bool, kdocs: bool) -> OTLEngine:
    """构造 OTLEngine，跳过真实 CLI 可用性探测"""
    with mock.patch("wps_backup.otl_engine.airpage_engine.check_airpage_available",
                    return_value=airpage), \
         mock.patch("wps_backup.otl_engine.kdocs_engine.check_kdocs_cli_available",
                    return_value=kdocs), \
         mock.patch("wps_backup.otl_engine.kdocs_engine.get_kdocs_version",
                    return_value="x"), \
         mock.patch.object(config, "BACKUP_DIR", Path(tempfile.mkdtemp())):
        # __init__ 会创建备份目录，重定向到临时目录
        with mock.patch("wps_backup.otl_engine.OTL_BACKUP_DIR", config.BACKUP_DIR / "_otl_files"), \
             mock.patch("wps_backup.otl_engine.OTL_CONTENT_DIR", config.BACKUP_DIR / "_otl_content"), \
             mock.patch("wps_backup.otl_engine.OTL_CONVERTED_DIR", config.BACKUP_DIR / "_otl_converted_docx"):
            return OTLEngine()


def _otl_file() -> OTLFileInfo:
    return OTLFileInfo(file_id="f_001", drive_id="d1", drive_name="盘A",
                       name="会议纪要.otl", size=100, mtime=1,
                       link_id="", link_url="")


class TestEngineContentDispatch(unittest.TestCase):
    """OTLEngine Phase 2 应按可用性分发到 airpage / kdocs-cli"""

    def test_dispatch_to_airpage(self):
        engine = _engine(airpage=True, kdocs=True)
        expected = ContentBackupResult(file_id="f_001", name="会议纪要.otl",
                                       success=True, docx_path="/x.docx")
        with mock.patch.object(config, "AIRPAGE_OTL_CONTENT_ENABLED", True), \
             mock.patch.object(config, "AIRPAGE_EXPORT_DOCX_ENABLED", True), \
             mock.patch("wps_backup.otl_engine.airpage_engine.backup_otl_via_airpage",
                        return_value=expected) as m_air, \
             mock.patch("wps_backup.otl_engine.kdocs_engine.backup_otl_content") as m_kd:
            r = engine._backup_content(_otl_file())
        self.assertTrue(r.success)
        self.assertEqual(r.docx_path, "/x.docx")
        m_air.assert_called_once()
        m_kd.assert_not_called()

    def test_dispatch_falls_back_to_kdocs(self):
        engine = _engine(airpage=False, kdocs=True)
        expected = ContentBackupResult(file_id="f_001", name="会议纪要.otl", success=True)
        with mock.patch.object(config, "AIRPAGE_OTL_CONTENT_ENABLED", True), \
             mock.patch("wps_backup.otl_engine.kdocs_engine.backup_otl_content",
                        return_value=expected) as m_kd:
            r = engine._backup_content(_otl_file())
        self.assertTrue(r.success)
        m_kd.assert_called_once()

    def test_dispatch_none_when_no_backend(self):
        engine = _engine(airpage=False, kdocs=False)
        with mock.patch.object(config, "AIRPAGE_OTL_CONTENT_ENABLED", True):
            self.assertIsNone(engine._backup_content(_otl_file()))


if __name__ == "__main__":
    unittest.main()
