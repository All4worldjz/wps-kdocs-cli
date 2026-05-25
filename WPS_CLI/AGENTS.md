# WPS CLI 工具集 — Agent 说明

**项目类型:** 运维自动化工具集 — WPS 365 云盘本地备份、共享文件目录生成、日历同步代理。  
**主要语言:** 中文（文档、注释），英文（代码标识符）。  
**运行平台:** macOS（主要），部分组件跨平台兼容。  
**状态:** 生产环境运行中，持续迭代维护。

---

## 项目概述

本项目是围绕 **WPS 365 开放平台**构建的本地 CLI 工具集合，核心解决三个问题：

1. **云盘差量备份** (`wps_backup.py` + `wps_backup/`)
   - 通过 `wps365-cli` 调用 WPS Drive API，将云端文件增量下载到本地。
   - 支持多线程并发、断点续传、指数退避重试。
   - 对 `.otl` 等不可直接下载的私有格式，通过 WPS Office 本地缓存进行中转备份。
   - 支持守护模式与 macOS `launchd` 定时任务。

2. **共享文件目录生成** (`sync_shared_files.py`)
   - 遍历所有云盘，列出共享文件元数据。
   - 按扩展名分类创建子目录索引，生成 `CATALOG.md`（不下载实体文件）。

3. **日历 CalDAV 代理** (`calendar_Sync/`)
   - 独立子项目，Go 编写的 CalDAV 代理网关，解决 WPS 日历与 iOS/macOS/Android 系统日历的兼容性问题。
   - 该子项目有独立的 `AGENTS.md`，见 `calendar_Sync/AGENTS.md`。

---

## 目录结构

```
WPS_CLI/
├── wps_backup.py              # 主入口：备份 CLI（run / daemon / install / status / log / backup-otl）
├── sync_shared_files.py       # 共享文件分类目录生成器
├── verify_fix.py              # 修复验证脚本（状态逻辑、路径隔离、dry-run 检查）
├── com.wps.backup.plist       # macOS launchd 定时任务配置（由 scheduler.py 生成）
│
├── wps_backup/                # 备份核心 Python 包
│   ├── __init__.py            # （空）
│   ├── config.py              # 路径、调度、并发、CLI 配置 + 环境变量覆盖
│   ├── engine.py              # 备份引擎 v3.0（多线程、断点续传、重试、差量对比）
│   ├── state.py               # 线程安全的增量状态管理器（JSON 持久化）
│   ├── scheduler.py           # 守护模式 & launchd plist 生成
│   ├── otl_engine.py          # OTL 专项备份（缓存扫描、文件名匹配、导出指南生成）
│   └── logger.py              # 统一日志（文件 + 控制台）
│
├── wps_backup_data/           # 备份存储目录
│   ├── 自动备份/               # 各盘文件按盘名子目录存放
│   ├── 我的企业文档/
│   ├── _otl_files/            # OTL 缓存中转备份
│   └── _otl_converted_docx/   # 手动导出的 OTL→docx 存放区
│
├── wps_backup_state/          # 状态与日志
│   ├── backup_state.json      # 差量备份状态（FileSnapshot 集合）
│   ├── _otl_state.json        # OTL 备份状态
│   └── backup.log             # 运行日志
│
├── wps_shared_files/          # 共享文件分类索引输出
│   ├── CATALOG.md             # 总索引
│   ├── .filelist              # 各扩展名子目录下的文件清单
│   └── docx/、pptx/、pdf/ ...  # 按扩展名分类的占位目录
│
├── calendar_Sync/             # CalDAV 代理子项目（Go + Python 测试脚本）
│   ├── AGENTS.md              # 子项目独立说明
│   ├── proxy_code/            # Go 源码
│   └── *.py                   # Python 调试/测试脚本
│
├── src/cli-0.1.0/             # wps365-cli 官方安装脚本与 README 副本
│   ├── install.sh
│   └── README.md
│
└── wps-mcp/
    └── docs/                  # MCP 相关文档（当前仅文档）
```

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 主语言 | Python 3（无版本锁定，开发环境使用 3.13–3.14） |
| 外部依赖 | `wps365-cli`（Go 二进制，必须预先安装并配置 OAuth 认证） |
| 标准库 | `urllib.request`, `subprocess`, `threading`, `json`, `pathlib`, `xml.etree`, `signal`, `logging` |
| 无第三方 Python 包 | 项目不依赖 `requirements.txt` / `pyproject.toml`，纯标准库实现 |
| 调度 | macOS `launchd`（`com.wps.backup.plist`）或 Python 守护模式 |
| 数据持久化 | JSON 文件（原子写入：先写 `.tmp` 再 `replace`） |

---

## 运行方式

### 1. 前置条件

必须已安装并认证 `wps365-cli`：

```bash
# 检查工具是否存在
wps365-cli --version

# 检查认证状态
wps365-cli auth status
wps365-cli auth token        # 应输出有效 token
```

