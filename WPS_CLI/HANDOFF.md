# WPS CLI 工具集 — 交接文档 (Handoff)

**版本:** 2.5
**日期:** 2026-09-26
**状态:** 生产运行中 — v5：OTL 官方 markdown_zip + docx 并行导出；WPS Backup.app 调度；wps365-cli v0.3.6
**交接人:** Kimi Code CLI → Claude Code（v4.2）
**接收人:** 下一位接力开发的大模型 Agent

---

## 1. 项目当前状态速览

```
WPS 云盘差量备份        ██████████████████████  100% 同步 (2026-09-26)
├── 快照记录:           1038 个文件，26.8 GB，0 个错误记录
├── 上次成功运行:        2026-09-26 18:5x（定时任务，无变化运行 43–58 s，exit 0；v4.2 基线 118 s）
├── 定时任务:           ✅ 由 WPS Backup.app 管理（cc.all4world.wpsbackup.scheduler，每小时检查、20:00 运行、失败重试），见 macos/README.md；旧 com.wps.backup 已迁移停用
│                       ✅ 16:00 整点自动触发已实测（仅写心跳，未到点不运行）
├── 历史事故:           2026-07-29～09-26 定时任务静默失效（见 §2.7）
│
OTL 专项备份（v5）       ██████████████████████  194/194 有内容的文档全部备份
├── 远程 .otl 总数:      220 个（主引擎一次遍历收集，OTL 阶段 0 s）
├── Markdown（官方）:     194 篇 format 5，771 处本地图片引用、失效 0（94 个 .assets 目录）
├── docx 导出:           195 个（`E6pC1h5m`、`Nn1SvNVS` 已补齐）
└── 永久失败（不再重试）: 26 个（6 个 .otl.link 无权限 403 + 20 个空文档），mtime 变化后自动重试
│
文档内容备份层          ⚠️ 40 个 Markdown（_content_backup/，kdocs 对企业账号 403001，已停止增长）
WPS Backup.app          ✅ ~/Applications/WPS Backup.app，--diagnose 健康度 ok
共享文件目录生成        ✅ 可用（手动运行）
日历 CalDAV 代理        📋 见 calendar_Sync/AGENTS.md 和 DESIGN.md
代码仓库                ✅ 已推送 GitHub（959e98c，2026-09-26）
```

---

## 2. 最近完成的升级（本次交接重点）

### 2.1 升级概述：引入 kdocs-cli 混合架构

**背景：** 金山文档官方发布了 `kdocs-cli` (v2.5.8) 替代旧版 MCP 中间层 `mcporter`。
`kdocs-cli` 具备 `drive read-file` 能力，可将 docx/pdf/xlsx/ksheet/dbt/otl 转为 Markdown，
这是 `wps365-cli` 完全不支持的能力。

**升级目标：**
1. 解决 `.otl` 文件无法通过 Drive API 下载的痛点（此前仅 23/201 能缓存备份）
2. 新增"文档内容备份层"——在实体文件外，额外备份 Markdown 内容作为"双保险"
3. 保持 `wps365-cli` 负责盘扫描和实体下载（kdocs-cli 无盘列表 API）

### 2.2 新增/修改文件清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `wps_backup/kdocs_engine.py` | **新增** | kdocs-cli 封装引擎：内容读取、搜索、OTL 备份、认证检查 |
| `wps_backup/config.py` | 修改 | 新增 `KDOCS_CLI_BIN`、`CONTENT_BACKUP_*`、`OTL_CONTENT_BACKUP_ENABLED` |
| `wps_backup/otl_engine.py` | **重写 v4.0** | 新增 kdocs-cli 内容备份路径；保留缓存实体备份作为补充 |
| `wps_backup/engine.py` | 修改 | 下载成功后自动触发 kdocs-cli 内容备份；新增 `content_backed_up/content_failed` 统计 |
| `wps_backup.py` | 修改 | `status` 显示 kdocs-cli 版本/认证状态和内容备份统计；`backup-otl` 新增 `--no-content` 参数 |
| `docs/kdocs-cli-setup.md` | **新增** | wps365-cli + kdocs-cli 完整安装配置与使用指南 v2.0 |
| `ADP.md` | **更新 v2.0** | 补充混合架构决策、内容备份设计、安全清理措施 |
| `README.md` | **新增** | 项目概览与快速开始 |
| `.gitignore` | 修改 | 排除敏感路径（.qwen, .antigravitycli, temp/, configs/） |

