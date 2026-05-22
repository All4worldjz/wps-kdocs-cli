# gai.cn 写作助手研究交接（第二轮，完整版）

时间：2026-05-22（第二轮研究完成）

## 2026-05-22 晚间接力补充

本轮继续使用当前 Chrome 会话和 Computer Use，仅进行只读研究，没有做本地 clone 代码开发。新的主指导文档已经生成：

```text
GAI_CN_CLONE_DEVELOPMENT_GUIDE.md
```

接力顺序：

1. 先读 `GAI_CN_CLONE_DEVELOPMENT_GUIDE.md`，它是下一步 clone 开发的主蓝图。
2. 再读 `CLONE_HANDOFF_COMPLETE.md` 的“最新只读研究补充（2026-05-22）”。
3. 然后查 `gai_cn_writer_reverse_engineering_report.md` 的完整 API、页面、数据模型说明。

本轮新增确认：

- 当前 Chrome 能进入 `/writer/document-list`，创作中心主要入口可见。
- 当前账号“我的文稿”为空，但页面仍显示筛选、分页和空态。
- 素材页懒加载正文未完全挂载，页面曾提示 `获取资料库类型失败`，后续如继续抓包需先恢复资源加载。
- NetLog 抽取到 153 条 gai.cn 业务请求，归并为 26 类唯一 API。
- 智能排版有两层轮询：`getKbImportStatus` 解析轮询与 `getSmartLayoutStatus` 排版轮询，间隔约 2 秒。
- 智能排版上传使用 `smart/layout/v2/upload`，`materialType=SMART_LAYOUT_MATERIAL`，支持 `.doc,.docx,.txt,.md,.wps`，单文件，最大 10MB。
- 创作中心上传使用 `document/upload`，`materialType=PERSONAL_MATERIAL`，支持 `.doc,.docx,.txt,.wps,.md`。

安全提醒：

- `chrome-net-export-log.json` 含认证头和 token query 参数，只能留作本机研究，不要提交公开仓库或外发。

## 研究进度

**第一轮**（已完成）：UI 流程测试、首次 NetLog 分析、前端 bundle 初步分析。
**第二轮**（已完成）：Chrome Computer Use 深度测试 + `performance.getEntriesByType` 抓包 + bundle 精细解析。

主报告：`gai_cn_writer_reverse_engineering_report.md`（完整版，约500行）

## 第二轮新增发现

### 文风模板完整 API（之前缺口）

通过 `performance.getEntriesByType('resource')` 实时抓包验证：

```
POST /geekseek/aiwriter/writingStyle/v1/pageList   — 列表
GET  /geekseek/aiwriter/writingStyle/v1/detail     — 详情
POST /geekseek/aiwriter/writingStyle/v1/query      — 查询
POST /geekseek/aiwriter/writingStyle/v1/add        — 新建（已验证）
POST /geekseek/aiwriter/writingStyle/v1/update     — 更新（已验证）
POST /geekseek/aiwriter/writingStyle/v1/delete     — 删除（已验证）
```

### 编辑器详细信息

- 编辑器类型：**TinyMCE**（不是 Tiptap/ProseMirror）
- 右侧 AI 工具4个 tab：内容优化（润色/扩写/缩写/改写）、格式排版、智能校对、小知AI
- 格式模板：通用2种 + 法定15种（报告/公报/公告/函/纪要/决定/决议/令/批复/请示/通报/通告/通知/议案/意见）
- 顶部「更多」菜单：另存为我的模板
- 下载下拉：导出为 Word / 导出为 PDF

### 文稿卡片操作（已全部确认）

4个图标：添加到知识管理 / 标题重命名 / 导出为 Word / 删除

### 素材卡片操作（已全部确认）

3个图标：添加到知识管理 / 移动到 / 删除

### 素材库 channel 枚举（完整）

- `PERSONAL_MATERIAL` — 个人资料
- `DEPARTMENT_KNOWLEDGE` — 部门资料
- `REGIONAL_FILE` — 地区文件
- `QIANGGUO_ARTICLE` — 强国文章
- `KNOWLEDGE_UPLOAD_MATERIAL` / `KNOWLEDGE` — 知识管理

### 写作类型完整表（15种）

SPEECH / REFLECTION / WORK_REPORT / RESEARCH_REPORT / NOTICE / THANK_YOU_LETTER / REFER_BASED_WRITING / FREE_WRITING / MEETING_SUMMARY / INDIVIDUAL_YEAR_END_REPORT / OFFICIAL_ACCOUNT_ARTICLE / DAILY_MONTHLY_REPORT / TRAINING_REFLECTION / QIANGGUO_ARTICLE / 模板创作

## 当前账号数据状态

| 类型 | 名称 | 状态 |
|---|---|---|
| 我的文稿 | gai_cn_safe_upload_test | 存在 |
| 我的文稿 | 通用模板-无红头 | 存在（已加入知识管理） |
| 我的文稿 | 未命名 | 存在（0字） |
| 素材文稿 | gai_cn_safe_upload_test | 存在 |
| 智能排版 | gai_cn_safe_upload_test | 存在 |
| 文风模板 | 测试文风模板–请删除 | 存在（词云已生成） |

## 仍需补充的缺口

1. AI 全文生成接口的具体 URL（需实际点击「生成全文」并 monitor）
2. 内容优化（润色/扩写等）具体 API
3. 回收站恢复/永久删除 API
4. 素材「移动到」API
5. 以稿写稿参数结构
