#!/usr/bin/env python3
"""
CalDAV 连接测试脚本（支持 Digest 认证）
用于测试 WPS CalDAV 服务器连接和排查同步问题
"""

import ssl
import hashlib
import uuid
import re
import urllib.request
import urllib.error
from datetime import datetime, timedelta

# CalDAV 服务器配置
CALDAV_CONFIG = {
    "url": "https://caldav.wps.cn",
    "username": "u_xQCBlhQAnuSvdY",
    "password": "LCGOFYWFxRon9rDYc3XIP30Gim",
}


class DigestAuth:
    """Digest 认证处理器"""
    
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.challenge = {}
    
    def parse_challenge(self, www_authenticate_header):
        """解析 WWW-Authenticate 头"""
        # 提取 Digest 参数
        params = {}
        # 移除 "Digest " 前缀
        auth_type, auth_params = www_authenticate_header.split(" ", 1)
        
        # 解析键值对
        for match in re.finditer(r'(\w+)="([^"]*)"', auth_params):
            params[match.group(1)] = match.group(2)
        
        self.challenge = params
        return params
    
    def generate_response(self, method, uri, body=None):
        """生成 Digest 认证响应"""
        if not self.challenge:
            return None
        
        realm = self.challenge.get("realm", "")
        nonce = self.challenge.get("nonce", "")
        opaque = self.challenge.get("opaque", "")
        algorithm = self.challenge.get("algorithm", "MD5")
        qop = self.challenge.get("qop", "")
        
        # 生成 cnonce 和 nc
        cnonce = uuid.uuid4().hex[:16]
        nc = "00000001"
        
        # 计算 HA1
        if algorithm == "MD5-sess":
            ha1 = hashlib.md5(
                f"{self.username}:{realm}:{self.password}".encode()
            ).hexdigest()
            ha1 = hashlib.md5(
                f"{ha1}:{nonce}:{cnonce}".encode()
            ).hexdigest()
        else:
            ha1 = hashlib.md5(
                f"{self.username}:{realm}:{self.password}".encode()
            ).hexdigest()
        
        # 计算 HA2
        if qop and "auth-int" in qop:
            body_hash = hashlib.md5(body or b"").hexdigest()
            ha2 = hashlib.md5(
                f"{method}:{uri}:{body_hash}".encode()
            ).hexdigest()
        else:
            ha2 = hashlib.md5(
                f"{method}:{uri}".encode()
            ).hexdigest()
        
        # 计算 response
        if qop:
            response = hashlib.md5(
                f"{ha1}:{nonce}:{nc}:{cnonce}:{qop}:{ha2}".encode()
            ).hexdigest()
        else:
            response = hashlib.md5(
                f"{ha1}:{nonce}:{ha2}".encode()
            ).hexdigest()
        
        # 构建 Authorization 头
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
    """发送 HTTP 请求（支持 Digest 认证和重定向）"""
    if headers is None:
        headers = {}
    headers["User-Agent"] = "CalDAV-Test/1.0"
    
    # 提取 URI（路径部分）
    from urllib.parse import urlparse
    parsed = urlparse(url)
    uri = parsed.path or "/"
    
    req = urllib.request.Request(url, method=method, headers=headers, data=data)
    
    # 创建 SSL 上下文
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
        # 处理 307 重定向
        if e.code == 307 and redirect_count < 5 and "Location" in e.headers:
            redirect_url = e.headers.get("Location")
            if not redirect_url.startswith("http"):
                redirect_url = CALDAV_CONFIG["url"].rstrip("/") + redirect_url
            print(f"  [重定向] {url} -> {redirect_url}")
            return make_request(redirect_url, method, headers, data, digest_auth, redirect_count + 1)
        
        # 如果是 401，尝试 Digest 认证
        if e.code == 401 and digest_auth and "www-authenticate" in e.headers:
            www_auth = e.headers.get("www-authenticate", "")
            if "Digest" in www_auth:
                # 解析挑战
                digest_auth.parse_challenge(www_auth)
                
                # 生成认证响应
                auth_header = digest_auth.generate_response(method, uri, data)
                if auth_header:
                    # 重新发送请求
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


