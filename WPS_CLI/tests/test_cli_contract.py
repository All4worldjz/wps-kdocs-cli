"""
wps365-cli 接口契约测试（线上冒烟）

背景：v0.3.3+ 的 remote curated spec 将 `drive files list/download`
更名为 `drive file list/download`，导致扫描返回 0 个文件。
本测试直接调用生产扫描/下载函数，升级 CLI 后能立刻发现接口漂移。
token 不可用时自动跳过（与 verify_fix.py 的在线验证策略一致）。
"""

import json
import subprocess
import unittest

from wps_backup import config


def _has_token() -> bool:
    try:
        r = subprocess.run([config.CLI_BIN, "auth", "token"],
                           capture_output=True, text=True, timeout=10)
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


@unittest.skipUnless(_has_token(), "wps365-cli token 不可用，跳过线上契约测试")
class TestCliContract(unittest.TestCase):
    """生产代码所依赖的 wps365-cli 命令接口必须真实可用"""

    def test_engine_scan_finds_files(self):
        """主引擎扫描：至少一个盘能列出可下载文件"""
        from wps_backup import engine
        drives = engine.scan_remote_drives()
        self.assertTrue(drives, "drive list 应返回至少一个盘")
        total = 0
        for d in drives:
            total += len(engine.scan_remote_files(d["id"], d.get("name", "")))
        self.assertGreater(total, 0, "扫描全部盘后应存在可下载文件")

    def test_otl_scan_finds_files(self):
        """OTL 扫描：应能找到 .otl 文件（已知约 200 个）"""
        from wps_backup import otl_engine
        files = otl_engine.list_otl_files_all_drives()
        self.assertGreater(len(files), 0, "OTL 扫描不应为空（疑似 CLI 接口漂移）")

    def test_download_url_command(self):
        """下载地址获取：对真实文件应返回 http(s) 链接"""
        from wps_backup import engine
        drives = engine.scan_remote_drives()
        url = None
        for d in drives:
            files = engine.scan_remote_files(d["id"], d.get("name", ""))
            if files:
                url = engine.get_download_url(d["id"], files[0].file_id)
                break
        self.assertTrue(url and url.startswith("http"),
                        f"应获取到下载地址，实际: {url}")


@unittest.skipUnless(_has_token(), "wps365-cli token 不可用，跳过线上契约测试")
class TestOtlV5Contract(unittest.TestCase):
    """v5 依赖的智能文档导出接口（CLI spec 未收录，经直连 HTTP 调用；按路径推测发现，最易变化）"""

    @classmethod
    def setUpClass(cls):
        from wps_backup import engine
        cls.otl = []
        for d in engine.scan_remote_drives():
            engine.scan_remote_files(d["id"], d.get("name", ""), otl_sink=cls.otl)

    def test_single_walk_matches_legacy_otl_scan(self):
        """一次遍历收集的 .otl 集合必须与旧的过滤扫描完全一致（含 .otl.link）"""
        from wps_backup import otl_engine
        legacy = {f.file_id for f in otl_engine.list_otl_files_all_drives()}
        self.assertEqual({f.file_id for f in self.otl}, legacy)

    def test_markdown_zip_and_docx_export_roundtrip(self):
        import tempfile, zipfile
        from pathlib import Path
        from wps_backup import airpage_engine
        target = next(f for f in self.otl if f.name.lower().endswith(".otl"))
        root = Path(tempfile.mkdtemp())
        res = airpage_engine.backup_otl_v5(
            file_id=target.file_id, name=target.name, drive_id=target.drive_id,
            drive_name=target.drive_name, content_root=root / "c", docx_root=root / "d")
        if res.permanent:
            self.skipTest(f"样本文档无内容: {res.md_error}")
        self.assertTrue(res.md_ok, res.md_error)
        self.assertTrue(res.docx_ok, res.docx_error)
        self.assertIn("format: 5", Path(res.content_path).read_text(encoding="utf-8"))
        self.assertTrue(zipfile.is_zipfile(res.docx_path), "docx 应为有效 Office 文件")


if __name__ == "__main__":
    unittest.main()
