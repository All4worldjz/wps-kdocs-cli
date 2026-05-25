# WPS CalDAV Proxy — Handoff Document

> **Date:** 2026-05-25
> **Status:** MVP deployed to VPS, functional via curl, macOS Calendar compatibility issue pending
> **Author:** Previous AI coding agent
> **Next Owner:** Any LLM coding tool (Claude, Kimi, GPT-4, etc.)

---

## 1. Project Purpose

Build a **WPS CalDAV Proxy** that solves compatibility issues between WPS Calendar's CalDAV server and standard calendar clients (iOS, macOS, Android).

**Why this proxy is needed:**

| Issue | WPS CalDAV | Impact on Clients |
|-------|-----------|-------------------|
| Auth | Digest Auth (MD5, qop=auth) | Many clients fail on nonce/nc sync |
| Redirects | 307 on trailing slashes | Clients don't handle CalDAV redirects well |
| ctag | Unstable (changes every 2s) | Clients do unnecessary full syncs |
| sync-token | Non-standard URL format | Clients can't do incremental sync |

**The proxy's value proposition:**
- Backend: Polls WPS CalDAV with Digest Auth, handles redirects
- Cache: SQLite with stable ctag (SHA256 of sorted etags) + numeric sync-token
- Frontend: Standard CalDAV with Basic Auth, compatible with all Apple/Google clients

---

## 2. What's Been Done

### ✅ Completed

1. **WPS Client** (`internal/wpsclient/`)
   - Digest Auth implementation (MD5, qop=auth)
   - 307 redirect handling
   - CalDAV discovery (3-level PROPFIND)
   - Event fetching via REPORT calendar-query
   - XML parsing with namespace-aware regex fallback

2. **Cache** (`internal/cache/`)
   - SQLite with WAL mode
   - Event table: uid, href, etag, ical_data, timestamps
   - Meta table: ctag, revision
   - Atomic updates with change detection (created/updated/deleted)
   - Stable ctag = SHA256(sorted etags joined by newline)
   - Revision counter for sync-token

3. **Poller** (`internal/poller/`)
   - RunOnce() for initial sync before serving
   - Background ticker every 60s
   - Change logging (+n ~n -n)

4. **CalDAV Server** (`internal/caldavserver/`)
   - Basic Auth
   - OPTIONS, PROPFIND, REPORT, GET
   - Principal discovery
   - Calendar properties (with macOS compatibility additions)
   - sync-collection REPORT
   - calendar-query REPORT with time-range filtering
   - Event GET with ETag

5. **Config** (`internal/config/`)
   - YAML loading with validation
   - Default values

6. **Deployment** (VPS: `admin@all4world.cc`)
   - Binary at `/opt/wps-caldav-proxy/wps-caldav-proxy`
   - systemd service running
   - Nginx reverse proxy with HTTPS
   - Docker networking fix (binds to `172.20.0.1:8843`)
   - iptables rule for Docker subnet access
   - `/.well-known/caldav` redirect

### 🔧 Bugs Fixed During Development

| Bug | Location | Fix |
|-----|----------|-----|
| Digest auth HA2 missing in Sprintf | `wpsclient.go:60` | `fmt.Sprintf("%s:%s", ha1, nonce, ha2)` → `fmt.Sprintf("%s:%s:%s", ha1, nonce, ha2)` |
| Race condition: server starts before initial poll | `main.go` | Added `p.RunOnce()` before `go p.Start()` |
| Nginx container can't reach localhost | nginx config | Changed proxy_pass from `127.0.0.1:8843` to Docker bridge `172.20.0.1:8843` |
| iptables DROP blocking port 8843 | VPS firewall | Added ACCEPT rule for `172.20.0.0/16` → port 8843 |

---

## 3. Known Issues & Active Problems

### 🔴 Critical: macOS Calendar Cannot Add Account

**Symptom:** macOS Calendar shows "无法验证账户名或密码" (Unable to verify account name or password)

**Evidence:**
- Nginx access logs show macOS `accountsd` making successful PROPFIND requests returning 207
- curl tests pass perfectly through HTTPS
- The error persists despite server returning successful responses

**Hypotheses (ordered by likelihood):**

1. **Password entry error** — User may have mistyped the 20-char random password. The dots in the screenshot LOOK correct but can't be verified.
   - **Test:** Ask user to copy-paste `9s7kZ7X4Y7kbgxKMs8uj` directly from config

2. **macOS Keychain stale credentials** — Previous failed attempts may have cached wrong credentials. The dialog might use Keychain instead of the manually entered password.
   - **Test:** Clear Keychain entries for `all4world.cc` and retry

