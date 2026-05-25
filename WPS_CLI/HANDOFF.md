# WPS CLI 工具集 — 交接文档 (Handoff)

**版本:** 1.0  
**日期:** 2026-05-25  
**状态:** 生产运行中，最近一次修复完成  
**交接人:** Kimi Code CLI  
**接收人:** 下一位接力开发的大模型 Agent  

---

## 1. 项目当前状态速览

```
WPS 云盘差量备份        ████████████████████░░  约 82% 完成
├── 已备份文件:         894 / ~1090 (状态文件记录)
├── 已备份大小:         ~19.4 GB
├── 历史错误:           1026 条 ERROR (已修复)
│   ├── HTTP 405:       613 条 (已修复: 加入重试 + URL 限流)
│   ├── 无下载地址:      403 条 (已修复: 扫描阶段过滤 .otl/.spt/.form)
│   ├── tmp 竞争丢失:     8 条 (已修复: file_id 路径隔离)
│   └── 分片下载失败:     1 条 (已修复: URL 刷新重试)
├── 待下载文件 (上次 dry-run): 4 个
│   ├── 五佳项目团队-政企政务办公大模型项目_政企260202-终稿.pptx
│   ├── 销售部2020工作计划汇报.spt          ← 将被过滤 (SKIP_EXTS)
│   ├── 165921_215521_Weekly_TGIF_分享会.mp4 ← 大文件，需验证
│   └── 客户满意度调查.form                 ← 将被过滤 (SKIP_EXTS)
│
OTL 专项备份            ████████████████░░░░░░  约 12% 完成
├── 远程 .otl 总数:      199 个
├── 缓存命中:            23 个
├── 需手动导出:          176 个
└── 导出指南:            wps_backup_data/_otl_files/EXPORT_GUIDE.md

共享文件目录生成        ✅ 可用（手动运行）
日历 CalDAV 代理        📋 见 calendar_Sync/HANDOFF.md
```

---

## 2. 最近完成的修复（本次交接重点）

### 2.1 修复清单

| # | 问题 | 根因 | 修复文件 | 验证状态 |
|---|------|------|---------|---------|
| 1 | HTTP 405 大量失败 | `_is_retryable()` 未将 405 视为可重试 | `engine.py` | ✅ 代码级验证通过 |
| 2 | `.spt`/`.form` 报"无下载地址" | 扫描阶段未过滤这些不可下载格式 | `engine.py` | ✅ 代码级验证通过 |
| 3 | `.otl` 进入主下载队列 | 旧版本扫描未完全过滤 .otl | `engine.py` | ✅ 已过滤 |
| 4 | 同名文件 tmp 竞争 | 同名文件映射到同一 `.tmp`，多线程冲突 | `engine.py` | ✅ 路径隔离测试通过 |
| 5 | 无下载地址文件反复重试 | `mark_failed` 不记录未备份文件，下次仍视为新文件 | `state.py` | ✅ 状态逻辑测试通过 |
| 6 | 旧版命名文件重复下载 | 旧路径无 file_id 后缀，新版会重新下载 | `engine.py` | ✅ 迁移逻辑测试通过 |

### 2.2 代码变更摘要

**`wps_backup/engine.py`** — 6 处修改：
1. 新增 `SKIP_EXTS = {".otl", ".spt", ".form"}`，扫描阶段过滤。
2. `_is_retryable()` 加入 `405`：`(405, 429, 500, 502, 503, 504)`。
3. `_download_worker` 中 `local_path` 生成加入 `file_id[:8]` 后缀。
4. 新增旧路径迁移 fallback：若旧版命名文件存在，自动 `rename` 到新路径。
5. 新增 `_get_download_url_throttled()`：线程锁 + 200ms 间隔串行化 URL 获取。
6. 下载失败时支持刷新 URL 重试：检测到 `405/chunk/expired/token/signature` 错误时重新获取 URL。

**`wps_backup/state.py`** — 2 处修改：
1. `needs_update()`：若 `error_msg` 含"无下载地址" / "不可下载"，返回 `False`（永久跳过）。
2. `mark_failed()`：为从未备份的文件也创建 `FileSnapshot` 记录，保留 `retry_count` 和 `error_msg`。