### 2.3 架构对比

```
旧架构 (v3.0):
  wps365-cli → Drive API → 下载实体文件
  .otl 无法下载 → 依赖本地缓存 (11% 覆盖率)

新架构 (v4.0):
  wps365-cli → Drive API → 下载实体文件
       ↓
  kdocs-cli → kdocs API → read-file (Markdown)
       ↓
  .otl 内容备份: 84% 覆盖率 (169/201)
  docx/pdf/xlsx 内容备份: 自动触发
```

### 2.4 升级验证结果

| 验证项 | 结果 |
|--------|------|
| 语法检查 (全部 Python 文件) | ✅ 全部通过 |
| kdocs-cli 认证 | ✅ v2.5.8 已认证 |
| OTL 内容备份 (169 文件 live) | ✅ 成功，256.7s |
| 主引擎 live 备份 (2 文件) | ✅ 成功，36.7s |
| `verify_fix.py` 回归测试 | ✅ 全部验证通过 |
| `wps_backup.py status` | ✅ 显示完整 kdocs 状态 |
| GitHub 推送 | ✅ 已推送，无敏感数据泄露 |

### 2.5 v4.0.1 运维恢复与内容备份修复（2026-07-27/28）

**背景：** 2026-07-27 巡检发现备份链路已中断约 7 周（上次成功备份 2026-06-09）：

1. `wps365-cli` delegated token 已于 2026-05-24 过期，导致盘扫描和下载全部不可用
2. `~/Library/LaunchAgents/com.wps.backup.plist` 缺失，launchd 定时任务未安装
3. 内容备份层存在类型错误 bug：xlsx/ksheet 全部失败

**处理过程：**

| 步骤 | 结果 |
|------|------|
| `wps365-cli auth refresh --delegated` | ✅ 成功，refresh token 有效期至 2027-07-27 |
| Dry-run + 正式备份 | ✅ 新增 57 + 更新 1，共 58 个文件，842s |
| OTL 专项 | ✅ 205 个 .otl，新增内容备份 3 个 |
| `python3 wps_backup.py install` + launchctl load | ✅ 每日 20:00 定时任务恢复 |

**Bug 修复（v4.0.1）：**

- **根因：** `kdocs-cli drive read-file` 对 docx/otl 返回 Markdown **字符串**，但对 xlsx/ksheet 返回结构化 **dict**（`range_data` + `sheets_info`）。`kdocs_engine.py` 中 `frontmatter + content` 直接拼接，抛出 `can only concatenate str (not "dict") to str`。
- **修复：** 新增 `_content_to_text()` 辅助函数——字符串原样返回，dict/list 序列化为格式化 JSON。`backup_file_content()` 和 `backup_otl_content()` 统一走该函数。
- **行为变化：** xlsx/ksheet 的 `.md` 内容备份文件现在存储表格结构化数据的 JSON（含单元格文本与格式信息），数据完整保留。
- **验证：** 语法检查 ✅；7 个失败 xlsx/ksheet 全部补跑成功（`_content_backup/` 达 40 个 .md）；`verify_fix.py` 全部 PASS ✅；dry-run 主流程无回归 ✅。

**遗留失败项（不可修复/需人工）：**

- 2 个 HTTP 403 文件（`ai_gov_doc.pptd.pptx`、`AI政务公文软硬一体化一体机产品全案_v2.0.docx`）——云端分享权限问题，403 被引擎标记为不可重试，需手动确认权限
- 6 个 `.otl.link` 快捷方式 + 1 个空 OTL——kdocs API 不支持/无内容，已知问题

### 2.6 v4.1 airpage 迁移与 wps365-cli v0.3.6 升级（2026-09-23/26）

**背景：** 巡检发现两个上游变化：

