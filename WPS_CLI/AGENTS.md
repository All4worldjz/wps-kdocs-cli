# WPS CLI 工具集 — Agent 说明

**项目类型:** 运维自动化工具集 — WPS 365 云盘本地备份、共享文件目录生成、日历同步代理。  
**主要语言:** 中文（文档、注释），英文（代码标识符）。  
**运行平台:** macOS（主要，Apple Silicon arm64），部分组件跨平台兼容。  
**状态:** 生产环境运行中，持续迭代维护。  
**GitHub:** https://github.com/All4worldjz/wps-kdocs-cli

---

## 项目概述

本项目是围绕 **WPS 365 开放平台**构建的本地 CLI 工具集合，核心解决三个问题：

1. **云盘差量备份** (`wps_backup.py` + `wps_backup/`)
   - 通过 `wps365-cli` 调用 WPS Drive API，将云端文件增量下载到本地。
   - 支持多线程并发、断点续传、指数退避重试。
   - 对 `.otl` 等不可直接下载的私有格式，通过 `kdocs-cli` 内容备份 + WPS Office 本地缓存中转实现混合备份。
   - 定时运行由 **WPS Backup.app**（`macos/`，菜单栏 App）管理：每小时检查、到点运行、失败重试、异常通知。

2. **共享文件目录生成** (`sync_shared_files.py`)
   - 遍历所有云盘，列出共享文件元数据。
   - 按扩展名分类创建子目录索引，生成 `CATALOG.md`（不下载实体文件）。

3. **日历 CalDAV 代理** (`calendar_Sync/`)
   - 独立子项目，Go 编写的 CalDAV 代理网关，解决 WPS 日历与 iOS/macOS/Android 系统日历的兼容性问题。
   - 该子项目有独立的 `AGENTS.md`，见 `calendar_Sync/AGENTS.md`。

**v4.0 混合架构（2026-06 升级）：** 引入 `kdocs-cli` 作为 `wps365-cli` 的补充。新增"文档内容备份层"——下载实体文件后，自动调用 `kdocs-cli drive read-file` 将 docx/pdf/xlsx/ksheet/dbt/otl 转为 Markdown 备份，实现"实体文件 + 内容文本"双保险。`.otl` 内容备份覆盖率从 11%（仅缓存）提升到约 84%（172/205）。

**v4.0.1 修复（2026-07）：** `read-file` 对 xlsx/ksheet 返回结构化 dict 而非 Markdown 字符串，导致内容备份报 `can only concatenate str (not "dict") to str`。修复方式：新增 `_content_to_text()` 类型归一化，dict/list 序列化为格式化 JSON 存入 `.md`。

**v4.1 airpage 迁移（2026-09）：** kdocs API 开始拒绝企业账号（错误码 403001，"暂仅支持个人账号"），kdocs-cli 内容备份路径整体失效。OTL 内容备份改用 `wps365-cli v0.3.3+` 的 `airpage` 命令（需 `kso.airpage.readwrite` scope）：`block get` 读取 v2 块树 → 扁平化为 Markdown；`export` 异步导出 **docx 实体**到 `_otl_converted_docx/`（自动化了原手动导出步骤）。kdocs-cli 保留为回退后端（个人账号仍可用）。新增 `tests/` unittest 测试套件（含线上契约测试，防止 CLI 接口漂移）。

**v4.2 定时任务修复 + macOS App（2026-09-26）：** 巡检发现 launchd 定时任务自 07-29 起静默失效两个月（launchd PATH 缺 `~/.local/bin`、失败仍返回 0、OTL 缓存扫描被 macOS TCC 权限弹窗永久阻塞、任务未加载）。修复：CLI 绝对路径解析、非零退出码、TCC 超时探测、扫描完整性防护、单实例锁、kdocs 企业账号探测、OTL 永久失败记忆。新增引擎↔App 契约（`app_contract.py`：`last_run.json`/`progress.json`/心跳/`scheduled` 命令/`status --json`）和 **WPS Backup.app**（`macos/`，SwiftUI 菜单栏 + 经典 LaunchAgent 调度）。详见 `docs/OPTIMIZATION_PLAN.md`、`docs/MACOS_APP_PLAN.md` §9、`macos/README.md`。

**v5 OTL 高效备份（2026-09-26）：** 改用 WPS 开放平台官方 `export_to_markdown_zip`（高保真 markdown + 图片，CLI spec 未收录，经 `wps_http` 直连调用）与 docx 并行导出；主引擎扫描时一次性收集 `.otl`，OTL 引擎不再二次扫描；产物级增量 + 4 路并发；WPS/金山云下载直连优先（本机代理对 ks3 握手超时）。日常运行 118 s → 43–58 s；永久失败只认响应码 403000001，任何临时失败令 run 退出码 1。详见 `docs/OTL_BACKUP_DESIGN_V5.md`。

---

## 目录结构

