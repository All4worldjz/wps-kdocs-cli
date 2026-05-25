#!/usr/bin/env python3
"""
简单测试：获取所有事件
"""

import ssl
import hashlib
import uuid
import re
import urllib.request
import urllib.error
from datetime import datetime

CALDAV_CONFIG = {
    "url": "https://caldav.wps.cn",
    "username": "u_xQCBlhQAnuSvdY",
    "password": "LCGOFYWFxRon9rDYc3XIP30Gim",
}


class DigestAuth:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.challenge = {}
    
    def parse_challenge(self, www_authenticate_header):
        params = {}
        auth_type, auth_params = www_authenticate_header.split(" ", 1)
        for match in re.finditer(r'(\w+)="([^"]*)"', auth_params):
            params[match.group(1)] = match.group(2)
        self.challenge = params
        return params
    
    def generate_response(self, method, uri, body=None):
        if not self.challenge:
            return None
        
        realm = self.challenge.get("realm", "")
        nonce = self.challenge.get("nonce", "")
        opaque = self.challenge.get("opaque", "")
        algorithm = self.challenge.get("algorithm", "MD5")
        qop = self.challenge.get("qop", "")
        
        cnonce = uuid.uuid4().hex[:16]
        nc = "00000001"
        
        ha1 = hashlib.md5(f"{self.username}:{realm}:{self.password}".encode()).hexdigest()
        ha2 = hashlib.md5(f"{method}:{uri}".encode()).hexdigest()
        
        if qop:
            response = hashlib.md5(f"{ha1}:{nonce}:{nc}:{cnonce}:{qop}:{ha2}".encode()).hexdigest()
        else:
            response = hashlib.md5(f"{ha1}:{nonce}:{ha2}".encode()).hexdigest()
        
        auth_header = (
            f'Digest username="{self.username}", '
            f'realm="{realm}", '
            f'nonce="{nonce}", '
            f'uri="{uri}", '
            f'response="{response}"'
        )
        
        if opaque:
            auth_header += f', opaque="{opaque}"'
        if algorithm:
            auth_header += f', algorithm={algorithm}'
        if qop:
            auth_header += f', qop={qop.split(",")[0]}'
            auth_header += f', nc={nc}'
            auth_header += f', cnonce="{cnonce}"'
        
        return auth_header


def make_request(url, method="GET", headers=None, data=None, digest_auth=None, redirect_count=0):
    if headers is None:
        headers = {}
    headers["User-Agent"] = "CalDAV-Test/1.0"
    
    from urllib.parse import urlparse
    parsed = urlparse(url)
    uri = parsed.path or "/"
    
    req = urllib.request.Request(url, method=method, headers=headers, data=data)
    ctx = ssl.create_default_context()
    
    try:
        with urllib.request.urlopen(req, context=ctx) as response:
            return {
                "status": response.status,
                "headers": dict(response.headers),
                "body": response.read().decode("utf-8", errors="replace"),
                "url": response.url,
            }
    except urllib.error.HTTPError as e:
        if e.code == 307 and redirect_count < 5 and "Location" in e.headers:
            redirect_url = e.headers.get("Location")
            if not redirect_url.startswith("http"):
                redirect_url = CALDAV_CONFIG["url"].rstrip("/") + redirect_url
            return make_request(redirect_url, method, headers, data, digest_auth, redirect_count + 1)
        
        if e.code == 401 and digest_auth and "www-authenticate" in e.headers:
            www_auth = e.headers.get("www-authenticate", "")
            if "Digest" in www_auth:
                digest_auth.parse_challenge(www_auth)
                auth_header = digest_auth.generate_response(method, uri, data)
                if auth_header:
                    headers["Authorization"] = auth_header
                    req = urllib.request.Request(url, method=method, headers=headers, data=data)
                    try:
                        with urllib.request.urlopen(req, context=ctx) as response:
                            return {
                                "status": response.status,
                                "headers": dict(response.headers),
                                "body": response.read().decode("utf-8", errors="replace"),
                                "url": response.url,
                            }
                    except urllib.error.HTTPError as e2:
                        return {
                            "status": e2.code,
                            "headers": dict(e2.headers),
                            "body": e2.read().decode("utf-8", errors="replace"),
                            "error": str(e2),
                        }
        
        return {
            "status": e.code,
            "headers": dict(e.headers),
            "body": e.read().decode("utf-8", errors="replace"),
            "error": str(e),
        }
    except Exception as e:
        return {
            "status": 0,
            "headers": {},
            "body": "",
            "error": str(e),
        }


