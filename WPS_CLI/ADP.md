# WPS CLI 工具集 — 架构决策文档 (ADP)

**版本:** 2.0
**日期:** 2026-06-09
**作者:** Kimi Code CLI
**状态:** 生产运行中，kdocs-cli 混合架构升级完成

---

## 1. 项目定位与范围

### 1.1 目标

构建围绕 **WPS 365 开放平台** 的本地 CLI 工具集，解决三个核心运维问题：

1. **云盘差量备份** — 自动化将 WPS 云盘文件增量同步到本地存储。
2. **共享文件目录生成** — 按扩展名分类索引云盘共享文件，生成可读的 `CATALOG.md`。
3. **日历 CalDAV 代理** — 桥接 WPS 日历与标准 CalDAV 客户端（iOS/macOS/Android）。

### 1.2 非目标

- 不替代 WPS 官方客户端的在线编辑功能。
- 不提供双向同步（本地修改不回写云端）。
- 不处理 WPS 协作权限、评论、版本历史等元数据。

---

## 2. 高层架构

### 2.1 v4.0 混合架构（当前）

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          WPS 365 云端 / 金山文档                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │  WPS Drive   │  │ WPS Calendar │  │ WPS Office   │  │ kdocs API    │ │
│  │   (API)      │  │   (API)      │  │ (本地缓存)   │  │ (read-file)  │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘ │
└─────────┼─────────────────┼─────────────────┼─────────────────┼─────────┘
          │                 │                 │                 │
          ▼                 ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  wps365-cli (Go)                    kdocs-cli (Go)                      │
│  OAuth · Drive/Calendar/IM/Meeting  OAuth · read-file · search · otl    │
│  负责: 盘扫描、实体下载               负责: 文档内容提取、全文搜索        │
└─────────────────────────────────────────────────────────────────────────┘
          │                                       │
          ▼                                       ▼
┌─────────────────┐ ┌───────────────┐ ┌───────────────────────────────────┐
│ wps_backup.py   │ │ sync_shared_  │ │ calendar_Sync/                    │
│ + wps_backup/   │ │   files.py    │ │ (Go CalDAV Proxy)                 │
│ (Python 3)      │ │ (Python 3)    │ │                                   │
└────────┬────────┘ └───────┬───────┘ └───────────┬───────────────────────┘
         │                  │                     │
         ▼                  ▼                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                              本地输出                                    │
│  wps_backup_data/          wps_shared_files/        CalDAV 客户端        │
│  ├── 自动备份/ (实体)       ├── CATALOG.md          (iOS/macOS/Android) │
│  ├── 我的企业文档/          ├── docx/                                    │
│  ├── _otl_files/ (实体)     ├── pptx/                                    │
│  ├── _otl_content/ (MD)     └── pdf/                                     │
│  ├── _content_backup/ (MD)                                               │
│  └── _otl_converted_docx/                                                │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 架构演进

| 版本 | 时间 | 核心变化 |
|------|------|----------|
| v1.0 | 2026-04 | 基础备份引擎，单线程下载 |
| v2.0 | 2026-05 | 多线程并发、断点续传、状态管理 |
| v3.0 | 2026-05 | URL 限流、405 重试、file_id 路径隔离、失败追踪 |
| **v4.0** | **2026-06** | **引入 kdocs-cli 混合架构，新增文档内容备份层** |

---

## 3. 核心模块架构

### 3.1 备份引擎 (`wps_backup/`)

```
wps_backup/
├── config.py          # 单一可信源配置（路径、并发、超时、黑名单、内容备份）
├── engine.py          # 主备份引擎 v3.0：扫描 → 差量对比 → 多线程下载 → 内容备份
├── state.py           # 线程安全状态管理器（JSON 原子写入）
├── otl_engine.py      # OTL 专项 v4.0：API 扫描 → kdocs-cli 内容备份 → 缓存匹配
├── kdocs_engine.py    # kdocs-cli 封装：内容读取、搜索、认证检查
├── scheduler.py       # 守护模式轮询 + launchd plist 生成
└── logger.py          # 统一日志（文件 + 控制台）
```

#### 3.1.1 扫描阶段 (`engine.py::scan_remote_files`)

- 递归调用 `wps365-cli drive files list`（分页 100/page）。
- 过滤逻辑在扫描阶段完成：
  - `type != "file"` → 递归进入子目录。
  - 扩展名在 `SKIP_EXTS` 中 → 跳过（由 otl_engine 或其他方式处理）。
- 输出：`list[RemoteFile]`（file_id, drive_id, name, size, mtime, link_url）。