```
WPS_CLI/
├── wps_backup.py              # 主入口：备份 CLI（run / scheduled / status [--json] / log / backup-otl / daemon / install）
├── sync_shared_files.py       # 共享文件分类目录生成器
├── verify_fix.py              # 修复验证脚本（状态逻辑、路径隔离、dry-run 检查）
├── com.wps.backup.plist       # ⚠️ 旧版 launchd 配置（已由 WPS Backup.app 取代，勿再安装）
│
├── wps_backup/                # 备份核心 Python 包
│   ├── __init__.py            # （空）
│   ├── config.py              # 路径、调度、并发、双 CLI、内容备份配置 + 环境变量覆盖
│   ├── engine.py              # 备份引擎 v3.0（多线程、断点续传、重试、差量对比、内容备份触发）
│   ├── state.py               # 线程安全的增量状态管理器（JSON 持久化，含空扫描防误清保护）
│   ├── scheduler.py           # 守护模式 & launchd plist 生成
│   ├── otl_engine.py          # OTL 专项备份 v4.1（airpage 内容 + docx 导出 + 缓存实体 + 导出指南）
│   ├── airpage_engine.py      # airpage 封装引擎 v4.1（块树读取 → Markdown、docx 导出、scope 检查）
│   ├── kdocs_engine.py        # kdocs-cli 封装引擎（回退后端；企业账号 403001 时自动判为不可用）
│   ├── app_contract.py        # v4.2 引擎↔App 契约：运行记录、进度、取消、看门狗、调度判定、健康度
│   ├── lock.py                # v4.2 单实例运行锁（flock，被锁退出码 75）
│   ├── wps_http.py            # v5 直连 openapi.wps.cn（Bearer，401 刷新）+ WPS 域名直连优先/代理回退下载
│   └── logger.py              # 统一日志（RotatingFileHandler 10MB×5 + 控制台；WPS_BACKUP_NO_CONSOLE=1 关闭控制台）
│
├── macos/                     # v4.2 WPS Backup.app（SwiftUI 菜单栏 App + runner），见 macos/README.md
│   ├── build.sh               # 测试 → swiftc 编译 → 组装 → 签名 →（--install）安装到 ~/Applications
│   ├── Sources/WPSBackupCore/ # 设置、引擎环境、状态模型、健康度合并、LaunchAgent plist/launchctl 解析
│   ├── Sources/WPSBackup/     # 菜单栏 UI、AgentManager、通知、--diagnose / --test-notify
│   ├── Sources/wps-backup-runner/  # 定时任务执行体：设置环境 → exec python3 wps_backup.py scheduled
│   └── Tests/                 # Core 单元测试（XCTest；无 XCTest 时用 Tests/Shim 兼容层）
│
├── tests/                     # unittest 测试套件（v4.1 新增，纯标准库）
│   ├── fixtures/              # 真实 airpage 块树样本
│   ├── test_airpage_engine.py # 块树→Markdown、CLI 封装、导出轮询、OTL 备份（注入 runner，离线）
│   ├── test_otl_airpage_integration.py  # 后端选择、状态 docx_path、Phase 2 分发
│   ├── test_state_guards.py   # prune_stale 空扫描防误清保护
│   ├── test_scan_completeness.py  # v4.2 扫描失败显式抛错、不完整扫描跳过 prune、OTL 子目录分页
│   ├── test_launchd_env.py    # v4.2 CLI 绝对路径解析、plist PATH、二进制缺失
│   ├── test_run_hygiene.py    # v4.2 kdocs 403001 探测、OTL 永久失败、TCC 探测、运行锁
│   ├── test_app_contract.py   # v4.2 last_run/progress/调度判定/健康度/看门狗/取消/测试隔离
│   ├── test_logger_console.py # v4.2 控制台 handler 开关
│   ├── test_wps_http.py       # v5 直连路由、代理回退、token 刷新、原子下载
│   ├── test_airpage_v5.py     # v5 markdown_zip/docx 并行导出、图片改写、永久/临时失败
│   ├── test_otl_v5_integration.py  # v5 产物级增量、一次遍历（含 shortcut）、并发与取消
│   └── test_cli_contract.py   # 线上契约测试：CLI 接口漂移检测（token 不可用时自动跳过）
│
├── wps_backup_data/           # 备份存储目录（.gitignore 排除）
│   ├── 自动备份/               # 各盘文件按盘名子目录存放
│   ├── 我的企业文档/
│   ├── _otl_files/            # OTL 缓存实体备份
│   ├── _otl_content/          # OTL Markdown（v5：官方 markdown_zip，含 frontmatter）+ {stem}_{id8}.assets/ 图片
│   ├── _content_backup/       # 其他文档 Markdown 内容备份（kdocs-cli，企业账号已失效）
│   └── _otl_converted_docx/   # OTL→docx 存放区（v4.1 起由 airpage 自动导出）
│
├── wps_backup_state/          # 状态与日志（.gitignore 排除）
│   ├── backup_state.json      # 差量备份状态（FileSnapshot 集合）
│   ├── _otl_state.json        # OTL 备份状态（含永久失败记录 error_msg/permanent）
│   ├── backup.log             # 运行日志（10MB×5 轮转）
│   ├── last_run.json          # v4.2 上次运行结果（App 读取）
│   ├── runs.jsonl             # v4.2 最近 50 次运行（调度判定）
│   ├── progress.json          # v4.2 运行中进度（结束即删除）
│   ├── scheduler_heartbeat.json  # v4.2 定时任务每小时心跳
│   ├── force_run              # v4.2 App“立即备份”标记（被 scheduled 消费）
│   ├── .run.lock              # v4.2 单实例锁
│   ├── agent_runner.log       # v4.2 runner 自身错误
│   └── legacy_com.wps.backup.plist  # 已迁移停用的旧 launchd 配置
│
├── wps_shared_files/          # 共享文件分类索引输出
│   ├── CATALOG.md             # 总索引
│   ├── .filelist              # 各扩展名子目录下的文件清单
│   └── docx/、pptx/、pdf/ ...  # 按扩展名分类的占位目录
│
├── calendar_Sync/             # CalDAV 代理子项目（Go）
│   ├── AGENTS.md              # 子项目独立说明
│   ├── DESIGN.md              # 设计文档
│   ├── cmd/、internal/        # Go 源码
│   └── proxy_code/            # 部署脚本
│
├── docs/
│   ├── kdocs-cli-setup.md     # wps365-cli + kdocs-cli 完整安装配置指南
│   ├── OPTIMIZATION_PLAN.md   # 2026-09-26 巡检结论、修复清单、后续优化优先级
│   └── MACOS_APP_PLAN.md      # macOS App 计划 + §9 实施记录
│
├── src/cli-0.1.0/             # wps365-cli 官方安装脚本与 README 副本
├── wps-mcp/docs/              # MCP 相关文档（当前仅文档）
│
├── README.md                  # 项目概览与快速开始
├── ADP.md                     # 架构决策记录
├── HANDOFF.md                 # 交接文档（当前状态、技术债务、调试技巧）
└── AGENTS.md                  # 本文件
```

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 主语言 | Python 3.13+（无版本锁定文件，纯标准库实现） |
| 外部依赖 | `wps365-cli`（Go 二进制，盘扫描 + 实体下载 + airpage 智能文档读取/导出）、`kdocs-cli`（Go 二进制，回退内容后端，企业账号已被拒） |
| 标准库 | `urllib.request`, `subprocess`, `threading`, `json`, `pathlib`, `xml.etree`, `signal`, `logging`, `concurrent.futures` |
| 无第三方 Python 包 | 项目不依赖 `requirements.txt` / `pyproject.toml`，无构建流程，直接 `python3` 运行 |
| 调度 | WPS Backup.app 安装的经典 LaunchAgent `cc.all4world.wpsbackup.scheduler`（每小时触发 `wps_backup.py scheduled`） |
| macOS App | Swift 6 / SwiftUI（MenuBarExtra），`swiftc` 直编，无 Xcode 工程 |
| 数据持久化 | JSON 文件（原子写入：先写 `.tmp` 再 `replace`） |
| 子项目 | Go（calendar_Sync，纯 Go CGO-Free SQLite，见子项目 AGENTS.md） |

