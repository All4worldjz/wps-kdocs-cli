# WPS CalDAV Proxy — Agent Instructions

**Repo type:** 运维工具项目 — WPS 日历 CalDAV 代理网关（Go + Python 调试脚本）。  
**Status:** 已实现并部署，持续维护中。  
**主要语言:** 中文（文档、注释），英文（代码标识符）。

---

## 项目概述

本项目是一个轻量级 CalDAV 代理服务，用于解决 **WPS 日历** 与主流日历客户端（iOS/macOS/Android 系统日历 App）之间的同步兼容性问题。

### 背景问题

WPS CalDAV 服务器 (`caldav.wps.cn`) 存在三个客户端兼容性"毒丸"：

1. **Digest Auth (MD5, qop=auth)** — 需要维护 nonce、nc 计数器，客户端第二次同步时容易认证失败。
2. **307 重定向** — REPORT 请求被 307 重定向，很多日历客户端对 CalDAV 重定向处理有 bug。
3. **ctag 不稳定** — 2 秒内变化但事件数不变，导致客户端频繁触发全量同步，最终失败。

### 解决方案架构

```
┌─────────────┐    Basic Auth      ┌─────────────────────┐    Digest Auth     ┌─────────────┐
│ iOS/macOS   │  ←──────────────→  │ WPS CalDAV Proxy    │  ←──────────────→ │ WPS CalDAV  │
│ Android     │   (稳定 ctag)      │ :8843 (loopback)    │   (处理重定向)    │ 服务器       │
│ 日历 App    │                    │ · SQLite 缓存        │                   │             │
└─────────────┘                    │ · 稳定 ctag (SHA256) │                   └─────────────┘
                                   │ · sync-token 支持    │
                                   └─────────────────────┘
                                              │
                                              ▼
                                        Nginx (:443 HTTPS)
```

**代理层的关键改进：**
- 对客户端暴露 **Basic Auth**（100% 兼容所有日历客户端）
- 对 WPS 后端自动处理 **Digest Auth**、nonce 维护、307 重定向
- 提供 **稳定的 ctag** = SHA256(所有 etag 排序后拼接)，仅在事件真实变化时改变
- 支持 **sync-token**（基于本地缓存 revision 号）
- **SQLite 本地缓存**，后台定时轮询 WPS，增量更新

---

## 目录结构

```
calendar_Sync/
├── proxy_code/                    # Go 代理服务源码
│   ├── main.go                    # 入口：加载配置 → 初始化缓存 → 启动轮询器 + CalDAV 服务
│   ├── config.go                  # YAML 配置解析与校验
│   ├── config.yaml                # 运行时配置文件（含敏感凭证，勿提交）
│   ├── wpsclient_v2.go            # WPS CalDAV 客户端（Digest Auth、日历发现、事件获取）
│   ├── caldavserver.go            # 对外 CalDAV 服务（Basic Auth、PROPFIND/REPORT/GET）
│   ├── cache_fixed.go             # SQLite 缓存 + 稳定 ctag 计算
│   ├── poller.go                  # 后台轮询器：定时从 WPS 拉取事件并更新缓存
│   ├── install.sh                 # 本地/服务器一键安装脚本
│   ├── deploy_all.sh              # 从开发机一键部署到远程服务器的脚本
│   └── wps-caldav-proxy.service   # systemd 服务配置模板
│
├── *.py                           # Python 调试与测试脚本（根目录）
│   ├── debug_auth.py              # 认证调试：测试 Basic/Digest/PasswordManager
│   ├── test_caldav.py             # 使用 caldav 库测试 WPS 连接
│   ├── test_caldav_digest.py      # 原生 urllib + Digest Auth 完整测试
│   ├── test_caldav_simple.py      # 简化版 CalDAV 测试
│   ├── test_all_events.py         # 获取所有事件
│   ├── test_sync_issue.py         # 同步问题排查（演示为何只能同步一次）
│   └── test_feishu_caldav.py      # 飞书 CalDAV 对比测试
│
├── *.md                           # 文档与报告
│   ├── SOLUTION_ANALYSIS.md       # 根因分析 & 三种方案对比（A: WPS→飞书桥接, B: CalDAV Proxy, C: .ics 订阅）
│   ├── SYNC_ISSUE_REPORT.md       # 同步故障诊断报告（ctag、sync-token、时间范围测试）
│   └── WPS_FEISHU_CALDAV_COMPARISON.md  # WPS vs 飞书 CalDAV 实现细节对比
│
├── .venv/                         # Python 虚拟环境（用于运行测试脚本）
└── temp/                          # 临时图片/截图
```

