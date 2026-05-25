# CalDAV 同步问题诊断报告

## 测试环境
- **服务器**: https://caldav.wps.cn
- **用户名**: u_xQCBlhQAnuSvdY
- **日历**: 刘长春的日历
- **认证方式**: Digest Auth

## 测试结果

### 事件数量统计
| 时间范围 | 事件数量 |
|---------|---------|
| 所有事件 | 155 个 |
| 最近 7 天 | 16 个 |
| 最近 30 天 | 55 个 |
| 最近 90 天 | 155 个 |
| 最近 365 天 | 586 个 |

### ctag 变化测试
- 第一次获取：`1779634696138474546`
- 2 秒后获取：`1779634700819096158`
- **结论**: ctag 变化频繁，即使事件数量相同

### sync-token
- 服务器返回格式：`https://rili.wps.cn/caldav/sync-token/eyJvcCI6MCwicmFuZG9tIjoxNzc5NjM0NTgwMjIyMTQwMTg0fQ==`
- 这是 URL 格式，不是标准的 opaque token

## 问题诊断

### 症状
只能第一次同步日历信息，以后就不能再同步了

### 可能原因

1. **ctag 变化频繁但没有实际变更**
   - ctag 在 2 秒内就变化了，但事件数量相同
   - 客户端可能检测到 ctag 变化后尝试同步，但发现没有新事件
   - 这可能导致客户端误判或进入错误状态

2. **sync-token 处理问题**
   - WPS CalDAV 使用 URL 格式的 sync-token
   - 客户端可能没有正确处理这种格式
   - 导致增量同步失败

3. **时间范围过滤**
   - 如果客户端使用有限时间范围查询
   - 可能错过范围外的事件
   - 导致"同步后没有新事件"的错觉

## 推荐解决方案

### 方案 1：使用 sync-token 增量同步（推荐）

```python
def sync_with_token(calendar_url, saved_token=None):
    if saved_token:
        # 增量同步
        query = f"""<?xml version="1.0" encoding="utf-8"?>
<C:sync-collection xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
    <D:sync-token>{saved_token}</D:sync-token>
    <D:sync-level>1</D:sync-level>
    <D:prop>
        <D:getetag/>
        <C:calendar-data/>
    </D:prop>
</C:sync-collection>"""
    else:
        # 全量同步
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
</C:calendar-query>"""
    
    # 执行请求...
    # 保存返回的 sync-token 用于下次同步
```

### 方案 2：使用 ctag + 全量同步

```python
def sync_with_ctag(calendar_url, saved_ctag=None):
    # 获取当前 ctag
    current_ctag = get_ctag(calendar_url)
    
    if saved_ctag == current_ctag:
        # ctag 未变化，跳过同步
        return []
    
    # ctag 变化，执行全量同步
    events = get_all_events(calendar_url)
    
    # 保存新 ctag
    save_ctag(current_ctag)
    
    return events
```

### 方案 3：混合策略

1. 首次同步：获取所有事件，保存 ctag 和 sync-token
2. 增量同步：
   - 优先使用 sync-token（如果服务器支持）
   - 如果 sync-token 失败，回退到 ctag 比较
3. 定期全量同步（如每周一次）以确保数据一致性

## 测试脚本

- `test_caldav_digest.py` - 完整的 CalDAV 测试脚本
- `test_all_events.py` - 简单的事件获取测试
- `test_sync_issue.py` - 同步问题排查脚本
- `debug_auth.py` - 认证调试脚本

## 服务器信息

- **认证方式**: Digest Auth (realm: "caldav.wps.cn")
- **算法**: MD5
- **qop**: auth
- **日历 URL**: `/caldav/calendar/u_xQCBlhQAnuSvdY/r/9/ab61ee56-dcee-8fc4-9598-9cf150bf73ac`
- **支持的特性**: VEVENT, ctag, sync-token

---

## 附录: WPS vs Feishu CalDAV 对比测试 (2026-05-24)

### Feishu CalDAV 测试结果

- **服务器**: `caldav.feishu.cn`
- **认证**: Basic Auth
- **日历URL**: `/u_ptkj8470/613469B5-4597-8001-6134-69B545978001/`
- **事件数**: 208 个 .ics 文件 (PROPFIND), 43 个事件 (REPORT)
- **ctag**: 数字时间戳格式，不稳定 (2秒内变化)
- **sync-token**: 不支持

### 主要差异

| 特性 | WPS | Feishu |
|------|-----|--------|
| 认证 | Digest (MD5, qop=auth) | Basic |
| 事件获取 | REPORT 直接返回 calendar-data | REPORT 返回404，需单独 GET .ics |
| ctag 格式 | URL | 时间戳数字 |
| ctag 稳定性 | 不稳定 | 不稳定 |
| 重定向 | 307 (尾斜杠问题) | 无 |

### 共同问题

1. **ctag 都不稳定** - 两者都在无实际变化时频繁更新 ctag
2. **都不支持 sync-token** - 无法使用标准的 WebDAV 增量同步
3. **都需要 etag-based 同步策略**

详见 `WPS_FEISHU_CALDAV_COMPARISON.md`