3. **PROPFIND response format incompleteness** — macOS is extremely picky about WebDAV compliance. Our server does NOT return proper 404 `<D:propstat>` sections for missing properties. It also returns ALL hardcoded properties regardless of what the client requested.
   - **Fix needed:** Rewrite PROPFIND handlers to:
     - Parse requested properties from XML body properly
     - Return only requested properties in 200 propstat
     - Return 404 propstat for unsupported properties
     - This is a significant refactor of `handlePropfind` and all `propfind*` functions

4. **Missing Apple-specific properties** — macOS may require `calendar-color`, `calendar-timezone`, `schedule-inbox-URL`, `schedule-outbox-URL`, etc.
   - **Fix:** Add these properties (can be dummy/empty values)

5. **HTTP/2 compatibility** — Nginx uses HTTP/2 to client, HTTP/1.1 to backend. Some older macOS versions had issues.
   - **Note:** User is on macOS 15.4.1 (build 25E253), HTTP/2 should work fine

### 🟡 Medium: Local Repo Structure is Messy

- `proxy_code/` contains flat files that don't compile as a Go module
- Missing `go.mod`, proper directory structure (`cmd/`, `internal/`)
- Duplicate files: `wpsclient_fixed.go` and `wpsclient_v2.go` (both define same package)
- The ACTUAL deployed code lives on VPS at `/opt/wps-caldav-proxy/` with proper structure
- **Action needed:** Either sync VPS code back to local repo, or restructure local files

### 🟢 Low: Event Time-Range Filtering is Naive

- `eventInTimeRange()` uses string comparison on DTSTART/DTEND values
- Doesn't handle `VALUE=DATE`, timezone parameters, all-day events properly
- **Impact:** Minor — clients can do their own filtering

---

## 4. Deployment Details

### VPS: `admin@all4world.cc` (via SSH key)

```
/opt/wps-caldav-proxy/
├── cmd/wps-caldav-proxy/main.go
├── internal/
│   ├── cache/cache.go
│   ├── caldavserver/server.go
│   ├── config/config.go
│   ├── poller/poller.go
│   └── wpsclient/client.go
├── config.yaml
├── go.mod
├── data/cache.db
├── logs/proxy.log
└── deploy/
    ├── install.sh
    └── wps-caldav-proxy.service
```

**Service management:**
```bash
sudo systemctl status wps-caldav-proxy
sudo systemctl restart wps-caldav-proxy
sudo journalctl -u wps-caldav-proxy -f
```

**Nginx config:** `/home/admin/workshop/nginx-conf/www.conf`
```nginx
location = /.well-known/caldav {
    return 301 /caldav/;
}
location /caldav/ {
    proxy_pass http://172.20.0.1:8843/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;
    proxy_read_timeout 120s;
    proxy_send_timeout 60s;
}
```

**Current client credentials (as deployed):**
- Server: `https://www.all4world.cc`
- Path: `/caldav/`
- Username: `caldav`
- Password: `9s7kZ7X4Y7kbgxKMs8uj`
- Port: 443, SSL: Yes

**Important:** The `proxy_pass` password can be changed by editing `/opt/wps-caldav-proxy/config.yaml` and restarting the service.

---

## 5. Code Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      macOS/iOS/Android                       │
│                    Basic Auth → HTTPS                        │
└──────────────────────────┬──────────────────────────────────┘
                           │
                    ┌──────▼──────┐
                    │    Nginx    │  (Docker container, HTTPS termination)
                    │  :443 → :8843 │
                    └──────┬──────┘
                           │
              ┌────────────▼────────────┐
              │   WPS CalDAV Proxy      │  (Go binary, systemd)
              │   172.20.0.1:8843       │
              │                         │
              │  ┌─────────────────┐    │
              │  │  CalDAV Server  │────┼──→ Basic Auth, stable ctag
              │  │  (caldavserver) │    │
              │  └─────────────────┘    │
              │           ↑             │
              │  ┌────────┴────────┐    │
              │  │  SQLite Cache   │    │
              │  │  (cache)        │    │
              │  └────────┬────────┘    │
              │           ↑             │
              │  ┌────────┴────────┐    │
              │  │  Poller (60s)   │    │
              │  │  (poller)       │    │
              │  └────────┬────────┘    │
              └───────────┼─────────────┘
                          │
              ┌───────────▼───────────┐
              │   WPS CalDAV Server   │
              │   caldav.wps.cn       │
              │   Digest Auth         │
              └───────────────────────┘