**注意：** 本项目没有 `go.mod` / `go.sum`，Go 代码是在远程服务器的 Go module 中直接替换文件使用的。开发机上的 `proxy_code/` 是源码副本，真正的构建发生在服务器 `/opt/wps-caldav-proxy/` 目录下。

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 代理服务 | Go 1.22+ (标准库 `net/http`, `database/sql`) |
| 数据库 | SQLite3 (`github.com/mattn/go-sqlite3`，CGO 依赖) |
| 配置 | YAML (`gopkg.in/yaml.v3`) |
| 部署 | systemd + Nginx 反向代理 (Docker 中运行) |
| 测试脚本 | Python 3 (caldav, requests, urllib 等) |

---

## 核心模块说明

### 1. `wpsclient` — WPS 后端客户端

文件：`proxy_code/wpsclient_v2.go`

- **Digest Auth 实现**：自动处理 401 挑战，计算 MD5 response（支持 qop=auth）
- **日历发现**：3 级 PROPFIND 流程（root → principal → calendar-home-set → calendar）
- **重定向处理**：自动跟随 301/302/307，去除尾斜杠问题
- **事件获取**：REPORT `calendar-query` 获取所有 VEVENT 的 etag + calendar-data
- **XML 解析**：使用正则表达式做 namespace 前缀无关的 XML 提取（兼容 WPS 的 XML 命名空间变化）

### 2. `caldavserver` — 对外 CalDAV 服务

文件：`proxy_code/caldavserver.go`

- **Basic Auth**：标准 base64 解码校验（对客户端最友好）
- **DAV 能力声明**：`DAV: 1, 2, 3, calendar-access`
- **PROPFIND 支持**：
  - `current-user-principal` / `calendar-home-set`
  - `getctag`（返回稳定 ctag）
  - `sync-token`（返回本地 revision 号）
  - 日历集合事件列表（Depth:1）
- **REPORT 支持**：
  - `calendar-query`（支持 time-range 过滤）
  - `sync-collection`（基于 revision 号的增量同步）
- **GET 支持**：按 UID 获取单个 .ics 事件内容

### 3. `cache` — SQLite 缓存与稳定 ctag

文件：`proxy_code/cache_fixed.go`

- **表结构**：`events` (uid, href, etag, ical_data, created_at, updated_at) + `meta` (ctag, revision)
- **稳定 ctag 算法**：`SHA256(所有 etag 按字母排序后用 "\n" 拼接)`
- **原子更新**：在一个事务内完成增删改检测 + ctag 重算 + revision 自增
- **WAL 模式**：`_journal_mode=WAL`，支持并发读写

### 4. `poller` — 后台轮询器

文件：`proxy_code/poller.go`

- 启动时立即执行一次全量同步
- 之后按配置间隔（默认 60 秒）定时轮询
- 每次轮询输出变更统计：`+created ~updated -deleted`

---

## 构建与运行

### 开发机（源码编辑）

```bash
# 编辑 Go 源码（proxy_code/ 目录）
# 编辑完成后，使用 deploy_all.sh 部署到服务器
```

### 服务器（构建 & 运行）

```bash
cd /opt/wps-caldav-proxy

# 安装依赖
go mod tidy

# 构建
go build -o wps-caldav-proxy ./cmd/wps-caldav-proxy/

# 运行（前台调试）
./wps-caldav-proxy -config config.yaml

# 运行（systemd）
sudo systemctl start wps-caldav-proxy
sudo systemctl status wps-caldav-proxy
```

### 一键部署（从开发机到服务器）

```bash
cd proxy_code/
bash deploy_all.sh   # 上传、编译、测试、输出 Nginx 配置提示
```

### 客户端连接配置

```
服务器:   https://www.all4world.cc/caldav
用户名:   caldav
密码:     <config.yaml 中的 proxy_pass>
端口:     443
SSL:      是
```

---

## 配置说明

`proxy_code/config.yaml`：

```yaml
wps:
  server_url: "https://caldav.wps.cn"
  username: "u_xQCBlhQAnuSvdY"
  password: "..."                 # WPS CalDAV 专用密码

proxy:
  listen_addr: "127.0.0.1:8843"   # 仅监听 loopback，Nginx 负责 HTTPS
  proxy_user: "caldav"             # 客户端连接用的 Basic Auth 用户名
  proxy_pass: "CHANGE_ME_PASSWORD" # 客户端连接用的 Basic Auth 密码

cache:
  db_path: "data/cache.db"

poller:
  interval_seconds: 60
  enabled: true
```

**安全提示：**
- `proxy_pass` 必须修改默认值
- 服务仅绑定 `127.0.0.1`，不直接对外暴露
- WPS 密码和代理密码是两个独立的凭证层

---

## 测试策略

### Python 脚本（根目录）

| 脚本 | 用途 |
|------|------|
| `python debug_auth.py` | 调试认证问题，测试 Basic/Digest/PasswordManager |
| `python test_caldav.py` | 使用 `caldav` Python 库测试 WPS 连接和事件获取 |
| `python test_caldav_digest.py` | 最完整的原生 Digest Auth 测试（日历发现、事件获取、ctag 检测） |
| `python test_sync_issue.py` | 复现"只能同步一次"的问题 |
| `python test_feishu_caldav.py` | 飞书 CalDAV 对比测试 |