1. **kdocs API 拒绝企业账号**（2026-08 起，错误码 403001"暂仅支持个人账号"）——kdocs-cli 所有业务接口失效，OTL 内容备份（84% 覆盖率主力路径）和 `_content_backup/` 层整体停摆
2. **wps365-cli v0.3.1 → v0.3.6** 五个版本未升级，v0.3.3 引入的 `airpage` 命令（智能文档读取 + 导出 docx）恰好可在企业账号下替代 kdocs-cli

**处理过程（TDD）：**

| 步骤 | 结果 |
|------|------|
| wps365-cli 升级 v0.3.6（SHA-256 校验，v0.3.1 备份在 `~/.local/bin/wps365-cli.v0.3.1.bak`） | ✅ |
| `spec update` + `auth login --device` 增加 `kso.airpage.readwrite` scope | ✅ |
| airpage PoC（block get / export docx 真实 OTL 文件） | ✅ 1.5MB 有效 docx |
| 新增 `wps_backup/airpage_engine.py`（块树→Markdown、导出轮询、超时防护） | ✅ 25 个单测 |
| `otl_engine.py` v4.1：后端分发（airpage 优先，kdocs 回退）、状态记录 `docx_path` | ✅ |
| **事故**：v0.3.3 spec 将 `drive files` 改名 `drive file`，扫描返回 0 → `prune_stale` 清空两份增量状态 | 已修复：5 处调用改名 + `prune_stale` 空扫描保护（`tests/test_state_guards.py`） |
| **事故**：airpage 导出下载 `urlopen` 无超时，进程挂起 42 小时 | 已修复：`download_timeout=60s` + 测试 |
| 新增 `tests/` unittest 套件（42 个测试，含线上契约 `test_cli_contract.py` 防接口漂移） | ✅ 全部通过 |
| 主备份状态重建（1037 文件） | ✅ 59 新增下载 + 843 本地校验跳过；160 失败为历史 403/权限问题重新暴露 |
| OTL 全量重备（220 文件，含 2026-07 后新增 15 个） | ✅ airpage Markdown + 自动导出 docx 至 `_otl_converted_docx/` |

**架构变化：**

```
旧 (v4.0):  wps365-cli 下载实体 + kdocs-cli read-file → Markdown（企业账号已失效）
新 (v4.1):  wps365-cli 下载实体 + airpage block get → Markdown + airpage export → docx 实体
            kdocs-cli 降级为回退后端（个人账号）
```

**遗留：**
- `_content_backup/`（docx/pdf/xlsx 内容备份）对企业账号仍失效，待评估 `drive file-content` 或个人账号
- ~~约 160 个文件 HTTP 403~~ 已解决（2026-09-26）：根因是 access token 仅 2 小时有效，长跑下载中过期后 hwc-bj.ag.wps.cn 域名返回 403；engine 已加 token 刷新重试（`tests/test_engine_token_refresh.py`），109 个历史"失败"文件全部成功下载（含 4.3GB 视频）
- 6 个 `.otl.link` 快捷方式 + 17 个空文档标记失败（服务端限制，无内容可备）

### 2.7 v4.2 定时任务修复 + WPS Backup.app（2026-09-26）

**事故：定时任务自 2026-07-29 起静默失效约两个月**（9 月所有备份均为手动运行）。根因四层：

| 根因 | 修复 | 测试 |
|---|---|---|
| launchd PATH 不含 `~/.local/bin` → `No such file or directory: 'wps365-cli'` | `config.resolve_cli_bin()` 绝对路径（`~/.local/bin` 优先，避开 `/usr/local/bin` 旧版 v0.1.0）；plist 加 `EnvironmentVariables` | `test_launchd_env.py` |
| 认证/扫描失败只记 errors，`run` 仍返回 0 | `result.errors` 非空 → 退出码 1 | — |
| OTL 缓存扫描访问 `~/Library/Containers/com.kingsoft.wpsoffice.mac` 触发 macOS TCC 授权弹窗，launchd 下 `opendir` **永久阻塞** | `cache_dir_accessible()` 子进程 15s 超时探测（超时 kill 不 wait）；App 默认关闭缓存扫描 | `test_run_hygiene.py`；`env -i` 最小环境实测 |
| launchd 任务未加载 | App 每次启动幂等安装 | App 端到端 |

