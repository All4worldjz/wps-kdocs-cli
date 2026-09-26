# WPS Backup.app — macOS GUI 应用开发计划

**日期:** 2026-09-26  **状态:** ✅ 已实现并投产（2026-09-26），见 `macos/README.md`；以下为原计划，§9 为实施记录

> 命名说明：kdocs-cli 对本企业账号已失效（403001），实际在跑的是 **wps365-cli（Drive 下载）+ airpage（OTL → Markdown/docx）**。本 App 覆盖整个 `wps_backup` 流水线，不围绕 kdocs-cli 设计。

## 1. 目标

| 目标 | 衡量标准 |
|---|---|
| 最少人工干预 | 正常情况下用户**零操作**；唯一需要人的场景是 wps365-cli 重新授权（refresh token 当前有效至 2027-09-26）和首次安装批准 |
| 失败不再静默 | 本次巡检发现任务静默失效 2 个月——任何失败/过期/未批准都必须在菜单栏变红并通知 |
| 保留已验证的引擎 | Python 引擎（77 个测试，已在 launchd 下实测通过）不重写 |

## 2. 架构决策

**薄 Swift 外壳 + 现有 Python 引擎**（推荐）

```
WPS Backup.app (SwiftUI, 非沙盒, macOS 13+)
├── 菜单栏 UI (MenuBarExtra)        ← 只读状态文件 + 发起操作
├── Settings 窗口
├── Contents/Library/LaunchAgents/com.wps.backup.agent.plist   ← SMAppService.agent 注册
└── Contents/MacOS/wps-backup-runner  ← 小型 Swift helper：设置 env，exec python3 wps_backup.py run
            │
            ▼
   wps_backup/ Python 引擎（现有）──► wps365-cli（外部，~/.local/bin）
            │
            ▼
   wps_backup_state/  last_run.json · progress.json · backup_state.json · backup.log
```

- **GUI 与定时运行解耦**：定时运行由 launchd 启动，GUI 可以不开；GUI 永远通过状态文件读取结果，绝不依赖 stdout。
- **“立即备份”= `launchctl kickstart` 同一个 agent**：环境、锁完全一致；重复点击由运行锁返回 75，无害。
- 被否决的方案：
  - Swift 重写引擎：丢掉唯一经过生产验证的部分，成本高。
  - py2app + rumps/PyObjC：开发快，但 SMAppService、通知、签名都更别扭，UI 质量差。

## 3. 需验证的 macOS 机制（Phase 0 Spike，先于一切 UI）

| 问题 | 为什么重要 | 验证方式 |
|---|---|---|
| `SMAppService.agent.register()` 是否返回 `.requiresApproval` | 用户可在“登录项 → 允许在后台”关闭；**这很可能就是 `com.wps.backup` 此前消失的原因** | 注册后读 `status`；手动关闭开关观察变化 |
| TCC 弹窗归属 App bundle 还是 `python3.14` | 决定“完全磁盘访问权限”加给谁 | helper 内调用 `cache_dir_accessible`，看弹窗名称 |
| FDA 授权能否跨重新构建保留 | 当前 **0 个签名身份**，ad-hoc 签名每次构建 cdhash 变化，授权大概率重置 | 在 Xcode 登录 Apple ID 获取免费 “Apple Development” 证书后对比 |

**兜底**：若 TCC 不顺，App 默认 `WPS_OTL_CACHE_SCAN=0`（airpage 已覆盖 Markdown + docx，最近一次真实运行缓存复制 0 个），缓存扫描做成“需完全磁盘访问权限”的可选开关。

## 4. 引擎侧改造（Python，TDD，App 的前置条件）

| 项 | 内容 |
|---|---|
| `status --json` | 上次成功时间、计数、错误数、wps365-cli 路径/版本、认证状态（含 `refresh_token_expires_at`、airpage scope 是否在） |
| `last_run.json` | 每次 `run` 结束原子写入（**含被锁跳过的运行**）：开始/结束时间、退出码 0/1/75、各阶段计数、前 N 条错误。GUI 以此为准，不解析中文日志 |
| `progress.json` | 运行中周期更新：阶段（scan/download/otl）、done/total、当前文件 |
| SIGTERM 处理 | `cmd_run` 目前没有（只有 daemon 模式有）；GUI 取消需停止线程池、落盘状态、释放锁 |
| 全局看门狗 | 整体超时（如 4h）后非零退出，GUI 不会永远显示“运行中”（OPTIMIZATION_PLAN P1） |
| 测试日志隔离 | 测试不得写生产 `backup.log`，否则 GUI 会展示假错误 `a.docx HTTP 500`（OPTIMIZATION_PLAN P2） |

## 5. App 功能

**菜单栏图标（三态）**
- 🟢 上次运行成功且 <36h
- 🟡 >36h 未成功 / refresh token 30 天内过期 / 有永久失败项新增
- 🔴 上次退出码 ≠ 0 / agent 需批准 / wps365-cli 缺失或未认证 / 运行超时

**Popover**：上次/下次运行时间、新增·跳过·失败计数、运行中进度条、“立即备份”“取消”、打开备份目录、最近错误（可展开）、查看日志。

