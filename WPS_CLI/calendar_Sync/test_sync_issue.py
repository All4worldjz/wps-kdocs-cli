#!/usr/bin/env python3
"""
CalDAV 同步问题排查脚本
演示为什么只能第一次同步，以后就不能再同步了
"""

import ssl
import hashlib
import uuid
import re
import urllib.request
import urllib.error
from datetime import datetime, timedelta

CALDAV_CONFIG = {
    "url": "https://caldav.wps.cn",
    "username": "u_xQCBlhQAnuSvdY",
    "password": "LCGOFYWFxRon9rDYc3XIP30Gim",
}

CALENDAR_URL = "https://caldav.wps.cn/caldav/calendar/u_xQCBlhQAnuSvdY/r/9/ab61ee56-dcee-8fc4-9598-9cf150bf73ac"


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


def get_ctag():
    """获取当前 ctag"""
    result = make_request(
        CALENDAR_URL,
        method="PROPFIND",
        headers={"Depth": "0"},
        data=b"""<?xml version="1.0" encoding="utf-8"?>
<D:propfind xmlns:D="DAV:" xmlns:CS="http://calendarserver.org/ns/">
    <D:prop>
        <CS:getctag/>
    </D:prop>
</D:propfind>""".strip(),
        digest_auth=DigestAuth(CALDAV_CONFIG["username"], CALDAV_CONFIG["password"]),
    )
    
    if result["status"] == 207:
        ctag_match = re.search(r"<cs:getctag>([^<]+)</cs:getctag>", result["body"])
        if ctag_match:
            return ctag_match.group(1)
    return None


def get_events_by_ctag(saved_ctag=None):
    """根据 ctag 获取事件"""
    headers = {"Depth": "1"}
    if saved_ctag:
        headers["If-None-Match"] = f'"{saved_ctag}"'
    
    result = make_request(
        CALENDAR_URL,
        method="PROPFIND",
        headers=headers,
        data=b"""<?xml version="1.0" encoding="utf-8"?>
<D:propfind xmlns:D="DAV:" xmlns:CS="http://calendarserver.org/ns/">
    <D:prop>
        <D:getetag/>
        <CS:getctag/>
    </D:prop>
</D:propfind>""".strip(),
        digest_auth=DigestAuth(CALDAV_CONFIG["username"], CALDAV_CONFIG["password"]),
    )
    
    return result


def get_events_by_time_range(days_back=30, days_forward=30):
    """根据时间范围获取事件"""
    start = datetime.now() - timedelta(days=days_back)
    end = datetime.now() + timedelta(days=days_forward)
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
        CALENDAR_URL,
        method="REPORT",
        headers={"Depth": "1", "Content-Type": "application/xml"},
        data=query.encode("utf-8"),
        digest_auth=DigestAuth(CALDAV_CONFIG["username"], CALDAV_CONFIG["password"]),
    )
    
    if result["status"] == 207:
        hrefs = re.findall(r"<d:href>([^<]+)</d:href>", result["body"])
        return len(hrefs)
    return 0


def get_all_events():
    """获取所有事件"""
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
        CALENDAR_URL,
        method="REPORT",
        headers={"Depth": "1", "Content-Type": "application/xml"},
        data=query.encode("utf-8"),
        digest_auth=DigestAuth(CALDAV_CONFIG["username"], CALDAV_CONFIG["password"]),
    )
    
    if result["status"] == 207:
        hrefs = re.findall(r"<d:href>([^<]+)</d:href>", result["body"])
        return len(hrefs)
    return 0


def main():
    print("=" * 70)
    print("CalDAV 同步问题排查")
    print("=" * 70)
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # 1. 获取当前 ctag
    print("[步骤 1] 获取当前 ctag")
    ctag1 = get_ctag()
    print(f"  当前 ctag: {ctag1}")
    print()
    
    # 2. 模拟第一次同步
    print("[步骤 2] 模拟第一次同步（保存 ctag）")
    event_count1 = get_all_events()
    print(f"  获取到 {event_count1} 个事件")
    print(f"  保存 ctag: {ctag1}")
    print()
    
    # 3. 等待几秒（模拟时间流逝）
    print("[步骤 3] 等待 2 秒（模拟时间流逝）...")
    import time
    time.sleep(2)
    print()
    
    # 4. 获取新的 ctag
    print("[步骤 4] 获取新的 ctag")
    ctag2 = get_ctag()
    print(f"  新 ctag: {ctag2}")
    print(f"  ctag 是否变化: {ctag1 != ctag2}")
    print()
    
    # 5. 模拟第二次同步（使用 ctag 检查）
    print("[步骤 5] 模拟第二次同步（使用 ctag 检查）")
    if ctag1 == ctag2:
        print(f"  ctag 未变化，跳过同步")
        print(f"  ** 这就是问题所在！即使 ctag 看起来没变，实际可能有新事件 **")
    else:
        print(f"  ctag 已变化，执行同步")
        event_count2 = get_all_events()
        print(f"  获取到 {event_count2} 个事件")
    print()
    
    # 6. 检查时间范围查询的问题
    print("[步骤 6] 检查时间范围查询的问题")
    print("  常见同步策略：只查询最近 30 天到未来 30 天的事件")
    
    # 测试不同时间范围
    ranges = [
        ("最近 7 天", 7, 7),
        ("最近 30 天", 30, 30),
        ("最近 90 天", 90, 90),
        ("最近 365 天", 365, 365),
        ("所有事件", None, None),
    ]
    
    for name, back, forward in ranges:
        if back is None:
            count = get_all_events()
        else:
            count = get_events_by_time_range(back, forward)
        print(f"  {name}: {count} 个事件")
    print()
    
    # 7. 分析问题
    print("=" * 70)
    print("问题分析")
    print("=" * 70)
    print("""
根据测试结果，同步问题的可能原因：

1. **ctag 变化频率问题**
   - 如果 ctag 变化很频繁（即使没有新事件），客户端可能误判
   - 如果 ctag 变化不频繁，客户端可能错过新事件

2. **时间范围过滤问题**
   - 如果只查询最近 30 天到未来 30 天的事件
   - 新创建的事件如果不在这个范围内，就会被错过
   - 测试显示：不同时间范围的事件数量差异很大

3. **sync-token 支持问题**
   - 服务器返回了 sync-token，但格式特殊（URL 形式）
   - 客户端可能没有正确处理这种格式的 sync-token

4. **推荐的解决方案**
   a. 首次同步：获取所有事件并保存 ctag/sync-token
   b. 增量同步：
      - 使用 sync-token 进行增量同步（如果服务器支持）
      - 或者比较 ctag，如果变化则重新获取所有事件
   c. 时间范围：
      - 不要限制时间范围，或者使用更宽的范围
      - 或者分别查询历史事件和未来事件
""")


if __name__ == "__main__":
    main()