**双 CLI 架构说明（v4.1）：**

```
wps365-cli → WPS Drive API → 盘扫描 + 实体文件下载
     └─→ airpage API → block get（OTL 块树 → Markdown）+ export（OTL → docx）
kdocs-cli → kdocs API → read-file（回退；企业账号已被 403001 拒绝，仅个人账号可用）
```

两个 CLI 的认证 Token **不互通**，需分别维护：

| 项 | 值 |
|---|---|
| wps365-cli 路径 | `~/.local/bin/wps365-cli`（v0.3.6；v0.3.1 备份在 `~/.local/bin/wps365-cli.v0.3.1.bak`，v0.1.0 在 `/usr/local/bin/`） |
| kdocs-cli 路径 | `~/.local/bin/kdocs-cli`（v2.5.22；旧版备份在 `~/.kdocs-cli/backup/`） |

⚠️ **wps365-cli v0.3.3+ 注意事项：**
- 升级后必须执行 `wps365-cli spec update`，否则无 `airpage`/`airsheet` 命令
- curated 命令重命名：`drive files list/download` → `drive file list/download`（代码已适配；`tests/test_cli_contract.py` 用于检测此类漂移）
- airpage 需要 scope `kso.airpage.readwrite`：`wps365-cli auth login --device --scopes "kso.calendar.read kso.drive.readwrite kso.file.readwrite kso.user_base.read kso.airpage.readwrite"`

---

## 运行方式

### 1. 前置条件

必须已安装并认证 `wps365-cli`（v0.3.3+，含 airpage scope）；`kdocs-cli` 为可选回退（个人账号）：

```bash
# 检查工具与认证状态
wps365-cli auth status       # delegated.granted_scopes 应含 kso.airpage.readwrite
wps365-cli auth token        # 应输出有效 token
kdocs-cli auth status        # 可选

# token 过期时刷新
wps365-cli auth refresh --delegated
kdocs-cli auth login

# 首次启用 airpage（授权智能文档 scope）
wps365-cli auth login --device --scopes "kso.calendar.read kso.drive.readwrite kso.file.readwrite kso.user_base.read kso.airpage.readwrite"
```

### 2. 备份命令

```bash
# 立即执行一次完整备份（含 OTL 专项）
python3 wps_backup.py run

# Dry-run：仅对比差异，不下载
python3 wps_backup.py run --dry-run

# 跳过 OTL 专项备份
python3 wps_backup.py run --no-otl

# 限制并发线程数（默认 4）
python3 wps_backup.py run --workers 8

# 限制下载文件数（测试用）
python3 wps_backup.py run --max 10

# OTL 专项备份（airpage 内容 + docx 导出 + 缓存实体）
python3 wps_backup.py backup-otl
python3 wps_backup.py backup-otl --dry-run      # 仅预览匹配结果
python3 wps_backup.py backup-otl --no-content   # 跳过内容备份

# 守护模式（后台轮询，到设定时间自动执行）
python3 wps_backup.py daemon

# 查看备份状态（含 kdocs-cli 版本/认证、内容备份统计）
python3 wps_backup.py status
python3 wps_backup.py status --json   # 机器可读（App 使用）：last_run、auth、cli、health 等

# 定时任务入口（由 App 的 runner 每小时调用）：到点/有 force_run 标记才运行
python3 wps_backup.py scheduled

# 查看最近 30 行日志
python3 wps_backup.py log -n 30

# ⚠️ 旧版 launchd 安装：App 已接管调度时会拒绝执行（避免两个计划）
python3 wps_backup.py install
```

退出码约定：`0` 成功 · `1` 有失败 · `75` 另一进程在运行（被锁跳过）· `124` 超时 · `130` 被取消（SIGTERM）。

### 2.1 定时任务 / macOS App

