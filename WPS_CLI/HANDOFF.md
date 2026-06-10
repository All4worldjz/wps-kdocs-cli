# WPS CLI 工具集 — 交接文档 (Handoff)

**版本:** 2.0
**日期:** 2026-06-09
**状态:** 生产运行中，kdocs-cli 集成升级完成
**交接人:** Kimi Code CLI
**接收人:** 下一位接力开发的大模型 Agent

---

## 1. 项目当前状态速览

```
WPS 云盘差量备份        ████████████████████░░  约 99% 完成
├── 已备份文件:         906 / ~918 (状态文件记录)
├── 已备份大小:         ~25.9 GB
├── 历史错误:           已大幅收敛
│   ├── HTTP 405:       已修复 (加入重试 + URL 限流)
│   ├── 无下载地址:      已修复 (扫描阶段过滤 .otl/.spt/.form)
│   ├── tmp 竞争丢失:     已修复 (file_id 路径隔离)
│   └── 分片下载失败:     已修复 (URL 刷新重试)
├── 待下载文件 (上次 dry-run): 12 个 (新增 docx/pdf/pptx)
│
OTL 专项备份            ████████████████████░░  约 84% 完成 (内容层)
├── 远程 .otl 总数:      201 个
├── kdocs-cli 内容备份:   169 个 ✅ (Markdown 格式)
├── 内容备份跳过:         26 个 (已是最新)
├── 内容备份失败:          6 个 (.otl.link 快捷方式)
├── 缓存命中:             23 个 (实体 .otl 缓存)
└── 导出指南:             wps_backup_data/_otl_files/EXPORT_GUIDE.md

共享文件目录生成        ✅ 可用（手动运行）
日历 CalDAV 代理        📋 见 calendar_Sync/HANDOFF.md
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
| 语法检查 (8 个文件) | ✅ 全部通过 |
| kdocs-cli 认证 | ✅ v2.5.8 已认证 |
| OTL 内容备份 (169 文件 live) | ✅ 成功，256.7s |
| 主引擎 live 备份 (2 文件) | ✅ 成功，36.7s |
| `verify_fix.py` 回归测试 | ✅ 全部验证通过 |
| `wps_backup.py status` | ✅ 显示完整 kdocs 状态 |

---

## 3. 已知问题与技术债务

### 3.1 当前状态

```bash
# wps365-cli 状态
$ wps365-cli auth status
  delegated.status: "expired" (需定期刷新)

# kdocs-cli 状态
$ kdocs-cli auth status
  authenticated: true
  token: 有效期约 8760 小时 (~1 年)
