"""
wps_http 直连 HTTP 客户端 — TDD

背景：
- export_to_markdown_zip 等新接口不在 wps365-cli 本地 spec 中，需直接调用 openapi.wps.cn（仅需 Bearer token）
- 本机系统代理（127.0.0.1:3213）对金山云 ks3 域名 SSL 握手超时，直连正常 → WPS/金山云域名直连优先，
  连接类错误回退代理；HTTP 错误（4xx/5xx）不回退
"""

import io
import json
import socket
import ssl
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from wps_backup import wps_http


class FakeResp(io.BytesIO):
    def __init__(self, body: bytes, status=200):
        super().__init__(body)
        self.status = status
        self.headers = {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeOpener:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def open(self, req, timeout=None):
        self.calls.append((req.full_url, dict(req.header_items()), req.data, timeout))
        o = self.outcomes.pop(0)
        if isinstance(o, BaseException):
            raise o
        return o


def http_error(code, body=b"{}"):
    return urllib.error.HTTPError("u", code, "err", {}, io.BytesIO(body))


class TestRouting(unittest.TestCase):

    def test_wps_hosts(self):
        for h in ("openapi.wps.cn", "weboffice-outline.ks3-cn-beijing.ksyun.com",
                  "hwc-bj.ag.wps.cn", "365.kdocs.cn", "img.qwps.cn"):
            self.assertTrue(wps_http.is_wps_host(h), h)
        self.assertFalse(wps_http.is_wps_host("github.com"))
        self.assertFalse(wps_http.is_wps_host("evilwps.cn.example.com"))

    def test_direct_first_for_wps_host(self):
        direct = FakeOpener(FakeResp(b"ok"))
        proxy = FakeOpener()
        r = wps_http.open_url("https://x.ks3-cn-beijing.ksyun.com/a", direct=direct, proxy=proxy)
        self.assertEqual(r.read(), b"ok")
        self.assertEqual(len(proxy.calls), 0)

    def test_fallback_to_proxy_on_connection_errors(self):
        for err in (urllib.error.URLError(ssl.SSLError("handshake timed out")),
                    socket.timeout("timed out"), ConnectionResetError()):
            direct = FakeOpener(err)
            proxy = FakeOpener(FakeResp(b"via-proxy"))
            r = wps_http.open_url("https://openapi.wps.cn/v7/x", direct=direct, proxy=proxy)
            self.assertEqual(r.read(), b"via-proxy", err)

    def test_http_error_not_retried_via_proxy(self):
        direct = FakeOpener(http_error(404))
        proxy = FakeOpener(FakeResp(b"x"))
        with self.assertRaises(urllib.error.HTTPError):
            wps_http.open_url("https://openapi.wps.cn/v7/x", direct=direct, proxy=proxy)
        self.assertEqual(len(proxy.calls), 0)

    def test_direct_attempt_uses_short_timeout(self):
        """直连被阻断时不能等满 600s 再回退代理"""
        direct = FakeOpener(FakeResp(b"ok"))
        wps_http.open_url("https://x.ksyun.com/a", timeout=600, direct=direct, proxy=FakeOpener())
        self.assertLessEqual(direct.calls[0][3], wps_http.DIRECT_TIMEOUT)

    def test_non_wps_host_uses_proxy_opener(self):
        direct = FakeOpener()
        proxy = FakeOpener(FakeResp(b"p"))
        wps_http.open_url("https://github.com/x", direct=direct, proxy=proxy)
        self.assertEqual(len(direct.calls), 0)


class TestApiClient(unittest.TestCase):

    def test_bearer_and_json(self):
        direct = FakeOpener(FakeResp(json.dumps({"code": 0, "data": {"a": 1}}).encode()))
        c = wps_http.WpsHttp(token_provider=lambda: "T1", direct=direct, proxy=FakeOpener())
        status, body = c.api("POST", "/v7/airpage/f/export_to_markdown_zip", {"version": "7"})
        self.assertEqual((status, body["data"]["a"]), (200, 1))
        url, headers, data, _ = direct.calls[0]
        self.assertEqual(url, "https://openapi.wps.cn/v7/airpage/f/export_to_markdown_zip")
        self.assertEqual(headers["Authorization"], "Bearer T1")
        self.assertEqual(json.loads(data), {"version": "7"})

    def test_401_refreshes_token_once(self):
        tokens = iter(["OLD", "NEW"])
        refreshed = []
        direct = FakeOpener(http_error(401), FakeResp(b'{"code":0}'))
        c = wps_http.WpsHttp(token_provider=lambda: next(tokens), refresher=lambda: refreshed.append(1),
                             direct=direct, proxy=FakeOpener())
        status, _ = c.api("GET", "/v7/airpage/f")
        self.assertEqual(status, 200)
        self.assertEqual(refreshed, [1])
        self.assertEqual(direct.calls[1][1]["Authorization"], "Bearer NEW")

    def test_http_error_body_returned(self):
        direct = FakeOpener(http_error(403, b'{"code":403000001,"msg":"unable to read user permission"}'))
        c = wps_http.WpsHttp(token_provider=lambda: "T", direct=direct, proxy=FakeOpener())
        status, body = c.api("GET", "/v7/airpage/f")
        self.assertEqual(status, 403)
        self.assertEqual(body["code"], 403000001)

    def test_token_never_in_repr(self):
        c = wps_http.WpsHttp(token_provider=lambda: "SECRET", direct=FakeOpener(), proxy=FakeOpener())
        self.assertNotIn("SECRET", repr(c))


class TestDownload(unittest.TestCase):

    def test_atomic_download(self):
        dest = Path(tempfile.mkdtemp()) / "sub" / "a.zip"
        direct = FakeOpener(FakeResp(b"PK\x03\x04data"))
        self.assertTrue(wps_http.download("https://x.ksyun.com/a", dest, direct=direct, proxy=FakeOpener()))
        self.assertEqual(dest.read_bytes(), b"PK\x03\x04data")
        self.assertFalse(dest.with_suffix(".zip.tmp").exists())

    def test_failed_download_leaves_no_file(self):
        dest = Path(tempfile.mkdtemp()) / "a.zip"
        direct = FakeOpener(urllib.error.URLError("x"))
        proxy = FakeOpener(urllib.error.URLError("y"))
        self.assertFalse(wps_http.download("https://x.ksyun.com/a", dest, direct=direct, proxy=proxy))
        self.assertFalse(dest.exists())
        self.assertFalse(dest.with_suffix(".zip.tmp").exists())


if __name__ == "__main__":
    unittest.main()