```bash
cd macos && ./build.sh --install          # 构建、测试、安装并启动 WPS Backup.app
"$HOME/Applications/WPS Backup.app/Contents/MacOS/WPSBackup" --diagnose   # App 所见全部状态
launchctl print gui/$(id -u)/cc.all4world.wpsbackup.scheduler | grep -E "state|last exit"
touch wps_backup_state/force_run && launchctl kickstart gui/$(id -u)/cc.all4world.wpsbackup.scheduler  # 等同“立即备份”
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
# 1) 不可下载格式（.spt / .form）是否已被过滤（在线，需 token 有效）
# 2) 状态管理逻辑（无下载地址的文件是否跳过，405 是否重试）
# 3) 同名文件路径隔离（file_id 前 8 位区分）
# token 不可用时自动跳过在线验证，仅执行离线验证
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
| `WPS365_CLI_BIN` / `KDOCS_CLI_BIN` | 自动解析 | CLI 绝对路径覆盖（默认：`~/.local/bin` > PATH；刻意避开 `/usr/local/bin` 旧版 v0.1.0） |
| `WPS_BACKUP_RUN_TIMEOUT` | `21600` | 单次运行看门狗秒数（超时 → 取消 → 宽限 300s 后强退，退出码 124） |
| `WPS_OTL_CACHE_SCAN` | `1`（App 默认传 `0`） | WPS Office 本地缓存扫描（需完全磁盘访问权限） |
| `WPS_AIRPAGE_OTL_CONTENT` / `WPS_AIRPAGE_EXPORT_DOCX` | `1` | airpage 内容备份 / docx 导出 |
| `WPS_BACKUP_NO_CONSOLE` | 未设 | `1` 时日志只写 `backup.log`（runner 设置） |
| `WPS_OTL_WORKERS` | `4` | v5 OTL 导出并发数 |

在 `python -m unittest` 下，`BACKUP_DIR`/`STATE_DIR` 默认改为临时目录（测试不写生产日志/状态）。

代码中硬编码的其他关键常量：
- `SCHEDULE_MINUTE = 0` — 每日触发分钟
- `MAX_RETRIES = 5` — 单文件最大重试次数（含 chunk 重试）
- `CHUNK_SIZE = 10MB` — 断点续传分块大小
- `DOWNLOAD_TIMEOUT = 600s` — 整体下载超时
- `CLI_BIN` / `KDOCS_CLI_BIN` — 由 `resolve_cli_bin()` 解析的绝对路径（launchd PATH 不含 `~/.local/bin`）
- `CONTENT_BACKUP_ENABLED = True` — 文档内容备份总开关
- `CONTENT_BACKUP_FORMATS = {".docx", ".doc", ".pdf", ".xlsx", ".xls", ".ksheet", ".dbt", ".otl"}` — 内容备份支持格式
- `OTL_CONTENT_BACKUP_ENABLED = True` — OTL 内容备份总开关
- `AIRPAGE_OTL_CONTENT_ENABLED = True` — 使用 airpage 备份 OTL 内容（环境变量 `WPS_AIRPAGE_OTL_CONTENT=0` 关闭）
- `AIRPAGE_EXPORT_DOCX_ENABLED = True` — airpage 同时导出 docx 到 `_otl_converted_docx/`（`WPS_AIRPAGE_EXPORT_DOCX=0` 关闭）
- `SKIP_EXTS`（engine.py）= `{".otl", ".spt", ".form"}` — 不可通过 Drive API 直接下载的格式

### `wps_backup/engine.py` — 备份引擎

- **多线程下载**：`ThreadPoolExecutor(max_workers=...)`
- **差量逻辑**：基于 `file_id + mtime` 对比，远程文件修改时间更新则重新下载
- **断点续传**：对 >10MB 文件使用 HTTP `Range` 请求分段下载，临时文件 `.tmp`
- **URL 串行化限流**：获取下载地址时加锁，避免并发轰炸 WPS API（间隔 200ms）
- **失败分类**：永久失败（无下载地址）记录到状态，后续跳过；临时失败（405/429/网络错误）重试
- **路径隔离**：本地文件名格式为 `{stem}_{file_id[:8]}{suffix}`，避免同名文件冲突
- **旧版迁移**：检测到旧版命名（无 file_id 后缀）的已存在文件，自动重命名为新格式
- **扫描完整性**（v4.2）：分页失败显式抛 `RuntimeError`；任一盘失败则跳过该盘且**不执行 prune_stale**，结果记入 errors（非零退出）
- **取消/进度**（v4.2）：worker 检查 `CANCEL`；`progress` 回调供 App 显示扫描/下载进度
- **内容备份触发**（v4.0）：实体下载成功后，自动调用 `kdocs_engine.backup_file_content()` 将支持格式转为 Markdown（含 YAML frontmatter：file_id, drive_id, name, source_format, backup_at）。**内容备份失败不影响主流程**，仅计入 `content_failed` 统计。

### `wps_backup/kdocs_engine.py` — kdocs-cli 封装（v4.1 起为回退后端）

⚠️ **2026-09 起 kdocs API 拒绝企业账号（错误码 403001），所有业务接口对本项目账号不可用**；OTL 内容备份已迁移到 airpage_engine。本模块保留用于个人账号场景，以及主引擎 `_content_backup/`（docx/pdf/xlsx 内容备份，目前对企业账号失效）。

- `read_file_content()` — 调用 `kdocs-cli drive read-file`，返回原始 `data`；支持 docx/pdf/xlsx/ksheet/dbt/otl，**不支持 pptx**。注意 `content` 字段类型因格式而异：docx/otl/pdf 为 Markdown 字符串，xlsx/ksheet 为结构化 dict
- `backup_file_content()` — 将文档内容备份为 `.md`（带 YAML frontmatter），输出到 `_content_backup/{drive_name}/`
- `backup_otl_content()` — OTL 专用内容备份（回退路径）
- `_content_to_text()` — 内容类型归一化（v4.0.1）：str 原样返回，dict/list 序列化为格式化 JSON
- `search_files()` — 文件名/全文搜索
- `check_kdocs_cli_available()` — 认证状态检查 + 业务接口探测（v4.2：返回 403001 企业账号时判为不可用，避免每个文件白跑 read-file）
- `get_kdocs_version()` — 版本获取
- Token 过期自动检测（错误码 400006 / expired），提示重新登录
- `ContentBackupResult.docx_path` — v4.1 新增，记录 airpage 导出的 docx 路径

### `wps_backup/airpage_engine.py` — airpage 封装（v4.1 新增，OTL 内容备份主路径）

基于 `wps365-cli airpage`（需 scope `kso.airpage.readwrite`，企业账号可用）：

- `read_airpage_blocks()` — `airpage block get <file_id>` 读取 v2 块树
- `blocks_to_markdown()` — 块树扁平化为 Markdown 文本（段落、heading 级别、@提及、图片占位符、嵌套递归）
- `get_airpage_version()` — 获取文档版本号（导出必需）
- `export_airpage_to_file()` — `export create` → 轮询 `export get`（task-id 即 create 返回的 key）→ 下载，支持 docx/json/pdf，原子写入
- `backup_otl_via_airpage()` — OTL 内容备份主入口：Markdown（带 frontmatter，含 `backend: airpage`）→ `_otl_content/{drive_name}/`，可选 docx → `_otl_converted_docx/`；**docx 导出失败不影响 Markdown 备份结果**
- `check_airpage_available()` — 检查 token 是否授予 airpage scope
- 所有函数支持 `runner`/`fetcher`/`sleep` 依赖注入（离线单测）

### `wps_backup/wps_http.py` — 直连 HTTP（v5）

- `WpsHttp.api(method, path, body)`：直接调用 `https://openapi.wps.cn`，`Authorization: Bearer <wps365-cli auth token>`；401 时 `auth refresh --delegated` 后重试一次；token 只在内存
- `open_url()` / `download()`：`*.wps.cn`、`*.ksyun.com`、`*.kdocs.cn`、`*.qwps.cn` 先直连，连接/SSL/超时错误回退系统代理；HTTP 错误不回退；下载原子写入
- 主引擎实体下载、旧 docx 导出、v5 导出均经此路由