```

**注意：** 两个 CLI 的 Token **不互通**，需分别维护认证。

### 3.2 技术债务

| 债务 | 优先级 | 说明 |
|------|--------|------|
| kdocs-cli CDN 不可解析 | 中 | `wpsai.wpscdn.cn` 在当前网络 DNS 无法解析，需用中国 DNS (114.114.114.114) 获取 IP 后 `--insecure` 下载。`kdocs-cli upgrade` 命令会失败。 |
| 状态文件 JSON → SQLite | 低 | 当前 906 条约 600KB，性能足够。超过 5K-10K 条时建议迁移。 |
| 日志轮转 | 低 | `backup.log` 持续增长，无自动切割。建议增加 `RotatingFileHandler`。 |
| 测试框架 | 中 | 当前仅脚本化验证，无 pytest/unittest。新增功能时回归成本较高。 |
| 备份通知机制 | 低 | 失败时无 webhook/邮件/飞书通知，需手动查看日志。 |
| .otl.link 文件处理 | 低 | 6 个 `.otl.link` 快捷方式无法读取内容，当前标记为失败。可考虑改为"跳过"而非"失败"。 |

### 3.3 风险项

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| kdocs-cli CDN 持续不可达 | 无法自动升级 kdocs-cli | 已记录手动升级流程（见 `docs/kdocs-cli-setup.md`） |
| kdocs-cli Token 过期 | OTL 内容备份和内容备份层失效 | Token 有效期约 1 年，过期后执行 `kdocs-cli auth login` |
| wps365-cli 与 kdocs-cli 双认证维护 | 操作复杂度增加 | `status` 命令同时显示两者状态，便于监控 |
| WPS API 限流策略变化 | 405/429 可能以更激进的方式出现 | 已增加 URL 限流和 405 重试 |

---

## 4. 下一步行动建议

### 4.1 立即行动

1. **确认双 CLI 认证状态**
   ```bash
   wps365-cli auth status
   kdocs-cli auth status
   ```

2. **执行完整备份验证**
   ```bash
   python3 wps_backup.py run --dry-run
   python3 wps_backup.py backup-otl --dry-run
   ```

3. **定期执行完整备份**
   ```bash
   python3 wps_backup.py run
   ```

### 4.2 短期优化（1-2 周）

1. **kdocs-cli 自动升级检测** — 在 `status` 中增加版本检查（绕过 CDN DNS 问题）。
2. **.otl.link 处理优化** — 将 `.otl.link` 从"失败"改为"跳过"，减少日志噪音。
3. **内容备份增量优化** — 当前每次都会调用 `read-file`，可考虑在 `state.py` 中增加 `content_mtime` 字段实现内容层增量。

### 4.3 中期规划（1-2 月）

1. **全文搜索索引** — 基于 `_otl_content/` 和 `_content_backup/` 的 Markdown 文件构建本地搜索索引（如 `ripgrep` 或轻量级 SQLite FTS）。
2. **Web 看板增强** — 展示内容备份覆盖率、OTL 备份统计、kdocs-cli 健康状态。
3. **内容备份格式扩展** — 评估是否支持 `.pptx`（当前 kdocs-cli `read-file` 不支持）。

---

## 5. 代码阅读指南（给接手 Agent）

### 5.1 新增模块速览

**`wps_backup/kdocs_engine.py`** — kdocs-cli 封装：
- `read_file_content()` — 调用 `kdocs-cli drive read-file`，返回 Markdown
- `backup_file_content()` — 将文档内容备份为 `.md`（带 YAML frontmatter）
- `backup_otl_content()` — OTL 专用内容备份
- `search_files()` — 文件名/全文搜索
- `check_kdocs_cli_available()` — 认证状态检查

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
```

### 5.3 修改时的注意事项

1. **双 CLI 依赖** — 修改备份逻辑时需考虑 `wps365-cli` 和 `kdocs-cli` 的独立认证状态。
2. **内容备份是"锦上添花"** — 主备份流程（实体文件下载）不应依赖 kdocs-cli 可用。`engine.py` 中内容备份失败不影响主流程。
3. **YAML frontmatter 格式** — 内容备份的 Markdown 文件包含固定 frontmatter，修改格式可能影响下游消费。
4. **kdocs-cli 升级限制** — 不要依赖 `kdocs-cli upgrade` 自动工作，当前网络环境会失败。

---

## 6. 环境信息

| 项 | 值 |
|---|---|
| 运行平台 | macOS (Apple Silicon arm64) |
| Python 版本 | 3.13–3.14 |
| wps365-cli 路径 | `/usr/local/bin/wps365-cli` (v0.1.0) |
| kdocs-cli 路径 | `~/.local/bin/kdocs-cli` (v2.5.8) |
| 项目根目录 | `/Users/whoami2028/Workshop/GITREPO/WPS_CLI` |
| 备份数据目录 | `wps_backup_data/` |
| 状态/日志目录 | `wps_backup_state/` |
| 定时任务 | `com.wps.backup.plist` (launchd) |
| Git 状态 | 未提交（修改在 working tree 中） |

---

## 7. 相关文档

| 文档 | 说明 |
|------|------|
| `AGENTS.md` | 项目背景、架构、开发规范 |
| `ADP.md` | 架构决策记录 |
| `docs/kdocs-cli-setup.md` | **WPS CLI 与 kdocs-cli 安装配置与使用指南 v2.0**（本次新增） |
| `calendar_Sync/HANDOFF.md` | CalDAV 代理子项目交接 |

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
- [x] OTL 内容备份验证通过 (169/201)
- [x] 主引擎内容备份层验证通过
- [x] `verify_fix.py` 回归测试通过
- [x] HANDOFF.md 已更新（本文档 v2.0）
- [x] `docs/kdocs-cli-setup.md` 已撰写（v2.0，含 wps365-cli + kdocs-cli 完整指南）
- [ ] 建议执行 `git add -A && git commit` 保存当前修改

---

*本交接文档基于 2026-06-09 的代码状态编写。下次重大变更后请更新版本号。*
