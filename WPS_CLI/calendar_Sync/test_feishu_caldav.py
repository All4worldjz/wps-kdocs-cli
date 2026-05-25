#!/usr/bin/env python3
"""
Feishu CalDAV Test Script - Compare with WPS CalDAV

Feishu CalDAV credentials:
- Server: https://caldav.feishu.cn
- Username: u_ptkj8470
- Password: 5yjeEQtmjh
"""

import http.client
import base64
import re
import sys
import time
from datetime import datetime, timedelta, timezone

def make_request(host, port, method, path, headers=None, body=None, use_https=True):
    if use_https:
        conn = http.client.HTTPSConnection(host, port, timeout=15)
    else:
        conn = http.client.HTTPConnection(host, port, timeout=15)
    try:
        if body:
            conn.request(method, path, body=body, headers=headers or {})
        else:
            conn.request(method, path, headers=headers or {})
        response = conn.getresponse()
        response_body = response.read().decode('utf-8')
        return {
            'status': response.status,
            'reason': response.reason,
            'headers': dict(response.getheaders()),
            'body': response_body,
        }
    finally:
        conn.close()

def auth_request(host, port, method, path, username, password, body=None, content_type=None, use_https=True):
    headers = {'User-Agent': 'CalDAV-Test/1.0'}
    if content_type:
        headers['Content-Type'] = content_type
    
    # First request - expect 401
    result = make_request(host, port, method, path, headers, body, use_https)
    
    if result['status'] == 401:
        # Feishu uses Basic Auth
        credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
        headers['Authorization'] = f'Basic {credentials}'
        result = make_request(host, port, method, path, headers, body, use_https)
    
    return result

def test_auth():
    print("\n" + "="*80)
    print("Feishu CalDAV - Auth Test")
    print("="*80)
    host = "caldav.feishu.cn"
    result = make_request(host, 443, "GET", "/")
    print(f"Status: {result['status']}")
    www_auth = result['headers'].get('WWW-Authenticate', '')
    print(f"WWW-Authenticate: {www_auth}")
    if 'Basic' in www_auth:
        print("Auth: Basic (DIFFERENT from WPS Digest!)")
    elif 'Digest' in www_auth:
        print("Auth: Digest")
    return 'Basic' in www_auth or 'Digest' in www_auth

def test_connectivity():
    print("\n" + "="*80)
    print("Feishu CalDAV - Connectivity")
    print("="*80)
    host, user, pwd = "caldav.feishu.cn", "u_ptkj8470", "5yjeEQtmjh"
    result = auth_request(host, 443, "OPTIONS", "/", user, pwd)
    print(f"OPTIONS / -> {result['status']}")
    if result['status'] == 200:
        print(f"DAV: {result['headers'].get('DAV', '')}")
        return True
    return result['status'] == 401 or result['status'] == 200

def test_discovery():
    print("\n" + "="*80)
    print("Feishu CalDAV - Discovery")
    print("="*80)
    host, user, pwd = "caldav.feishu.cn", "u_ptkj8470", "5yjeEQtmjh"
    
    body = '''<?xml version="1.0"?>
<D:propfind xmlns:D="DAV:">
  <D:prop>
    <D:current-user-principal/>
    <D:displayname/>
  </D:prop>
</D:propfind>'''
    
    result = auth_request(host, 443, "PROPFIND", "/", user, pwd, body, "text/xml")
    print(f"PROPFIND / -> {result['status']}")
    
    if result['status'] == 207:
        href = re.search(r'<D:href>([^<]+)</D:href>', result['body'])
        if href:
            print(f"Principal: {href.group(1)}")
            return href.group(1)
    
    # Try /{username}/
    result = auth_request(host, 443, "PROPFIND", f"/{user}/", user, pwd, body, "text/xml")
    print(f"PROPFIND /{user}/ -> {result['status']}")
    if result['status'] == 207:
        return f"/{user}/"
    return None

def test_calendars(principal):
    print("\n" + "="*80)
    print("Feishu CalDAV - List Calendars")
    print("="*80)
    host, user, pwd = "caldav.feishu.cn", "u_ptkj8470", "5yjeEQtmjh"
    
    path = principal or f"/{user}/"
    body = '''<?xml version="1.0"?>
<D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav" xmlns:CS="http://calendarserver.org/ns/">
  <D:prop>
    <D:displayname/>
    <C:calendar-description/>
    <CS:getctag/>
  </D:prop>
</D:propfind>'''
    
    result = auth_request(host, 443, "PROPFIND", path, user, pwd, body, "text/xml")
    print(f"PROPFIND {path} -> {result['status']}")
    
    calendars = []
    if result['status'] == 207:
        responses = re.findall(r'<D:response>(.*?)</D:response>', result['body'], re.DOTALL)
        for resp in responses:
            href_m = re.search(r'<D:href>([^<]+)</D:href>', resp)
            dn_m = re.search(r'<D:displayname>([^<]*)</D:displayname>', resp)
            if href_m and 'calendar-description' in resp:
                href = href_m.group(1)
                name = dn_m.group(1) if dn_m else "(unnamed)"
                ctag_m = re.search(r'<CS:getctag>([^<]+)</CS:getctag>', resp)
                print(f"  Calendar: {name}")
                print(f"    URL: {href}")
                if ctag_m:
                    print(f"    ctag: {ctag_m.group(1)[:40]}...")
                calendars.append({'name': name, 'url': href})
    
    print(f"Found {len(calendars)} calendar(s)")
    return calendars