### `airpage_engine` v5 函数

- `backup_otl_v5(file_id, name, …, want_md, want_docx)`：`GET /v7/airpage/{id}` 取 version（403/404 → 永久失败）→ 创建 `export_to_markdown_zip` / `export_to_docx` 任务 → `export_task/query` 统一轮询 → 下载；md 解包、`rewrite_image_links()` 按 `image_id` 改写为 `.assets/` 相对路径、frontmatter 含 `backend: airpage-markdown-zip`、`airpage_version`、`format: 5`；空文档 → 永久失败；任何失败都不破坏已有文件
- 旧的 `backup_otl_via_airpage()`（块树转换）保留为 markdown_zip 临时失败时的回退

### `wps_backup/otl_engine.py` — OTL 专项备份 v5（前身 v4.1）

v5：`run(api_files=…, scan_complete=…)` 复用主引擎扫描结果；airpage 后端走 `_run_v5()`（`plan_v5()` 产物级计划 → 线程池并发 → `record_v5()` 加锁合并状态）；kdocs 后端保持旧流程。


`.otl`（WPS 在线文档私有格式）无法通过 Drive API 直接下载，采用四阶段混合策略：

1. **API 扫描**：通过 wps365-cli 获取所有 `.otl` 文件元数据
2. **airpage 内容备份**（主力）：`block get` 块树 → Markdown 存 `_otl_content/`；`export` 导出 docx 实体存 `_otl_converted_docx/`。后端选择见 `select_content_backend()`：airpage 优先，kdocs-cli 回退，均不可用则跳过
3. **缓存实体备份**（补充）：扫描 WPS Office macOS 本地云同步缓存 `~/Library/Containers/com.kingsoft.wpsoffice.mac/.../filecache`，解析 `rectfile2.xml`（文件名、fileId、accessTime）
4. **导出指南**：仅在无任何内容备份后端时生成 `EXPORT_GUIDE.md`

缓存匹配策略：精确文件名匹配（不区分大小写）+ 大小容差 0.5x–2.0x；模糊大小匹配（容差 ±15%）。缓存实体复制到 `_otl_files/`，保留时间戳。

v4.2 变更：
- 扫描失败抛 `ScanIncompleteError(partial)`：使用已扫描部分继续内容备份，但跳过 `prune_stale`；不再回退硬编码默认盘；子目录列表分页
- 缓存阶段先用 `cache_dir_accessible()` 在带 15s 超时的子进程中探测（TCC 阻塞时 kill 且不再 wait），失败跳过；`WPS_OTL_CACHE_SCAN=0` 关闭
- 永久失败记忆：`.otl.link` 快捷方式与空文档记录 `error_msg`+`permanent`，mtime 不变不再重试；临时失败照常重试

### `wps_backup/state.py` — 状态管理器

- 线程安全（`threading.Lock`）
- 以 `drive_id/file_id` 为 key 存储 `FileSnapshot`
- `needs_update()` 判断依据：
  - 新文件 → 需要下载
  - 已知永久不可下载（error_msg 含"无下载地址" / "不可下载"）→ 跳过
  - 远程 `mtime >` 本地记录 `mtime` → 需要更新
- `prune_stale()` 清理远程已不存在的本地记录；**空扫描保护**：远程结果为空但本地有记录时视为扫描异常，跳过清理（v4.1，防止 CLI 接口漂移清空增量状态）
- 原子写入：`.tmp` → 重命名覆盖原文件

### `wps_backup/app_contract.py` — 引擎↔App 契约（v4.2）

- `RunRecorder`：`start()` 写 `progress.json`，`update()` 更新阶段/进度，`finish()` 写 `last_run.json` + 追加 `runs.jsonl`（被锁 75 也记录，但不删除他人的 progress）
- `should_run_scheduled(now, hour, history)`：到点后当天无成功才运行；失败每小时重试，每天最多 3 次；75 不计入尝试；到点前的手动成功不算
- `CANCEL`（`threading.Event`）：SIGTERM / 看门狗置位；下载 worker 与 OTL 循环检查后退出
- `Watchdog`：超时置位 CANCEL，宽限期后 `os._exit(124)`（锁随进程释放）
- `collect_status()` / `compute_health()`：`status --json` 的数据与 ok/warn/error 判定（登录失效、CLI 缺失、上次失败/超时、36h 未成功、refresh token 30 天内过期）
- dry-run 不记录（否则会被当作当天已成功）

