# WPS CalDAV Proxy — Design Document

> **Version:** 1.0
> **Date:** 2026-05-25
> **Status:** MVP in production, design evolved through debugging

---

## 1. Problem Statement

### 1.1 Background
WPS Office provides a CalDAV server (`caldav.wps.cn`) for calendar sync. However, its implementation has compatibility issues with mainstream calendar clients (Apple Calendar, iOS Calendar, Google Calendar, Thunderbird, etc.).

### 1.2 Root Cause Analysis

After extensive protocol testing (see `SYNC_ISSUE_REPORT.md` and `WPS_FEISHU_CALDAV_COMPARISON.md`), three "poison pills" were identified:

| Issue | WPS Behavior | Client Impact |
|-------|-------------|---------------|
| **Digest Auth** | MD5, qop=auth, nonce expires quickly | Clients fail on 2nd sync when nonce invalid |
| **307 Redirects** | `/r/9/` → `/r/9` trailing slash | Many clients don't handle CalDAV redirects |
| **Unstable ctag** | Changes every 2 seconds even with no events | Clients do unnecessary full syncs, then hit auth issues |

**Why Feishu CalDAV works:** Feishu uses Basic Auth, no redirects, and while ctag is also unstable, the auth simplicity makes it more forgiving.

### 1.3 Solution Strategy

Build a **protocol translator proxy**:
- **Backend:** Speaks WPS's "dialect" of CalDAV (Digest Auth, handles redirects, ignores unstable ctag)
- **Cache:** SQLite with computed stable ctag + sync-token
- **Frontend:** Speaks standard CalDAV (Basic Auth, stable identifiers, no redirects)

---

## 2. Architecture

### 2.1 High-Level Design

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CLIENT DEVICES                               │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐               │
│  │ iPhone  │  │  macOS  │  │ Android │  │ Windows │               │
│  │ Calendar│  │ Calendar│  │ Calendar│  │ Outlook │               │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘               │
│       │            │            │            │                      │
│       └────────────┴──────┬─────┴────────────┘                      │
│                           │                                         │
│                    HTTPS + Basic Auth                               │
│                           │                                         │
└───────────────────────────┼─────────────────────────────────────────┘
                            │
                    ┌───────▼────────┐
                    │  Nginx (Docker) │  Terminates TLS, HTTP/2
                    │   :443 → :8843  │  Static files, reverse proxy
                    └───────┬────────┘
                            │ HTTP/1.1
                ┌───────────▼────────────┐
                │  WPS CalDAV Proxy       │  Go binary, systemd service
                │  172.20.0.1:8843        │  Loopback + Docker bridge
                │                         │
                │  ┌───────────────────┐  │
                │  │  CalDAV Server    │  │  HTTP handler, Basic Auth
                │  │  (caldavserver)   │  │  PROPFIND/REPORT/GET/OPTIONS
                │  └─────────┬─────────┘  │
                │            │ Read       │
                │  ┌─────────▼─────────┐  │
                │  │   SQLite Cache    │  │  WAL mode, single-writer
                │  │     (cache)       │  │  events + meta tables
                │  └─────────┬─────────┘  │
                │            │ Write      │
                │  ┌─────────▼─────────┐  │
                │  │     Poller        │  │  60s ticker
                │  │    (poller)       │  │  Fetch → Diff → Update
                │  └─────────┬─────────┘  │
                └────────────┼────────────┘
                             │
                    ┌────────▼────────┐
                    │  WPS CalDAV      │
                    │  caldav.wps.cn   │
                    │  Digest Auth     │
                    └──────────────────┘
