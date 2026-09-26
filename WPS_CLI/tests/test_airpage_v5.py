"""
OTL v5 导出流程 — TDD

官方接口（2026-09-26 实测）：
- GET  /v7/airpage/{id}                      → data.version
- POST /v7/airpage/{id}/export_to_markdown_zip {"version": v} → data.status Building/Completed, data.url
- POST /v7/airpage/{id}/export_to_docx          {"version": v}
- POST /v7/airpage/{id}/export_task/query      {"format": f, "version": v}
- zip 内容：export.md + 图片；md 中图片为远端 URL，query 参数 image_id=XXXX 对应 zip 内 XXXX.ext
- .otl.link（他人文档快捷方式）：airpage get 返回 403 → 永久失败
"""

import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from wps_backup import airpage_engine as ae

IMG_URL = ("https://hwc-bj.ag.wps.cn/api/object/2_abc/compatible?image_id=ZTI2MNBFADQFE"
           "&kso_type=image&kso_extra=eyJ4IjoxfQ")
MD = f"## **标题**\n\n- 列表 [链接](https://example.com \"t\")\n\n![Picture]({IMG_URL})\n\n![Other](https://x/y.png)\n"


def make_zip(md=MD, images=("ZTI2MNBFADQFE.jpg",)):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("export.md", md)
        for n in images:
            z.writestr(n, b"\xff\xd8img")
    return buf.getvalue()


class FakeHttp:
    """按 (method, path 后缀) 返回脚本化响应；记录调用"""

    def __init__(self, version="7", md_status="Completed", docx_status="Completed",
                 get_status=200, zip_bytes=None, docx_bytes=b"PK-docx", query_steps=0, get_body=None):
        self.get_body = get_body or {"code": 403000001, "msg": "unable to read user permission"}
        self.version = version
        self.statuses = {"markdown_zip": md_status, "docx": docx_status}
        self.get_status = get_status
        self.files = {"https://ks3/md.zip": zip_bytes if zip_bytes is not None else make_zip(),
                      "https://ks3/a.docx": docx_bytes}
        self.query_steps = query_steps
        self.calls = []

    def api(self, method, path, body=None, timeout=60):
        self.calls.append((method, path, body))
        if method == "GET":
            if self.get_status != 200:
                return self.get_status, self.get_body
            return 200, {"code": 0, "data": {"version": int(self.version)}}
        fmt = "markdown_zip" if path.endswith("export_to_markdown_zip") else (
            "docx" if path.endswith("export_to_docx") else body.get("format"))
        st = self.statuses[fmt]
        if path.endswith("/export_task/query"):
            if self.query_steps > 0:
                self.query_steps -= 1
                return 200, {"code": 0, "data": {"status": "Building"}}
        elif st == "Completed" and self.query_steps:
            return 200, {"code": 0, "data": {"status": "Building"}}
        url = {"markdown_zip": "https://ks3/md.zip", "docx": "https://ks3/a.docx"}[fmt]
        return 200, {"code": 0, "data": {"status": st, "url": url if st == "Completed" else ""}}

    def download(self, url, dest):
        data = self.files.get(url)
        if data is None:
            return False
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(data)
        return True


def run(http, **kw):
    root = Path(tempfile.mkdtemp())
    args = dict(file_id="xZNcZmRh2xM6", name="计划书.otl", drive_id="Q53", drive_name="我的企业文档",
                want_md=True, want_docx=True, http=http, downloader=http.download,
                content_root=root / "c", docx_root=root / "d", sleep=lambda s: None)
    args.update(kw)
    return ae.backup_otl_v5(**args), root


class TestRewriteImages(unittest.TestCase):

    def test_rewrites_image_id_urls_to_local_assets(self):
        out = ae.rewrite_image_links(MD, "x.assets", {"ZTI2MNBFADQFE": "ZTI2MNBFADQFE.jpg"})
        self.assertIn("![Picture](x.assets/ZTI2MNBFADQFE.jpg)", out)
        self.assertIn("![Other](https://x/y.png)", out, "无对应文件的图片保留原链接")
        self.assertIn('[链接](https://example.com "t")', out)