### `wps_backup/lock.py` — 单实例锁（v4.2）

`flock` 非阻塞排他锁 `wps_backup_state/.run.lock`，写入持锁 PID；`run`/`scheduled`/`backup-otl` 均受保护，被锁时退出码 `75`。

### `wps_backup/scheduler.py`

- **守护模式**：`daemon_mode()` 轮询当前时间（间隔 60s），到达 `SCHEDULE_HOUR:SCHEDULE_MINUTE` 自动触发备份
- **launchd 配置生成**（旧版，已由 App 取代）：生成 `com.wps.backup.plist`（含 `EnvironmentVariables` PATH/HOME）。App 的 scheduler plist 存在时 `install` 拒绝执行。

---

## 代码风格与约定

- **注释与文档字符串**：全部使用中文，面向中文开发者。
- **代码标识符**：英文，遵循 PEP 8。
- **私有函数**：下划线前缀（`_cli`, `_download_chunk`, `_get_dest_path`）。
- **模块日志**：每个模块通过 `setup_logger()` 获取同名 logger，统一输出到 `backup.log` + stderr（`WPS_BACKUP_NO_CONSOLE=1` 时仅文件）。
- **退出码语义**：见“运行方式”；任何失败（含认证/扫描失败）都必须非零退出，不得以 0 掩盖。
- **数据结构**：优先使用 `@dataclass`（`RemoteFile`, `FileSnapshot`, `BackupResult`, `ContentBackupResult` 等）。
- **线程安全**：状态修改和结果计数均使用 `threading.Lock`。
- **路径处理**：统一使用 `pathlib.Path`，避免字符串拼接。
- **临时文件**：所有文件写入均先写 `.tmp`，完成后再 `Path.replace()` 原子覆盖。
- **纯标准库**：不引入第三方 Python 依赖；新能力优先通过外部 CLI（wps365-cli / kdocs-cli）扩展。

---

## 测试策略

本项目使用 **stdlib unittest**（v4.1 引入，仍无第三方依赖）+ 脚本化验证：

| 测试手段 | 文件/命令 | 说明 |
|----------|-----------|------|
| 单元测试 | `python3 -m unittest discover -s tests` | airpage 引擎（离线，注入 runner）、集成分发、状态防护、线上契约 |
| 线上契约测试 | `python3 -m unittest tests.test_cli_contract` | 验证 wps365-cli 命令接口未漂移（token 不可用时自动跳过） |
| 修复验证脚本 | `python3 verify_fix.py` | 离线验证状态逻辑与路径隔离；在线验证 dry-run 时不可下载格式是否被过滤 |
| 手动 Dry-run | `python3 wps_backup.py run --dry-run` | 预览差异，确认待下载列表 |
| 限制规模测试 | `python3 wps_backup.py run --max 3` | 小批量端到端测试 |
| 日志检查 | `python3 wps_backup.py log -n 50` | 查看下载、失败、跳过的具体记录 |
| OTL 专项测试 | `python3 wps_backup.py backup-otl --dry-run` | 预览 OTL 缓存匹配结果 |
| 语法检查 | `python3 -m py_compile wps_backup.py wps_backup/*.py` | 修改后快速验证 |
| macOS App | `cd macos && ./build.sh` | Core 单元测试 + 编译 + 签名（`--install` 安装） |
| launchd 环境验证 | `env -i HOME=$HOME PATH=/usr/bin:/bin:/usr/sbin:/sbin python3 wps_backup.py run --dry-run` | 模拟 launchd 最小环境（交互 shell 中测试通过不代表 launchd 能跑） |
| App 端到端 | `touch wps_backup_state/force_run && launchctl kickstart …scheduler` + `WPSBackup --diagnose` | 以 `backup.log` 新的开始/完成对 + `last_run.json` exit 0 为准，不只看退出码 |

**新功能开发遵循 TDD**：先写失败测试（RED）→ 最小实现（GREEN）→ 重构。CLI 边界通过注入 `runner`/`fetcher`/`sleep` 实现离线测试。

**建议新增功能时的测试步骤：**
1. 先为新逻辑写 unittest（离线部分）；
2. `--dry-run` 确认逻辑正确；
3. 用 `--max N` 做小批量真实下载验证；
4. 检查 `backup.log` 和 `backup_state.json` 是否符合预期；
5. 运行 `python3 -m unittest discover -s tests` 和 `verify_fix.py` 确保没有回归。

---

## 安全注意事项

1. **认证 Token**
   - 项目本身不存储密码，依赖 `wps365-cli` 和 `kdocs-cli` 管理 OAuth token。
   - `wps365-cli` 将凭证存储在系统 Keychain（macOS）或加密文件中。
   - `_get_auth_token()` 从 `wps365-cli auth token` 获取临时 access token，仅在内存中使用。
   - 两个 CLI 的 token 不互通，需分别维护认证。

2. **日志安全**
   - `backup.log` 中可能包含文件名称、大小、下载 URL 等元数据，**不包含文件内容**。
   - 日志文件位于本地 `wps_backup_state/backup.log`，已启用 `RotatingFileHandler`（10MB × 5 个轮转文件）。

3. **状态文件**
   - `backup_state.json` 和 `_otl_state.json` 包含文件元数据（文件名、link_url、hash）。
   - 这些文件是差量备份的核心，删除将导致下次全量重新下载。