若 token 过期：
```bash
wps365-cli auth refresh --delegated
```

### 2. 备份命令

```bash
# 立即执行一次完整备份（含 OTL）
python3 wps_backup.py run

# Dry-run：仅对比差异，不下载
python3 wps_backup.py run --dry-run

# 跳过 OTL 专项备份
python3 wps_backup.py run --no-otl

# 限制并发线程数（默认 4）
python3 wps_backup.py run --workers 8

# 限制下载文件数（测试用）
python3 wps_backup.py run --max 10

# OTL 专项备份（单独执行）
python3 wps_backup.py backup-otl

# 守护模式（后台轮询，到设定时间自动执行）
python3 wps_backup.py daemon

# 查看备份状态
python3 wps_backup.py status

# 查看最近 30 行日志
python3 wps_backup.py log -n 30

# 生成 launchd 配置（输出到当前目录的 com.wps.backup.plist）
python3 wps_backup.py install
```

### 3. 共享文件目录生成

```bash
python3 sync_shared_files.py
# 输出到 wps_shared_files/CATALOG.md
```

### 4. 验证修复

```bash
python3 verify_fix.py
# 验证项：
# 1) 不可下载格式（.spt / .form）是否已被过滤
# 2) 状态管理逻辑（无下载地址的文件是否跳过）
# 3) 同名文件路径隔离（file_id 前 8 位区分）
```

---

## 核心模块说明

### `wps_backup/config.py`

所有可调整参数的集中地，支持环境变量覆盖：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `WPS_BACKUP_DIR` | `./wps_backup_data` | 备份存储根目录 |
| `WPS_BACKUP_STATE_DIR` | `./wps_backup_state` | 状态/日志目录 |
| `WPS_BACKUP_HOUR` | `20` | 每日备份触发小时 |
| `WPS_BACKUP_WORKERS` | `4` | 并发下载线程数 |

代码中硬编码的其他关键常量：
- `SCHEDULE_MINUTE = 0` — 每日触发分钟
- `MAX_RETRIES = 5` — 单文件最大重试次数
- `CHUNK_SIZE = 10MB` — 断点续传分块大小
- `DOWNLOAD_TIMEOUT = 600s` — 整体下载超时
- `SKIP_EXTS = {".otl", ".spt", ".form"}` — 不可通过 Drive API 直接下载的格式

### `wps_backup/engine.py` — 备份引擎

- **多线程下载**：`ThreadPoolExecutor(max_workers=...)`
- **差量逻辑**：基于 `file_id + mtime` 对比，远程文件修改时间更新则重新下载
- **断点续传**：对 >10MB 文件使用 HTTP `Range` 请求分段下载，临时文件 `.tmp`
- **URL 串行化**：获取下载地址时加锁，避免并发轰炸 WPS API（间隔 200ms）
- **失败分类**：永久失败（无下载地址）记录到状态，后续跳过；临时失败（405/429/网络错误）重试
- **路径隔离**：本地文件名格式为 `{stem}_{file_id[:8]}{suffix}`，避免同名文件冲突
- **旧版迁移**：检测到旧版命名（无 file_id 后缀）的已存在文件，自动重命名为新格式

### `wps_backup/state.py` — 状态管理器

- 线程安全（`threading.Lock`）
- 以 `drive_id/file_id` 为 key 存储 `FileSnapshot`
- `needs_update()` 判断依据：
  - 新文件 → 需要下载
  - 已知永久不可下载（error_msg 含"无下载地址" / "不可下载"）→ 跳过
  - 远程 `mtime >` 本地记录 `mtime` → 需要更新
- `prune_stale()` 清理远程已不存在的本地记录
- 原子写入：`.tmp` → 重命名覆盖原文件

### `wps_backup/otl_engine.py` — OTL 专项备份

`.otl`（WPS 在线文档私有格式）无法通过 Drive API 直接下载，策略如下：

1. 通过 API 扫描所有 `.otl` 文件元数据
2. 扫描 WPS Office macOS 本地云同步缓存：`~/Library/Containers/com.kingsoft.wpsoffice.mac/.../filecache`
3. 解析 `rectfile2.xml` 获取缓存条目（文件名、fileId、accessTime）
4. **匹配策略**：
   - 精确文件名匹配（不区分大小写）+ 大小容差 0.5x–2.0x
   - 模糊大小匹配（容差 ±15%）
5. 将缓存中的 `content.otl` 复制到 `_otl_files/`，保留时间戳
6. 未缓存的文件生成 `EXPORT_GUIDE.md`，列出 kdocs.cn 在线编辑链接，提示手动导出为 `.docx`

### `wps_backup/scheduler.py`

- **守护模式**：`daemon_mode()` 轮询当前时间，到达 `SCHEDULE_HOUR:SCHEDULE_MINUTE` 自动触发备份
- **launchd 配置生成**：根据当前 Python 解释器路径和脚本路径，生成 `com.wps.backup.plist`
- 安装命令示例（脚本会打印）：
  ```bash
  cp com.wps.backup.plist ~/Library/LaunchAgents/
  launchctl load ~/Library/LaunchAgents/com.wps.backup.plist
  ```

