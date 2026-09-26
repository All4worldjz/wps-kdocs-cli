# WPS 备份 — 巡检结论与优化计划

**日期:** 2026-09-26  **范围:** `wps_backup`（主引擎 + OTL 专项）、launchd 定时任务

## 1. 巡检结论

| 项 | 状态 | 证据 |
|---|---|---|
| 备份数据/状态 | ✅ 健康 | `backup_state.json` 1038 文件 / 26.8 GB / 0 错误；OTL 197 条记录，194 有 Markdown、192 有 docx |
| 单元测试 | ✅ 50/50（巡检前）→ 76/76（修复后，另含线上契约测试） | `python3 -m unittest discover -s tests` |
| **定时任务** | ❌ **自 2026-07-29 起无任何自动运行** | `launchctl print gui/501/com.wps.backup` → 服务未加载；最后两次 launchd 运行报 `No such file or directory: 'wps365-cli'` |
| 9 月的成功备份 | 全部为手动运行 | `backup.log` |

### 根因（定时任务静默失效，共三层）

1. **PATH**：launchd 默认 PATH 为 `/usr/bin:/bin:/usr/sbin:/sbin`，不含 `~/.local/bin`；`config.CLI_BIN` 是裸命令名 → 找不到 wps365-cli。
2. **退出码**：认证/扫描失败只写入 `result.errors`（`failed=0`），`cmd_run` 仍返回 0 → launchd 视为成功，无人察觉。
3. **TCC 挂起**（本次复现）：OTL Phase 3 直接 `iterdir()` `~/Library/Containers/com.kingsoft.wpsoffice.mac/...`，该目录受 macOS “App 数据”隐私保护；在 launchd/无终端环境下 `opendir` 阻塞等待授权弹窗，**进程永久挂起**。即使修好 PATH，每日任务也会卡死在这里。
4. 另：服务未加载（`print-disabled` 无禁用覆盖，属未 bootstrap；原因不明，可能是被 bootout 后未重载）。

## 2. 本次已完成的修复（TDD，全部有测试）

| 修复 | 文件 | 测试 |
|---|---|---|
| CLI 绝对路径解析：`WPS365_CLI_BIN`/`KDOCS_CLI_BIN` 环境变量 > `~/.local/bin` > PATH（刻意避开 `/usr/local/bin` 下的旧版 v0.1.0） | `config.py` | `test_launchd_env.py` |
| plist 模板新增 `EnvironmentVariables`（PATH 以 `~/.local/bin` 开头、HOME） | `scheduler.py` | 同上 |
| `_cli` 封装捕获 `FileNotFoundError`，给出清晰错误而非崩溃/“无 token” | `engine.py` `otl_engine.py` `airpage_engine.py` | 同上 |
| `run` 在 `result.errors` 非空时返回非零退出码 | `wps_backup.py` | — |
| **扫描完整性**：分页失败显式抛错；任一盘扫描失败则跳过 `prune_stale`（原先“非空但不完整”的扫描会误删其他盘增量记录）；OTL 扫描不再回退硬编码默认盘 | `engine.py` `otl_engine.py` | `test_scan_completeness.py` |
| OTL 子目录列表分页（原先目录项 >200 时后续子文件夹不递归） | `otl_engine.py` | 同上 |
| **TCC 防挂起**：缓存目录先在带 15s 超时的子进程中探测（超时 kill 且不再 wait），失败则跳过缓存阶段；`WPS_OTL_CACHE_SCAN=0` 可关闭。已在 `env -i` 最小环境下对真实目录实测：15s 返回 False，进程正常退出 | `otl_engine.py` `config.py` | `test_run_hygiene.py` |
| kdocs 企业账号探测：`auth status` 已认证但业务接口返回 403001 时判为不可用（原先每个 docx/pdf/xlsx 下载后白跑 3 次 read-file；`status` 显示误导性的 ✅） | `kdocs_engine.py` | 同上 |
| OTL 永久失败记忆：`.otl.link` 快捷方式、空文档记录失败 + mtime，mtime 不变不再重试（每次运行省 ~23 次调用）；临时失败照常重试 | `otl_engine.py` | 同上 |
| 单实例锁（`wps_backup_state/.run.lock`，`flock`）：`run` / `backup-otl` 重叠时后者以退出码 75 跳过并记录持锁 PID，避免两进程整体重写状态 JSON | `lock.py` `wps_backup.py` | 同上 |

## 3. 部署（已完成，2026-09-26）