class TestBackupV5(unittest.TestCase):

    def test_full_success_md_with_assets_and_docx(self):
        http = FakeHttp()
        res, root = run(http)
        self.assertTrue(res.md_ok and res.docx_ok, res)
        md = Path(res.content_path)
        self.assertEqual(md, root / "c" / "我的企业文档" / "计划书_xZNcZmRh.md")
        text = md.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\nfile_id: xZNcZmRh2xM6\n"))
        self.assertIn("airpage_version: 7", text)
        self.assertIn("format: 5", text)
        self.assertIn("## **标题**", text)
        self.assertIn("![Picture](计划书_xZNcZmRh.assets/ZTI2MNBFADQFE.jpg)", text)
        self.assertTrue((md.parent / "计划书_xZNcZmRh.assets" / "ZTI2MNBFADQFE.jpg").exists())
        self.assertEqual(Path(res.docx_path).read_bytes(), b"PK-docx")
        self.assertEqual(res.version, "7")

    def test_both_tasks_created_before_polling(self):
        http = FakeHttp(query_steps=2)
        run(http)
        posts = [p for m, p, b in http.calls if m == "POST"]
        self.assertTrue(posts[0].endswith("export_to_markdown_zip"))
        self.assertTrue(posts[1].endswith("export_to_docx"), "两个任务应先后创建，再统一轮询")

    def test_only_missing_docx(self):
        http = FakeHttp()
        res, _ = run(http, want_md=False)
        self.assertTrue(res.docx_ok)
        self.assertIsNone(res.content_path)
        self.assertFalse(any(p.endswith("markdown_zip") for m, p, b in http.calls))

    def test_docx_failure_does_not_fail_md(self):
        http = FakeHttp(docx_status="Failed")
        res, _ = run(http)
        self.assertTrue(res.md_ok)
        self.assertFalse(res.docx_ok)
        self.assertTrue(res.docx_error)
        self.assertFalse(res.permanent)

    def test_permission_denied_is_permanent(self):
        res, _ = run(FakeHttp(get_status=403), name="x.otl.link")
        self.assertFalse(res.md_ok)
        self.assertTrue(res.permanent)

    def test_only_permission_code_is_permanent(self):
        """2026-09-26 实测响应：只有 403000001（快捷方式/不存在/无权限）是永久失败"""
        transient = [
            (403, {"code": 400000003, "msg": "kso: PermissionDenied access_token verify err: invalid_scope"}),
            (404, {"code": 404000001, "msg": "404 Route Not Found"}),
            (500, {"code": 500000004, "msg": "method not implemented"}),
            (502, "bad gateway"),
        ]
        for status, body in transient:
            res, _ = run(FakeHttp(get_status=status, get_body=body))
            self.assertFalse(res.permanent, (status, body))
            self.assertTrue(res.md_error)

    def test_empty_document_is_permanent(self):
        res, _ = run(FakeHttp(zip_bytes=make_zip(md="\n", images=())))
        self.assertFalse(res.md_ok)
        self.assertTrue(res.permanent)
        self.assertEqual(res.md_error, "OTL 内容为空")

    def test_md_zip_failure_keeps_previous_file(self):
        http = FakeHttp()
        res, root = run(http)
        md = Path(res.content_path)
        before = md.read_text(encoding="utf-8")
        http2 = FakeHttp(md_status="Failed")
        res2, _ = run(http2, content_root=root / "c", docx_root=root / "d")
        self.assertFalse(res2.md_ok)
        self.assertEqual(md.read_text(encoding="utf-8"), before, "失败时不得破坏旧文件")

    def test_timeout_is_transient_failure(self):
        http = FakeHttp(query_steps=10 ** 6)
        res, _ = run(http, poll_timeout=0)
        self.assertFalse(res.md_ok)
        self.assertFalse(res.permanent)


if __name__ == "__main__":
    unittest.main()
