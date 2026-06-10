# WPS CalDAV Proxy — Agent Instructions

**Repo type:** 运维工具项目 — WPS 日历 CalDAV 代理网关 (Standard Go Module + SQLite WAL + WebDAV Compliance).
**Status:** 生产环境运行中，由 systemd 守护，Nginx 负责反向代理与 TLS 终结。
**主要语言:** 中文（文档、注释），英文（代码标识符）。
**最后更新:** 2026-05-25

---

## 项目概述

本项目是一个高性能、轻量级的 CalDAV 代理网关，旨在解决 **WPS 日历** (`caldav.wps.cn`) 与主流系统原生客户端（iOS/macOS/Android 系统日历 App）之间的严重同步兼容性问题。

### 背景兼容性 "毒丸"
1. **Digest Auth 挑战**: WPS 后端强制使用 MD5 qop=auth 的 Digest 认证。多数日历客户端在二次同步时，因 nonce 维护或 nc 计数不匹配导致认证失效。
2. **307 临时重定向**: WPS 针对 REPORT 请求发起 307 重定向。许多客户端在重定向处理上存在 Bug，会抛出同步异常。
3. **ctag 不稳定**: 后端返回的 ctag 即使在日程无实际变化时也会频繁变更，导致客户端陷入高频全量拉取循环。
4. **macOS `calendar-multiget` 批量查询**: 原生 macOS/iOS 客户端深度拉取日程时会发起 `calendar-multiget` 类型的 REPORT 请求，要求批量提取指定 ics 列表。
5. **MKCALENDAR 兼容**: Reminders 等客户端在同步时会频繁发送 `MKCALENDAR` 来尝试在服务端创建任务集目录。

### 解决方案架构

```
┌─────────────┐    Basic Auth      ┌─────────────────────┐    Digest Auth     ┌─────────────┐
│ iOS/macOS   │  ←──────────────→  │  WPS CalDAV Proxy   │  ←──────────────→ │ WPS CalDAV  │
│ Android     │   (稳定 ctag)      │  :8843 (loopback)   │   (处理重定向)    │ 服务器       │
│ 日历 App    │                    │ · 纯 Go SQLite3     │                   │             │
└─────────────┘                    │ · 稳定 ctag (SHA256) │                   └─────────────┘
                                   │ · sync-token (增量) │
                                   └─────────────────────┘
                                              │
                                              ▼
                                        Nginx (:443 HTTPS)
```

**核心网关机制：**
- **Basic Auth 统一网关**: 对客户端暴露极简的 Basic Auth 校验（100% 客户端兼容性）。
- **Digest 自动重试 RoundTripper**: Go 内部实现 `DigestTransport` 重建 Body 流，自动拦截 challenge、计算 response 并极速跟随 307 重定向。
- **纯 Go CGO-Free 缓存**: 引入 `modernc.org/sqlite` 驱动，排除 C 编译器依赖，保证完美的跨平台单二进制交叉编译。
- **高效增量同步 (RFC 6578)**: 网关内部引入 `change_log` 增量表，基于 revision 自增值记录日程变更，100% 支撑高效的 `sync-collection` REPORT 增量拉取。
- **安全防擦除边界 (Keep-Stale)**: 如果 WPS 后端离线或返回 0 events，同步 Poller 自动开启故障闭锁保护，绝对不清除本地 SQLite 缓存，避免客户端清空用户本地日历（防数据灾难）。
- **macOS Client 深度兼容**:
  - 自动拦截 `MKCALENDAR`，安全返回 `403 Forbidden` 及标准 WebDAV 错误 XML，向提醒事项等客户端声明此网关为只读订阅，优雅安抚客户端防其挂起。
  - 完整实现 `calendar-multiget` 批量日程读取，极速响应 `207 Multi-Status`。

---

## 目录结构