```

### 2.2 Component Responsibilities

#### `wpsclient` — WPS Backend Client
- **Authentication:** Digest Auth (MD5, qop=auth) with manual nonce/nc/cnonce handling
- **Discovery:** 3-level PROPFIND to find principal → calendar-home-set → calendar
- **Fetching:** REPORT calendar-query to get all events with etag + ical_data
- **Redirects:** Manual 307 handling (Go's default CheckRedirect disabled)
- **XML Parsing:** Namespace-aware regex fallbacks (WPS uses inconsistent prefixes)

#### `cache` — SQLite Event Cache
- **Schema:**
  ```sql
  events(uid PRIMARY KEY, href, etag, ical_data, created_at, updated_at)
  meta(key PRIMARY KEY, value)
  ```
- **Stable ctag:** `SHA256(sort(etags).join("\n"))` — only changes when events actually change
- **sync-token:** Simple incrementing integer stored in meta table
- **WAL mode:** Enables concurrent reads during writes
- **Single connection:** `SetMaxOpenConns(1)` avoids SQLite locking issues

#### `poller` — Background Synchronization
- **Initial sync:** `RunOnce()` called synchronously before server starts
- **Interval:** 60 seconds (configurable)
- **Change detection:** Compares incoming etags with cached etags
- **Atomic update:** Single transaction for all changes + ctag recalculation

#### `caldavserver` — Frontend CalDAV Server
- **Auth:** Basic Auth (realm: "WPS CalDAV Proxy")
- **URL Layout:**
  ```
  /caldav/                        → principal/calendar-home-set
  /caldav/u/{user}/               → principal collection
  /caldav/u/{user}/default/       → calendar
  /caldav/u/{user}/default/{uid}.ics → individual event
  ```
- **Supported methods:** OPTIONS, PROPFIND, REPORT, GET
- **PROPFIND types:** Principal, Calendar-Home, Calendar props, Calendar events
- **REPORT types:** sync-collection, calendar-query (with time-range)

#### `config` — Configuration Management
- **Source:** YAML file
- **Validation:** All fields required, interval >= 10s
- **Defaults:** Sensible defaults with empty passwords

---

## 3. Key Design Decisions

### 3.1 Why Go (not Python)?

| Criterion | Go | Python |
|-----------|-----|--------|
| Single binary deployment | ✅ | ❌ (needs venv) |
| SQLite performance | ✅ | ⚠️ (GIL) |
| HTTP server built-in | ✅ | ❌ (needs framework) |
| Cross-compile for ARM | ✅ | ❌ |
| Startup time | <100ms | ~1s |

**Decision:** Go for the proxy server. Python retained for testing scripts.

### 3.2 Why SQLite (not PostgreSQL/MySQL)?

- Single-node deployment (one VPS)
- Small dataset (~155 events, ~1MB)
- Zero operational overhead
- WAL mode provides sufficient concurrency
- Easy backup (single file)

**Future:** Can migrate to PostgreSQL if multi-user or high-availability needed.

### 3.3 Why Basic Auth on Frontend?

- Maximum client compatibility (100% of CalDAV clients support Basic Auth)
- HTTPS protects credentials in transit
- Simple, stateless implementation
- No session management needed

**Trade-off:** Lower security than Digest Auth, but acceptable behind HTTPS.

### 3.4 Why Stable ctag + sync-token?

**ctag problem:** WPS ctag changes every 2 seconds. If we forwarded WPS ctag directly, clients would sync constantly.

**Solution:** Compute ctag from event etags. Only changes when events actually change.

**sync-token problem:** WPS returns URL-formatted sync-tokens that clients can't parse.

**Solution:** Use simple incrementing integer. Client sends `sync-token: 3`, server knows if changes occurred since revision 3.

### 3.5 Why Read-Only (No Write-Back)?

**Scope decision:** MVP is read-only. Reasons:
1. WPS Calendar API for writes is undocumented/unsupported
2. Bidirectional sync requires conflict resolution (last-write-wins is dangerous for calendars)
3. Most use cases are "view WPS calendar on Apple devices"

**Future:** Could add write-through by mapping CalDAV PUT/DELETE to WPS API calls.

### 3.6 Docker Bridge IP Binding

**Problem:** Nginx runs in Docker container. `127.0.0.1` in container != host localhost.

**Options considered:**
1. `host.docker.internal` — Linux support unreliable
2. `0.0.0.0:8843` — Exposes to all interfaces, security risk
3. Docker bridge IP (`172.20.0.1`) — Clean, isolated, reachable from container

**Decision:** Bind to `172.20.0.1:8843` + iptables rule to only allow Docker subnet.

---

## 4. Data Model

### 4.1 Event Entity

```go
type Event struct {
    UID       string    // Unique identifier from iCalendar
    Href      string    // Original WPS href
    ETag      string    // WPS etag (used for change detection)
    ICalData  string    // Raw iCalendar VEVENT data
    CreatedAt time.Time // First seen timestamp
    UpdatedAt time.Time // Last update timestamp
}
```

### 4.2 Cache Meta

| Key | Value | Purpose |
|-----|-------|---------|
| `ctag` | hex string | Stable ctag for clients |
| `revision` | integer | sync-token version |

### 4.3 Change Detection Algorithm

```
1. Fetch all events from WPS → incoming[]
2. Load all (uid, etag) from cache → existing{}
3. For each incoming event:
   a. If uid not in existing → CREATED
   b. If etag differs from existing → UPDATED
   c. Else → unchanged
4. For each existing uid not in incoming → DELETED
5. If any CREATED/UPDATED/DELETED:
   a. recalcCtag() = SHA256(sort(all_etags).join("\n"))
   b. revision++