**通知（仅异常，不通知成功）**：失败、超过 36h 未成功、token 即将过期、需在系统设置中批准后台运行。

**重新授权流程（唯一需要人的步骤）**：点击“重新登录” → 后台运行 `wps365-cli auth login --device`（CLI 自动打开浏览器，无终端也可用）→ 轮询 `auth status` 直到 delegated 为 valid 且含 `kso.airpage.readwrite` → 自动触发一次备份。

**Settings**：每日运行时间、备份目录（`WPS_BACKUP_DIR`）、并发数、docx 导出开关、缓存扫描开关（附 FDA 引导）、开机登录、wps365-cli 路径与版本（升级后提示运行契约测试——`drive files`→`drive file` 改名事故的教训）。

## 6. 约束

- **非沙盒**：需执行外部二进制、写任意目录、可能需要 FDA。
- **迁移**：注册新 agent 前必须 `bootout` 并删除 `~/Library/LaunchAgents/com.wps.backup.plist`，否则两个计划同时触发、每晚一个以 75 退出。
- **数据原地保留**：`wps_backup_data/`、`wps_backup_state/` 不动；`backup_state.json` 为原子替换写入，GUI 可安全读取。
- **wps365-cli 保持外部依赖**：用 `resolve_cli_bin` 探测，缺失时引导安装，不打包进 App。
- **错过的定时**：`StartCalendarInterval` 在睡眠唤醒后补跑一次，无需自建补偿逻辑。

## 7. 分阶段交付与验收

| 阶段 | 交付 | 验收 |
|---|---|---|
| 0 Spike | 最小 App + SMAppService agent + helper 调用 TCC 探测 | §3 三个问题有实测答案并记录 |
| 1 引擎契约 | §4 全部，含测试 | `status --json` / `last_run.json` 在 launchd 运行后正确生成；全部单测通过 |
| 2 只读状态 UI | 菜单栏三态 + popover | 用伪造的 `last_run.json`（成功/失败/过期/75）逐一驱动出正确颜色 |
| 3 调度 + 迁移 | SMAppService 注册、旧 plist 迁移、立即备份/取消 | 通过 agent 触发的运行在 `backup.log` 产生新的 开始/完成 对 + `last_run.json` exit 0（**不只看退出码**）；旧 plist 已移除，`launchctl list` 只有一个任务 |
| 4 通知 + 重新授权 | 异常通知、device 登录流程 | 模拟 token 过期 → 红色 + 通知 → 重新登录后自动恢复 |
| 5 Settings | 设置窗口，写入 agent 环境变量 | 修改时间/目录后下一次运行生效 |
| 6 打包 | Release 构建、签名、安装说明 | 全新用户账户下安装 → 批准 → 次日自动运行成功 |

**测试**：Python 引擎沿用 unittest；Swift 侧 XCTest 覆盖 `last_run.json`/`status --json` 解析与状态三态判定；端到端用假 `wps365-cli`（`WPS365_CLI_BIN` 指向脚本）驱动成功/失败/过期场景。

## 8. 待确认决策（已给默认值，不阻塞）

| 决策 | 默认 | 另一选项的代价 |
|---|---|---|
| 仅自用 vs 分发给他人 | **自用**：本机构建，Apple Development 签名，不公证 | 分发需 Developer ID（付费）+ 公证 + Hardened Runtime，并需打包 Python |
| Python 运行时 | **依赖 Homebrew `python@3.14`**（引擎纯标准库） | 打包 python-build-standalone：App 增大约 40MB，但免依赖 |
| 最低系统 | macOS 13（MenuBarExtra / SMAppService） | — |

## 9. 实施记录（2026-09-26）

| 项 | 结果 |
|---|---|
| 引擎契约 | `wps_backup/app_contract.py`：last_run / runs.jsonl / progress / 心跳 / force_run、SIGTERM 取消（130）、看门狗（124）、`scheduled` 调度判定、`status --json` 健康度；测试日志隔离 |
| App | `macos/`：菜单栏三态、立即备份/取消、设置窗口、重新登录（`auth login --device`）、异常通知、`--diagnose` / `--test-notify` |
| 构建 | `macos/build.sh`：swiftc 直编（Xcode 许可未接受 → Command Line Tools），Core 测试 18 个 |
| **偏离计划：调度机制** | Spike 发现 ad-hoc 签名下 SMAppService agent 在重建后被 launchd 以 `OS_REASON_CODESIGNING` 拒绝（LWCR 为空且 `needs LWCR update`，重新注册不可靠）→ 改用经典 `~/Library/LaunchAgents` plist（无 LWCR）；登录项同样改为经典 plist |
| **偏离计划：TCC** | 缓存扫描默认关闭（设置中可开启，需完全磁盘访问权限） |
| **通知** | 本机系统通知授权为“拒绝”，且 `add()` 不报错会静默丢弃 → 先检查授权，未授权时改用 AppleScript 通知 |
| 验收 | 真实 runner 代码变更（新 CDHash）→ `build.sh --install` → 无人工步骤 kickstart → `last_run.json` exit 0、launchd last exit 0；取消 → 130；`--diagnose` health ok |
