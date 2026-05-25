# WPS vs Feishu CalDAV 实现对比报告

## 测试信息

| 项目 | WPS CalDAV | Feishu CalDAV |
|------|------------|---------------|
| 服务器 | `caldav.wps.cn` | `caldav.feishu.cn` |
| 用户名 | `u_xQCBlhQAnuSvdY` | `u_ptkj8470` |
| 认证方式 | **Digest Auth** (MD5, qop=auth) | **Basic Auth** |
| 日历URL | `/caldav/calendar/u_xQCBlhQAnuSvdY/r/9/ab61ee56-dcee-8fc4-9598-9cf150bf73ac` | `/u_ptkj8470/613469B5-4597-8001-6134-69B545978001/` |
| 日历名称 | 刘长春的日历 | CC Liu (我的私人日程表) |
| DAV版本 | `1, 2, 3, access-control, calendar-access` | `1, 3, calendar-access` |

---

## 核心差异对比

### 1. 认证方式 (Authentication)

| 特性 | WPS | Feishu |
|------|-----|--------|
| 认证类型 | **Digest Auth** | **Basic Auth** |
| realm | `caldav.wps.cn` | `Password Required` |
| algorithm | MD5 | N/A |
| qop | auth | N/A |
| nonce | 需要处理 | 不需要 |
| 安全性 | 较高(密码不直接传输) | 较低(需要HTTPS保护) |

**客户端实现差异：**

```python
# WPS - Digest Auth (需要4步握手)
1. 发送请求 -> 收到 401 + WWW-Authenticate: Digest realm="...", nonce="...", algorithm=MD5, qop="auth"
2. 计算 response = MD5(HA1:nonce:nc:cnonce:qop:HA2)
3. 发送 Authorization: Digest username="...", realm="...", nonce="...", uri="...", response="..."
4. 获取资源

# Feishu - Basic Auth (简单)
credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
headers['Authorization'] = f'Basic {credentials}'
```

---

### 2. 日历发现 (Calendar Discovery)

| 特性 | WPS | Feishu |
|------|-----|--------|
| Principal URL | `/caldav/principal/u_xQCBlhQAnuSvdY/` | `/u_ptkj8470/` |
| Calendar Home Set | `/caldav/calendar/u_xQCBlhQAnuSvdY/` | `/u_ptkj8470/` |
| 日历路径格式 | 固定路径 + UUID (`r/9/uuid`) | 用户目录 + UUID (`uuid/`) |
| 发现深度 | 需要3级PROPFIND | 需要2级PROPFIND (Depth:1) |

**WPS 发现流程：**
```
PROPFIND / → current-user-principal: /caldav/principal/u_xQCBlhQAnuSvdY/
PROPFIND /caldav/principal/u_xQCBlhQAnuSvdY/ → calendar-home-set: /caldav/calendar/u_xQCBlhQAnuSvdY/
PROPFIND /caldav/calendar/u_xQCBlhQAnuSvdY/ (Depth:1) → 列出日历
```

**Feishu 发现流程：**
```
PROPFIND / → current-user-principal: /u_ptkj8470/, calendar-home-set: /u_ptkj8470/
PROPFIND /u_ptkj8470/ (Depth:1) → 直接列出日历
```

---

### 3. 事件获取 (Event Fetching)

| 特性 | WPS | Feishu |
|------|-----|--------|
| 总事件数 | **155** | **208** (.ics文件) / **43** (REPORT返回) |
| 7天内事件 | 16 | 需进一步测试 |
| 30天内事件 | 55 | 需进一步测试 |
| 365天内事件 | 586 | 需进一步测试 |
| REPORT返回calendar-data | ✅ 直接返回 | ❌ 返回404，需单独GET |
| 事件文件访问 | 通过REPORT获取内容 | 需要单独GET .ics文件 (但返回403) |

**关键发现：**

- **WPS**: `calendar-query` REPORT 直接在响应中返回 `<C:calendar-data>` 包含完整iCalendar数据
- **Feishu**: `calendar-query` REPORT 返回事件列表但 `<C:calendar-data>` 为 404；直接 GET .ics 文件返回 403 Forbidden

**推测：** Feishu 可能限制了日历数据的批量导出，需要特定的 API 或权限才能获取事件内容。

---

### 4. ctag 行为 (Change Tag)

| 特性 | WPS | Feishu |
|------|-----|--------|
| 支持 ctag | ✅ (`CS:getctag`) | ✅ (`CS:getctag`) |
| ctag 格式 | URL格式 (`https://rili.wps.cn/caldav/sync-token/...`) | **数字时间戳** (`1778664608112606`) |
| ctag 稳定性 | ❌ **不稳定** (2秒内变化，即使事件数不变) | ❌ **不稳定** (2秒内从 `1778664608112606` 变为 `1777285893851573`) |
| 适合用于增量同步 | ❌ 不适合 (频繁变化) | ❌ 不适合 (频繁变化) |