#### 3.1.2 差量对比 (`state.py::needs_update`)

状态以 `drive_id/file_id` 为 key 存储 `FileSnapshot`。

判断逻辑：
1. key 不存在 → **需要下载**（新文件）。
2. `error_msg` 含"无下载地址" / "不可下载" → **跳过**（已知永久失败）。
3. 远程 `mtime >` 本地记录 `mtime` → **需要更新**。
4. 否则 → **跳过**。

#### 3.1.3 下载阶段 (`engine.py::_download_worker`)

**线程模型：** `ThreadPoolExecutor(max_workers=4)`，每个 worker 处理单个文件。

**关键设计决策：**

| 决策 | 实现 | 原因 |
|------|------|------|
| **同名文件隔离** | `local_path = {stem}_{file_id[:8]}{suffix}` | 避免多线程竞争同一 `.tmp` 文件 |
| **旧版迁移** | `old_path.rename(local_path)` | 旧版本使用无 file_id 的路径，自动迁移避免重复下载 |
| **URL 限流** | `_url_lock` + 200ms 间隔 | 防止并发获取下载 URL 轰炸 WPS API，减少 405 错误 |
| **断点续传** | HTTP `Range` 请求，10MB/chunk | 大文件（>10MB）网络中断后可恢复，不从头开始 |
| **失败刷新 URL** | 检测到 405/chunk/expired 错误时，重新获取 URL 重试一次 | WPS 预签名 URL 可能中途过期 |
| **原子写入** | `.tmp` → `Path.replace()` | 确保下载不完整时不会留下损坏的目标文件 |
| **重试策略** | 指数退避 (2^attempt, max 30s)，405/429/500/502/503/504 均可重试 | 区分临时失败和永久失败 |
| **内容备份** | 下载成功后自动触发 `kdocs-cli drive read-file` | 将 docx/pdf/xlsx/ksheet/dbt/otl 转为 Markdown 备份 |

#### 3.1.4 OTL 专项 (`otl_engine.py` v4.0)

WPS Drive API 无法直接下载 `.otl`（在线文档私有格式）。v4.0 采用混合策略：

1. **API 扫描** — 通过 `wps365-cli` 获取所有 `.otl` 的元数据（file_id, name, size, mtime, link_url）。
2. **kdocs-cli 内容备份** — 调用 `kdocs-cli drive read-file` 将 OTL 内容转为 Markdown，保存到 `_otl_content/`。
3. **缓存扫描** — 读取 macOS WPS Office 沙盒：`~/Library/Containers/com.kingsoft.wpsoffice.mac/.../filecache/rectfile2.xml`。
4. **匹配算法** —
   - 精确文件名匹配（不区分大小写）+ 大小容差 0.5x–2.0x。
   - 模糊大小匹配（容差 ±15%）作为 fallback。
5. **增量复制** — 命中缓存的 `.otl` 复制到 `_otl_files/`，未命中的生成 `EXPORT_GUIDE.md`。

**覆盖率对比：**

| 方式 | v3.0 | v4.0 |
|------|------|------|
| 缓存实体备份 | 23/201 (11%) | 23/201 (11%，保留) |
| kdocs-cli 内容备份 | 0/201 | **169/201 (84%)** |
| 导出指南 | 178 个 | 32 个 |

#### 3.1.5 kdocs-cli 封装 (`kdocs_engine.py`)

- `read_file_content()` — 调用 `kdocs-cli drive read-file`，返回 Markdown 内容
- `backup_file_content()` — 将文档内容备份为 `.md`（带 YAML frontmatter）
- `backup_otl_content()` — OTL 专用内容备份
- `search_files()` — 文件名/全文搜索
- `check_kdocs_cli_available()` — 认证状态检查
- `get_kdocs_version()` — 版本获取

**内容备份文件格式：**

```markdown
---
file_id: xxx
drive_id: xxx
name: 文件名.docx
source_format: .docx
backup_at: 2026-06-09 23:01:47
---

文档内容（Markdown 格式）...
```

### 3.2 状态持久化 (`state.py`)

```
backup_state.json
├── meta
│   ├── version: 1
│   ├── last_backup_at: "2026-06-09 22:55:13"
│   ├── total_files: 906
│   └── total_size: 25988303665
└── files: { "drive_id/file_id" → FileSnapshot }
```

`FileSnapshot` 字段：
- `file_id`, `drive_id`, `name`, `size`, `mtime` — 远程元数据。
- `local_path`, `local_hash` — 本地存储路径和 SHA256。
- `link_url` — WPS 在线编辑链接。
- `backed_up_at` — 备份时间戳。
- `retry_count`, `error_msg` — 失败追踪。