def main():
    calendar_url = "https://caldav.wps.cn/caldav/calendar/u_xQCBlhQAnuSvdY/r/9/ab61ee56-dcee-8fc4-9598-9cf150bf73ac"
    digest_auth = DigestAuth(CALDAV_CONFIG["username"], CALDAV_CONFIG["password"])
    
    print("测试 1: 获取所有事件（无时间过滤）")
    query = """<?xml version="1.0" encoding="utf-8"?>
<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
    <D:prop>
        <D:getetag/>
        <C:calendar-data/>
    </D:prop>
    <C:filter>
        <C:comp-filter name="VCALENDAR">
            <C:comp-filter name="VEVENT"/>
        </C:comp-filter>
    </C:filter>
</C:calendar-query>""".strip()
    
    result = make_request(
        calendar_url,
        method="REPORT",
        headers={"Depth": "1", "Content-Type": "application/xml"},
        data=query.encode("utf-8"),
        digest_auth=digest_auth,
    )
    
    print(f"状态码: {result['status']}")
    if result["status"] == 207:
        # 统计事件数量
        hrefs = re.findall(r"<d:href>([^<]+)</d:href>", result["body"])
        print(f"找到 {len(hrefs)} 个事件")
        
        # 提取事件摘要
        summaries = re.findall(r"<SUMMARY>([^<]*)</SUMMARY>", result["body"])
        for i, summary in enumerate(summaries[:10]):
            print(f"  {i+1}. {summary}")
    else:
        print(f"响应: {result['body'][:500]}")
    
    print("\n测试 2: 获取最近 1 年的事件")
    start = datetime.now().replace(year=datetime.now().year - 1)
    end = datetime.now().replace(year=datetime.now().year + 1)
    start_str = start.strftime("%Y%m%dT%H%M%SZ")
    end_str = end.strftime("%Y%m%dT%H%M%SZ")
    
    query = f"""<?xml version="1.0" encoding="utf-8"?>
<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
    <D:prop>
        <D:getetag/>
        <C:calendar-data/>
    </D:prop>
    <C:filter>
        <C:comp-filter name="VCALENDAR">
            <C:comp-filter name="VEVENT">
                <C:time-range start="{start_str}" end="{end_str}"/>
            </C:comp-filter>
        </C:comp-filter>
    </C:filter>
</C:calendar-query>""".strip()
    
    result = make_request(
        calendar_url,
        method="REPORT",
        headers={"Depth": "1", "Content-Type": "application/xml"},
        data=query.encode("utf-8"),
        digest_auth=digest_auth,
    )
    
    print(f"状态码: {result['status']}")
    print(f"时间范围: {start_str} 至 {end_str}")
    if result["status"] == 207:
        hrefs = re.findall(r"<d:href>([^<]+)</d:href>", result["body"])
        print(f"找到 {len(hrefs)} 个事件")
        
        summaries = re.findall(r"<SUMMARY>([^<]*)</SUMMARY>", result["body"])
        for i, summary in enumerate(summaries[:10]):
            print(f"  {i+1}. {summary}")
    else:
        print(f"响应: {result['body'][:500]}")
    
    print("\n测试 3: 获取 ctag 并检查变化")
    result = make_request(
        calendar_url,
        method="PROPFIND",
        headers={"Depth": "0"},
        data=b"""<?xml version="1.0" encoding="utf-8"?>
<D:propfind xmlns:D="DAV:" xmlns:CS="http://calendarserver.org/ns/">
    <D:prop>
        <CS:getctag/>
    </D:prop>
</D:propfind>""".strip(),
        digest_auth=digest_auth,
    )
    
    print(f"状态码: {result['status']}")
    if result["status"] == 207:
        ctag_match = re.search(r"<cs:getctag>([^<]+)</cs:getctag>", result["body"])
        if ctag_match:
            print(f"ctag: {ctag_match.group(1)}")
        else:
            print("未找到 ctag")
    else:
        print(f"响应: {result['body'][:500]}")


if __name__ == "__main__":
    main()