```

**Data flow:**
1. Poller fetches events from WPS every 60s via Digest Auth
2. Events stored in SQLite with etag + ical_data
3. Stable ctag recalculated on any change
4. Client connects via HTTPS → Nginx → Go server
5. Go server serves events from cache with Basic Auth

---

## 6. Recommended Next Steps

### Priority 1: Fix macOS Calendar Compatibility

This is the #1 user-facing issue. Options:

**Option A: Minimal fix** (recommended first)
- Ask user to verify password and clear Keychain
- If that fails, move to Option B

**Option B: Proper PROPFIND compliance** (recommended if A fails)
- Rewrite `handlePropfind` to properly parse requested properties from XML
- Return exact requested properties with proper 200/404 propstats
- Add Apple-specific properties: `calendar-color`, `calendar-timezone`, `schedule-inbox-URL`, `schedule-outbox-URL`
- Test with `cadaver` or Python `caldav` library
- This is ~2-3 hours of work

**Option C: Debug with macOS Console logs**
- Ask user to open Console.app, filter for `accountsd` or `Calendar`
- Look for exact error messages during account setup
- This requires user cooperation

### Priority 2: Code Organization

- Restructure local repo to match deployed structure
- Add `go.mod`, `cmd/`, `internal/` directories
- Remove duplicate `wpsclient_fixed.go`
- Add `.gitignore`

### Priority 3: Testing & Observability

- Add HTTP request/response logging (with auth redaction)
- Add Prometheus metrics or simple stats endpoint
- Create integration tests that simulate iOS/macOS discovery flow
- Add health check endpoint (`/healthz`)

### Priority 4: Features

- Support multiple calendars (currently hardcoded to one)
- Support TODO/VTODO (currently only VEVENT)
- Support writing events back to WPS (currently read-only)
- Web UI for status monitoring

---

## 7. Development Commands

```bash
# Local build (from /opt/wps-caldav-proxy on VPS)
cd /opt/wps-caldav-proxy
go build -o wps-caldav-proxy ./cmd/wps-caldav-proxy/

# Test WPS connection
curl -s -u "caldav:PASSWORD" -X OPTIONS https://www.all4world.cc/caldav/

# Test discovery
curl -s -u "caldav:PASSWORD" -X PROPFIND https://www.all4world.cc/caldav/ \
  -H "Content-Type: text/xml" \
  -d '<?xml version="1.0"?><D:propfind xmlns:D="DAV:"><D:prop><D:current-user-principal/></D:prop></D:propfind>'

# View logs
sudo tail -f /opt/wps-caldav-proxy/logs/proxy.log
sudo journalctl -u wps-caldav-proxy -f

# View nginx logs
docker exec webserver tail -f /var/log/nginx/access.log | grep caldav
```

---

## 8. Security Notes

- WPS credentials are in plaintext in `config.yaml` on VPS
- Proxy password is in plaintext in `config.yaml`
- Service runs as `admin` user (not root)
- Port 8843 is blocked from external access by iptables (only Docker subnet + localhost)
- No rate limiting on CalDAV endpoints yet
- No TLS between Nginx and Go backend (both on same host, considered safe)

---

## 9. Credentials & Secrets

**WPS CalDAV (backend):**
- URL: `https://caldav.wps.cn`
- Username: `u_xQCBlhQAnuSvdY`
- Password: `LCGOFYWFxRon9rDYc3XIP30Gim`

**Proxy (frontend):**
- Username: `caldav`
- Password: `9s7kZ7X4Y7kbgxKMs8uj` (randomly generated)

**⚠️ These are REAL credentials. Do not commit to public repos.**

---

## 10. Files Reference

| Local File | Purpose | Status |
|-----------|---------|--------|
| `proxy_code/main.go` | Entry point | ✅ Fixed |
| `proxy_code/caldavserver.go` | CalDAV frontend | ⚠️ Needs PROPFIND rewrite |
| `proxy_code/poller.go` | Background sync | ✅ Fixed |
| `proxy_code/cache_fixed.go` | SQLite cache | ✅ Good |
| `proxy_code/wpsclient_v2.go` | WPS backend client | ✅ Fixed |
| `proxy_code/config.go` | Config loader | ✅ Added |
| `proxy_code/config.yaml` | Config template | ✅ Good |
| `SOLUTION_ANALYSIS.md` | Original analysis | 📖 Reference |
| `SYNC_ISSUE_REPORT.md` | WPS issue diagnosis | 📖 Reference |
| `WPS_FEISHU_CALDAV_COMPARISON.md` | Comparison report | 📖 Reference |
| `test_*.py` | Python test scripts | 📖 Historical |

---

## 11. Questions for Next Developer

1. Should we invest in full WebDAV PROPFIND compliance, or try a lighter workaround for macOS?
2. Do we want to support multiple calendars (WPS user has multiple calendars)?
3. Should we add a web dashboard for monitoring sync status?
4. Is bidirectional sync (write back to WPS) in scope?

---

*End of handoff. Good luck!*