6. Commit transaction
```

---

## 5. Protocol Implementation Details

### 5.1 CalDAV Discovery Flow

```
Client                                  Proxy
  |                                       |
  |── OPTIONS /caldav/ ──────────────────→|  (capability check)
  |←─ 200 Dav: 1,2,3,calendar-access ────|
  |                                       |
  |── PROPFIND /caldav/ Depth:0 ─────────→|  (find principal)
  |←─ 207 current-user-principal=/caldav/u/caldav/
  |                                       |
  |── PROPFIND /caldav/u/caldav/ Depth:1 →|  (find calendars)
  |←─ 207 calendar-home-set + calendars   |
  |                                       |
  |── PROPFIND /caldav/u/caldav/default/  →|  (calendar props)
  |←─ 207 displayname, ctag, sync-token   |
```

### 5.2 Sync Flow

```
Client                                  Proxy
  |                                       |
  |── REPORT sync-collection ────────────→|  (incremental sync)
  |   Body: <sync-token>3</sync-token>    |
  |←─ 207 with changes (if rev > 3)       |
  |   or empty 207 with new token         |
  |                                       |
  |── REPORT calendar-query ─────────────→|  (fallback full sync)
  |←─ 207 all events with etags           |
```

### 5.3 Auth Flow

**Backend (WPS):**
```
Proxy → WPS: PROPFIND / (no auth)
WPS → Proxy: 401 WWW-Authenticate: Digest realm="...", nonce="..."
Proxy → WPS: PROPFIND / (Digest auth with computed response)
WPS → Proxy: 207 response
```

**Frontend (Clients):**
```
Client → Proxy: PROPFIND /caldav/ (no auth)
Proxy → Client: 401 WWW-Authenticate: Basic realm="WPS CalDAV Proxy"
Client → Proxy: PROPFIND /caldav/ (Basic: base64(user:pass))
Proxy → Client: 207 response
```

---

## 6. Error Handling Strategy

| Layer | Error Type | Handling |
|-------|-----------|----------|
| WPS Client | Network timeout | Log error, retry next poll cycle |
| WPS Client | 401 Digest failure | Fatal (config wrong), log and exit |
| WPS Client | 307 redirect | Follow automatically (max 5 hops) |
| Cache | SQLite locked | WAL mode prevents most; transaction rollback |
| Cache | Disk full | Log fatal error |
| Poller | Fetch failure | Log, skip update, retry next tick |
| CalDAV Server | Invalid auth | 401 with WWW-Authenticate |
| CalDAV Server | Unknown method | 405 Method Not Allowed |
| CalDAV Server | Missing event | 404 Not Found |

---

## 7. Security Model

### 7.1 Threat Model

| Threat | Mitigation |
|--------|-----------|
| Credentials in config file | File permissions 600, run as non-root user |
| Man-in-the-middle (client→nginx) | HTTPS with valid Let's Encrypt cert |
| Man-in-the-middle (nginx→proxy) | Both on same host, no external exposure |
| Brute force on Basic Auth | No rate limiting yet — add fail2ban or nginx limit_req |
| SQL injection | Parameterized queries only |
| XML injection | No external XML parsing except from WPS (trusted) |
| Information disclosure | Error messages don't leak stack traces to clients |

### 7.2 Network Security

```
Internet ──► Nginx :443 ──► Proxy :8843 (172.20.0.1)
                ↑              ↑
           TLS 1.2/1.3      HTTP/1.1 (localhost only)
           Valid cert        iptables: DROP non-local, non-docker