**同时修复的隐患：**
- 扫描分页失败静默 break → 不完整扫描使 `prune_stale` 误删其他盘记录：改为显式抛错 + 不完整时跳过 prune；OTL 不再回退硬编码默认盘；OTL 子目录分页（`test_scan_completeness.py`）
- kdocs-cli `auth status` 已认证但业务接口 403001 → 每个 docx/pdf 白跑 3 次 read-file：新增业务探测
- 23 个 OTL 永久失败每次重试 → 记录 `permanent` + mtime
- 手动与定时运行重叠 → `flock` 单实例锁（退出码 75）
- 测试写入生产 `backup.log` → unittest 下默认临时目录

**新增：引擎↔App 契约**（`wps_backup/app_contract.py`）：`last_run.json`、`runs.jsonl`、`progress.json`、`scheduler_heartbeat.json`、`force_run`；`scheduled` 命令（到点且当天未成功才跑，失败每小时重试、每天 ≤3 次）；`status --json`（含 health）；SIGTERM 取消（130）；看门狗（124）。

**新增：WPS Backup.app**（`macos/`）：SwiftUI 菜单栏三态图标、立即备份/取消、设置、重新登录（`auth login --device`）、异常通知、`--diagnose` / `--test-notify`。`build.sh` 用 `swiftc` 直编（Xcode 许可未接受 → Command Line Tools）。

**实施中的两个发现（已写入 ADP）：**
1. **SMAppService 不可用于 ad-hoc 签名 App**：重建后 launchd 的 LWCR（cdhash 约束）变为空并标记 `needs LWCR update`，agent 以 `OS_REASON_CODESIGNING` / `spawn failed` 被拒；注销重注册不可靠 → 改用经典 `~/Library/LaunchAgents` plist（无 LWCR），登录项同样改为经典 plist。旧 SMAppService 注册已由 App 清理。
2. **系统通知授权为“拒绝”时 `UNUserNotificationCenter.add()` 不报错、静默丢弃** → 先查授权状态，未授权改用 AppleScript 通知。

**验收证据（2026-09-26）：** 真实 runner 代码变更（新 CDHash）→ `build.sh --install` → 无人工步骤 kickstart → `last_run.json` exit 0、launchd last exit 0；取消 → 130；16:00 整点自动触发写入心跳；`--diagnose` health ok；Python 111 测试 + Swift Core 18 测试全部通过。

### 2.8 v5 OTL 高效备份（2026-09-26 晚）

- **调研**：从 WPS 开放平台文档树（`/docs/api/collections/wps365`）发现官方“ap 转 markdown / markdown_zip 任务”、导出结果按版本缓存、限频“无”、文件更新事件与长连接订阅；实测 markdown_zip（95 MB/49 图文档 10.4 s）。记录：`docs/OTL_EXPORT_RESEARCH.md`（已标注被推翻的早期结论）、`docs/OTL_BACKUP_DESIGN_V5.md`
- **实现**（TDD）：`wps_http.py` 直连客户端（代理回退）；`backup_otl_v5()` md_zip+docx 并行；产物级状态 `plan_v5/record_v5`；主引擎一次遍历收集 `.otl`（快捷方式 `type=shortcut`，契约测试发现并修复）；4 路并发
- **验收（定时任务实跑）**：197 篇升级 3 分 50 秒 exit 0；`E6pC1h5m`/`Nn1SvNVS` docx 补齐；771 图片引用 0 失效；无变化运行 118 s → 43–58 s；离线 146 + 线上契约 5 全部通过
- **复核修正**：永久失败只认响应码 403000001（HTTP 403 也可能是 token 失效）；OTL 临时失败令 run 退出码 1；直连超时上限 20 s；主引擎下载新路由已实测（含 12.7 MB 分块续传，哈希一致）

---

## 3. 已知问题与技术债务

### 3.1 当前状态

```bash
# wps365-cli（2026-09-26）
$ wps365-cli auth status      # delegated: valid，含 kso.airpage.readwrite
  access_token 有效期 2 小时（自动刷新）
  refresh_token 有效期至 2027-09-26    ← 过期前 30 天 App 图标变为“需留意”

# kdocs-cli：已认证，但 kdocs API 对企业账号返回 403001（引擎自动判为不可用）

# 一键查看 App 所见全部状态
$ "$HOME/Applications/WPS Backup.app/Contents/MacOS/WPSBackup" --diagnose
```

