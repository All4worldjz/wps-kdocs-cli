#!/usr/bin/env python3
"""
CalDAV 连接测试脚本
用于测试 WPS CalDAV 服务器连接和排查同步问题
"""

import sys
import json
from datetime import datetime, timedelta
from caldav import DAVClient, Calendar

# CalDAV 服务器配置
CALDAV_CONFIG = {
    "url": "https://caldav.wps.cn",
    "username": "u_xQCBlhQAnuSvdY",
    "password": "LCGOFYWFxRon9rDYc3XIP30Gim",
}


def test_connection():
    """测试基本连接"""
    print("=" * 60)
    print("1. 测试 CalDAV 服务器连接")
    print("=" * 60)
    
    try:
        client = DAVClient(
            url=CALDAV_CONFIG["url"],
            username=CALDAV_CONFIG["username"],
            password=CALDAV_CONFIG["password"],
        )
        principal = client.principal()
        print(f"✓ 连接成功")
        print(f"  用户名: {principal.name}")
        print(f"  URL: {principal.url}")
        return client
    except Exception as e:
        print(f"✗ 连接失败: {e}")
        return None


def list_calendars(client):
    """列出所有日历"""
    print("\n" + "=" * 60)
    print("2. 列出所有日历")
    print("=" * 60)
    
    try:
        calendars = client.principal().calendars()
        print(f"找到 {len(calendars)} 个日历:")
        for i, cal in enumerate(calendars, 1):
            print(f"  {i}. {cal.name} ({cal.url})")
        return calendars
    except Exception as e:
        print(f"✗ 获取日历列表失败: {e}")
        return []


def get_events(calendar, days_back=7, days_forward=30):
    """获取指定时间范围内的事件"""
    print(f"\n" + "=" * 60)
    print(f"3. 获取事件 ({calendar.name})")
    print("=" * 60)
    
    start = datetime.now() - timedelta(days=days_back)
    end = datetime.now() + timedelta(days=days_forward)
    
    try:
        events = calendar.date_search(start=start, end=end)
        print(f"时间范围: {start.strftime('%Y-%m-%d')} 至 {end.strftime('%Y-%m-%d')}")
        print(f"找到 {len(events)} 个事件:")
        for i, event in enumerate(events, 1):
            print(f"  {i}. {event.name or '无标题'}")
            print(f"     UID: {event.id}")
        return events
    except Exception as e:
        print(f"✗ 获取事件失败: {e}")
        return []


def debug_sync_issue(client, calendars):
    """排查同步问题"""
    print("\n" + "=" * 60)
    print("4. 排查同步问题")
    print("=" * 60)
    
    if not calendars:
        print("没有可用的日历")
        return
    
    calendar = calendars[0]
    
    # 测试 1: 检查日历的 sync-token (用于增量同步)
    print("\n[测试 1] 检查日历的 sync-token")
    try:
        props = calendar.get_properties(
            ["{DAV:}sync-token", "{DAV:}ctag", "{http://apple.com/ns/cal/}getctag"]
        )
        print(f"  sync-token: {props.get('{DAV:}sync-token', 'N/A')}")
        print(f"  ctag: {props.get('{DAV:}ctag', 'N/A')}")
        print(f"  getctag: {props.get('{http://apple.com/ns/cal/}getctag', 'N/A')}")
    except Exception as e:
        print(f"  获取 sync-token 失败: {e}")
    
    # 测试 2: 获取所有事件（不限制时间）
    print("\n[测试 2] 获取所有事件")
    try:
        all_events = calendar.events()
        print(f"  总共 {len(all_events)} 个事件")
        for i, event in enumerate(all_events[:5], 1):
            print(f"  {i}. {event.name or '无标题'} (UID: {event.id})")
    except Exception as e:
        print(f"  获取所有事件失败: {e}")
    
    # 测试 3: 检查事件修改时间
    print("\n[测试 3] 检查事件修改时间")
    try:
        events = calendar.events()
        for i, event in enumerate(events[:5], 1):
            props = event.get_properties(
                ["{DAV:}getetag", "{DAV:}getlastmodified"]
            )
            print(f"  {i}. {event.name or '无标题'}")
            print(f"     etag: {props.get('{DAV:}getetag', 'N/A')}")
            print(f"     lastmodified: {props.get('{DAV:}getlastmodified', 'N/A')}")
    except Exception as e:
        print(f"  检查修改时间失败: {e}")
    
    # 测试 4: 增量同步测试 (sync-collection)
    print("\n[测试 4] 增量同步测试")
    try:
        # 第一次同步：获取初始 sync-token
        sync_token = None
        try:
            props = calendar.get_properties(["{DAV:}sync-token"])
            sync_token = props.get("{DAV:}sync-token")
            print(f"  当前 sync-token: {sync_token}")
        except Exception as e:
            print(f"  获取 sync-token 失败: {e}")
        
        if sync_token:
            # 尝试增量同步
            print("  尝试增量同步...")
            changes = calendar.calendar_multiget(event_objects=[])
            print(f"  增量同步结果: {len(changes)} 个变更")
        else:
            print("  服务器不支持 sync-token，需要全量同步")
    except Exception as e:
        print(f"  增量同步测试失败: {e}")
    
    # 测试 5: 检查服务器限制
    print("\n[测试 5] 检查服务器响应头")
    try:
        # 发送一个简单请求来检查响应头
        import requests
        session = requests.Session()
        session.auth = (CALDAV_CONFIG["username"], CALDAV_CONFIG["password"])
        response = session.get(CALDAV_CONFIG["url"], headers={"Depth": "1"})
        print(f"  状态码: {response.status_code}")
        print(f"  响应头:")
        for key, value in response.headers.items():
            if key.lower() in ["x-sync-token", "x-caldav-sync-token", "etag", "last-modified"]:
                print(f"    {key}: {value}")
    except Exception as e:
        print(f"  检查响应头失败: {e}")


def main():
    print(f"CalDAV 测试脚本 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"服务器: {CALDAV_CONFIG['url']}")
    print(f"用户名: {CALDAV_CONFIG['username']}")
    print()
    
    # 测试连接
    client = test_connection()
    if not client:
        print("\n连接失败，退出测试")
        sys.exit(1)
    
    # 列出日历
    calendars = list_calendars(client)
    if not calendars:
        print("\n没有找到日历，退出测试")
        sys.exit(1)
    
    # 获取事件
    for calendar in calendars:
        get_events(calendar)
    
    # 排查同步问题
    debug_sync_issue(client, calendars)
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
