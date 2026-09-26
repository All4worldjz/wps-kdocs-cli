# WPS Backup.app — 菜单栏备份应用

WPS 云盘备份（`wps_backup` Python 引擎）的 macOS 外壳：定时运行、状态一览、异常提醒、一键备份/取消、重新登录。
正常情况下**零操作**；唯一需要人的是 wps365-cli 登录过期（当前有效至 2027-09-26）时点“重新登录 WPS”。

## 构建与安装

```bash
cd WPS_CLI/macos
./build.sh --install      # 测试 → 编译 → 组装 → 签名 → 安装到 ~/Applications 并启动
```

- 不依赖 Xcode 工程/SwiftPM：`build.sh` 直接用 `swiftc`；Xcode 许可未接受时自动回退到 Command Line Tools。
- 签名：有 “Apple Development” 证书则使用，否则 ad-hoc（`-`）。环境变量 `CODESIGN_IDENTITY` 可指定。
- Core 单元测试在构建时运行（无 XCTest 的工具链下用 `Tests/Shim` 兼容层）；装好 Xcode 许可后也可 `swift test`。

## 组成

| 组件 | 说明 |
|---|---|
| `WPSBackup`（菜单栏 App） | 读取引擎状态文件 + 每 60s 调 `wps_backup.py status --json`；图标 ✓/!/✗ 三态 |
| `wps-backup-runner` | 由定时任务执行：读取设置 → 设置 PATH 等环境 → `exec python3 wps_backup.py scheduled` |
| `~/Library/LaunchAgents/cc.all4world.wpsbackup.scheduler.plist` | 每小时整点触发 runner；引擎判断是否到点（默认 20:00）、当天是否已成功、失败重试（每天最多 3 次） |
| `~/Library/LaunchAgents/cc.all4world.wpsbackup.login.plist` | 登录时打开菜单栏 App（异常通知由 App 发出） |
| `~/Library/Application Support/WPS Backup/settings.json` | 设置（时间、并发、docx 导出、缓存扫描、Python 路径） |

App 每次启动都会幂等地安装/修复定时任务（内容未变且已加载时不做任何事），并迁移旧版 `com.wps.backup`（移入 `wps_backup_state/legacy_com.wps.backup.plist`）。

## 引擎契约（`wps_backup_state/`）

| 文件 | 写入者 | 用途 |
|---|---|---|
| `last_run.json` | 每次 `run`/`scheduled` 运行结束 | 退出码 0 成功 / 1 有失败 / 75 已在运行 / 124 超时 / 130 取消；计数与前 20 条错误 |
| `runs.jsonl` | 同上 | 最近 50 次运行，调度判定用 |
| `progress.json` | 运行中 | 阶段、进度、PID（取消 = 向该 PID 发 SIGTERM） |
| `scheduler_heartbeat.json` | 每次定时触发 | App 判断定时任务是否在跑（>3h 无心跳告警） |
| `force_run` | App “立即备份” | `scheduled` 消费该标记后立即运行 |
| `agent_runner.log` | runner | 仅 runner 自身错误（引擎日志在 `backup.log`） |

## 排障

```bash
"$HOME/Applications/WPS Backup.app/Contents/MacOS/WPSBackup" --diagnose     # App 所见的全部状态，error 时退出码 1
"$HOME/Applications/WPS Backup.app/Contents/MacOS/WPSBackup" --test-notify  # 通知链路自检
launchctl print gui/$(id -u)/cc.all4world.wpsbackup.scheduler | grep -E "state|last exit"
```

- **通知**：ad-hoc 签名的 App 系统通知授权为“拒绝”时（`--test-notify` 显示 `authorizationStatus=1`），自动改用 AppleScript 通知（显示为“脚本编辑器”）。可在“系统设置 → 通知 → WPS Backup”手动开启。
- **不要**再运行 `python3 wps_backup.py install`：会产生第二个计划（命令现已拒绝执行）。

## 为什么不用 SMAppService（2026-09-26 实测）

`SMAppService.agent` 为 ad-hoc 签名的 App 注册时，launchd 给 agent 固定 cdhash 约束（LWCR）。App 重新构建后约束变为空并标记
`needs LWCR update`，不会自愈，注销/重新注册也不可靠，agent 以 `OS_REASON_CODESIGNING` / `spawn failed` 被拒绝启动。
经典 `~/Library/LaunchAgents` plist 没有 LWCR，重建不受影响。若将来改用 Apple Development / Developer ID（有 Team ID）签名，
可重新评估 SMAppService（约束基于 Team ID + 签名标识，跨构建稳定）。

## 文档维护

修改 App、调度或排障后，按 `AGENTS.md`“文档维护规则”同步更新：本文件、`docs/MACOS_APP_PLAN.md` §9、`HANDOFF.md`（定时任务行与事故记录）、`AGENTS.md` 故障排查速查表。

*最后更新: 2026-09-26（v1.0：经典 LaunchAgent 调度、AppleScript 通知回退）*
