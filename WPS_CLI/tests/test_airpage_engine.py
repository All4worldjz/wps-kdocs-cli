"""
airpage_engine 单元测试 — TDD
wps365-cli airpage 封装：块树读取 → Markdown 转换 → docx 导出 → OTL 内容备份
"""

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from wps_backup.airpage_engine import (
    backup_otl_via_airpage,
    blocks_to_markdown,
    check_airpage_available,
    export_airpage_to_file,
    get_airpage_version,
    read_airpage_blocks,
)

FIXTURE = Path(__file__).parent / "fixtures" / "airpage_blocks_sample.json"


def _para(text, **attrs):
    """构造一个段落块"""
    a = {"align": "left", "first_indent": 0, "left_indent": 0}
    a.update(attrs)
    return {"paragraph": {
        "attributes": a,
        "block_id": "b_" + text[:6],
        "elements": [{"text": {"attributes": {"content": text}, "range_marks": []}}],
        "range_marks": [],
    }}


def _doc(*children):
    return {"doc": {"attributes": {}, "block_id": "doc", "children": list(children)}}


class TestBlocksToMarkdown(unittest.TestCase):
    """v2 块树 → Markdown 文本转换"""

    def test_real_fixture_extracts_text(self):
        """真实样本（超级个体.otl）应提取出段落文本"""
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        md = blocks_to_markdown(data["data"]["block"])
        self.assertIn("2026/02/26-2026/02/26", md)

    def test_real_fixture_user_mention(self):
        """wps_user 元素应渲染为 @姓名"""
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        md = blocks_to_markdown(data["data"]["block"])
        self.assertIn("@测试用户", md)

    def test_real_fixture_pictures(self):
        """picture 块应渲染为图片占位符，数量与样本一致（3 张）"""
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        md = blocks_to_markdown(data["data"]["block"])
        self.assertEqual(md.count("!["), 3)

    def test_paragraphs_become_lines(self):
        md = blocks_to_markdown(_doc(_para("第一行"), _para("第二行")))
        self.assertEqual(md, "第一行\n第二行")

    def test_heading_attribute(self):
        """段落 attributes 带 heading 级别时应加 # 前缀"""
        md = blocks_to_markdown(_doc(_para("标题", heading=2)))
        self.assertEqual(md, "## 标题")

    def test_nested_children_recursion(self):
        """含 children 的容器块应递归展开"""
        tree = _doc({"list": {
            "attributes": {}, "block_id": "l1",
            "children": [_para("子项A"), _para("子项B")],
        }})
        md = blocks_to_markdown(tree)
        self.assertIn("子项A", md)
        self.assertIn("子项B", md)

    def test_empty_doc_returns_empty(self):
        self.assertEqual(blocks_to_markdown(_doc()), "")
        self.assertEqual(blocks_to_markdown({"doc": {}}), "")

    def test_unknown_element_skipped(self):
        """无法识别的元素类型不应导致异常"""
        tree = _doc({"paragraph": {
            "attributes": {}, "block_id": "x",
            "elements": [{"unknown_widget": {"attributes": {}}}],
        }})
        self.assertEqual(blocks_to_markdown(tree), "")


def _fake_runner(payload, returncode=0, stderr=""):
    """构造 subprocess.run 的替身，返回给定 JSON"""
    def runner(cmd, **kwargs):
        return SimpleNamespace(
            returncode=returncode,
            stdout=json.dumps(payload, ensure_ascii=False),
            stderr=stderr,
        )
    return runner