**注意：** 两个 CLI 的 Token **不互通**。wps365-cli refresh 失败时：App 设置 → “重新登录 WPS”（后台执行 `auth login --device`，浏览器授权后自动补跑一次备份）。

### 3.2 技术债务

| 债务 | 优先级 | 说明 |
|------|--------|------|
| OTL v5 依赖未收录接口 | 中 | `export_to_markdown_zip` 不在 CLI spec，经直连调用；由 `TestOtlV5Contract` 监测 |
| 通知依赖 GUI 运行 | 中 | 异常通知由菜单栏 App 发出（已设登录自启）；系统通知授权当前为“拒绝”，走 AppleScript 回退 |
| `_content_backup` 对企业账号失效 | 中 | docx/pdf/xlsx 无 Markdown 层；评估 wps365-cli 等价接口 |
| `verify_fix.py` 写生产状态 | — | ~~已修复~~：改用临时状态文件（其在线 dry-run 仍写生产日志，可接受） |
| wps365-cli 接口漂移 | 中 | 升级后必须跑 `tests/test_cli_contract.py` |
| 目录树遍历两次 | 低 | 主引擎与 OTL 各遍历一次；可合并，扫描耗时约减半 |
| 主引擎单目录失败整盘跳过 | 低 | 可仿照 OTL 保留部分结果 |
| 状态文件每文件全量重写 | 低 | ~700KB JSON；万级文件时改批量落盘或 SQLite |
| 签名 | 低 | ad-hoc 签名；若改 Apple Development（需接受 Xcode 许可 + Apple ID）可重新评估 SMAppService |

### 3.3 风险项

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| kdocs-cli CDN 不稳定 | 自动升级可能失败（2026-07 曾恢复并成功升级至 2.5.22） | 优先 `kdocs-cli upgrade -y`，失败则用手动升级流程（见 `docs/kdocs-cli-setup.md`）；升级后注意 `chmod +x` 修复执行权限 |
| kdocs-cli Token 过期 | OTL 内容备份和内容备份层失效 | Token 有效期约 1 年，过期后执行 `kdocs-cli auth login` |
| wps365-cli 与 kdocs-cli 双认证维护 | 操作复杂度增加 | `status` 命令同时显示两者状态，便于监控 |
| WPS API 限流策略变化 | 405/429 可能以更激进的方式出现 | 已增加 URL 限流和 405 重试 |
| 敏感数据泄露 | GitHub 仓库暴露凭证 | 已清理所有硬编码凭证，.gitignore 已配置，推送前验证通过 |

---

## 4. 下一步行动建议

### 4.1 日常（零操作）

App 自动运行。仅在菜单栏图标变为 ! / ✗ 时查看原因行；或运行 `WPSBackup --diagnose`。

### 4.2 短期

2. 系统设置 → 通知 → WPS Backup 开启系统通知（当前走 AppleScript 回退）

### 4.3 中期

见 `docs/OPTIMIZATION_PLAN.md` §4：单次目录树遍历、主引擎保留部分扫描结果、状态批量落盘、`_content_backup` 替代后端、全文搜索索引。

---

## 5. 代码阅读指南（给接手 Agent）

### 5.1 新增模块速览

**`wps_backup/kdocs_engine.py`** — kdocs-cli 封装：
- `read_file_content()` — 调用 `kdocs-cli drive read-file`，返回原始 data（content 可能是 str 或 dict）
- `backup_file_content()` — 将文档内容备份为 `.md`（带 YAML frontmatter）
- `backup_otl_content()` — OTL 专用内容备份
- `_content_to_text()` — 内容类型归一化：str 原样返回，dict/list（xlsx/ksheet 结构化数据）序列化为 JSON
- `search_files()` — 文件名/全文搜索
- `check_kdocs_cli_available()` — 认证状态检查
- `get_kdocs_version()` — 版本获取