**原子写入机制：** 先写 `.tmp`，再用 `os.replace()` 覆盖原文件，确保进程崩溃不会损坏状态。

### 3.3 调度系统 (`scheduler.py`)

- **守护模式** — Python 进程轮询当前时间，到达 `SCHEDULE_HOUR:SCHEDULE_MINUTE` 自动触发备份。
- **launchd** — 生成 `com.wps.backup.plist`，通过 macOS `launchctl` 实现系统级定时任务。

### 3.4 共享文件目录生成 (`sync_shared_files.py`)

- 遍历所有云盘，收集共享文件元数据。
- 按扩展名分类，在 `wps_shared_files/` 下创建子目录索引。
- 生成 `CATALOG.md` 总索引（不下载实体文件）。

### 3.5 日历 CalDAV 代理 (`calendar_Sync/`)

独立子项目，见 `calendar_Sync/AGENTS.md` 和 `calendar_Sync/DESIGN.md`。

---

## 4. 数据流详解

### 4.1 备份主流程

```
[开始备份]
    │
    ▼
[认证检查] ──► wps365-cli auth token
    │ 失败 ──► 报错退出
    │
    ▼
[扫描远程盘列表] ──► wps365-cli drive list
    │
    ▼
[递归扫描文件] ──► wps365-cli drive files list (分页)
    │ 过滤 SKIP_EXTS
    │
    ▼
[差量对比] ──► 对比 state.json 中的 mtime
    │ 需要更新? ──► 加入 to_download 列表
    │ 已最新?   ──► skipped++
    │
    ▼
[多线程下载] ──► ThreadPoolExecutor(4)
    │ 每个 worker:
    │   1. 检查本地是否已存在（新路径 + 旧路径 fallback）
    │   2. 限流获取下载 URL
    │   3. >10MB: 断点续传下载
    │   4. ≤10MB: 简单下载
    │   5. 失败时刷新 URL 重试
    │   6. 成功: 更新 state
    │   7. 成功: 【v4.0】触发 kdocs-cli 内容备份（如格式支持）
    │   8. 失败: mark_failed
    │
    ▼
[清理过期记录] ──► prune_stale (删除远程已不存在的本地记录)
    │
    ▼
[输出汇总] ──► 日志 + 返回 BackupResult
```

### 4.2 OTL 备份流程 (v4.0)

```
[开始 OTL 备份]
    │
    ▼
[API 扫描] ──► wps365-cli drive files list 过滤 .otl
    │
    ▼
[kdocs-cli 内容备份] ──► kdocs-cli drive read-file
    │ ✅ 成功 ──► 保存到 _otl_content/{drive_name}/{name}_{file_id[:8]}.md
    │ ❌ 失败 ──► 记录错误（.otl.link 快捷方式预期失败）
    │
    ▼
[缓存扫描] ──► 读取 WPS Office 本地 filecache/rectfile2.xml
    │
    ▼
[匹配算法] ──► 文件名 + 大小容差匹配
    │ 命中 ──► 复制到 _otl_files/
    │ 未命中 ──► 加入 EXPORT_GUIDE.md
    │
    ▼
[更新 OTL 状态] ──► _otl_state.json
```

### 4.3 失败处理与重试状态机

```
下载请求
    │
    ▼
HTTP 405 / chunk failed / expired
    │
    ▼
是否可重试? ──► 是 ──► 指数退避等待 ──► 重试同一 URL (最多 5 次)
    │ 否            │ 仍失败
    ▼               ▼
永久失败      刷新下载 URL ──► 重试一次
    │               │ 仍失败
    ▼               ▼
mark_failed   mark_failed
(error_msg)   (error_msg)
    │               │
    ▼               ▼
下次备份:     下次备份:
- 永久失败      - 405 不是永久失败
  (无下载地址)    继续尝试
  → needs_update
    返回 False
```

---

## 5. 关键技术决策

### 5.1 为什么纯标准库？

WPS_CLI 不使用任何第三方 Python 包（无 `requirements.txt` / `pyproject.toml`）。

**原因：**
- 部署极简：仅需 Python 3 和 `wps365-cli` / `kdocs-cli` 二进制。
- 跨平台兼容：标准库在 macOS/Linux/Windows 行为一致。
- 维护成本低：无依赖更新、无版本冲突。

**代价：** 缺少 `requests` 的自动重试、`pytest` 的测试框架、`rich` 的终端美化。通过 urllib 原生实现和手动脚本验证弥补。