class TestCliWrapper(unittest.TestCase):
    """wps365-cli airpage 子进程封装（注入 runner，不发起真实调用）"""

    def test_read_blocks_returns_block_tree(self):
        cli_payload = {"code": 0, "data": {"block": _doc(_para("内容"))}}
        block = read_airpage_blocks("f_001", runner=_fake_runner(cli_payload))
        self.assertIn("doc", block)

    def test_read_blocks_api_error_returns_none(self):
        block = read_airpage_blocks("f_001", runner=_fake_runner({"code": 403, "msg": "denied"}))
        self.assertIsNone(block)

    def test_read_blocks_cli_crash_returns_none(self):
        block = read_airpage_blocks("f_001", runner=_fake_runner({}, returncode=1, stderr="boom"))
        self.assertIsNone(block)

    def test_get_version(self):
        payload = {"code": 0, "data": {"version": 3}}
        self.assertEqual(get_airpage_version("f_001", runner=_fake_runner(payload)), 3)

    def test_get_version_error_returns_none(self):
        self.assertIsNone(get_airpage_version("f_001", runner=_fake_runner({"code": 1})))

    def test_available_with_airpage_scope(self):
        payload = {"delegated": {"granted_scopes": ["kso.airpage.readwrite", "kso.drive.readwrite"]}}
        self.assertTrue(check_airpage_available(runner=_fake_runner(payload)))

    def test_unavailable_without_scope(self):
        payload = {"delegated": {"granted_scopes": ["kso.drive.readwrite"]}}
        self.assertFalse(check_airpage_available(runner=_fake_runner(payload)))

    def test_unavailable_when_cli_missing(self):
        def bad_runner(cmd, **kwargs):
            raise FileNotFoundError("wps365-cli not found")
        self.assertFalse(check_airpage_available(runner=bad_runner))


class _FakeResp:
    """urlopen 返回值的替身"""
    def __init__(self, data: bytes):
        self._data = data
    def read(self):
        return self._data


def _export_runner(get_statuses):
    """
    构造 runner 替身：
    - airpage get          → 返回 version=1
    - airpage export create → 返回 key=k1, Building
    - airpage export get    → 依次返回 get_statuses 中的状态，最后一个带 url
    """
    state = {"polls": 0}

    def runner(cmd, **kwargs):
        args = list(cmd[1:])
        if args[:2] == ["airpage", "get"]:
            payload = {"code": 0, "data": {"version": 1}}
        elif args[:3] == ["airpage", "export", "create"]:
            payload = {"code": 0, "data": {"key": "k1", "status": "Building"}}
        elif args[:3] == ["airpage", "export", "get"]:
            status = get_statuses[min(state["polls"], len(get_statuses) - 1)]
            state["polls"] += 1
            data = {"key": "k1", "status": status}
            if status == "Completed":
                data["url"] = "https://example.com/export.docx"
            payload = {"code": 0, "data": data}
        else:
            raise AssertionError(f"unexpected cmd: {cmd}")
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

    runner.polls = state
    return runner


class TestExportAirpage(unittest.TestCase):
    """airpage 导出 docx：创建任务 → 轮询 → 下载"""

    def test_export_success_after_poll(self):
        runner = _export_runner(["Building", "Completed"])
        fetcher = lambda url, **kw: _FakeResp(b"DOCX_BYTES")
        dest = Path(self._tmpdir()) / "out.docx"
        ok = export_airpage_to_file("f_001", dest, runner=runner, fetcher=fetcher,
                                    sleep=lambda s: None)
        self.assertTrue(ok)
        self.assertEqual(dest.read_bytes(), b"DOCX_BYTES")
        self.assertEqual(runner.polls["polls"], 2)

    def test_export_failed_status(self):
        runner = _export_runner(["Failed"])
        fetcher = lambda url, **kw: _FakeResp(b"x")
        dest = Path(self._tmpdir()) / "out.docx"
        ok = export_airpage_to_file("f_001", dest, runner=runner, fetcher=fetcher,
                                    sleep=lambda s: None)
        self.assertFalse(ok)
        self.assertFalse(dest.exists())

    def test_export_timeout_gives_up(self):
        runner = _export_runner(["Building"] * 100)
        fetcher = lambda url, **kw: _FakeResp(b"x")
        dest = Path(self._tmpdir()) / "out.docx"
        ok = export_airpage_to_file("f_001", dest, runner=runner, fetcher=fetcher,
                                    sleep=lambda s: None, timeout=0)
        self.assertFalse(ok)
        self.assertFalse(dest.exists())

    def test_export_without_version_fails(self):
        def no_version_runner(cmd, **kwargs):
            return SimpleNamespace(returncode=1, stdout="", stderr="boom")
        dest = Path(self._tmpdir()) / "out.docx"
        ok = export_airpage_to_file("f_001", dest, runner=no_version_runner,
                                    fetcher=lambda u, **kw: _FakeResp(b"x"),
                                    sleep=lambda s: None)
        self.assertFalse(ok)

    def test_export_passes_timeout_to_fetcher(self):
        """下载必须带超时，防止网络停滞导致备份进程永久挂起"""
        seen = {}
        def recording_fetcher(url, **kwargs):
            seen.update(kwargs)
            return _FakeResp(b"DOCX")
        runner = _export_runner(["Completed"])
        dest = Path(self._tmpdir()) / "out.docx"
        ok = export_airpage_to_file("f_001", dest, runner=runner,
                                    fetcher=recording_fetcher, sleep=lambda s: None)
        self.assertTrue(ok)
        self.assertIn("timeout", seen)
        self.assertGreater(seen["timeout"], 0)

    def _tmpdir(self):
        import tempfile
        return tempfile.mkdtemp()