### 2.3 新增验证脚本

- `verify_fix.py` — 离线验证状态逻辑与路径隔离；在线验证 dry-run 时不可下载格式过滤。

---

## 3. 已知问题与技术债务

### 3.1 已修复但待在线验证的问题

以下修复已通过代码级单元测试，但因 **WPS token 过期 + 网络超时** 未能执行端到端验证：

```bash
# 当前 wps365-cli 状态
$ wps365-cli auth status
  delegated.status: "expired"
  delegated.remaining_seconds: 0

# 刷新请求超时
$ wps365-cli auth refresh --delegated
  context deadline exceeded (Client.Timeout exceeded while awaiting headers)
```

**待验证项：**
- [ ] Dry-run 确认 `.spt` / `.form` 不在待下载队列。
- [ ] 真实备份验证 4 个待下载文件（应减为 2 个：1 个 pptx + 1 个 mp4）。
- [ ] 确认 `五佳项目团队...pptx` 能正常下载（此前 12 次 405）。
- [ ] 确认 `.mp4` 大文件分片下载稳定。
- [ ] 确认日志中无 `No such file ... .tmp` 错误。
- [ ] 确认旧路径文件被正确迁移（无重复下载）。

**验证命令（Token 恢复后执行）：**
```bash
wps365-cli auth refresh --delegated
python3 verify_fix.py
python3 wps_backup.py run --dry-run
python3 wps_backup.py run --max 10   # 小批量真实测试
```

### 3.2 技术债务

| 债务 | 优先级 | 说明 |
|------|--------|------|
| 状态文件 JSON → SQLite | 低 | 当前 894 条约 12KB，性能足够。超过 5K-10K 条时建议迁移。 |
| 日志轮转 | 低 | `backup.log` 持续增长，无自动切割。建议增加 `RotatingFileHandler`。 |
| 测试框架 | 中 | 当前仅脚本化验证，无 pytest/unittest。新增功能时回归成本较高。 |
| 配置文件热重载 | 低 | 修改 `config.py` 需重启进程，无 SIGHUP 监听。 |
| 备份通知机制 | 低 | 失败时无 webhook/邮件/飞书通知，需手动查看日志。 |
| 大文件下载优化 | 低 | `.mp4` (>2GB) 分片下载在弱网环境下仍可能失败，可考虑降低 chunk size 或增加 URL 中途刷新。 |
| 状态文件重复路径 | 中 | 历史状态文件中有 196 条记录共享 84 个本地路径（旧版同名覆盖导致）。新版已隔离，但旧状态未清理。 |

### 3.3 风险项

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| WPS API 限流策略变化 | 405/429 可能以更激进的方式出现 | 已增加 URL 限流和 405 重试，若限流加剧可降低并发或增加间隔 |
| `wps365-cli` 不兼容升级 | Drive API 变更或 CLI 命令格式变化 | 关注 `wps365-cli` 版本更新日志，当前使用版本需确认 |
| macOS WPS Office 缓存路径变化 | `.otl` 缓存中转失效 | 缓存路径硬编码在 `otl_engine.py` 中，新版 WPS 可能改变沙盒结构 |
| 大文件下载 URL 过期 | >2GB 视频下载中途 URL 失效 | 已增加 URL 刷新重试，若仍失败需考虑单线程下载或分片后刷新 URL |

---

## 4. 下一步行动建议

### 4.1 立即行动（Token 恢复后）

1. **执行验证脚本**
   ```bash
   python3 verify_fix.py
   ```

2. **执行 Dry-run 检查过滤效果**
   ```bash
   python3 wps_backup.py run --dry-run
   # 预期：待下载 = 2（pptx + mp4），无 .spt/.form
   ```

3. **小批量真实备份测试**
   ```bash
   python3 wps_backup.py run --max 5
   # 检查日志中无 ERROR，确认旧路径迁移成功
   ```

4. **确认 .mp4 大文件下载**
   ```bash
   # 单独测试大文件
   python3 wps_backup.py run
   # 观察 165921_215521_Weekly_TGIF_分享会.mp4 的下载进度和日志
   ```

