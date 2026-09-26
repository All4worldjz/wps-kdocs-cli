# OTL 高效备份设计 v5（2026-09-26）

**状态：✅ 已实现并投产（2026-09-26 18:35），验收结果见 §5**

**目标：** 高效、高保真地备份全部智能文档（.otl）——日常增量运行尽量少的 API 调用与耗时，全量重建可并行，产物同时覆盖“可读文本 + 图片 + Office 格式”。

## 1. 调研依据（全部实测）

| 来源 | 发现 |
|---|---|
| WPS 开放平台文档树（`/docs/api/collections/wps365`，1543 个页面） | 智能文档有 **“创建 ap 转 markdown 任务”**、**“创建 ap 转 markdown_zip 任务”**、转 DOCX、转 PDF、获取导出任务结果；云文档有 **文件更新事件 `kso_file_update`**、文件事件订阅、**事件长连接（WebSocket）订阅**、批量下载、文件版本列表 |
| 开放平台接口页（转 DOCX / 转 PDF / 任务结果） | 限频策略均为“无”；docx `version` 形如 `{文档版本}_A4_1`（A4）或 `_autofit1_1`；导出结果按版本键缓存（`tmp/exportfiles/{id}/{format}/{version}`）；PDF 的 `group_id/parent_id` 已标注废弃，改用字符串 `drive_id` |
| 直连实测 `POST /v7/airpage/{id}/export_to_markdown_zip` | ✅ 可用（CLI 本地 spec 未收录，需直接 HTTP）。返回 zip：`export.md` + 全部图片；95 MB/49 图的文档 **10.4 s** 完成；空文档返回 2 字节 |
| 官方 markdown vs 现有块树转换 | 现有转换丢失标题层级、加粗、列表、超链接与图片；官方保留 `##`、`**`、列表、`[文本](url "title")`，图片以 `image_id=XXXX` 引用、zip 内文件名即 `XXXX.ext` |
| `.otl.link` 快捷方式 | `airpage get` 返回 403 `unable to read user permission` → 维持永久失败 |
| CLI 请求形态（`--dry-run`） | 仅 `Authorization: Bearer <delegated token>`，可用 `wps365-cli auth token` 的 token 直接调用 openapi.wps.cn |
| 本机网络 | 系统/环境代理 `127.0.0.1:3213` 对金山云 ks3 下载 SSL 握手超时；直连 0.16 s 成功 |
| 基线（2026-09-26 15:18 定时运行，无变化） | 总 118 s = 主引擎扫描 42 s + **OTL 二次扫描 75 s**（每目录 2 次列表请求）+ OTL 内容 0 个 |

## 2. 设计

```
主引擎扫描（一次遍历全部盘）
  ├─ 可下载文件 → 实体下载（直连优先，代理回退）
  └─ .otl / .otl.link 条目 → 交给 OTL 引擎（不再二次扫描；扫描不完整则 OTL 不 prune）
OTL 引擎（有界并发，默认 4）
  每个文件：比较 mtime / 格式版本 / 缺失产物 → 只做缺的部分
    airpage get（version）
    ├─ markdown_zip 任务 ─┐   并行创建，统一轮询 export_task/query
    └─ docx 任务 ─────────┘
    下载（直连优先）→ md 改写图片链接到 {stem}_{id8}.assets/ → 原子替换
    失败回退：markdown_zip 失败 → 块树转换（旧路径）
```

### 2.1 组件

| 组件 | 职责 |
|---|---|
| `wps_backup/wps_http.py`（新） | 直接调用 openapi.wps.cn：Bearer token 仅驻留内存、401 时经 CLI 刷新重试一次；**路由**：WPS/金山云域名先直连（短连接超时），连接/SSL 错误回退系统代理；HTTP 错误不回退 |
| `airpage_engine.export_task()`（新） | create → query 轮询 → 下载，支持 `markdown_zip` / `docx` / `markdown` |
| `airpage_engine.backup_otl_v5()`（新） | 产物级增量：md（含图片）与 docx 独立成功/失败 |
| `otl_engine` | 接受主引擎传入的 .otl 列表；并发执行；状态加锁；取消与进度 |
| `engine` | 扫描时收集 .otl 条目；实体下载改用直连优先的 opener |

### 2.2 产物与路径（向后兼容）

| 产物 | 路径 | 说明 |
|---|---|---|
| Markdown | `_otl_content/{drive}/{stem}_{id8}.md`（路径不变） | YAML frontmatter 保留（新增 `airpage_version`、`format: v5`）；正文为官方 markdown |
| 图片 | `_otl_content/{drive}/{stem}_{id8}.assets/` | md 中 `image_id=XXXX` 的远端链接改写为相对路径 |
| docx | `_otl_converted_docx/{stem}_{id8}.docx`（不变） | 官方 docx（含图片） |

### 2.3 状态（`_otl_state.json`，逐文件）

