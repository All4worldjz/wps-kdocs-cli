# WPS CLI 工具集 — 架构决策文档 (ADP)

**版本:** 1.0  
**日期:** 2026-05-25  
**作者:** Kimi Code CLI  
**状态:** 生产运行中，持续迭代  

---

## 1. 项目定位与范围

### 1.1 目标

构建围绕 **WPS 365 开放平台**的本地 CLI 工具集，解决三个核心运维问题：

1. **云盘差量备份** — 自动化将 WPS 云盘文件增量同步到本地存储。
2. **共享文件目录生成** — 按扩展名分类索引云盘共享文件，生成可读的 `CATALOG.md`。
3. **日历 CalDAV 代理** — 桥接 WPS 日历与标准 CalDAV 客户端（iOS/macOS/Android）。

### 1.2 非目标

- 不替代 WPS 官方客户端的在线编辑功能。
- 不提供双向同步（本地修改不回写云端）。
- 不处理 WPS 协作权限、评论、版本历史等元数据。

---

## 2. 高层架构

```
┌─────────────────────────────────────────────────────────────┐
│                        WPS 365 云端                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  WPS Drive   │  │ WPS Calendar │  │ WPS Office   │      │
│  │   (API)      │  │   (API)      │  │ (本地缓存)   │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
└─────────┼─────────────────┼─────────────────┼──────────────┘
          │                 │                 │
          ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────┐
│                    wps365-cli (Go 二进制)                    │
│         OAuth 认证 · Drive API · Calendar API                │
└─────────────────────────────────────────────────────────────┘
          │                 │                 │
          ▼                 ▼                 ▼
┌─────────────────┐ ┌───────────────┐ ┌───────────────────────┐
│ wps_backup.py   │ │ sync_shared_  │ │ calendar_Sync/        │
│ + wps_backup/   │ │   files.py    │ │ (Go CalDAV Proxy)     │
│ (Python 3)      │ │ (Python 3)    │ │                       │
└────────┬────────┘ └───────┬───────┘ └───────────┬───────────┘
         │                  │                     │
         ▼                  ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│                         本地输出                             │
│  wps_backup_data/      wps_shared_files/    CalDAV 客户端    │
│  ├── 自动备份/          ├── CATALOG.md      (iOS/macOS/      │
│  ├── 我的企业文档/      ├── docx/           Android)         │
│  ├── _otl_files/        ├── pptx/                          │
│  └── _otl_converted_    └── pdf/                           │
│      docx/                                                 │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 核心模块架构

### 3.1 备份引擎 (`wps_backup/`)

```
wps_backup/
├── config.py          # 单一可信源配置（路径、并发、超时、黑名单）
├── engine.py          # 主备份引擎：扫描 → 差量对比 → 多线程下载
├── state.py           # 线程安全状态管理器（JSON 原子写入）
├── otl_engine.py      # OTL 专项：API 扫描 → 缓存匹配 → 导出指南
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

#### 3.1.4 OTL 专项 (`otl_engine.py`)

WPS Drive API 无法直接下载 `.otl`（在线文档私有格式）。策略：

1. **API 扫描** — 获取所有 `.otl` 的元数据（file_id, name, size, mtime, link_url）。
2. **缓存扫描** — 读取 macOS WPS Office 沙盒：`~/Library/Containers/com.kingsoft.wpsoffice.mac/.../filecache/rectfile2.xml`。
3. **匹配算法** —
   - 精确文件名匹配（不区分大小写）+ 大小容差 0.5x–2.0x。
   - 模糊大小匹配（容差 ±15%）作为 fallback。
4. **增量复制** — 命中缓存的 `.otl` 复制到 `_otl_files/`，未命中的生成 `EXPORT_GUIDE.md`。

### 3.2 状态持久化 (`state.py`)

```
backup_state.json
├── meta
│   ├── version: 1
│   ├── last_backup_at: "2026-05-25 09:20:15"
│   ├── total_files: 894
│   └── total_size: 20862436920
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
    │   7. 失败: mark_failed
    │
    ▼
[清理过期记录] ──► prune_stale (删除远程已不存在的本地记录)
    │
    ▼
[输出汇总] ──► 日志 + 返回 BackupResult
```

### 4.2 失败处理与重试状态机

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
- 部署极简：仅需 Python 3 和 `wps365-cli` 二进制。
- 跨平台兼容：标准库在 macOS/Linux/Windows 行为一致。
- 维护成本低：无依赖更新、无版本冲突。

**代价：** 缺少 `requests` 的自动重试、`pytest` 的测试框架、`rich` 的终端美化。通过 urllib 原生实现和手动脚本验证弥补。

### 5.2 为什么 JSON 而非 SQLite？

状态持久化使用 JSON 文件而非 SQLite。

**原因：**
- 零依赖：SQLite 虽是标准库，但 JSON 更透明，可直接 `cat` 查看。
- 调试友好：人工可编辑、可版本控制（小规模状态下）。
- 原子写入简单：`.tmp` + `replace()` 即可。

**代价：** 文件变大后读写性能下降。当前 894 条记录约 12KB，远未触及瓶颈。若未来超过 10K 条记录，建议迁移到 SQLite。

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
python3 wps_backup.py backup-otl [--dry-run]

# 共享文件目录
python3 sync_shared_files.py
```

---

## 7. 安全与隐私设计

### 7.1 认证安全

- 不存储密码，完全依赖 `wps365-cli` 管理 OAuth token。
- `wps365-cli` 将凭证存储在 macOS Keychain 或加密文件中。
- 运行时通过 `wps365-cli auth token` 获取临时 access token，仅在内存中使用。

### 7.2 日志安全

- `backup.log` 仅包含文件元数据（名称、大小、下载速度、错误信息）。
- **不包含**文件内容、token、下载 URL（URL 仅在 DEBUG 级别可能输出）。
- 建议定期轮转日志或限制大小。

### 7.3 状态文件安全

- `backup_state.json` 包含文件名和 `link_url`（WPS 在线编辑链接）。
- 注意：link_url 可能包含文档的共享访问标识，应视为敏感数据。
- 状态文件是差量备份的核心，删除将导致下次全量重新下载。

---

## 8. 性能特征

| 指标 | 数值 | 备注 |
|------|------|------|
| 并发下载线程 | 4 | 通过 `WPS_BACKUP_WORKERS` 可调 |
| 断点续传分块 | 10 MB | 大文件分片下载 |
| 单文件最大重试 | 5 次 | 含 chunk 级 3 次重试 |
| URL 获取间隔 | 200 ms | 串行化限流 |
| 整体下载超时 | 600 秒 | 单文件 |
| 状态文件大小 | ~12 KB (894 条记录) | JSON 格式 |

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

---

## 10. 参考文档

- `AGENTS.md` — 项目总体说明与运行方式
- `HANDOFF.md` — 当前状态与交接事项（本文档同级）
- `calendar_Sync/AGENTS.md` — CalDAV 代理子项目说明
- `calendar_Sync/DESIGN.md` — CalDAV 代理设计文档
- `verify_fix.py` — 修复验证脚本