def test_events(cal_url):
    print("\n" + "="*80)
    print("Feishu CalDAV - Events")
    print("="*80)
    host, user, pwd = "caldav.feishu.cn", "u_ptkj8470", "5yjeEQtmjh"
    
    body = '''<?xml version="1.0"?>
<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop><D:getetag/><C:calendar-data/></D:prop>
  <C:filter><C:comp-filter name="VCALENDAR"><C:comp-filter name="VEVENT"/></C:comp-filter></C:filter>
</C:calendar-query>'''
    
    result = auth_request(host, 443, "REPORT", cal_url, user, pwd, body, "text/xml")
    print(f"CALENDAR-QUERY -> {result['status']}")
    
    count = len(re.findall(r'<C:calendar-data>', result['body']))
    print(f"Total events: {count}")
    
    summary = re.search(r'SUMMARY:([^\r\n]+)', result['body'])
    if summary:
        print(f"First event: {summary.group(1)}")
    
    # Time range test
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    month_later = now + timedelta(days=30)
    
    body2 = f'''<?xml version="1.0"?>
<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop><D:getetag/><C:calendar-data/></D:prop>
  <C:filter><C:comp-filter name="VCALENDAR"><C:comp-filter name="VEVENT">
    <C:time-range start="{week_ago.strftime('%Y%m%d')}T000000Z" end="{month_later.strftime('%Y%m%d')}T000000Z"/>
  </C:comp-filter></C:comp-filter></C:filter>
</C:calendar-query>'''
    
    result2 = auth_request(host, 443, "REPORT", cal_url, user, pwd, body2, "text/xml")
    count2 = len(re.findall(r'<C:calendar-data>', result2['body']))
    print(f"Events (last 7d to next 30d): {count2}")
    
    return {'total': count, 'time_range': count2}

def test_ctag(cal_url):
    print("\n" + "="*80)
    print("Feishu CalDAV - ctag Stability")
    print("="*80)
    host, user, pwd = "caldav.feishu.cn", "u_ptkj8470", "5yjeEQtmjh"
    
    body = '''<?xml version="1.0"?>
<D:propfind xmlns:D="DAV:" xmlns:CS="http://calendarserver.org/ns/">
  <D:prop><CS:getctag/></D:prop>
</D:propfind>'''
    
    r1 = auth_request(host, 443, "PROPFIND", cal_url, user, pwd, body, "text/xml")
    c1 = re.search(r'<CS:getctag>([^<]+)</CS:getctag>', r1['body'])
    ctag1 = c1.group(1) if c1 else None
    print(f"ctag #1: {ctag1[:40] if ctag1 else 'N/A'}...")
    
    time.sleep(2)
    
    r2 = auth_request(host, 443, "PROPFIND", cal_url, user, pwd, body, "text/xml")
    c2 = re.search(r'<CS:getctag>([^<]+)</CS:getctag>', r2['body'])
    ctag2 = c2.group(1) if c2 else None
    print(f"ctag #2: {ctag2[:40] if ctag2 else 'N/A'}...")
    
    if ctag1 and ctag2:
        stable = ctag1 == ctag2
        print(f"Stable: {stable}")
        return {'stable': stable}
    return None

def test_sync_token(cal_url):
    print("\n" + "="*80)
    print("Feishu CalDAV - sync-token")
    print("="*80)
    host, user, pwd = "caldav.feishu.cn", "u_ptkj8470", "5yjeEQtmjh"
    
    body = '''<?xml version="1.0"?>
<D:propfind xmlns:D="DAV:">
  <D:prop><D:sync-token/></D:prop>
</D:propfind>'''
    
    result = auth_request(host, 443, "PROPFIND", cal_url, user, pwd, body, "text/xml")
    print(f"PROPFIND -> {result['status']}")
    
    token_m = re.search(r'<D:sync-token>([^<]+)</D:sync-token>', result['body'])
    token = token_m.group(1) if token_m else None
    print(f"sync-token: {token[:60] if token else 'N/A'}...")
    
    if token:
        print(f"Format: {'URL' if token.startswith('http') else 'Opaque'}")
    
    return {'token': token}

if __name__ == "__main__":
    print("#"*80)
    print("# Feishu CalDAV Test")
    print("#"*80)
    
    test_auth()
    
    if not test_connectivity():
        print("FAIL: connectivity")
        sys.exit(1)
    
    principal = test_discovery()
    calendars = test_calendars(principal)
    
    if not calendars:
        print("FAIL: no calendars")
        sys.exit(1)
    
    cal_url = calendars[0]['url']
    events = test_events(cal_url)
    ctag = test_ctag(cal_url)
    sync = test_sync_token(cal_url)
    
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"  Server: caldav.feishu.cn")
    print(f"  Auth: Basic")
    print(f"  Events: {events}")
    print(f"  ctag: {ctag}")
    print(f"  sync-token: {sync}")