~~手动重装 com.wps.backup~~ 已被 **WPS Backup.app** 取代：App 安装经典 LaunchAgent `cc.all4world.wpsbackup.scheduler`（每小时触发 `wps_backup.py scheduled`），并迁移停用旧 `com.wps.backup`（plist 移至 `wps_backup_state/legacy_com.wps.backup.plist`）。卡住的 dry-run（PID 36703）已自行结束。部署与验收见 `macos/README.md`、`docs/MACOS_APP_PLAN.md` §9。

## 4. 后续优化（按优先级）

| # | 优化 | 价值 | 说明 |
|---|---|---|---|
| ~~P1~~ ✅ | **失败通知**（v4.2 App：异常才通知，未授权时 AppleScript 回退） | 防止再次静默失效 | 退出码非零时 `osascript -e 'display notification'` 或飞书 webhook；另加“距上次成功 >36h”检查（可放进 `status`） |
| ~~P1~~ ✅ | **全局看门狗**（v4.2：`WPS_BACKUP_RUN_TIMEOUT`，124） | 防任何未知阻塞 | `run` 设整体超时（如 4h，`signal.alarm`），超时记日志并以非零退出，锁随进程释放 |
| ~~P1~~ ✅ | **提交代码**（959e98c 已推送） | 生产依赖的 `airpage_engine.py`、`tests/` 仍未纳入 git | HANDOFF 声称已推送，实际未跟踪 |
| ~~P1~~ ✅ | **下载绕过本地代理**（v5 `wps_http`：直连优先、代理回退） | 修复 docx 随机缺失 | 本机代理 127.0.0.1:3213 对金山云 ks3 域名 SSL 握手超时，直连 0.16s 成功；对 `*.ksyun.com`/`*.wps.cn` 等直连或失败后直连重试 |
| ~~P1~~ ✅ | **OTL docx 补导**（v5 产物级增量，`E6pC1h5m`/`Nn1SvNVS` 已补齐） | 2 个文档缺 docx | docx 失败后仅 mtime 变化才重试；`docx_path` 为空时下次运行补导 |
| ~~P2~~ ✅ | **单次目录树遍历**（v5：OTL 阶段 75 s → 0 s） | 扫描耗时约减半 | 主引擎与 OTL 各自遍历一次；OTL 每目录还发 2 次请求（带过滤 + 列子目录）。主引擎扫描时顺带收集 `.otl`，传给 OTL 引擎 |
| P2 | 主引擎扫描保留部分结果 | 韧性 | 目前某盘任一目录失败即整盘跳过（例：自动备份 815 个文件当日全部不备份，但会非零退出）；可仿照 OTL 侧的 `ScanIncompleteError(partial)` 保留已扫描部分 |
| ~~P2~~ ✅ | 测试日志隔离（v4.2：unittest 下默认临时目录） | 日志监控可信 | 测试写入生产 `backup.log`（如 `a.docx — HTTP 500`、`d2: scan failed`）；测试运行时将 `WPS_BACKUP_STATE_DIR` 指向临时目录 |
| P3 | **事件驱动增量**（`kso_file_update` + 长连接订阅） | 免定时全量扫描 | 需在开放平台开发者后台为应用订阅事件；见 `docs/OTL_BACKUP_DESIGN_V5.md` §3 |
| P2 | OTL 缓存复制与内容状态解耦 | 正确性 | 内容备份临时失败后，缓存复制的 `mark_backed_up` 会覆盖失败记录，下次不再重试内容 |
| P3 | 状态写入批量化 | 性能 | `mark_backed_up` 每个文件整体重写 ~700KB JSON；改为每 N 个或定时落盘 |
| P3 | `_content_backup/` 替代后端 | 覆盖率 | kdocs 对企业账号失效，docx/pdf/xlsx 无 Markdown 层；评估 wps365-cli 是否有等价接口 |
| P3 | 大文件跳过重算 hash | 性能 | 本地同尺寸文件每次 `compute_hash`（26GB 规模下耗时） |

## 5. 同机其他定时任务（未改动，仅记录）

- `crontab`: 每小时 `2ndBrain/scripts/gitsync.sh`
- `~/Library/LaunchAgents/com.user.sync.2ndbrain.plist`、`com.2ndbrain.sync-feishu-local.plist` 存在但 **当前同样未加载**（`launchctl list` 无记录），建议一并检查。

*最后更新: 2026-09-26（部署改由 WPS Backup.app 完成；P1 通知/看门狗、P2 测试隔离已完成）*
