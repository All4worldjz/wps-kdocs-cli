#!/usr/bin/env python3
"""
CalDAV 认证调试脚本
尝试不同的认证方式连接 WPS CalDAV
"""

import ssl
import base64
import urllib.request
import urllib.error
from datetime import datetime

# CalDAV 服务器配置
CALDAV_CONFIG = {
    "url": "https://caldav.wps.cn",
    "username": "u_xQCBlhQAnuSvdY",
    "password": "LCGOFYWFxRon9rDYc3XIP30Gim",
}


def make_request_debug(url, method="GET", headers=None, data=None):
    """发送 HTTP 请求（详细调试版本）"""
    if headers is None:
        headers = {}
    headers["User-Agent"] = "CalDAV-Test/1.0"
    
    req = urllib.request.Request(url, method=method, headers=headers, data=data)
    
    # 创建 SSL 上下文
    ctx = ssl.create_default_context()
    
    print(f"\n[请求] {method} {url}")
    print(f"  请求头:")
    for key, value in req.headers.items():
        if key.lower() != "authorization":
            print(f"    {key}: {value}")
        else:
            print(f"    {key}: Basic *** (已隐藏)")
    
    try:
        with urllib.request.urlopen(req, context=ctx) as response:
            print(f"[响应] 状态码: {response.status}")
            print(f"  响应头:")
            for key, value in response.headers.items():
                print(f"    {key}: {value}")
            body = response.read().decode("utf-8", errors="replace")
            print(f"  响应体 ({len(body)} bytes):")
            print(f"    {body[:500]}")
            return {
                "status": response.status,
                "headers": dict(response.headers),
                "body": body,
            }
    except urllib.error.HTTPError as e:
        print(f"[响应] 状态码: {e.code}")
        print(f"  响应头:")
        for key, value in e.headers.items():
            print(f"    {key}: {value}")
        body = e.read().decode("utf-8", errors="replace")
        print(f"  响应体 ({len(body)} bytes):")
        print(f"    {body[:500]}")
        return {
            "status": e.code,
            "headers": dict(e.headers),
            "body": body,
        }
    except Exception as e:
        print(f"[异常] {e}")
        return {
            "status": 0,
            "headers": {},
            "body": "",
            "error": str(e),
        }


def test_no_auth():
    """测试无认证访问"""
    print("=" * 60)
    print("测试 1: 无认证访问")
    print("=" * 60)
    return make_request_debug(CALDAV_CONFIG["url"])


def test_basic_auth():
    """测试 Basic Auth"""
    print("\n" + "=" * 60)
    print("测试 2: Basic Auth")
    print("=" * 60)
    
    credentials = f"{CALDAV_CONFIG['username']}:{CALDAV_CONFIG['password']}"
    encoded = base64.b64encode(credentials.encode()).decode()
    auth_header = f"Basic {encoded}"
    
    return make_request_debug(
        CALDAV_CONFIG["url"],
        headers={"Authorization": auth_header}
    )


def test_proppfind_basic_auth():
    """测试 PROPFIND + Basic Auth"""
    print("\n" + "=" * 60)
    print("测试 3: PROPFIND + Basic Auth")
    print("=" * 60)
    
    credentials = f"{CALDAV_CONFIG['username']}:{CALDAV_CONFIG['password']}"
    encoded = base64.b64encode(credentials.encode()).decode()
    auth_header = f"Basic {encoded}"
    
    return make_request_debug(
        CALDAV_CONFIG["url"],
        method="PROPFIND",
        headers={
            "Authorization": auth_header,
            "Depth": "0",
        },
        data=b"""<?xml version="1.0" encoding="utf-8"?>
<D:propfind xmlns:D="DAV:">
    <D:prop>
        <D:current-user-principal/>
    </D:prop>
</D:propfind>""".strip(),
    )


def test_options():
    """测试 OPTIONS 请求（查看服务器支持的认证方式）"""
    print("\n" + "=" * 60)
    print("测试 4: OPTIONS 请求")
    print("=" * 60)
    return make_request_debug(CALDAV_CONFIG["url"], method="OPTIONS")


def test_with_password_manager():
    """测试使用 PasswordManager 的认证方式"""
    print("\n" + "=" * 60)
    print("测试 5: 使用 PasswordManager 认证")
    print("=" * 60)
    
    # 创建密码管理器
    password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    password_mgr.add_password(
        None,
        CALDAV_CONFIG["url"],
        CALDAV_CONFIG["username"],
        CALDAV_CONFIG["password"],
    )
    
    # 创建认证处理器
    auth_handler = urllib.request.HTTPBasicAuthHandler(password_mgr)
    opener = urllib.request.build_opener(auth_handler)
    
    req = urllib.request.Request(CALDAV_CONFIG["url"], method="PROPFIND")
    req.add_header("Depth", "0")
    req.add_header("User-Agent", "CalDAV-Test/1.0")
    req.data = b"""<?xml version="1.0" encoding="utf-8"?>
<D:propfind xmlns:D="DAV:">
    <D:prop>
        <D:current-user-principal/>
    </D:prop>
</D:propfind>""".strip()
    
    ctx = ssl.create_default_context()
    
    print(f"\n[请求] PROPFIND {CALDAV_CONFIG['url']}")
    print(f"  使用 PasswordManager 认证")
    
    try:
        with opener.open(req, context=ctx) as response:
            print(f"[响应] 状态码: {response.status}")
            print(f"  响应头:")
            for key, value in response.headers.items():
                print(f"    {key}: {value}")
            body = response.read().decode("utf-8", errors="replace")
            print(f"  响应体 ({len(body)} bytes):")
            print(f"    {body[:500]}")
            return {
                "status": response.status,
                "headers": dict(response.headers),
                "body": body,
            }
    except urllib.error.HTTPError as e:
        print(f"[响应] 状态码: {e.code}")
        print(f"  响应头:")
        for key, value in e.headers.items():
            print(f"    {key}: {value}")
        body = e.read().decode("utf-8", errors="replace")
        print(f"  响应体 ({len(body)} bytes):")
        print(f"    {body[:500]}")
        return {
            "status": e.code,
            "headers": dict(e.headers),
            "body": body,
        }
    except Exception as e:
        print(f"[异常] {e}")
        return {
            "status": 0,
            "headers": {},
            "body": "",
            "error": str(e),
        }


def main():
    print(f"CalDAV 认证调试脚本 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"服务器: {CALDAV_CONFIG['url']}")
    print(f"用户名: {CALDAV_CONFIG['username']}")
    
    test_no_auth()
    test_basic_auth()
    test_proppfind_basic_auth()
    test_options()
    test_with_password_manager()
    
    print("\n" + "=" * 60)
    print("调试完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