4. **敏感数据规范**
   - 代码库已清理所有硬编码凭证；`wps_backup_data/`、`wps_backup_state/` 及 IDE 配置目录已被 `.gitignore` 排除。
   - 新增测试脚本或配置文件时，确保不含硬编码凭证。推送前可扫描：
     ```bash
     grep -rn "password\|secret\|token" --include="*.py" --include="*.yaml" --include="*.json" .
     ```

5. **本地缓存路径**
   - `otl_engine.py` 读取 `~/Library/Containers/com.kingsoft.wpsoffice.mac/...`，这是 WPS Office 的私有沙盒数据，**只读不修改**。

6. **launchd 配置 / App**
   - App 的 scheduler/login plist 含 App 与引擎绝对路径；移动 App 后重新打开 App 即自动更新 plist。迁移项目目录需在 App 设置或 `~/Library/Application Support/WPS Backup/settings.json` 修改 `engineRoot` 并重新构建（`WPSEngineRoot` 写入 Info.plist）。
   - App 为 ad-hoc 签名、非沙盒；不使用 SMAppService（见 `macos/README.md`）。

---

## 故障排查速查表

| 症状 | 可能原因 | 排查方法 |
|------|---------|---------|
| 认证失败 / 无法获取盘列表 | `wps365-cli` token 过期 | `wps365-cli auth status` → `wps365-cli auth refresh --delegated`；refresh 失败则重新 `auth login --device`（带完整 scopes） |
| airpage 报 invalid_scope | token 缺 `kso.airpage.readwrite` | 重新 `auth login --device --scopes "... kso.airpage.readwrite"`（见"前置条件"） |
| `unknown command "airpage"` | 升级后未刷新 spec | `wps365-cli spec update` |
| 扫描返回 0 个文件 | CLI curated 命令接口漂移（如 v0.3.3 将 `drive files` 改名 `drive file`） | `python3 -m unittest tests.test_cli_contract` 定位失效命令 |
| 内容备份失败 / 错误码 403001 | kdocs API 已拒绝企业账号（2026-09 起） | 预期行为：OTL 已走 airpage；`_content_backup` 需个人账号 kdocs-cli |
| kdocs-cli 无法安装/升级 | CDN DNS 不可解析 | 先尝试 `kdocs-cli upgrade -y`；失败则见 `docs/kdocs-cli-setup.md` §3.3 手动下载方案。升级后注意 `chmod +x ~/.local/bin/kdocs-cli` |
| 大量文件失败 | 下载 URL 过期或网络抖动 | 查看 `backup.log` 中的错误码；引擎会自动重试，通常下次运行可恢复 |
| 个别文件 HTTP 403 | 云端分享权限不足 | 在 WPS 云端确认文件权限；403 被标记为不可重试，权限恢复后需清理状态中的 error_msg 才会重下 |
| .otl 文件无法备份 | airpage/kdocs 均不可用且缓存中不存在 | 确认 airpage scope 已授权；或在 WPS Office 中打开一次，或按 `EXPORT_GUIDE.md` 手动导出 |
| 备份进程挂起无进展 | 导出下载网络停滞（v4.1 已加 60s 超时） | 升级代码后重跑；`ps aux \| grep wps_backup` 确认 |
| 同名文件被覆盖 | 旧版本引擎未使用 file_id 隔离 | 检查本地路径是否包含 `_fileid[:8]` 后缀；引擎会自动迁移旧格式 |
| 定时任务不跑 / App 图标红色 | scheduler 未加载、在“登录项”中被关闭、或 spawn failed | `WPSBackup --diagnose`；App 设置点“启用定时备份/重新安装定时任务”；`launchctl print gui/$(id -u)/cc.all4world.wpsbackup.scheduler` |
| launchd 下报 `No such file or directory: 'wps365-cli'` | launchd PATH 不含 `~/.local/bin`（2026-07 事故） | v4.2 已用绝对路径；或设 `WPS365_CLI_BIN` |
| 运行卡在“扫描 WPS Office 本地缓存” | macOS TCC“App 数据”权限弹窗阻塞 opendir（2026-09 事故） | v4.2 已加 15s 子进程探测；如需缓存扫描，为 Python 授予完全磁盘访问权限 |
| agent `OS_REASON_CODESIGNING` / `spawn failed` | SMAppService + ad-hoc 签名重建后 LWCR 失效 | 已弃用 SMAppService；清理旧注册后用经典 plist（App 启动自动处理） |
| `last_run.json` 退出码 75 | 另一备份进程持锁 | `cat wps_backup_state/.run.lock` 查看 PID；确认后结束该进程 |
| 退出码 124 / 130 | 运行超时 / 被取消 | 下次运行会续传；超时频繁则调大 `runTimeoutHours` |
| 收不到异常通知 | 系统通知授权被拒（ad-hoc App 常见） | `WPSBackup --test-notify`；未授权时自动改用 AppleScript 通知；系统设置 → 通知 → WPS Backup |
| OTL 有 Markdown 但缺 docx；日志 `导出下载失败 … handshake operation timed out` | 本机 HTTP(S) 代理（127.0.0.1:3213，系统设置 + 环境变量）对金山云 ks3 域名握手超时 | `curl --noproxy '*'` 验证直连；修复方案见 `docs/OTL_EXPORT_RESEARCH.md` §4 |
| `last_run` 退出码 1，错误含“OTL 临时失败 N 个” | 导出/下载临时失败（token、网络、接口变化） | 定时任务每小时自动重试；持续失败先跑 `tests.test_cli_contract.TestOtlV5Contract`。永久失败只认响应码 403000001，不会因一次 token 故障误标 |
| OTL 日志 `markdown_zip 失败…已回退块树转换` | 官方导出接口临时失败 | 自动回退，文本仍有备份；下次运行会重试 markdown_zip（`md_error` 非空） |
| v5 契约测试失败 / 导出返回 404 Route Not Found | 官方调整了 `export_to_markdown_zip` 等未收录接口 | `python3 -m unittest tests.test_cli_contract.TestOtlV5Contract`；对照开放平台“智能文档”文档树更新路径 |
| OTL 数量与旧扫描不一致 | 新条目类型（如快捷方式 `type=shortcut`）未被收集 | 契约测试 `test_single_walk_matches_legacy_otl_scan` 定位 |
| App 报“定时任务已超过 3 小时未触发” | Mac 长时间睡眠或 scheduler 异常 | 唤醒后会补跑；持续出现则 `--diagnose` 检查 |
| 状态文件损坏 | JSON 被意外截断 | 删除 `backup_state.json` 重新全量备份（本地文件存在则只重建状态不重下） |