def test_connection():
    """测试基本连接"""
    print("=" * 60)
    print("1. 测试 CalDAV 服务器连接")
    print("=" * 60)
    
    digest_auth = DigestAuth(CALDAV_CONFIG["username"], CALDAV_CONFIG["password"])
    
    result = make_request(
        CALDAV_CONFIG["url"],
        method="PROPFIND",
        headers={"Depth": "0"},
        data=b"""<?xml version="1.0" encoding="utf-8"?>
<D:propfind xmlns:D="DAV:">
    <D:prop>
        <D:current-user-principal/>
    </D:prop>
</D:propfind>""".strip(),
        digest_auth=digest_auth,
    )
    
    if result["status"] in [200, 207]:
        print(f"✓ 连接成功 (状态码: {result['status']})")
        print(f"  响应头:")
        for key, value in result["headers"].items():
            if key.lower() in ["dav", "x-dav", "x-caldav-support", "server", "x-powered-by"]:
                print(f"    {key}: {value}")
        return True, digest_auth
    elif result["status"] == 401:
        print(f"✗ 认证失败 (状态码: {result['status']})")
        print(f"  响应: {result['body'][:200]}")
        return False, None
    else:
        print(f" 连接失败 (状态码: {result['status']})")
        print(f"  错误: {result.get('error', 'Unknown')}")
        print(f"  响应: {result['body'][:200]}")
        return False, None


def discover_calendars(digest_auth):
    """发现日历集合"""
    print("\n" + "=" * 60)
    print("2. 发现日历集合")
    print("=" * 60)
    
    # 1. 获取 principal URL
    print("\n[步骤 1] 获取 Principal URL")
    result = make_request(
        CALDAV_CONFIG["url"],
        method="PROPFIND",
        headers={"Depth": "0"},
        data=b"""<?xml version="1.0" encoding="utf-8"?>
<D:propfind xmlns:D="DAV:">
    <D:prop>
        <D:current-user-principal/>
    </D:prop>
</D:propfind>""".strip(),
        digest_auth=digest_auth,
    )
    
    if result["status"] != 207:
        print(f"  获取 Principal URL 失败 (状态码: {result['status']})")
        print(f"  响应: {result['body'][:500]}")
        return None
    
    # 解析 Principal URL - 支持嵌套的 XML 结构
    match = re.search(r"<d:current-user-principal>.*?<d:href>([^<]+)</d:href>", result["body"], re.DOTALL)
    if not match:
        match = re.search(r"<D:current-user-principal>.*?<D:href>([^<]+)</D:href>", result["body"], re.DOTALL)
    if not match:
        match = re.search(r"<current-user-principal><D:href>([^<]+)</D:href>", result["body"])
    if not match:
        match = re.search(r"<current-user-principal><d:href>([^<]+)</d:href>", result["body"])
    
    if not match:
        print("  无法解析 Principal URL")
        print(f"  响应: {result['body'][:500]}")
        return None
    
    principal_url = match.group(1)
    if not principal_url.startswith("http"):
        principal_url = CALDAV_CONFIG["url"].rstrip("/") + principal_url
    print(f"  Principal URL: {principal_url}")
    
    # 2. 获取日历主页
    print("\n[步骤 2] 获取日历主页 (calendar-home-set)")
    result = make_request(
        principal_url,
        method="PROPFIND",
        headers={"Depth": "0"},
        data=b"""<?xml version="1.0" encoding="utf-8"?>
<D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
    <D:prop>
        <C:calendar-home-set/>
    </D:prop>
</D:propfind>""".strip(),
        digest_auth=digest_auth,
    )
    
    if result["status"] != 207:
        print(f"  获取日历主页失败 (状态码: {result['status']})")
        print(f"  响应: {result['body'][:500]}")
        return None
    
    match = re.search(r"<cal:calendar-home-set>.*?<d:href>([^<]+)</d:href>", result["body"], re.DOTALL)
    if not match:
        match = re.search(r"<C:calendar-home-set>.*?<D:href>([^<]+)</D:href>", result["body"], re.DOTALL)
    if not match:
        match = re.search(r"<calendar-home-set[^>]*><D:href>([^<]+)</D:href>", result["body"])
    
    if not match:
        print("  无法解析日历主页 URL")
        print(f"  响应: {result['body'][:500]}")
        return None
    
    calendar_home_url = match.group(1)
    if not calendar_home_url.startswith("http"):
        calendar_home_url = CALDAV_CONFIG["url"].rstrip("/") + calendar_home_url
    print(f"  日历主页 URL: {calendar_home_url}")
    
    # 3. 列出所有日历
    print("\n[步骤 3] 列出所有日历")
    result = make_request(
        calendar_home_url,
        method="PROPFIND",
        headers={"Depth": "1"},
        data=b"""<?xml version="1.0" encoding="utf-8"?>
<D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav" xmlns:CS="http://calendarserver.org/ns/">
    <D:prop>
        <D:displayname/>
        <D:resourcetype/>
        <C:supported-calendar-component-set/>
        <C:calendar-description/>
        <CS:getctag/>
    </D:prop>
</D:propfind>""".strip(),
        digest_auth=digest_auth,
    )
    
    if result["status"] != 207:
        print(f"  列出日历失败 (状态码: {result['status']})")
        print(f"  响应: {result['body'][:500]}")
        return None
    
    # 解析日历列表 - 按 response 分组解析
    calendars = []
    
    # 使用正则表达式提取每个 response 块
    response_blocks = re.findall(r'<d:response>(.*?)</d:response>', result["body"], re.DOTALL)
    
    print(f"  找到 {len(response_blocks)} 个资源:")
    
    for block in response_blocks:
        # 提取 href
        href_match = re.search(r'<d:href>([^<]+)</d:href>', block)
        if not href_match:
            continue
        href = href_match.group(1)
        
        # 提取 displayname
        name_match = re.search(r'<d:displayname>([^<]*)</d:displayname>', block)
        name = name_match.group(1) if name_match else "(无名称)"
        
        # 检查是否有 VEVENT 组件
        has_vevent = 'name="VEVENT"' in block or 'name="vevent"' in block.lower()
        
        # 检查是否是 inbox/outbox
        is_inbox_outbox = "postbox" in href.lower() or "inbox" in href.lower() or "outbox" in href.lower()
        
        full_url = href if href.startswith("http") else CALDAV_CONFIG["url"].rstrip("/") + href
        print(f"  - {name} ({full_url}) - VEVENT: {has_vevent}, inbox/outbox: {is_inbox_outbox}")
        
        if has_vevent and not is_inbox_outbox:
            calendars.append({"name": name, "url": full_url})
    
    print(f"\n  找到 {len(calendars)} 个有效日历:")
    for cal in calendars:
        print(f"    - {cal['name']} ({cal['url']})")
    
    return calendars


