#!/usr/bin/env python3
"""
CalDAV 连接测试脚本（使用标准库，无需安装额外依赖）
用于测试 WPS CalDAV 服务器连接和排查同步问题
"""

import json
import ssl
import base64
import urllib.request
import urllib.error
from datetime import datetime, timedelta

# CalDAV 服务器配置
CALDAV_CONFIG = {
    "url": "https://caldav.wps.cn",
    "username": "u_xQCBlhQAnuSvdY",
    "password": "LCGOFYWFxRon9rDYc3XIP30Gim",
}


def create_auth_header(username, password):
    """创建 Basic Auth 头"""
    credentials = f"{username}:{password}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"


def make_request(url, method="GET", headers=None, data=None):
    """发送 HTTP 请求"""
    auth_header = create_auth_header(CALDAV_CONFIG["username"], CALDAV_CONFIG["password"])
    
    if headers is None:
        headers = {}
    headers["Authorization"] = auth_header
    headers["User-Agent"] = "CalDAV-Test/1.0"
    
    req = urllib.request.Request(url, method=method, headers=headers, data=data)
    
    # 创建 SSL 上下文
    ctx = ssl.create_default_context()
    
    try:
        with urllib.request.urlopen(req, context=ctx) as response:
            return {
                "status": response.status,
                "headers": dict(response.headers),
                "body": response.read().decode("utf-8", errors="replace"),
            }
    except urllib.error.HTTPError as e:
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
    
    result = make_request(CALDAV_CONFIG["url"])
    
    # CalDAV 服务器对 GET 请求可能返回 200 或 207 (Multi-Status)
    # 401 表示认证失败，其他状态码通常是成功的
    if result["status"] in [200, 207]:
        print(f"✓ 连接成功 (状态码: {result['status']})")
        print(f"  响应头:")
        for key, value in result["headers"].items():
            if key.lower() in ["dav", "x-dav", "x-caldav-support", "server", "x-powered-by"]:
                print(f"    {key}: {value}")
        return True
    elif result["status"] == 401:
        print(f"✗ 认证失败 (状态码: {result['status']})")
        print(f"  请检查用户名和密码")
        return False
    elif result["status"] == 404:
        print(f"✗ 服务器未找到 (状态码: {result['status']})")
        print(f"  请检查服务器地址是否正确")
        return False
    else:
        print(f"✗ 连接失败 (状态码: {result['status']})")
        print(f"  错误: {result.get('error', 'Unknown')}")
        print(f"  响应: {result['body'][:200]}")
        return False


def discover_calendars():
    """发现日历集合"""
    print("\n" + "=" * 60)
    print("2. 发现日历集合")
    print("=" * 60)
    
    # CalDAV 标准发现流程
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
    )
    
    if result["status"] != 207:
        print(f"  获取 Principal URL 失败 (状态码: {result['status']})")
        print(f"  响应: {result['body'][:500]}")
        return None
    
    # 解析 Principal URL
    import re
    match = re.search(r"<D:href>([^<]+)</D:href>", result["body"])
    if not match:
        match = re.search(r"<current-user-principal><D:href>([^<]+)</D:href>", result["body"])
    
    if not match:
        print("  无法解析 Principal URL")
        print(f"  响应: {result['body'][:500]}")
        return None
    
    principal_url = match.group(1)
    # 确保 URL 是完整的
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
    )
    
    if result["status"] != 207:
        print(f"  获取日历主页失败 (状态码: {result['status']})")
        print(f"  响应: {result['body'][:500]}")
        return None
    
    match = re.search(r"<C:calendar-home-set><D:href>([^<]+)</D:href>", result["body"])
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
    )
    
    if result["status"] != 207:
        print(f"  列出日历失败 (状态码: {result['status']})")
        print(f"  响应: {result['body'][:500]}")
        return None
    
    # 解析日历列表
    calendars = []
    # 查找每个日历的 href 和 displayname
    hrefs = re.findall(r"<D:href>([^<]+)</D:href>", result["body"])
    names = re.findall(r"<D:displayname>([^<]*)</D:displayname>", result["body"])
    ctypes = re.findall(r"<C:supported-calendar-component-set>(.*?)</C:supported-calendar-component-set>", result["body"], re.DOTALL)
    
    print(f"  找到 {len(hrefs)} 个资源:")
    for i, href in enumerate(hrefs):
        name = names[i] if i < len(names) else "(无名称)"
        ctype = ctypes[i] if i < len(ctypes) else ""
        is_calendar = "calendar" in ctype.lower()
        
        full_url = href if href.startswith("http") else CALDAV_CONFIG["url"].rstrip("/") + href
        print(f"  {i+1}. {name} ({full_url})")
        if is_calendar:
            calendars.append({"name": name, "url": full_url})
    
    return calendars