**`wps_backup/otl_engine.py` v4.0** — 混合 OTL 备份：
- Phase 1: API 扫描（wps365-cli）
- Phase 2: **kdocs-cli 内容备份**（新增，169/201 成功）
- Phase 3: 缓存扫描（WPS Office 本地缓存）
- Phase 4: 缓存实体复制（保留）

### 5.2 关键调试技巧

```bash
# 查看 kdocs-cli 状态
kdocs-cli auth status
kdocs-cli version

# 测试单个文件内容读取
kdocs-cli drive read-file '{"file_id":"xxx"}'

# 查看内容备份目录
find wps_backup_data/_otl_content -name "*.md" | wc -l
find wps_backup_data/_content_backup -name "*.md" | wc -l

# 查看最近 50 行日志
python3 wps_backup.py log -n 50

# 查看状态（含 kdocs-cli 信息）
python3 wps_backup.py status

# 验证修复
python3 verify_fix.py
```

### 5.3 修改时的注意事项

1. **双 CLI 依赖** — 修改备份逻辑时需考虑 `wps365-cli` 和 `kdocs-cli` 的独立认证状态。
2. **内容备份是"锦上添花"** — 主备份流程（实体文件下载）不应依赖 kdocs-cli 可用。`engine.py` 中内容备份失败不影响主流程。
3. **YAML frontmatter 格式** — 内容备份的 Markdown 文件包含固定 frontmatter，修改格式可能影响下游消费。
4. **kdocs-cli 升级限制** — 不要依赖 `kdocs-cli upgrade` 自动工作，当前网络环境会失败。
5. **敏感数据清理** — 新增测试脚本或配置文件时，确保不含硬编码凭证。推送前运行凭证扫描：
   ```bash
   grep -rn "password\|secret\|token" --include="*.py" --include="*.yaml" --include="*.json" .
   ```

---

## 6. 环境信息

| 项 | 值 |
|---|---|
| 运行平台 | macOS (Apple Silicon arm64) |
| Python 版本 | 3.14.4（`/opt/homebrew/opt/python@3.14/bin/python3.14`，App/runner 使用此路径） |
| wps365-cli 路径 | `~/.local/bin/wps365-cli` (v0.3.6；v0.3.1 备份 `~/.local/bin/wps365-cli.v0.3.1.bak`；旧版 v0.1.0 在 `/usr/local/bin/`，**不得**进入 PATH 前列) |
| kdocs-cli 路径 | `~/.local/bin/kdocs-cli` (v2.5.22；旧版备份在 `~/.kdocs-cli/backup/`) |
| 项目根目录 | `/Users/whoami2028/Workshop/GITREPO/WPS_CLI` |
| 备份数据目录 | `wps_backup_data/` |
| 状态/日志目录 | `wps_backup_state/` |
| 定时任务 | `~/Library/LaunchAgents/cc.all4world.wpsbackup.scheduler.plist`（由 App 安装，每小时触发 runner） |
| 登录项 | `~/Library/LaunchAgents/cc.all4world.wpsbackup.login.plist`（登录时打开 App） |
| App | `~/Applications/WPS Backup.app`（`macos/build.sh --install` 构建安装；设置在 `~/Library/Application Support/WPS Backup/settings.json`） |
| 旧定时任务 | `com.wps.backup` 已停用，plist 移至 `wps_backup_state/legacy_com.wps.backup.plist` |
| 构建工具链 | Xcode 26.6 已装但许可未接受 → `build.sh` 回退 Command Line Tools（Swift 6.3.3） |
| GitHub 仓库 | https://github.com/All4worldjz/wps-kdocs-cli |
| Git 状态 | ✅ main 已推送（959e98c）；仓库根为上级目录 `GITREPO/`，只提交 `WPS_CLI/` |

---

## 7. 相关文档