def get_calendar_events(calendar_url, digest_auth, days_back=7, days_forward=30):
    """获取指定时间范围内的事件"""
    print(f"\n" + "=" * 60)
    print(f"3. 获取事件")
    print("=" * 60)
    print(f"日历 URL: {calendar_url}")
    
    start = datetime.now() - timedelta(days=days_back)
    end = datetime.now() + timedelta(days=days_forward)
    
    start_str = start.strftime("%Y%m%dT%H%M%SZ")
    end_str = end.strftime("%Y%m%dT%H%M%SZ")
    
    print(f"时间范围: {start.strftime('%Y-%m-%d %H:%M')} 至 {end.strftime('%Y-%m-%d %H:%M')}")
    
    query = f"""<?xml version="1.0" encoding="utf-8"?>
<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
    <D:prop>
        <D:getetag/>
        <D:getlastmodified/>
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
    
    if result["status"] != 207:
        print(f"  获取事件失败 (状态码: {result['status']})")
        print(f"  响应: {result['body'][:500]}")
        return []
    
    events = []
    hrefs = re.findall(r"<D:href>([^<]+)</D:href>", result["body"])
    etags = re.findall(r"<D:getetag>([^<]*)</D:getetag>", result["body"])
    lastmodified = re.findall(r"<D:getlastmodified>([^<]*)</D:getlastmodified>", result["body"])
    summaries = re.findall(r"<SUMMARY>([^<]*)</SUMMARY>", result["body"])
    dtstarts = re.findall(r"<DTSTART[^>]*>([^<]*)</DTSTART>", result["body"])
    dtends = re.findall(r"<DTEND[^>]*>([^<]*)</DTEND>", result["body"])
    
    print(f"  找到 {len(hrefs)} 个事件:")
    for i, href in enumerate(hrefs):
        summary = summaries[i] if i < len(summaries) else "(无标题)"
        etag = etags[i] if i < len(etags) else "N/A"
        lm = lastmodified[i] if i < len(lastmodified) else "N/A"
        dtstart = dtstarts[i] if i < len(dtstarts) else "N/A"
        dtend = dtends[i] if i < len(dtends) else "N/A"
        
        print(f"  {i+1}. {summary}")
        print(f"     UID: {href}")
        print(f"     ETag: {etag}")
        print(f"     Last-Modified: {lm}")
        print(f"     DTSTART: {dtstart}")
        print(f"     DTEND: {dtend}")
        
        events.append({
            "href": href,
            "summary": summary,
            "etag": etag,
            "lastmodified": lm,
            "dtstart": dtstart,
            "dtend": dtend,
        })
    
    return events


def debug_sync_issue(calendar_url, digest_auth):
    """排查同步问题"""
    print("\n" + "=" * 60)
    print("4. 排查同步问题")
    print("=" * 60)
    
    # 测试 0: 检查日历的基本属性
    print("\n[测试 0] 检查日历的基本属性")
    result = make_request(
        calendar_url,
        method="PROPFIND",
        headers={"Depth": "0"},
        data=b"""<?xml version="1.0" encoding="utf-8"?>