def get_calendar_events(calendar_url, days_back=7, days_forward=30):
    """获取指定时间范围内的事件"""
    print(f"\n" + "=" * 60)
    print(f"3. 获取事件")
    print("=" * 60)
    print(f"日历 URL: {calendar_url}")
    
    start = datetime.now() - timedelta(days=days_back)
    end = datetime.now() + timedelta(days=days_forward)
    
    # 格式化时间为 CalDAV 要求的格式
    start_str = start.strftime("%Y%m%dT%H%M%SZ")
    end_str = end.strftime("%Y%m%dT%H%M%SZ")
    
    print(f"时间范围: {start.strftime('%Y-%m-%d %H:%M')} 至 {end.strftime('%Y-%m-%d %H:%M')}")
    
    # 使用 calendar-query 获取事件
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
    )
    
    if result["status"] != 207:
        print(f"  获取事件失败 (状态码: {result['status']})")
        print(f"  响应: {result['body'][:500]}")
        return []
    
    # 解析事件
    import re
    events = []
    hrefs = re.findall(r"<D:href>([^<]+)</D:href>", result["body"])
    etags = re.findall(r"<D:getetag>([^<]*)</D:getetag>", result["body"])
    lastmodified = re.findall(r"<D:getlastmodified>([^<]*)</D:getlastmodified>", result["body"])
    
    # 提取事件摘要
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


def debug_sync_issue(calendar_url):
    """排查同步问题"""
    print("\n" + "=" * 60)
    print("4. 排查同步问题")
    print("=" * 60)
    
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
    )
    
    if result["status"] == 207:
        import re
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
    )
    
    if result["status"] == 207:
        import re
        hrefs = re.findall(r"<D:href>([^<]+)</D:href>", result["body"])
        print(f"  总共 {len(hrefs)} 个事件")
        
        # 检查事件修改时间
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
    
    # 首先获取当前 sync-token
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
    )
    
    import re
    sync_token_match = re.search(r"<D:sync-token>([^<]*)</D:sync-token>", result["body"])
    
    if sync_token_match:
        sync_token = sync_token_match.group(1)
        print(f"  当前 sync-token: {sync_token[:50]}...")
        
        # 尝试使用 sync-collection 获取变更
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
        )
        
        if result["status"] == 207:
            hrefs = re.findall(r"<D:href>([^<]+)</D:href>", result["body"])
            print(f"  增量同步结果: {len(hrefs)} 个变更")
            
            # 检查新的 sync-token
            new_sync_token = re.search(r"<D:sync-token>([^<]*)</D:sync-token>", result["body"])
            if new_sync_token:
                print(f"  新 sync-token: {new_sync_token.group(1)[:50]}...")
        else:
            print(f"  增量同步失败 (状态码: {result['status']})")
            print(f"  响应: {result['body'][:500]}")
    else:
        print("  服务器不支持 sync-token，需要全量同步")
    
    # 测试 4: 检查服务器是否限制了请求频率
    print("\n[测试 4] 检查服务器响应头（速率限制等）")
    result = make_request(calendar_url, method="PROPFIND", headers={"Depth": "0"})
    
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
    print(f"CalDAV 测试脚本 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"服务器: {CALDAV_CONFIG['url']}")
    print(f"用户名: {CALDAV_CONFIG['username']}")
    print()
    
    # 测试连接
    if not test_connection():
        print("\n连接失败，退出测试")
        return
    
    # 发现日历
    calendars = discover_calendars()
    if not calendars:
        print("\n没有找到日历，退出测试")
        return
    
    # 获取事件（对第一个日历）
    if calendars:
        get_calendar_events(calendars[0]["url"])
    
    # 排查同步问题（对第一个日历）
    if calendars:
        debug_sync_issue(calendars[0]["url"])
    
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