| 文档 | 说明 |
|------|------|
| `README.md` | 项目概览与快速开始 |
| `AGENTS.md` | 项目背景、架构、开发规范 |
| `ADP.md` | 架构决策记录 |
| `HANDOFF.md` | 本文档 — 当前状态与交接事项 |
| `macos/README.md` | **WPS Backup.app 构建、组成、契约文件、排障** |
| `docs/OPTIMIZATION_PLAN.md` | 2026-09-26 巡检结论、修复清单、后续优化优先级 |
| `docs/MACOS_APP_PLAN.md` | App 设计计划 + §9 实施记录 |
| `docs/kdocs-cli-setup.md` | **WPS CLI 与 kdocs-cli 安装配置与使用指南 v2.0** |
| `calendar_Sync/AGENTS.md` | CalDAV 代理子项目说明 |
| `calendar_Sync/DESIGN.md` | CalDAV 代理设计文档 |

### 7.1 docs/kdocs-cli-setup.md 文档内容

该文档面向小白用户和 AI Agent，包含完整的全流程安装配置部署和基础运维指南：

**wps365-cli 部分（基于 https://github.com/wps365-open/cli）：**
- 一键安装脚本（macOS/Linux/Windows）
- 手动下载安装（GitHub Release）
- 三步开始：`auth setup` → `auth login` → `user me`
- 双轨命令体系：精装命令 + 通用 API 调用
- 认证管理：setup/login/status/token/refresh/logout/clean 全命令
- 两种认证模式：delegated（用户授权）/ app（应用身份）
- 7 大业务域命令速查：云文档、日历、即时通讯、会议、通讯录、邮箱
- 环境变量全表（13 个变量）
- 安全与凭证存储说明（Keychain / AES-256-GCM）
- Token 自动刷新机制

**kdocs-cli 部分（基于 https://bbs.wps.cn/topic/86117）：**
- Skill 包安装 + CDN 手动下载（含 DNS 问题处理）
- 认证配置（login/set-token/status/logout）
- 九大服务模块 93 个工具概览
- 云文档全生命周期操作（搜索/读取/下载/权限/分享）
- 智能文档(OTL)块级操作（查询/插入/更新/删除/转换）
- 多维表四维管理（表/字段/记录/视图）
- 演示文稿 JSAPI 引擎、网页剪藏
- 四种参数输入方式（键值对/JSON/stdin/文件引用）
- 版本检查与升级回滚

**故障排查：**
- wps365-cli 常见问题表（5 项）
- kdocs-cli 常见问题表（5 项）
- 诊断命令集合
- 认证问题速查

---

## 8. 交接检查清单

- [x] kdocs-cli 集成升级完成
- [x] OTL 内容备份验证通过 (172/205)
- [x] 主引擎内容备份层验证通过（40 个 Markdown）
- [x] v4.0.1 内容备份类型修复（xlsx/ksheet dict → JSON）验证通过
- [x] wps365-cli token 已刷新（refresh token 至 2027-07-27）
- [x] launchd 定时任务已重新安装（每日 20:00）
- [x] `verify_fix.py` 回归测试通过
- [x] ADP.md 已更新（v2.1）
- [x] HANDOFF.md 已更新（v2.2）
- [x] README.md 已创建并更新
- [x] `docs/kdocs-cli-setup.md` 已撰写（v2.0）
- [x] 敏感数据已清理（凭证、本地路径、IDE 配置）
- [x] `.gitignore` 已更新排除敏感路径
- [x] 代码已推送 GitHub（https://github.com/All4worldjz/wps-kdocs-cli）
- [x] GitHub 仓库无敏感数据泄露

**v4.2（2026-09-26）：**

- [x] 定时任务失效根因定位（PATH / 退出码 / TCC 阻塞 / 未加载）并修复，均有测试
- [x] 引擎↔App 契约（app_contract.py）+ `scheduled` / `status --json`
- [x] WPS Backup.app 构建、安装、定时任务端到端验收（exit 0 / 取消 130 / 整点自动触发）
- [x] 旧 com.wps.backup 与 SMAppService 注册已清理
- [x] Python 111 测试 + Swift Core 18 测试通过
- [x] README / AGENTS / HANDOFF / ADP / docs / macos/README 已同步更新
- [x] 代码提交并推送（959e98c）
- [ ] 系统通知授权（用户在系统设置中开启；当前 AppleScript 回退）

---

*本交接文档基于 2026-09-26 的代码状态编写（v2.4）。按 AGENTS.md“文档维护规则”，每次排障/升级后更新。*