<D:propfind xmlns:D="DAV:" xmlns:CAL="urn:ietf:params:xml:ns:caldav" xmlns:CS="http://calendarserver.org/ns/">
    <D:prop>
        <D:displayname/>
        <CAL:calendar-description/>
        <CS:getctag/>
        <D:sync-token/>
    </D:prop>
</D:propfind>""".strip(),
        digest_auth=digest_auth,
    )
    
    if result["status"] == 207:
        print(f"  响应: {result['body'][:500]}")
    else:
        print(f"  获取日历属性失败 (状态码: {result['status']})")
    
    # 测试 1: 检查日历的 sync-token / ctag
    print("\n[测试 1] 检查日历的 sync-token / ctag")
    result = make_request(
        calendar_url,
        method="PROPFIND",
        headers={"Depth": "0"},
        data=b"""<?xml version="1.0" encoding="utf-8"?>
<D:propfind xmlns:D="DAV:" xmlns:CS="http://calendarserver.org/ns/">
    <D:prop>
        <D:sync-token/>
        <CS:getctag/>
        <D:ctag/>
    </D:prop>
</D:propfind>""".strip(),
        digest_auth=digest_auth,
    )
    
    if result["status"] == 207:
        sync_token = re.search(r"<D:sync-token>([^<]*)</D:sync-token>", result["body"])
        ctag = re.search(r"<CS:getctag>([^<]*)</CS:getctag>", result["body"])
        d_ctag = re.search(r"<D:ctag>([^<]*)</D:ctag>", result["body"])
        
        print(f"  sync-token: {sync_token.group(1) if sync_token else 'N/A'}")
        print(f"  getctag: {ctag.group(1) if ctag else 'N/A'}")
        print(f"  ctag: {d_ctag.group(1) if d_ctag else 'N/A'}")
    else:
        print(f"  获取 sync-token 失败 (状态码: {result['status']})")
        print(f"  响应: {result['body'][:300]}")
    
    # 测试 2: 获取所有事件（不限制时间）
    print("\n[测试 2] 获取所有事件（不限制时间）")
    query = """<?xml version="1.0" encoding="utf-8"?>