### 5.2 为什么 JSON 而非 SQLite？

状态持久化使用 JSON 文件而非 SQLite。

**原因：**
- 零依赖：SQLite 虽是标准库，但 JSON 更透明，可直接 `cat` 查看。
- 调试友好：人工可编辑、可版本控制（小规模状态下）。
- 原子写入简单：`.tmp` + `replace()` 即可。

**代价：** 文件变大后读写性能下降。当前 906 条记录约 600KB，远未触及瓶颈。若未来超过 10K 条记录，建议迁移到 SQLite。

### 5.3 为什么 file_id 隔离而非内容哈希去重？

同名文件使用 `file_id[:8]` 后缀隔离，而非通过内容哈希合并。

**原因：**
- WPS 云盘中同名文件通常是**不同版本**（如 `报告_v1.pptx` 和 `报告_v2.pptx`），需要独立保留。
- 内容哈希需要下载完整文件后才能计算，无法在扫描阶段决定去重。
- `file_id` 是 WPS 分配的全局唯一标识，天然稳定。

### 5.4 为什么扫描阶段过滤而非下载阶段？

不可下载格式（`.otl`/`.spt`/`.form`）在 `scan_remote_files` 阶段过滤，而非在 `_download_worker` 中获取 URL 失败后再处理。

**原因：**
- 减少无效 API 调用：不必为已知不可下载的文件请求 `drive files download` URL。
- 减少日志噪音：跳过记录为 `DEBUG` 级别，而非 `ERROR`。
- 状态一致性：filter 逻辑集中在一处，避免 worker 中分散处理。

### 5.5 为什么 URL 串行化而非并发？

获取下载 URL 时使用线程锁串行化，间隔 200ms。

**原因：**
- WPS API 对并发获取下载 URL 有隐式限流，高并发下返回 405。
- 下载阶段本身已是多线程并发，URL 获取的串行化不会成为瓶颈（200ms × 文件数 vs 实际下载时间）。

### 5.6 为什么引入 kdocs-cli 混合架构？

**背景：** `wps365-cli` 无法读取文档内容（仅支持实体文件下载），而 `.otl` 等格式甚至无法通过 Drive API 下载。

**决策：** 引入 `kdocs-cli` 作为第二层备份工具，与 `wps365-cli` 形成互补：

| 能力 | wps365-cli | kdocs-cli | 分工 |
|------|-----------|-----------|------|
| 盘列表扫描 | ✅ | ❌ | wps365-cli |
| 实体文件下载 | ✅ | ✅ | wps365-cli |
| 文档内容读取 | ❌ | ✅ | kdocs-cli |
| 全文搜索 | 基础 | ✅ | kdocs-cli |
| OTL 操作 | ❌ | ✅ | kdocs-cli |
| 日程/会议/通讯录 | ✅ | ❌ | wps365-cli |

**关键原则：** 内容备份是"锦上添花"，主备份流程（实体文件下载）不依赖 kdocs-cli 可用。kdocs-cli 失败不影响主流程。

### 5.7 为什么内容备份使用 Markdown 格式？

**原因：**
- kdocs-cli `drive read-file` 原生输出 Markdown，无需额外转换。
- Markdown 是纯文本，便于版本控制、全文搜索、跨平台阅读。
- YAML frontmatter 可嵌入元数据（file_id, drive_id, source_format, backup_at），便于下游处理。

---

## 6. 接口定义

### 6.1 模块间接口

```python
# engine.py ──► state.py
state.get_snapshot(drive_id, file_id) → Optional[FileSnapshot]
state.needs_update(drive_id, file_id, remote_mtime) → bool
state.mark_backed_up(FileSnapshot) → None
state.mark_failed(drive_id, file_id, error, name, size, mtime, drive_name) → None
state.prune_stale(current_keys: set) → int

# engine.py ──► config.py
config.BACKUP_DIR: Path
config.STATE_FILE: Path
config.MAX_CONCURRENT: int
config.DOWNLOAD_TIMEOUT: int
config.CONTENT_BACKUP_ENABLED: bool
config.CONTENT_BACKUP_FORMATS: set

# engine.py ──► kdocs_engine.py
kdocs_engine.read_file_content(file_id, drive_id) → Optional[dict]
kdocs_engine.backup_file_content(file_id, drive_id, name, dest_dir) → ContentBackupResult
kdocs_engine.is_content_readable(ext) → bool

# wps_backup.py ──► engine.py
engine.run(max_files=None, dry_run=False) → BackupResult

# wps_backup.py ──► otl_engine.py
run_otl_backup(drive_id=None, dry_run=False) → OTLBackupResult
```