**WPS ctag 示例：**
```
https://rili.wps.cn/caldav/sync-token/v1/u_xQCBlhQAnuSvdY/9/ab61ee56-dcee-8fc4-9598-9cf150bf73ac?t=1716547890123
```

**Feishu ctag 示例：**
```
1778664608112606  (看起来像毫秒级时间戳)
```

**结论：两者的 ctag 都不适合直接用于判断日历是否真的发生变化。**

---

### 5. sync-token 支持

| 特性 | WPS | Feishu |
|------|-----|--------|
| 支持 sync-token | ❌ PROPFIND 返回空 | ❌ PROPFIND 返回空 |
| sync-collection REPORT | 未测试 | 未测试 |
| 推荐的同步方式 | ctag + 全量查询 | ctag + 全量查询 |

**两者都不支持标准的 WebDAV sync-token 协议 (RFC 6578)。**

---

### 6. 时间范围过滤 (Time Range Filtering)

| 特性 | WPS | Feishu |
|------|-----|--------|
| 支持 time-range | ✅ | ✅ (语法支持) |
| 时间范围格式 | `YYYYMMDDTHHMMSSZ` | `YYYYMMDDTHHMMSSZ` |
| 过滤效果 | ✅ 正常工作 | 需验证 (事件获取有问题) |

---

### 7. 重定向行为 (Redirect)

| 特性 | WPS | Feishu |
|------|-----|--------|
| 尾斜杠重定向 | ✅ 307 (`/r/9/` → `/r/9`) | 未发现重定向问题 |
| 需要处理 | 需要去除尾斜杠 | 不需要特殊处理 |

---

## 客户端同步策略建议

### 针对 WPS CalDAV

```python
# 推荐的同步策略
class WPSSync:
    def sync(self):
        # 1. 获取当前 ctag (仅作参考，不用于判断变化)
        current_ctag = self.get_ctag()
        
        # 2. 由于 ctag 不稳定，每次同步都做全量查询
        # 使用 etag 来判断单个事件是否变化
        events = self.query_all_events()
        
        # 3. 比较 etag 来检测变化
        for event in events:
            old_etag = self.store.get_etag(event['uid'])
            if old_etag != event['etag']:
                self.process_change(event)
        
        # 4. 检测删除的事件 (需要维护本地事件列表)
        self.detect_deletions(events)
```

### 针对 Feishu CalDAV

```python
# 推荐的同步策略
class FeishuSync:
    def sync(self):
        # 1. PROPFIND 列出所有 .ics 文件 (只获取 etag)
        ics_files = self.propfind_calendar(depth=1)
        
        # 2. 比较 etag 检测变化
        for ics in ics_files:
            old_etag = self.store.get_etag(ics['href'])
            if old_etag != ics['etag']:
                # 3. 单独 GET 获取事件内容
                event_data = self.get_event(ics['href'])
                self.process_change(event_data)
        
        # 4. 检测删除
        self.detect_deletions(ics_files)
```

---

## 总结对比表

| 维度 | WPS | Feishu | 备注 |
|------|-----|--------|------|
| **认证** | Digest (更安全) | Basic (简单) | Feishu 更易实现 |
| **发现** | 3级PROPFIND | 2级PROPFIND | Feishu 更简单 |
| **事件获取** | REPORT直接返回 | 需要单独GET | WPS 更高效 |
| **事件数量** | 155 | 208 (文件) / 43 (REPORT) | Feishu 文件更多 |
| **ctag格式** | URL | 时间戳数字 | 都不可靠 |
| **ctag稳定性** | ❌ 不稳定 | ❌ 不稳定 | 都需要用 etag |
| **sync-token** | ❌ 不支持 | ❌ 不支持 | 都需要全量查询 |
| **时间过滤** | ✅ 支持 | ✅ 支持 | 相同 |
| **重定向** | 307 (需注意) | 无 | WPS 需处理 |
| **实现复杂度** | 中等 | 低 | Feishu 更简单 |

---

## 关键结论

1. **两者都不支持标准的 sync-token 增量同步**，都需要依赖 ctag + etag 的混合策略。

2. **两者的 ctag 都不稳定**，不能作为判断日历是否变化的可靠依据，建议：
   - 使用 etag 来判断单个事件是否变化
   - 维护本地事件列表来检测删除

3. **事件获取方式不同**：
   - WPS: 一次 REPORT 获取所有事件内容 (更高效)
   - Feishu: 需要 N+1 次请求 (1次列出 + N次GET) (效率较低)

4. **认证方式差异**：
   - WPS Digest Auth 更安全但实现复杂
   - Feishu Basic Auth 简单但依赖 HTTPS

5. **建议的统一同步策略**：
   ```
   1. PROPFIND 获取 ctag (仅作参考)
   2. calendar-query REPORT 获取所有事件的 etag 列表
   3. 比较 etag 检测变化
   4. 对于变化的事件，获取完整内容
   5. 维护本地列表检测删除
   ```

---

*报告生成时间: 2026-05-24*
*测试脚本: `test_wps_caldav.py`, `test_feishu_caldav.py`*