class TestBackupOtlViaAirpage(unittest.TestCase):
    """OTL 内容备份主入口：块树 → Markdown（+ 可选 docx 导出）"""

    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())
        self.content_dir = self.tmp / "content"
        self.docx_dir = self.tmp / "docx"

    def _read_runner(self):
        """只支持 block get 的 runner"""
        tree = _doc(_para("会议纪要正文"), _para("第二段"))
        return _fake_runner({"code": 0, "data": {"block": tree}})

    def test_writes_markdown_with_frontmatter(self):
        r = backup_otl_via_airpage(
            "f_001", "会议纪要.otl", drive_id="d1", drive_name="盘A",
            export_docx=False, content_dir=self.content_dir, docx_dir=self.docx_dir,
            runner=self._read_runner(),
        )
        self.assertTrue(r.success, r.error)
        out = Path(r.content_path)
        self.assertTrue(out.exists())
        text = out.read_text(encoding="utf-8")
        self.assertIn("file_id: f_001", text)
        self.assertIn("backend: airpage", text)
        self.assertIn("会议纪要正文", text)
        self.assertEqual(out.parent, self.content_dir / "盘A")
        self.assertIn("f_001"[:8], out.name)

    def test_docx_export_written_and_recorded(self):
        read = self._read_runner()
        export = _export_runner(["Completed"])

        def runner(cmd, **kwargs):
            if "export" in cmd or (cmd[1:3] == ["airpage", "get"]):
                return export(cmd, **kwargs)
            return read(cmd, **kwargs)

        r = backup_otl_via_airpage(
            "f_001", "会议纪要.otl", drive_id="d1", drive_name="盘A",
            export_docx=True, content_dir=self.content_dir, docx_dir=self.docx_dir,
            runner=runner, fetcher=lambda url, **kw: _FakeResp(b"DOCX"),
            sleep=lambda s: None,
        )
        self.assertTrue(r.success, r.error)
        self.assertTrue(r.docx_path)
        self.assertEqual(Path(r.docx_path).read_bytes(), b"DOCX")
        self.assertEqual(Path(r.docx_path).parent, self.docx_dir)

    def test_docx_export_failure_does_not_fail_backup(self):
        """docx 导出失败时 Markdown 内容备份仍应成功"""
        def runner(cmd, **kwargs):
            if "export" in cmd or (cmd[1:3] == ["airpage", "get"]):
                return SimpleNamespace(returncode=1, stdout="", stderr="boom")
            return self._read_runner()(cmd, **kwargs)

        r = backup_otl_via_airpage(
            "f_001", "会议纪要.otl", export_docx=True,
            content_dir=self.content_dir, docx_dir=self.docx_dir,
            runner=runner, sleep=lambda s: None,
        )
        self.assertTrue(r.success, r.error)
        self.assertFalse(r.docx_path)

    def test_dry_run_makes_no_calls(self):
        def boom(cmd, **kwargs):
            raise AssertionError("dry-run 不应调用 CLI")
        r = backup_otl_via_airpage(
            "f_001", "会议纪要.otl", content_dir=self.content_dir,
            docx_dir=self.docx_dir, runner=boom, dry_run=True,
        )
        self.assertTrue(r.success)
        self.assertFalse(self.content_dir.exists())

    def test_read_failure(self):
        r = backup_otl_via_airpage(
            "f_001", "会议纪要.otl", export_docx=False,
            content_dir=self.content_dir, docx_dir=self.docx_dir,
            runner=_fake_runner({"code": 403001, "message": "denied"}),
        )
        self.assertFalse(r.success)
        self.assertTrue(r.error)


if __name__ == "__main__":
    unittest.main()