```json
{"mtime": 1727..., "airpage_version": "7", "format": 5,
 "content_path": ".../x.md", "docx_path": ".../x.docx",
 "md_error": "", "docx_error": "", "permanent": false, "backed_up_at": "..."}
```

`needs_update`：永久失败且 mtime 未变 → 跳过；否则 mtime 变化 / `format < 5`（一次性升级 197 篇旧文档）/ md 缺失 / docx 缺失（启用时）→ 只做缺失的产物。新产物成功后才替换旧文件。

### 2.4 效率目标

| 场景 | 基线 | 目标 |
|---|---|---|
| 日常无变化 | 118 s | ≈ 45 s（去掉 OTL 二次扫描） |
| 单篇变化 | 块树 + docx 串行 ~4–8 s/篇 | md_zip 与 docx 并行，服务端按版本缓存 |
| 全量重建 220 篇 | 串行 ~15 min | 4 路并发 |

## 3. 不在本次范围（后续选项）

- **事件驱动增量**：`kso_file_update` 事件 + 长连接（WebSocket）订阅，可免去定时全量扫描；需在开放平台开发者后台为应用订阅事件并配置，无法在本机验证。
- **PDF 归档**：官方接口可用（`drive_id` + 分享链接 `url`），但 CLI 本地校验仍要求已废弃字段，需走直接 HTTP；docx 已覆盖 Office 格式，暂不做。
- **不执行 `wps365-cli spec update`**：曾导致 curated 命令改名事故；新接口经直接 HTTP 调用，无需更新 spec。

## 4. 验收

- 单元测试（TDD）+ 线上契约测试（markdown_zip / docx 的 create → query → download）
- 经 WPS Backup.app 定时任务（force_run + kickstart）实跑：`last_run.json` exit 0；`E6pC1h5m`、`Nn1SvNVS` 两篇补齐 docx；新 md 中图片链接指向存在的本地文件；无变化运行耗时相对 118 s 基线下降

## 5. 实施结果（2026-09-26，经 WPS Backup.app 定时任务实跑）

| 指标 | 基线 | v5 实测 |
|---|---|---|
| 日常无变化运行总耗时 | 118 s | **43–58 s（−51%～−64%，差异来自主引擎扫描的网络波动）** |
| 其中 OTL 阶段 | 75 s（二次扫描） | **0.0 s**（复用主引擎扫描，220 个均判定最新） |
| 197 篇旧格式一次性升级 + 补齐 docx | — | **3 分 50 秒**（4 路并发），exit 0 |
| Markdown | 块树转换（无标题/加粗/链接/图片） | 官方 markdown，**194 篇**；**771 处本地图片引用、失效 0**，94 个 `.assets` 目录 |
| docx | 192（2 篇因代理缺失） | **195**（`E6pC1h5m`、`Nn1SvNVS` 已补齐） |
| 永久失败（mtime 不变不再重试） | 23 | 26 = 6 个 `.otl.link`（403）+ 20 个空文档（块树交叉验证确为空） |

实现要点：
- `wps_backup/wps_http.py`：直连 openapi.wps.cn（Bearer，401 刷新重试一次）；WPS/金山云域名直连优先、连接/SSL 错误回退代理；主引擎实体下载与旧 docx 导出也改用此路由
- `airpage_engine.backup_otl_v5()`：`markdown_zip` 与 `docx` 任务先后创建、统一轮询；图片按 `image_id` 改写为 `{stem}_{id8}.assets/` 相对路径；新产物成功才替换旧文件；markdown_zip 临时失败回退块树转换
- `OTLBackupState.plan_v5()/record_v5()`：md/docx 独立增量；`format` < 5 一次性升级；状态写入加锁
- `engine.scan_remote_files(otl_sink=...)`：一次遍历收集 `.otl` 与 `.otl.link`（注意快捷方式 `type` 为 `shortcut`）；线上契约测试验证与旧过滤扫描集合完全一致（220 = 220）
- 并发：`WPS_OTL_WORKERS`（默认 4）；取消（CANCEL）与进度回调保留

失败语义（复核后修正）：
- **永久失败只认响应码 `403000001`**（快捷方式/不存在/无权限，实测三者相同）。同为 HTTP 403 的 token/scope 失效（`400000003`）、路由变化 `404000001`、5xx 均为临时失败——否则一次 token 故障会把全部文档永久标记且不再重试
- **任何临时失败写入 `result.errors` → run 退出码 1**：App 显示为需处理，定时任务每小时重试（每天 ≤3 次）
- 直连尝试 socket 超时上限 `DIRECT_TIMEOUT=20s`，被阻断时尽快回退代理
- 缓存阶段 `mark_backed_up` 改为合并写入，不再丢失 `format`/`airpage_version`

主引擎下载新路由实测：`ksc-bj.ag.wps.cn` 小文件（200 KB）与分块续传（12.7 MB）均下载成功且 SHA-256 与已备份文件一致。

测试：Python 离线 146 个 + 线上契约 5 个（含 v5 往返与一次遍历等价性）全部通过。