### 4.2 短期优化（1-2 周）

1. **日志轮转** — 在 `logger.py` 中加入 `RotatingFileHandler(maxBytes=10MB, backupCount=5)`。
2. **状态文件清理** — 编写脚本检测并合并/清理历史重复路径记录。
3. **.mp4 下载稳定性** — 若大文件仍失败，考虑在 `download_with_resume` 中每下载 N 个 chunk 后主动刷新 URL。
4. **测试覆盖** — 为 `engine.py` 核心函数增加 pytest 单元测试（网络无关部分）。

### 4.3 中期规划（1-2 月）

1. **Web 看板** — 轻量级 HTTP 服务读取 `backup_state.json`，展示备份进度、失败文件清单、磁盘使用。
2. **通知集成** — 备份失败时调用飞书 webhook 发送告警。
3. **状态迁移 SQLite** — 当文件数超过 2000 时评估 JSON 性能瓶颈。

---

## 5. 代码阅读指南（给接手 Agent）

### 5.1 从哪里开始读

**如果你要理解备份流程：**
1. `wps_backup.py` — 主入口，看 `cmd_run()` 调用链。
2. `wps_backup/engine.py` — 核心引擎，从 `BackupEngine.run()` 开始。
3. `wps_backup/state.py` — 差量逻辑，重点看 `needs_update()` 和 `mark_backed_up()`。

**如果你要修复下载问题：**
1. `wps_backup/engine.py::download_with_resume()` — 断点续传逻辑。
2. `wps_backup/engine.py::_download_worker()` — 多线程 worker 和错误处理。
3. `wps_backup/engine.py::_is_retryable()` — 重试策略判定。

**如果你要处理 OTL 文件：**
1. `wps_backup/otl_engine.py` — 完整阅读，逻辑较独立。

### 5.2 关键调试技巧

```bash
# 查看最近 50 行日志
python3 wps_backup.py log -n 50

# 手动查看状态文件（JSON 格式，易读）
cat wps_backup_state/backup_state.json | python3 -m json.tool | less

# 测试单个文件下载（修改 engine.py 在 run() 中限制 max_files）
python3 wps_backup.py run --max 1

# 检查 .tmp 残留（应无）
find wps_backup_data -name "*.tmp"

# 检查旧路径迁移（旧格式无 file_id 后缀）
find wps_backup_data -not -name "*_*.*" -type f | head
```

### 5.3 修改时的注意事项

1. **不要修改 `SKIP_EXTS` 中的 `.ksheet` / `.pof`** — 这些格式已成功备份过，Drive API 支持下载。
2. **线程安全** — `state.py` 和 `BackupResult` 的修改必须使用锁（`_result_lock` / `_lock`）。
3. **原子写入** — 任何文件持久化都应先写 `.tmp` 再 `replace()`。
4. **TDD 风格** — 新增功能先在 `verify_fix.py` 或独立脚本中写验证逻辑。
5. **路径处理** — 统一使用 `pathlib.Path`，禁止字符串拼接路径。

---

## 6. 环境信息

| 项 | 值 |
|---|---|
| 运行平台 | macOS (Apple Silicon arm64) |
| Python 版本 | 3.13–3.14 |
| wps365-cli 路径 | 系统 PATH 中可用 |
| 项目根目录 | `/Users/whoami2028/Workshop/GITREPO/WPS_CLI` |
| 备份数据目录 | `wps_backup_data/` |
| 状态/日志目录 | `wps_backup_state/` |
| 定时任务 | `com.wps.backup.plist` (launchd) |
| Git 状态 | 未提交（修改在 working tree 中） |

---

## 7. 交接检查清单

- [x] ADP.md 已撰写（架构决策文档）
- [x] HANDOFF.md 已撰写（本文档）
- [x] 代码修复已完成并本地验证
- [x] `verify_fix.py` 验证脚本已提供
- [ ] 在线端到端验证待执行（Blocked by token 过期）
- [ ] 建议执行 `git add -A && git commit` 保存当前修改

---

*本交接文档基于 2026-05-25 的代码状态编写。下次重大变更后请更新版本号。*