---

## 代码风格与约定

- **注释与文档字符串**：全部使用中文，面向中文开发者。
- **代码标识符**：英文，遵循 PEP 8。
- **私有函数**：下划线前缀（`_cli`, `_download_chunk`, `_get_dest_path`）。
- **模块日志**：每个模块通过 `setup_logger()` 获取同名 logger，统一输出到 `backup.log` + stderr。
- **数据结构**：优先使用 `@dataclass`（`RemoteFile`, `FileSnapshot`, `BackupResult` 等）。
- **线程安全**：状态修改和结果计数均使用 `threading.Lock`。
- **路径处理**：统一使用 `pathlib.Path`，避免字符串拼接。
- **临时文件**：所有文件写入均先写 `.tmp`，完成后再 `Path.replace()` 原子覆盖。

---

## 测试策略

本项目**没有使用 pytest/unittest 等测试框架**，测试以脚本化和手动验证为主：

| 测试手段 | 文件 | 说明 |
|----------|------|------|
| 修复验证脚本 | `verify_fix.py` | 离线验证状态逻辑与路径隔离；在线验证 dry-run 时不可下载格式是否被过滤 |
| 手动 Dry-run | `python3 wps_backup.py run --dry-run` | 预览差异，确认待下载列表 |
| 限制规模测试 | `python3 wps_backup.py run --max 3` | 小批量端到端测试 |
| 日志检查 | `python3 wps_backup.py log -n 50` | 查看下载、失败、跳过的具体记录 |
| OTL 专项测试 | `python3 wps_backup.py backup-otl --dry-run` | 预览 OTL 缓存匹配结果 |

**建议新增功能时的测试步骤：**
1. 先 `--dry-run` 确认逻辑正确；
2. 用 `--max N` 做小批量真实下载验证；
3. 检查 `backup.log` 和 `backup_state.json` 是否符合预期；
4. 运行 `verify_fix.py` 确保没有破坏现有验证项。

---

## 安全注意事项

1. **认证 Token**
   - 项目本身不存储密码，依赖 `wps365-cli` 管理 OAuth token。
   - `wps365-cli` 将凭证存储在系统 Keychain（macOS）或加密文件中。
   - `_get_auth_token()` 从 `wps365-cli auth token` 获取临时 access token，仅在内存中使用。

2. **日志安全**
   - `backup.log` 中可能包含文件名称、大小、下载 URL 等元数据，**不包含文件内容**。
   - 日志文件位于本地 `wps_backup_state/backup.log`，注意定期清理或限制大小。

3. **状态文件**
   - `backup_state.json` 和 `_otl_state.json` 包含文件元数据（文件名、link_url、hash）。
   - 这些文件是差量备份的核心，删除将导致下次全量重新下载。

4. **本地缓存路径**
   - `otl_engine.py` 读取 `~/Library/Containers/com.kingsoft.wpsoffice.mac/...`，这是 WPS Office 的私有沙盒数据，**只读不修改**。

5. **launchd 配置**
   - `com.wps.backup.plist` 中包含本地文件系统绝对路径，若迁移项目目录需重新生成（`python3 wps_backup.py install`）。

---

## 故障排查速查表

| 症状 | 可能原因 | 排查方法 |
|------|---------|---------|
| 认证失败 / 无法获取盘列表 | `wps365-cli` token 过期 | `wps365-cli auth status` → `wps365-cli auth refresh --delegated` |
| 大量文件失败 | 下载 URL 过期或网络抖动 | 查看 `backup.log` 中的错误码；引擎会自动重试，通常下次运行可恢复 |
| .otl 文件无法备份 | WPS Office 未打开过该文件，缓存中不存在 | 在 WPS Office 中打开一次，或按 `EXPORT_GUIDE.md` 手动导出 |
| 同名文件被覆盖 | 旧版本引擎未使用 file_id 隔离 | 检查本地路径是否包含 `_fileid[:8]` 后缀；引擎会自动迁移旧格式 |
| launchd 未按时执行 | plist 路径未加载或时间未到 | `launchctl list com.wps.backup` / `launchctl start com.wps.backup` |
| 状态文件损坏 | JSON 被意外截断 | 删除 `backup_state.json` 重新全量备份（或从备份恢复） |

---

## 子项目索引

| 目录 | 内容 | 独立文档 |
|------|------|----------|
| `calendar_Sync/` | WPS 日历 CalDAV 代理（Go） | `calendar_Sync/AGENTS.md` |
| `wps-mcp/` | MCP 协议相关文档 | — |
| `src/cli-0.1.0/` | `wps365-cli` 官方安装脚本副本 | `src/cli-0.1.0/README.md` |

---

*最后更新: 2026-05-25*