```

---

## 8. Performance Characteristics

| Metric | Value | Notes |
|--------|-------|-------|
| Binary size | ~12 MB | Static linked with SQLite CGO |
| Memory usage | ~10 MB | 151 events in cache |
| Startup time | ~5s | Includes initial WPS sync |
| Poll latency | ~4-5s | WPS REPORT for 155 events |
| Request latency | <10ms | Served from SQLite cache |
| Cache size | ~1 MB | 155 events × ~6KB each |
| Concurrent clients | ~100 | Limited by SQLite single-writer |

---

## 9. Testing Strategy

### 9.1 Current Tests

| Test | Type | Status |
|------|------|--------|
| `test_caldav_digest.py` | Manual WPS protocol test | ✅ Working |
| `test_all_events.py` | WPS event fetching | ✅ Working |
| `test_sync_issue.py` | ctag/sync-token diagnosis | ✅ Working |
| curl integration | End-to-end proxy test | ✅ Working |

### 9.2 Needed Tests

1. **Unit tests** for each package (cache, wpsclient, caldavserver)
2. **Go test** for stable ctag calculation
3. **Go test** for change detection logic
4. **Integration test** simulating iOS discovery sequence
5. **Integration test** simulating macOS Calendar setup
6. **Load test** for concurrent PROPFIND/REPORT

### 9.3 macOS Compatibility Testing Checklist

```
□ OPTIONS /caldav/ returns correct Dav header
□ PROPFIND /caldav/ returns principal + calendar-home-set
□ PROPFIND /caldav/u/{user}/ returns calendar list with Depth:1
□ PROPFIND /caldav/u/{user}/default/ returns all required calendar properties
□ REPORT sync-collection works with numeric sync-token
□ REPORT calendar-query returns events with proper XML escaping
□ GET /caldav/.../{uid}.ics returns raw iCalendar data
□ 401 challenge includes Basic realm
□ /.well-known/caldav returns 301 to /caldav/
```

---

## 10. Deployment Architecture

### 10.1 Runtime Environment

```
OS: Ubuntu 22.04 LTS
Container Runtime: Docker + docker-compose
Nginx: nginx:alpine (Docker)
Go Binary: Compiled natively on host (Go 1.22)
Database: SQLite 3 (file-based)
Process Manager: systemd
```

### 10.2 File Layout (VPS)

```
/opt/wps-caldav-proxy/
├── wps-caldav-proxy          # Binary (rebuilt on deploy)
├── config.yaml               # Runtime config
├── go.mod / go.sum           # Dependencies
├── data/
│   └── cache.db              # SQLite database
├── logs/
│   └── proxy.log             # Application logs
├── cmd/wps-caldav-proxy/
│   └── main.go               # Entry point
├── internal/
│   ├── cache/cache.go
│   ├── caldavserver/server.go
│   ├── config/config.go
│   ├── poller/poller.go
│   └── wpsclient/client.go
└── deploy/
    ├── install.sh
    └── wps-caldav-proxy.service
```

### 10.3 Configuration

```yaml
wps:
  server_url: "https://caldav.wps.cn"
  username: "u_xQCBlhQAnuSvdY"
  password: "..."

proxy:
  listen_addr: "172.20.0.1:8843"  # Docker bridge for nginx container
  proxy_user: "caldav"
  proxy_pass: "..."

cache:
  db_path: "data/cache.db"

poller:
  interval_seconds: 60
  enabled: true
```

---

## 11. Future Roadmap

### Phase 1: Stability (Current)
- ✅ Basic read-only proxy
- ✅ Single calendar support
- ⚠️ macOS client compatibility (in progress)

### Phase 2: Compatibility
- Proper WebDAV PROPFIND compliance (404 propstats)
- Apple-specific properties (calendar-color, timezone)
- Multiple calendar support
- Better time-range filtering (parse iCalendar properly)

### Phase 3: Features
- Web dashboard for status/monitoring
- Bidirectional sync (write back to WPS)
- Multiple WPS accounts
- Event modification through proxy
- ICS file export endpoint

### Phase 4: Scale
- PostgreSQL backend option
- Redis for distributed caching
- Horizontal scaling (multiple proxy instances)
- Webhook notifications for changes

---

## 12. Appendix: CalDAV Property Mapping

### What macOS Calendar typically requests

**Principal PROPFIND:**
```xml
<current-user-principal/>
<principal-URL/>
<calendar-home-set/>
<principal-collection-set/>
<calendar-user-address-set/>
<displayname/>
<resourcetype/>
```

**Calendar PROPFIND:**
```xml
<displayname/>
<calendar-description/>
<resourcetype/>
<supported-calendar-component-set/>
<calendar-color/>
<calendar-timezone/>
<getctag/>
<sync-token/>
<owner/>
<current-user-privilege-set/>
<supported-report-set/>
<acl/>
<quota-available-bytes/>
```

**Current Implementation Status:**

| Property | Status | Location |
|----------|--------|----------|
| current-user-principal | ✅ | propfindPrincipal |
| principal-URL | ✅ | propfindPrincipal |
| calendar-home-set | ✅ | propfindPrincipal |
| principal-collection-set | ✅ | propfindCollection |
| calendar-user-address-set | ✅ | propfindPrincipal |
| displayname | ✅ | All propfind* |
| resourcetype | ✅ | All propfind* |
| calendar-description | ✅ | propfindCalendarProps |
| supported-calendar-component-set | ✅ | propfindCalendarProps |
| calendar-color | ❌ | Not implemented |
| calendar-timezone | ❌ | Not implemented |
| getctag | ✅ | propfindCalendarProps |
| sync-token | ✅ | propfindCalendarProps |
| owner | ✅ | propfindCalendarProps |
| current-user-privilege-set | ✅ | propfindCalendarProps |
| supported-report-set | ✅ | propfindCalendarProps |
| acl | ❌ | Not implemented |
| quota-available-bytes | ❌ | Not implemented |

---

*Document end.*