<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
    <D:prop>
        <D:getetag/>
        <D:getlastmodified/>
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
    
    if result["status"] == 207:
        hrefs = re.findall(r"<D:href>([^<]+)</D:href>", result["body"])
        print(f"  总共 {len(hrefs)} 个事件")
        
        lastmodified = re.findall(r"<D:getlastmodified>([^<]*)</D:getlastmodified>", result["body"])
        if lastmodified:
            print(f"  最近修改的事件:")
            for i, lm in enumerate(lastmodified[:5]):
                print(f"    {i+1}. {lm}")
    else:
        print(f"  获取所有事件失败 (状态码: {result['status']})")
        print(f"  响应: {result['body'][:500]}")
    
    # 测试 3: 测试增量同步 (sync-collection)
    print("\n[测试 3] 测试增量同步 (sync-collection)")
    
    result = make_request(
        calendar_url,
        method="PROPFIND",
        headers={"Depth": "0"},
        data=b"""<?xml version="1.0" encoding="utf-8"?>
<D:propfind xmlns:D="DAV:">
    <D:prop>
        <D:sync-token/>
    </D:prop>
</D:propfind>""".strip(),
        digest_auth=digest_auth,
    )
    
    sync_token_match = re.search(r"<D:sync-token>([^<]*)</D:sync-token>", result["body"])
    
    if sync_token_match:
        sync_token = sync_token_match.group(1)
        print(f"  当前 sync-token: {sync_token[:50]}...")
        
        sync_query = f"""<?xml version="1.0" encoding="utf-8"?>
<C:sync-collection xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
    <D:sync-token>{sync_token}</D:sync-token>
    <D:sync-level>1</D:sync-level>
    <D:prop>
        <D:getetag/>
        <C:calendar-data/>
    </D:prop>
</C:sync-collection>""".strip()
        
        result = make_request(
            calendar_url,
            method="REPORT",
            headers={"Depth": "1", "Content-Type": "application/xml"},
            data=sync_query.encode("utf-8"),
            digest_auth=digest_auth,
        )
        
        if result["status"] == 207:
            hrefs = re.findall(r"<D:href>([^<]+)</D:href>", result["body"])
            print(f"  增量同步结果: {len(hrefs)} 个变更")
            
            new_sync_token = re.search(r"<D:sync-token>([^<]*)</D:sync-token>", result["body"])
            if new_sync_token:
                print(f"  新 sync-token: {new_sync_token.group(1)[:50]}...")
        else:
            print(f"  增量同步失败 (状态码: {result['status']})")
            print(f"  响应: {result['body'][:500]}")
    else:
        print("  服务器不支持 sync-token，需要全量同步")
    
    # 测试 4: 检查服务器响应头
    print("\n[测试 4] 检查服务器响应头")
    result = make_request(
        calendar_url,
        method="PROPFIND",
        headers={"Depth": "0"},
        digest_auth=digest_auth,
    )
    
    rate_limit_headers = [
        "x-ratelimit-limit",
        "x-ratelimit-remaining",
        "x-ratelimit-reset",
        "retry-after",
        "x-rate-limit",
    ]
    
    found_rate_limit = False
    for key, value in result["headers"].items():
        if key.lower() in rate_limit_headers:
            print(f"  {key}: {value}")
            found_rate_limit = True
    
    if not found_rate_limit:
        print("  未发现速率限制头")


def main():
    print(f"CalDAV 测试脚本 (Digest 认证) - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"服务器: {CALDAV_CONFIG['url']}")
    print(f"用户名: {CALDAV_CONFIG['username']}")
    print()
    
    # 测试连接
    success, digest_auth = test_connection()
    if not success:
        print("\n连接失败，退出测试")
        return
    
    # 发现日历
    calendars = discover_calendars(digest_auth)
    if not calendars:
        print("\n没有找到日历，退出测试")
        return
    
    # 获取事件
    if calendars:
        # 使用第一个真正的日历（有 VEVENT 组件的）
        # calendars 列表只包含有 VEVENT 组件的日历
        if calendars:
            calendar_url = calendars[0]["url"]
            print(f"\n使用日历: {calendars[0]['name']} ({calendar_url})")
            get_calendar_events(calendar_url, digest_auth)
        else:
            print("\n没有找到包含事件的日历")
            return

    # 排查同步问题
    if calendars:
        calendar_url = calendars[0]["url"]
        debug_sync_issue(calendar_url, digest_auth)
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
    print("\n可能的同步问题原因:")
    print("1. 服务器不支持 sync-token，需要全量同步")
    print("2. ctag/sync-token 未正确更新，导致客户端认为没有变更")
    print("3. 时间范围过滤问题，新事件不在查询范围内")
    print("4. 服务器速率限制，后续请求被拒绝")
    print("5. 认证 token 过期，需要重新认证")


if __name__ == "__main__":
    main()