### 服务器端快速测试

```bash
# OPTIONS
curl -s -u "caldav:PASSWORD" -X OPTIONS http://127.0.0.1:8843/ -D-

# PROPFIND (发现日历)
curl -s -u "caldav:PASSWORD" -X PROPFIND http://127.0.0.1:8843/ \
  -H "Content-Type: text/xml" \
  -d '<?xml version="1.0"?><D:propfind xmlns:D="DAV:"><D:prop><D:current-user-principal/></D:prop></D:propfind>'

# REPORT (获取事件)
curl -s -u "caldav:PASSWORD" -X REPORT "http://127.0.0.1:8843/u/caldav/default/" \
  -H "Content-Type: text/xml" \
  -d '<?xml version="1.0"?><C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav"><D:prop><D:getetag/><C:calendar-data/></D:prop><C:filter><C:comp-filter name="VCALENDAR"><C:comp-filter name="VEVENT"/></C:comp-filter></C:filter></C:calendar-query>'
```

---

## 部署架构

```
互联网用户
    │
    ▼
Nginx (Docker, :443)
    │ proxy_pass to http://127.0.0.1:8843/
    ▼
wps-caldav-proxy (systemd, :8843 loopback)
    │
    ├── SQLite cache (data/cache.db)
    │
    └── 定时轮询 ──► WPS CalDAV (caldav.wps.cn, Digest Auth)
```

**systemd 服务文件：** `proxy_code/wps-caldav-proxy.service`
- 用户：`admin`
- 工作目录：`/opt/wps-caldav-proxy`
- 自动重启：always，间隔 10 秒
- 日志输出：`/opt/wps-caldav-proxy/logs/proxy.log`

---

## 开发规范

### 代码组织

- Go 源码按功能分包（`wpsclient`, `caldavserver`, `cache`, `poller`, `config`）
- 各包独立，通过接口依赖（`cache.Cache`, `wpsclient.Client`）
- `main.go` 只做初始化和编排，不含业务逻辑

### 命名约定

- 包名：小写单数（`cache`, `config`, `poller`）
- 导出类型/函数：PascalCase
- 内部函数：camelCase
- Go 文件使用 `*_fixed.go` / `*_v2.go` 等后缀表示迭代版本（项目历史遗留风格）

### 日志规范

- 使用标准库 `log`，带 `log.Lshortfile`
- 所有日志前缀带模块名：`[Main]`, `[CalDAV]`, `[Poller]`, `[Server]`
- 错误日志必须包含上下文：`[Poller] ERROR fetching events: %v`

### 安全注意事项

1. **凭证管理**
   - `config.yaml` 包含明文密码，**绝对不能提交到 Git**
   - 服务器上应设置文件权限 `chmod 600 config.yaml`
   - 开发机与服务器密码不同，修改后需同步更新

2. **网络绑定**
   - 服务默认只绑定 `127.0.0.1:8843`
   - 如需外网访问，**必须**通过 Nginx 反向代理 + HTTPS
   - 禁止直接修改 `listen_addr` 为 `0.0.0.0`

3. **数据库**
   - SQLite 文件包含所有日历事件数据（可能含敏感信息）
   - 定期备份 `data/cache.db`
   - 删除缓存文件会触发全量重新同步

4. **Go 依赖**
   - `github.com/mattn/go-sqlite3` 依赖 CGO，构建环境需要 SQLite 开发库
   - 交叉编译（如 macOS → Linux）需使用 `CC=x86_64-linux-gnu-gcc` 等工具链

---

## 故障排查速查表

| 症状 | 可能原因 | 排查方法 |
|------|---------|---------|
| 客户端无法添加账号 | Nginx 未配置或证书问题 | 检查 `curl -v https://www.all4world.cc/caldav/` |
| 认证失败 | proxy_pass 不匹配 | 检查 config.yaml 与客户端输入的密码 |
| 事件不更新 | poller 未运行或 WPS 认证失败 | 查看 `journalctl -u wps-caldav-proxy` |
| ctag 频繁变化 | 代理层 ctag 计算问题 | 检查 SQLite 中 events 表的 etag 是否有异常 |
| 首次同步后停止 | 客户端缓存了旧 ctag / sync-token | 删除客户端账号重新添加，或删除 `data/cache.db` 重启 |

---

## 相关文档索引

| 文件 | 内容 |
|------|------|
| `SOLUTION_ANALYSIS.md` | 三种同步方案对比（桥接 vs 代理 vs 订阅），推荐方案 A+B 组合 |
| `SYNC_ISSUE_REPORT.md` | WPS CalDAV 问题诊断：ctag、sync-token、时间范围、事件数量统计 |
| `WPS_FEISHU_CALDAV_COMPARISON.md` | WPS 与飞书 CalDAV 的 7 维度对比（认证、发现、事件获取、ctag、sync-token、时间过滤、重定向） |

---

*最后更新: 2026-05-25*