**调试单文件内容读取：**
```bash
# airpage（OTL，企业账号）
wps365-cli airpage block get <file_id> | head -50
wps365-cli airpage export create <file_id> --format docx --version 1
# kdocs-cli（回退，个人账号）
kdocs-cli drive read-file '{"file_id":"xxx"}'
find wps_backup_data/_otl_content -name "*.md" | wc -l
find wps_backup_data/_otl_converted_docx -name "*.docx" | wc -l
find wps_backup_data/_content_backup -name "*.md" | wc -l
```

---

## 已知技术债务（v4.2 更新）

| 债务 | 优先级 | 说明 |
|------|--------|------|
| `_content_backup` 对企业账号失效 | 中 | kdocs API 403001；docx/pdf/xlsx 内容备份需个人账号 kdocs-cli，或评估 wps365-cli `drive file-content` |
| wps365-cli 接口漂移 | 中 | remote spec 会重命名 curated 命令（v0.3.3 `drive files`→`drive file` 曾致全量状态被清，已加防护）；升级后跑 `tests/test_cli_contract.py` |
| 通知依赖 GUI 运行 | 中 | 异常通知由菜单栏 App 发出（已设登录自启）；App 未运行时仅靠下次打开 App 发现 |
| 目录树遍历两次 | — | ~~OTL 二次扫描~~ 已修复（v5：一次遍历，OTL 阶段 75 s → 0 s） |
| 事件驱动增量 | 低 | `kso_file_update` + 长连接订阅可免定时全量扫描；需开发者后台配置 |
| 主引擎整盘跳过 | 低 | 单个目录失败导致整盘本次跳过（OTL 侧已保留部分结果） |
| `verify_fix.py` 污染生产状态 | — | ~~写入真实状态~~ 已修复：`check_state_logic()` 使用临时状态文件 |
| .otl.link 文件处理 | — | ~~每次重试~~ 已修复（v4.2）：记录为永久失败，mtime 不变不再重试 |
| 状态文件 JSON → SQLite | 低 | 当前约 1K 条约 600KB，性能足够；超过 5K–10K 条时建议迁移 |
| 备份通知机制 | — | ~~无通知~~ 已由 WPS Backup.app 提供（异常才通知） |
| HTTP 403 重试 | 低 | ~~403 永久跳过~~ 已修复（v4.1）：下载遇 401/403 自动刷新 token 重试一次（hwc-bj.ag.wps.cn 等域名要求 Bearer，token 仅 2h）；仍失败才判定权限不足 |
| 每文件全量重写状态 | 低 | `mark_backed_up` 每次重写整个 JSON 并重算 total_size，万级文件时会变慢 |

---

## 子项目索引

| 目录 | 内容 | 独立文档 |
|------|------|----------|
| `calendar_Sync/` | WPS 日历 CalDAV 代理（Go，SQLite WAL + WebDAV，生产运行中） | `calendar_Sync/AGENTS.md`、`calendar_Sync/DESIGN.md` |
| `wps-mcp/` | MCP 协议相关文档 | — |
| `src/cli-0.1.0/` | `wps365-cli` 官方安装脚本副本 | `src/cli-0.1.0/README.md` |
| `docs/` | `OTL_EXPORT_RESEARCH.md`（OTL 导出调研）、`kdocs-cli-setup.md`（双 CLI 指南）、`OPTIMIZATION_PLAN.md`（巡检与优化）、`MACOS_APP_PLAN.md`（App 计划与实施记录） | — |
| `macos/` | WPS Backup.app（菜单栏 App + 定时任务 runner） | `macos/README.md` |

---

## 文档维护规则（必须遵守）

**任何排障、升级（wps365-cli / kdocs-cli / Python / macOS / Xcode）、调度变更或功能开发完成后，必须在同一次工作中同步更新文档**，否则视为未完成：

| 变更类型 | 必须更新 |
|---|---|
| 排障（发现并修复问题） | `HANDOFF.md` 状态速览 + 事故/修复记录；本文件“故障排查速查表”新增症状行；`README.md` 故障排查（用户可见症状时） |
| 外部 CLI 升级 | `HANDOFF.md` 环境信息（版本、路径、回退备份位置）；本文件“技术栈”版本；运行 `tests/test_cli_contract.py` 并记录结果 |
| 调度 / App 变更 | `macos/README.md`；`docs/MACOS_APP_PLAN.md` §9 实施记录；`HANDOFF.md` 定时任务行 |
| 架构决策 | `ADP.md` 新增决策条目（背景、选项、决定、后果） |
| 新优化项 / 技术债务 | `docs/OPTIMIZATION_PLAN.md` 与本文件“已知技术债务” |
| 新命令、配置项、环境变量、状态文件 | 本文件对应章节 + `README.md` |

同时更新各文档末尾的“最后更新”日期；结论必须有证据（测试结果、日志、`--diagnose` 输出），不要写未验证的“已完成”。

---

*最后更新: 2026-09-26（v5 OTL 高效备份：官方 markdown_zip + docx 并行、一次遍历、直连下载）*