### 6.2 CLI 外部接口

```bash
# 主入口
python3 wps_backup.py run [--dry-run] [--no-otl] [--workers N] [--max N]
python3 wps_backup.py daemon
python3 wps_backup.py install
python3 wps_backup.py status
python3 wps_backup.py log [-n N]
python3 wps_backup.py backup-otl [--dry-run] [--no-content]

# 共享文件目录
python3 sync_shared_files.py
```

---

## 7. 安全与隐私设计

### 7.1 认证安全

- 不存储密码，完全依赖 `wps365-cli` 和 `kdocs-cli` 管理 OAuth token。
- `wps365-cli` 将凭证存储在 macOS Keychain 或加密文件中（AES-256-GCM）。
- `kdocs-cli` 将 token 存储在系统密钥链中。
- 运行时通过 `wps365-cli auth token` / `kdocs-cli auth status` 获取临时 access token，仅在内存中使用。
- **两个 CLI 的 Token 不互通**，需分别维护认证。

### 7.2 日志安全

- `backup.log` 仅包含文件元数据（名称、大小、下载速度、错误信息）。
- **不包含**文件内容、token、下载 URL（URL 仅在 DEBUG 级别可能输出）。
- 建议定期轮转日志或限制大小。

### 7.3 状态文件安全

- `backup_state.json` 包含文件名和 `link_url`（WPS 在线编辑链接）。
- 注意：link_url 可能包含文档的共享访问标识，应视为敏感数据。
- 状态文件是差量备份的核心，删除将导致下次全量重新下载。

### 7.4 凭证清理

推送代码到 GitHub 前已执行以下清理：
- 从 git tracking 中移除所有含硬编码凭证的测试脚本（`test_caldav*.py`, `debug_auth.py` 等）。
- 从 git tracking 中移除 IDE 配置（`.qwen/`）和 Agent 元数据（`.antigravitycli/`）。
- 脱敏编辑保留文档中的示例配置（替换为 `YOUR_*` 占位符）。
- `.gitignore` 已配置排除敏感路径。

---

## 8. 性能特征

| 指标 | 数值 | 备注 |
|------|------|------|
| 并发下载线程 | 4 | 通过 `WPS_BACKUP_WORKERS` 可调 |
| 断点续传分块 | 10 MB | 大文件分片下载 |
| 单文件最大重试 | 5 次 | 含 chunk 级 3 次重试 |
| URL 获取间隔 | 200 ms | 串行化限流 |
| 整体下载超时 | 600 秒 | 单文件 |
| 状态文件大小 | ~600 KB (906 条记录) | JSON 格式 |
| OTL 内容备份 | 169 文件 / 256 秒 | kdocs-cli read-file |
| 内容备份格式 | Markdown + YAML frontmatter | 纯文本，便于搜索 |

---

## 9. 扩展性考虑

### 9.1 未来可能的扩展

| 扩展方向 | 当前状态 | 建议实现路径 |
|---------|---------|-------------|
| **双向同步** | 不支持 | 需监听本地文件系统变更（`fsevents`/`inotify`），调用 WPS 上传 API |
| **增量备份到对象存储** | 不支持 | 在 `mark_backed_up` 后增加 S3/OSS 上传钩子 |
| **Web 管理界面** | 不支持 | 轻量级 Flask/FastAPI 服务，读取 `backup_state.json` 展示进度 |
| **邮件/飞书通知** | 不支持 | 在 `BackupResult` 返回后增加 webhook 调用 |
| **压缩/加密存储** | 不支持 | 在 `download_with_resume` 完成后增加压缩/加密步骤 |
| **状态迁移到 SQLite** | 不需要 | 当记录 >10K 时，替换 `state.py` 的 JSON 读写为 SQLite |
| **内容备份增量** | 不支持 | 在 `state.py` 中增加 `content_mtime` 字段，避免重复调用 read-file |
| **全文搜索索引** | 不支持 | 基于 `_content_backup/` 的 Markdown 文件构建 ripgrep 或 SQLite FTS |

---

## 10. 参考文档

- `README.md` — 项目概览与快速开始
- `AGENTS.md` — 项目总体说明与运行方式
- `HANDOFF.md` — 当前状态与交接事项
- `docs/kdocs-cli-setup.md` — wps365-cli 与 kdocs-cli 安装配置指南
- `calendar_Sync/AGENTS.md` — CalDAV 代理子项目说明
- `calendar_Sync/DESIGN.md` — CalDAV 代理设计文档
- `verify_fix.py` — 修复验证脚本