```
calendar_Sync/
├── cmd/
│   └── wps-caldav-proxy/
│       └── main.go                 # 服务主入口（加载配置、加载缓存、启动轮询器与服务监听）
├── internal/
│   ├── cache/
│   │   └── cache.go                # 纯 Go SQLite3 缓存（WAL模式、表结构变更、增量 changelog 维护）
│   ├── caldavserver/
│   │   ├── server.go               # CalDAV HTTP 路由器 (OPTIONS, Basic Auth, GET, MKCALENDAR)
│   │   ├── propfind.go             # WebDAV PROPFIND 解析引擎 (精准划分 200/404 propstat，支持 Apple 拓展属性)
│   │   └── report.go               # CalDAV REPORT 解析器 (calendar-query, sync-collection, calendar-multiget)
│   ├── config/
│   │   └── config.go               # YAML 配置文件解析与安全验证
│   ├── poller/
│   │   └── poller.go               # 安全增量轮询器 (VEVENT 日程提取、Keep-Stale 防擦除合并)
│   └── wpsclient/
│       ├── client.go               # WPS 后端 API 发现与 iCalendar 日程提取 (VEVENT 严格隔离解析)
│       └── digest_transport.go     # 质询重试型 http.RoundTripper 传输层 (自动处理 401 和重定向)
├── configs/
│   └── config.yaml.example         # 基础配置模板
├── tests/
│   └── integration_test.go         # 100% 覆盖率的端到端 macOS/Android 客户端握手与实时增量同步模拟测试
├── deploy/
│   ├── nginx.conf                  # Nginx 反向代理配置段
│   └── wps-caldav-proxy.service    # Systemd 生产部署服务单元模板
├── go.mod                          # Go modules 依赖控制
├── go.sum
└── *.md                            # 技术方案、故障根因分析、对比报告及手册
```

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 代理服务核心 | Go 1.22+ (标准库 `net/http`, `database/sql`, `regexp`) |
| 数据库 | SQLite3 (`modernc.org/sqlite`，**100% 纯 Go 无 CGO 依赖**) |
| 依赖管理 | Go Modules |
| 配置管理 | YAML (`gopkg.in/yaml.v3`) |
| 生产部署 | Systemd (服务控制) + Nginx (Nginx Docker, SSL终结) |
| 原生客户端 | macOS/iOS (`dataaccessd`, `accountsd`, `remindd`) & Android |

---

## 核心开发规范

### 1. VEVENT 严格边界解析 (防止时区定义遮蔽)
WPS 后端输出的 iCalendar 字节流中，时区配置块 (`VTIMEZONE`) 和日程事件块 (`VEVENT`) 均含有 `DTSTART` 属性。
- **严重 Bug**: 历史 line-by-line 解析器会优先提取到 `VTIMEZONE` 中的基准 DTSTART (`1989-09-17`)，造成所有日程的开始时间错乱并被客户端丢弃。
- **防错约束**: 在解析日程开始和结束时间时，必须在 `BEGIN:VEVENT` 和 `END:VEVENT` 的严格包夹边界内做属性扫描，绝对禁止全文盲扫。

### 2. 数据库变更日志 (Changelog) 机制
所有日程的更新均会由 Poller 完成差量判定后合并入库：
- **新增/更新**: 写入 `events` 表并同步写 `change_log`（action = `'set'`）。
- **删除**: 从 `events` 表移除并向 `change_log` 追加删除记录（action = `'delete'`）。
- 所有 `change_log` 的动作会携带当前系统的自增 Revision，供 RFC 6578 `sync-collection` REPORT 做高效率的极速增量同步。

### 3. 数据安全 (Keep-Stale Boundary)
- 任何情况下，当轮询 WPS 接口出现鉴权超时、503、网络异常、或者发现抓回的日历数量为 0 时，Poller **绝不能**清理本地 SQLite 缓存。
- Poller 必须输出警告日志，启动 Keep-Stale 状态闭锁，继续使用本地过期缓存服务客户端，防止客户端因同步到空表而擦除用户本地数据。

---

## 构建与运行

### 1. 本地单元测试与编译
```bash
# 执行全 workspace TDD 测试 (含 E2E macOS 握手模拟及增量同步测试)
go test -v ./...

# 静态交叉编译 (CGO-free，可在任何目标机直接运行)
go build -o wps-caldav-proxy ./cmd/wps-caldav-proxy/
```

### 2. 生产环境部署 (VPS)
```bash
# 1. 复制静态编译的二进制和 configs/config.yaml 到 /opt/wps-caldav-proxy/
# 2. 设置配置文件权限
chmod 600 config.yaml

# 3. 部署 systemd 服务
sudo cp deploy/wps-caldav-proxy.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now wps-caldav-proxy

# 4. 实时跟踪运行日志
tail -f /opt/wps-caldav-proxy/logs/proxy.log
```

---

## 故障排查速查表

| 症状 | 可能原因 | 排查方法 |
|------|---------|---------|
| 客户端添加账户失败 | Nginx 转发路径或证书异常 | 执行 `curl -v https://<your-domain>/caldav/` 确认连通性 |
| 提醒事项一直发起 MKCALENDAR | Reminders 试图创建任务集 | 属于正常兼容流程，网关已稳定截断并返回 `403`，直接无视即可 |
| 日历同步为空或时间全部为 1989 年 | Timezone DTSTART 遮蔽了日程时间 | 检查是否使用了 legacy 版本。升级最新包含 `BEGIN:VEVENT` 严格隔离的 Go 版本，删除 `data/cache.db` 并重启服务重置缓存即可 |
| VPS 服务重启失败 | SQLite WAL 锁冲突或数据库只读 | 检查 `/opt/wps-caldav-proxy/data/` 目录所有者权限是否属于 `admin:admin` |

---

## 关联文档
- [HANDOFF.md](HANDOFF.md) — 详尽的开发与部署交接指南。
- walkthrough.md — 重构与 macOS 兼容性漏洞修复过程的详细演进记录（本地文件，未纳入版本控制）。
