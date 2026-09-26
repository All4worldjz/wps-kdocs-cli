"""
WPS 直连 HTTP 客户端（v5）

用途：
1. 调用 wps365-cli 本地 spec 未收录的新接口（如 /v7/airpage/{id}/export_to_markdown_zip）。
   CLI 发出的请求只带 `Authorization: Bearer <delegated token>`，因此可直接调用 openapi.wps.cn。
2. 下载导出/实体文件：本机系统代理对金山云 ks3 域名 SSL 握手超时（直连 0.16s 成功），
   WPS/金山云域名先直连，连接类错误再回退系统代理；HTTP 错误不回退。

安全：token 只驻留内存，不写日志、不出现在 repr 中。
"""

import json
import socket
import ssl
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

from . import config
from .logger import setup_logger

logger = setup_logger()

API_BASE = "https://openapi.wps.cn"
WPS_DOMAINS = ("wps.cn", "ksyun.com", "kdocs.cn", "qwps.cn", "wpscdn.cn")
CONNECT_ERRORS = (urllib.error.URLError, socket.timeout, TimeoutError, ssl.SSLError,
                  ConnectionError, OSError)

DIRECT_TIMEOUT = 20  # 直连尝试的 socket 超时（连接/单次读），被阻断时尽快回退代理
_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_PROXY = urllib.request.build_opener()   # 默认：环境变量 / macOS 系统代理


def is_wps_host(host: str) -> bool:
    host = (host or "").lower().rstrip(".")
    return any(host == d or host.endswith("." + d) for d in WPS_DOMAINS)


def open_url(req, timeout: float = 60, direct=None, proxy=None):
    """WPS/金山云域名：直连优先，连接/SSL 错误回退代理；其他域名走默认（代理）。HTTPError 直接抛出。"""
    direct = direct or _DIRECT
    proxy = proxy or _PROXY
    if isinstance(req, str):
        req = urllib.request.Request(req)
    if not is_wps_host(urlparse(req.full_url).hostname or ""):
        return proxy.open(req, timeout=timeout)
    try:
        return direct.open(req, timeout=min(timeout, DIRECT_TIMEOUT))
    except urllib.error.HTTPError:
        raise
    except CONNECT_ERRORS as e:
        logger.debug(f"直连失败，回退代理: {urlparse(req.full_url).hostname} — {e}")
        return proxy.open(req, timeout=timeout)


def download(url: str, dest: Path, timeout: float = 600, direct=None, proxy=None) -> bool:
    """下载到 dest（先写 .tmp 再原子替换）。失败返回 False 且不留残余文件。"""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    try:
        with open_url(url, timeout=timeout, direct=direct, proxy=proxy) as resp, open(tmp, "wb") as f:
            while True:
                block = resp.read(1 << 16)
                if not block:
                    break
                f.write(block)
        tmp.replace(dest)
        return True
    except Exception as e:
        logger.warning(f"   ⚠️  下载失败: {urlparse(url).hostname} — {e}")
        tmp.unlink(missing_ok=True)
        return False


def _cli_token() -> str:
    r = subprocess.run([config.CLI_BIN, "auth", "token"], capture_output=True, text=True, timeout=30)
    return r.stdout.strip() if r.returncode == 0 else ""


def _cli_refresh() -> None:
    subprocess.run([config.CLI_BIN, "auth", "refresh", "--delegated"], capture_output=True, timeout=30)


class WpsHttp:
    """openapi.wps.cn 直连客户端：Bearer token（401 时刷新重试一次）"""

    def __init__(self, token_provider: Callable[[], str] = _cli_token,
                 refresher: Callable[[], None] = _cli_refresh, direct=None, proxy=None):
        self._token_provider = token_provider
        self._refresher = refresher
        self._token: Optional[str] = None
        self._direct = direct
        self._proxy = proxy

    def __repr__(self):
        return "WpsHttp(<token hidden>)"

    def _token_value(self) -> str:
        if not self._token:
            self._token = self._token_provider()
        return self._token

    def api(self, method: str, path: str, body=None, timeout: float = 60):
        """返回 (http_status, 解析后的 JSON 或原始文本)"""
        for attempt in range(2):
            data = json.dumps(body).encode() if body is not None else None
            req = urllib.request.Request(API_BASE + path, data=data, method=method, headers={
                "Authorization": f"Bearer {self._token_value()}",
                "Content-Type": "application/json",
                "User-Agent": "WPS-Backup/5.0",
            })
            try:
                with open_url(req, timeout=timeout, direct=self._direct, proxy=self._proxy) as r:
                    raw = r.read()
                    return getattr(r, "status", 200), (json.loads(raw) if raw else {})
            except urllib.error.HTTPError as e:
                raw = e.read()
                if e.code == 401 and attempt == 0:
                    logger.info("   🔑 access token 过期，刷新后重试")
                    self._refresher()
                    self._token = None
                    continue
                try:
                    return e.code, json.loads(raw)
                except ValueError:
                    return e.code, raw.decode("utf-8", "ignore")[:300]
        return 401, {}


_CLIENT: Optional[WpsHttp] = None


def client() -> WpsHttp:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = WpsHttp()
    return _CLIENT
