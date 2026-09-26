# OTL 备份调研：导出为 Office 格式并下载到本地

**日期:** 2026-09-26  **账号:** 企业账号（wps365-cli v0.3.6，scope 含 `kso.airpage.readwrite`）
**结论（2026-09-26 晚更新）:** 本文的“docx 是唯一可行路径、PDF 不实用”结论**已被后续调研推翻**：官方另有 `export_to_markdown_zip`（高保真 markdown + 图片）接口，PDF 可改用 `drive_id` 调用。最新设计见 [`OTL_BACKUP_DESIGN_V5.md`](OTL_BACKUP_DESIGN_V5.md)。下文保留为调研过程记录；§4 的两个缺口（代理、docx 不重试）仍然成立，已纳入 v5 设计。

## 1. 候选导出路径（均为实测）

| 路径 | 格式 | 权限 | 实测结果 |
|---|---|---|---|
| **`wps365-cli airpage export create/get`**（`/v7/airpage/{id}/export_to_docx`） | **docx** | `kso.airpage.readwrite` ✅ 已有 | ✅ **可用，生产在用**（`airpage_engine.export_airpage_to_file`） |
| 同上 `--format json` | json（块结构） | 同上 | 可用（非 Office 格式；可作为无损结构备份） |
| `/v7/airpage/{id}/export_to_pdf` | pdf | 同上 | ❌ 不实用：必填 `url/url_param`/纸张页边距等打印参数，且 `group_id`/`parent_id` 须为 int64 旧版数字 ID，v7 接口（盘列表、文件详情）只返回字符串 ID，无法获得 |
| `/v7/coop/airpage/{id}/export_to_pdf/async_tasks/create` | pdf | 同上 | ❌ 服务端返回 `500000004 method AirpageExportToPdfTask not implemented`（规格有、未上线） |
| `/v7/coop/airpage/{id}/export_to_docx`、`export_to_image` | docx / 图片 | 同上 | 未单独测试（docx 已有稳定路径；同系列 pdf 未实现） |
| `/v7/documents/{id}/exports`（通用文档导出，`format` + `store_type` ks3/云盘） | 任意 format | `kso.documents.readwrite` ❌ 未授权 | ❌ `invalid_scope`；需在开放平台为应用开通该 scope 并重新登录后才能验证是否支持 otl |
| `/v7/aidocs/file_id_convert`（v7 ID → 数字 ID，用于上面 pdf） | — | `kso.aidocs.readwrite` ❌ 未授权 | 未测；且本身需要 group_id 入参 |
| Drive `file download` | 原始 otl | — | ❌ .otl 无下载地址（私有格式） |
| kdocs-cli `read-file` | Markdown | kdocs 个人账号 | ❌ 企业账号 403001 |

OTL 是文档类型，对应的 Office 格式只有 docx（xlsx/pptx 不适用）。

## 2. 现有 docx 导出质量（2026-09-26 实测）

- 220 个远程 .otl → 197 有内容（其余 23 个为 `.otl.link` 快捷方式/空文档）
- **192 个 docx 全部为有效 Office 文件**（zip 结构含 `word/document.xml`）
- **112 个 docx 内嵌图片，共 1,243 张**（图片随 docx 一起备份；Markdown 中仅为占位符）
- 最大 95 MB（最大的一篇）

## 3. 流程（生产实现）

`airpage get`（取 version）→ `airpage export create --format docx --version N` → 轮询 `export get` → 下载签名 URL（`weboffice-outline.ks3-cn-beijing.ksyun.com`）→ 原子写入 `_otl_converted_docx/{name}_{file_id[:8]}.docx`。

## 4. 发现的问题

### 4.1 本地代理导致导出下载 SSL 握手超时（已定位）

- 2 个文档有 Markdown 但无 docx（文档 `E6pC1h5m…`、`Nn1SvNVS…`），手动重试稳定失败：导出任务 `Completed`，下载 `The handshake operation timed out`。
- 本机配置了 HTTP(S) 代理 `127.0.0.1:3213`（环境变量 **和** 系统网络设置）；Python `urllib` 在 macOS 上会读取系统代理，因此 **launchd 下同样走代理**。
- 同一 URL：经代理 120s 超时；`curl --noproxy '*'` 直连 **0.16s 成功**（HTTP 200，11.5 KB 有效 docx）。DNS 正常解析到金山云北京（60.28.198.x）。
- 代理对国内金山云/WPS 存储域名间歇性失败 → docx 会随机缺失；主引擎下载（`hwc-bj.ag.wps.cn` 等）同样经过该代理，存在同类风险。

**建议修复**：下载金山云/WPS 域名（`*.ksyun.com`、`*.wps.cn`、`*.kdocs.cn`、`*.qwps.cn`）时绕过代理（`urllib.request.build_opener(ProxyHandler({}))`），或"先代理、失败后直连"重试；加单测。

### 4.2 docx 导出失败不会重试

Markdown 成功即标记 OTL 已备份；docx 失败只记日志，在文档修改（mtime 变化）前永远不会补导。
**建议修复**：OTL 状态中 `docx_path` 为空且启用 docx 导出时，下次运行仅补导 docx（不重读块树）。

## 5. 可选扩展

- **json 导出**：`--format json` 保存完整块结构（比 Markdown 保真），可作为第三层备份，成本低。
- **通用导出 / PDF**：如需 PDF 归档，需在 WPS 开放平台为应用开通 `kso.documents.readwrite` 后重新登录，再验证 `/v7/documents/{id}/exports` 是否支持 otl→pdf。
