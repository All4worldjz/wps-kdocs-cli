# gai.cn 写作助手功能复刻研究报告（完整版）

> 研究时间：2026-05-22（三轮深度研究，最终完整版）
> 最新补充：2026-05-22 晚间只读核验，新增 `GAI_CN_CLONE_DEVELOPMENT_GUIDE.md`
> 研究对象：`https://gai.cn/writer/document-list` 写作助手创作中心
> 研究方式：已登录 Chrome 会话 + Computer Use UI 操作 + Chrome NetLog + 前端静态 bundle 分析 + 浏览器 performance API 实测抓包
> **完整交接文件**：见 `CLONE_HANDOFF_COMPLETE.md`（为克隆任务优化，含优先级列表）
> 重要边界：本报告是"功能与行为级复刻蓝图"。隐藏服务端源码、模型提示词、私有训练数据、内部任务队列实现无法仅凭浏览器会话 100% 还原，只能按可观察 API、页面行为和数据状态复刻。

---

## 0. 2026-05-22 晚间补充：只读核验与开发蓝图沉淀

本轮继续使用当前 Chrome 会话和 Computer Use，仅做目标站理解与取证，不做本地 clone 代码开发。新增指导文档：

```text
GAI_CN_CLONE_DEVELOPMENT_GUIDE.md
```

该文档已经把已掌握的产品功能、路由、API、数据模型、SSE、智能排版轮询、文风训练、TinyMCE 编辑器、素材库、回收站和本地替代算法整理成下一步 clone 开发蓝图。

### 0.1 当前 Chrome 会话核验

- 成功进入 `https://gai.cn/writer/document-list`。
- 页面可见：新建写作、创作中心、素材文稿、智能排版、文风模板、回收站。
- 可见入口：交互式创作、以稿写稿、模板创作、自由创作、空白文稿创作、上传文稿创作。
- 当前账号“我的文稿”为 `暂无文稿`、`共 0 条`，但仍显示筛选和分页壳。
- 页面提示过 `获取资料库类型失败`；素材页正文懒加载没有完整挂载，说明当前网络/缓存对部分 chunk 有影响。

### 0.2 NetLog 请求级补证

从 `chrome-net-export-log.json` 中抽取到 153 条 gai.cn 业务请求，归并为 26 类唯一 API。再次确认的关键链路：

```text
初始化：
GET  /gdios/api/user/getMyInfo
GET  /gdios/api/setup/uiConfig
GET  /gdios/api/user/checkUserMsg
GET  /gdios/api/user/getCurrentUserMenuList
POST /gdios/api/service/userMembership/queryUsage
GET  /geekseek/aiwriter/module/list
GET  /geekseek/aiwriter/common/getWritingConfig
GET  /geekseek/aiwriter/template/getWriterTemplateConfig

文稿：
POST /geekseek/aiwriter/document/v1/list
GET  /geekseek/aiwriter/document/v1/detail?docId={id}&version=
POST /geekseek/aiwriter/document/v1/addOrUpdate
POST /geekseek/aiwriter/document/v1/addDocToKnowledge
POST /geekseek/aiwriter/document/v1/categorySort
POST /geekseek/aiwriter/document/upload

素材与排版：
POST /geekseek/aiwriter/document/v2/list
POST /geekseek/aiwriter/file/v2/upload
POST /geekseek/aiwriter/document/v2/getKbImportStatus
POST /geekseek/aiwriter/document/v2/getSmartLayoutStatus
POST /geekseek/aiwriter/format/template/list
GET  /geekseek/aiwriter/format/template/group/list
POST /geekseek/aiwriter/smart/layout/v2/upload

导出：
POST /geekseek/aiwriter/file/v1/createDownloadFileTask
POST /geekseek/aiwriter/file/v1/taskStatus
GET  /geekseek/aiwriter/file/v2/download?taskUuid={id}
```

### 0.3 智能排版状态机补充

前端 `Typed` 模块确认了两个轮询层：

```text
上传文件
  -> getKbImportStatus 解析轮询
  -> getSmartLayoutStatus 排版轮询
  -> 结果卡片
  -> 编辑/导出/删除/重新解析/重新排版
```

- 解析轮询间隔约 `2000ms`。
- 解析停止状态：`contentCompleted`、`summaryCompleted`、`completed`、`process_failed`。
- 排版轮询间隔约 `2000ms`。
- `layoutStatus` 使用 `pending`、`success`、`failed`。
- `process_failed` 支持重新解析；`layoutStatus=failed` 支持重新排版。
- 上传限制：`materialType=SMART_LAYOUT_MATERIAL`，单文件，最大 10MB，支持 `.doc,.docx,.txt,.md,.wps`。

### 0.4 安全记录

`chrome-net-export-log.json` 仍包含自定义认证头和带 token 的下载 URL 参数。该文件只适合本机继续分析，不能提交公开仓库、不能外发、不能在文档里贴出真实 token。

---

## 1. 总体结论

该站点是一个 **Vue 3 + Vite 单页应用**，前端版本号 `1.22.0`，产品名「写作助手」，入口由 `/writer` 承载。富文本编辑器使用 **TinyMCE**（不是 ProseMirror/Tiptap）。UI 框架为 **Element Plus**。

业务 API 分两个命名空间：
- `/geekseek/aiwriter/...` — 写作助手核心业务
- `/gdios/api/...` — 用户账号、菜单、配置

所有 API 通过统一 axios 实例 `lr` 发出，认证头为：
```
Geekseek-Authorization: <token>   (从 localStorage['GEEKSEEK_USER_TOKEN'] 读取)
Geekseek-Language: zh-CN
```

---

## 2. 路由结构

```
/writer (重定向 → /writer/document-list)
/writer/document-list                   创作中心（我的文稿）
/writer/document-list/library           素材文稿
/writer/document-list/dustbin           回收站
/writer/document-list/typed             智能排版
/writer/document-list/style             文风模板
/writer/content/create                  新建创作（编辑器，无文档ID）
/writer/content/edit/:docId             编辑器
/writer/content/chat/:docId             对话页（小知AI对话模式）
/writer/content/templateEdit/:templateType  模板编辑
/writer/content/page/:docId?            文档详情预览页
/writer/lexicon                         词库
/writer/user                            个人中心
/writer/intro                           使用手册
/writer/preview                         预览页
/writer/playground                      测试页
```

编辑器 URL 参数：
- `type=typed` — 上传文稿/排版来源
- `category=UPLOAD_TEMPLATE_WRITE|SPEECH|WORK_REPORT|...` — 写作类型
- `navType=myDocList` — 返回导航目标
- `page=1&pageSize=24` — 来源页面分页状态

---

## 3. 完整 API 列表

### 3.1 初始化（每次进入应用加载）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/gdios/api/user/getMyInfo` | 当前用户信息 |
| GET | `/gdios/api/setup/uiConfig` | 应用标题/部署模式/功能开关 |
| GET | `/gdios/api/user/checkUserMsg` | 用户消息/通知提醒 |
| GET | `/gdios/api/user/getCurrentUserMenuList` | 当前用户菜单权限 |
| POST | `/gdios/api/service/userMembership/queryUsage` | SaaS 用量/额度信息 |
| GET | `/geekseek/aiwriter/module/list` | 写作助手模块开关列表 |
| GET | `/geekseek/aiwriter/template/getWriterTemplateConfig` | 写作模板全局配置 |
| GET | `/geekseek/aiwriter/common/getWritingConfig` | 写作配置/上传限制/功能开关 |
| GET | `/geekseek/aiwriter/common/getUiConfig` | 写作助手 UI 配置 |

### 3.2 用户账号

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/gdios/api/user/sendUserSmsCode` | 发送短信验证码 |
| POST | `/gdios/api/user/updateCurrentUser` | 更新用户信息 |
| POST | `/gdios/api/user/updateUserPassword` | 修改密码 |
| POST | `/gdios/api/user/updateUserProfession` | 更新职业信息 |

### 3.3 文稿管理（我的文稿）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/geekseek/aiwriter/document/v1/list` | 文稿列表/搜索/分页 |
| GET | `/geekseek/aiwriter/document/v1/detail?docId={id}&version={v}` | 文稿详情+版本 |
| POST | `/geekseek/aiwriter/document/v1/addOrUpdate` | 新建/保存文稿 |
| POST | `/geekseek/aiwriter/document/v1/categorySort` | 文稿分类/排序 |
| POST | `/geekseek/aiwriter/document/v1/addDocToKnowledge` | 加入知识管理 |
| POST | `/geekseek/aiwriter/document/v1/cancelAddDocToKnowledge` | 取消知识管理 |
| POST | `/geekseek/aiwriter/document/v1/recycle` | 删除到回收站 |
| POST | `/geekseek/aiwriter/document/v1/version/list` | 历史版本列表 |
| POST | `/geekseek/aiwriter/document/v1/addToPersonalMaterial` | 加入个人素材库 |
| POST | `/geekseek/aiwriter/document/v1/convertPunctuation` | 标点转换 |
| POST | `/geekseek/aiwriter/document/v1/webSearch` | 联网检索 |

### 3.4 素材文稿（document/v2 命名空间）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/geekseek/aiwriter/document/v2/list` | 素材列表/搜索/分页（含 channel 参数） |
| GET | `/geekseek/aiwriter/document/v2/detail?docId={id}&channel={ch}` | 素材详情 |
| POST | `/geekseek/aiwriter/document/v2/collect` | 收藏素材 |
| POST | `/geekseek/aiwriter/document/v2/delete` | 删除素材 |
| POST | `/geekseek/aiwriter/document/v2/reParse` | 重新解析素材 |
| POST | `/geekseek/aiwriter/document/v2/semanticSearch` | 语义搜索 |
| GET | `/geekseek/aiwriter/document/v2/tag` | 标签列表 |
| POST | `/geekseek/aiwriter/document/v2/getKbImportStatus` | 知识库导入状态 |
| POST | `/geekseek/aiwriter/document/v2/getSmartLayoutStatus` | 智能排版任务状态轮询 |

素材库 `channel` 枚举值（通过 v2/list 的 channel 参数区分不同 tab）：
- `PERSONAL_MATERIAL` — 个人资料
- `DEPARTMENT_KNOWLEDGE` — 部门资料
- `REGIONAL_FILE` — 地区文件
- `QIANGGUO_ARTICLE` — 强国文章
- `KNOWLEDGE_UPLOAD_MATERIAL` / `KNOWLEDGE` — 知识管理
- `WEB_SEARCH_MATERIAL` — 网络文章（搜索结果）

素材来源标签：
- `PERSONAL_MATERIAL` — 个人资料（自主上传）
- `CONTENT_REFER` — 参考内容
- `STYLE_REFER` — 参考文风

素材 materialType 枚举（卡片图标区分）：
- `QIANGGUO_ARTICLE` / `REGIONAL_FILE` / `DEPARTMENT_KNOWLEDGE` / `PERSONAL_MATERIAL` / `KNOWLEDGE_UPLOAD_MATERIAL` / `KNOWLEDGE` / `WEB_SEARCH_MATERIAL` / 其他文件类型

### 3.5 引用溯源与版本

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/geekseek/aiwriter/article/v1/citationSource` | 引用来源标注 |
| POST | `/geekseek/aiwriter/article/v1/md2Html` | Markdown 转 HTML |
| POST | `/geekseek/aiwriter/document/source/getCitationSourceStatus` | 引用来源/解析状态 |
| POST | `/geekseek/aiwriter/document/source/saveVersion` | 保存版本 |

### 3.6 文件上传与下载

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/geekseek/aiwriter/file/v2/upload` | 通用文件上传（multipart/form-data） |
| POST | `/geekseek/aiwriter/file/storage/v1/upload` | 存储文件上传 |
| GET | `/geekseek/aiwriter/file/v1/download?docId={id}` | 文档下载（blob） |
| GET | `/geekseek/aiwriter/file/v1/downloadPdf?docId={id}` | 导出 PDF（blob） |
| GET | `/geekseek/aiwriter/file/v2/download?taskUuid={id}` | 异步任务结果下载 |
| GET | `/geekseek/aiwriter/file/storage/v1/download?{params}` | 存储文件预览/下载（带 token URLParam） |

### 3.7 导出任务（异步）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/geekseek/aiwriter/file/v1/createDownloadFileTask` | 创建导出任务 |
| POST | `/geekseek/aiwriter/file/v1/taskStatus` | 轮询任务状态 |
| POST | `/geekseek/aiwriter/file/v1/cancelDownloadTask` | 取消任务 |

### 3.8 写作模板

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/geekseek/aiwriter/template/getWriterTemplateConfig` | 模板全局配置 |
| GET | `/geekseek/aiwriter/template/getWriteTemplate?templateCategory={cat}` | 按分类获取模板列表 |

### 3.9 智能排版

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/geekseek/aiwriter/format/template/list` | 排版格式模板列表 |
| GET | `/geekseek/aiwriter/format/template/group/list` | 排版模板分组 |
| POST | `/geekseek/aiwriter/smart/layout/v2/upload` | 上传并创建排版任务 |
| POST | `/geekseek/aiwriter/document/v2/getSmartLayoutStatus` | 排版任务状态轮询 |
| POST | `/geekseek/aiwriter/smart/layout/v1/layout` | 执行排版 |
| POST | `/geekseek/aiwriter/smart/layout/v1/reLayout` | 重新排版 |
| POST | `/geekseek/aiwriter/smart/layout/v1/updateSmartLayout` | 更新排版结果 |
| POST | `/geekseek/aiwriter/smart/layout/v1/delete` | 删除排版记录 |

### 3.10 文风模板（完整已验证）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/geekseek/aiwriter/writingStyle/v1/pageList` | 文风模板列表/分页 |
| GET | `/geekseek/aiwriter/writingStyle/v1/detail` | 文风模板详情 |
| POST | `/geekseek/aiwriter/writingStyle/v1/query` | 查询文风模板 |
| POST | `/geekseek/aiwriter/writingStyle/v1/add` | 新建文风模板 |
| POST | `/geekseek/aiwriter/writingStyle/v1/update` | 更新文风模板 |
| POST | `/geekseek/aiwriter/writingStyle/v1/delete` | 删除文风模板 |

### 3.11 智能校对（纠错）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/geekseek/aiwriter/text/correct/v1/getAbilityList` | 校对能力列表 |
| POST | `/geekseek/aiwriter/text/correct/v1/textCorrector` | 执行文本校对 |
| POST | `/geekseek/aiwriter/text/correct/v1/updateTextCorrectorItem` | 应用/忽略校对建议 |
| POST | `/geekseek/aiwriter/text/correct/v1/getTextCorrectorItemList` | 获取校对结果列表 |
| POST | `/geekseek/aiwriter/text/correct/v1/exportTextCorrectorItem` | 导出校对结果 |

### 3.12 字体配置

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/geekseek/aiwriter/font/config/getAllFontList` | 全部字体列表（支持搜索） |
| GET | `/geekseek/aiwriter/font/config/getDocumentFont?docId={id}` | 文档字体配置 |
| GET | `/geekseek/aiwriter/font/config/addFontCount?fontFamily={name}` | 字体使用计数 |

### 3.13 文件夹管理（第三轮新发现）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/geekseek/aiwriter/folder/v1/move` | 素材移动到指定文件夹（已实测） |
| POST | `/geekseek/aiwriter/folder/v1/create` | 新建文件夹（推断） |
| POST | `/geekseek/aiwriter/folder/v1/delete` | 删除文件夹（推断） |
| POST | `/geekseek/aiwriter/folder/v1/rename` | 重命名文件夹（推断） |
| POST | `/geekseek/aiwriter/folder/v1/list` | 文件夹列表（推断） |

「移动文件」弹窗 UI：显示文件名 + 文件夹树（含「根目录」）+ 「移动至此」按钮。

### 3.14 多步向导新增接口（第三轮新发现）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/geekseek/aiwriter/article/v1/generateExplainQrCode` | 生成微信扫码语音交代二维码 |
| POST | `/geekseek/aiwriter/article/v1/checkSensitiveWord` | 交代内容实时敏感词检查 |
| POST | `/geekseek/aiwriter/article/v1/checkOutlineSensitiveWord` | 提纲内容敏感词检查 |
| POST | `/geekseek/aiwriter/article/v1/outlineOrTitle/generateStream` | 提纲+标题流式生成（SSE，步骤3）|
| POST | `/geekseek/aiwriter/writingStyle/v1/downList` | 写作时文风模板下拉列表 |

### 3.15 回收站（第三轮确认）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/geekseek/aiwriter/document/v1/recycle` | 软删除（移入回收站）/ 恢复（参数区分） |
| POST | `/geekseek/aiwriter/document/v2/delete` | 彻底删除（物理删除，已实测） |

### 3.16 内容优化（第三轮确认）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/geekseek/aiwriter/article/v1/optimize` | 润色/扩写/缩写/改写（type 参数区分，已实测） |

type 参数推断值：`POLISH`（润色）、`EXPAND`（扩写）、`SHORTEN`（缩写）、`REWRITE`（改写）

操作结果返回后，右侧面板显示：
- 「插入」— 在光标处插入优化后内容
- 「替换」— 替换原选中内容
- 「重新生成」— 重新调用 optimize

### 3.17 AI 写作生成（chat/article 命名空间，**已实测验证**）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/geekseek/aiwriter/article/v1/getExplainContent` | 根据交代内容生成构思摘要（进入 chat 页前调用） |
| POST | `/geekseek/aiwriter/article/v1/generate` | **AI 全文生成**（SSE 流式，边生成边渲染） |
| POST | `/geekseek/aiwriter/article/v1/citationSource` | 引用溯源标注 |
| POST | `/geekseek/aiwriter/article/v1/md2Html` | Markdown 转 HTML |

生成流程（已观测）：
1. 点击「生成全文」→ 跳转 `/writer/chat/:docId`
2. 调用 `getExplainContent` 获取构思描述（页面顶部灰色说明文字）
3. 调用 `article/v1/generate`（SSE 流式）渲染文字
4. 生成完成后自动调用 `document/v1/addOrUpdate` 保存
5. 调用 `document/v1/convertPunctuation` 转换标点
6. 调用 `article/v1/citationSource` 标注引用来源
7. 页面显示「重新生成」按钮，右上角「编辑文稿」跳转编辑器

语音代理路径（微信扫码语音输入）：
- `/v1/voice/geekseek-proxy/geekseek/aiwriter/article/v1/getExplainContent`

### 3.14 其他

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/geekseek/aiwriter/feedback/insert` | 用户反馈提交 |
| GET | `/geekseek/aiwriter/kkfile/preview?...` | 文件预览（kkFileView） |

---

## 4. 页面功能详细说明

### 4.1 创作中心 / 我的文稿

**页面元素：**
- 顶部「开始创作」区（4张方式卡）：交互式创作、以稿写稿、模板创作、自由创作
- 右上角快速入口：空白文稿创作、上传文稿创作
- 素材文稿快捷入口卡（上传个人素材）
- 常用创作横向滚动卡（11种）
- 更多功能区：智能排版、文风模板
- 我的文稿列表（卡片式，分页）

**文稿卡片字段（可观察）：**
- 标题、内容摘要、字数、创建/更新时间
- 知识管理状态标识（蓝色图标）
- 文稿类型图标

**文稿卡片 hover 操作（4个图标）：**
1. 添加到知识管理（`icon-knowledge`）
2. 标题重命名（`rename-title`）
3. 导出为 Word
4. 删除（移入回收站）

**文稿卡列表功能：**
- 搜索（URL 参数 `searchKeyword=`）
- 知识管理筛选（URL 参数 `filterImportedKnowledge=true`）
- 分页（24条/页，可切换12/24/36/48/60）

### 4.2 写作类型与创作流程

**分类完整表：**

| 枚举值 | 中文名 | 流程 | 步骤 |
|---|---|---|---|
| `SPEECH` | 讲话稿 | 多步向导 | 交代→参考→提纲 |
| `REFLECTION` | 心得体会 | 多步向导 | 交代→参考→提纲 |
| `WORK_REPORT` | 工作报告 | 多步向导 | 交代→参考→提纲 |
| `RESEARCH_REPORT` | 调研报告 | 多步向导 | 交代→参考→提纲 |
| `NOTICE` | 通知 | 多步向导 | 交代→参考 |
| `THANK_YOU_LETTER` | 感谢信 | 多步向导 | 交代→参考 |
| `REFER_BASED_WRITING` | 以稿写稿 | 单弹窗 | 直接生成 |
| `FREE_WRITING` | 自由创作 | 单弹窗 | 直接生成 |
| `MEETING_SUMMARY` | 会议纪要 | 单弹窗 | 直接生成 |
| `INDIVIDUAL_YEAR_END_REPORT` | 年终总结 | 单弹窗 | 直接生成 |
| `OFFICIAL_ACCOUNT_ARTICLE` | 公众号文章 | 单弹窗 | 直接生成 |
| `DAILY_MONTHLY_REPORT` | 日报月报 | 单弹窗 | 直接生成 |
| `TRAINING_REFLECTION` | 培训心得 | 单弹窗 | 直接生成 |
| `QIANGGUO_ARTICLE` | 强国文章 | 单弹窗 | 直接生成 |
| 模板创作 | 模板创作 | 模板选择器 | 选模板→直接生成 |
| 上传创作 | `UPLOAD_TEMPLATE_WRITE` | 文件上传 | 上传解析→进入编辑器 |

**多步向导共有元素：**
- 微信扫码语音交代区
- 文本交代输入框
- AI 优化交代按钮
- 联网搜索开关
- 字数输入框（滑块+数字）
- 默认字数：讲话稿/报告类 ~3000字，通知/信函类 ~1000字

**提纲步骤功能：**
- 一级标题模式 / 二级标题模式切换
- 添加一级标题、二级标题节点（最多20个）
- 重新生成提纲
- 对提纲节点输入调整要求
- 生成全文

### 4.3 编辑器

**URL 格式：** `/writer/content/edit/:docId?type=...&category=...`

**顶部栏：**
- ← 面包屑（创作中心 / 文档标题）
- 标题（可点击编辑，inline 编辑）
- 知识管理图标（切换知识库状态）
- 保存状态（「已保存于 HH:MM:SS」）
- 更多菜单（…）：另存为我的模板
- 下载图标（下拉）：导出为 Word / 导出为 PDF
- 保存按钮

**编辑器工具栏（TinyMCE）：**
```
撤销 重做 | 段落块(blocks) | 字体(fontfamily) | 字号(fontsize) |
加粗(B) | 斜体(I) | 下划线(U) | 删除线(S) | 首行缩进(I斜) | 清除格式 |
字体颜色(A▼) | 背景色(高亮▼) | 减少缩进 | 增加缩进 | 对齐方式(▼) | 行距(▼) |
列表(无序▼) | 列表(有序+间距▼)
```

**自定义字体（中文公文专用）：**
- 仿宋_GB2312 / FangSong_GB2312
- 楷体 KaiTi / 楷体 KaiTi_GB2312
- 黑体 SimHei
- 文星简小标宋 JXBS
- 方正小标宋 FZXiaoBiaoSong-B05S
- 方正书宋 FZShuSong-Z01
- 方正美黑 FZMeiHei-M07S
- 阿里妈妈数黑体 Alimama ShuHeiTi

**右侧 AI 工具面板（4个 tab）：**

1. **内容优化** — 子 tab：润色 / 扩写 / 缩写 / 改写
   - 需先选中文稿内容，激活操作按钮

2. **格式排版** — 搜索 + 分 tab 浏览
   - tab：全部格式 / 通用格式 / 法定格式 / 自定格式
   - 通用格式：通用格式-无红头、通用格式-有红头
   - 法定格式（15种）：报告、公报、公告、函、纪要、决定、决议、令（命令）、批复、请示、通报、通告、通知、议案、意见

3. **智能校对** — 点击「开始校对」对全文校对
   - 结果展示：错误标记 + 修改建议列表
   - 操作：应用/忽略单项，导出校对结果

4. **小知AI** — 对话式 AI 助手
   - 输入框（Shift+Enter 换行，Enter 发送）
   - 底部工具：📎 附件 / 个人资料 / 联网 / 事实核查
   - 右上角「开启新对话」按钮

### 4.4 素材文稿

**页面 tab（5个，对应 channel 枚举）：**
1. 个人资料（`PERSONAL_MATERIAL`）
2. 部门资料（`DEPARTMENT_KNOWLEDGE`）
3. 地区文件（`REGIONAL_FILE`）
4. 强国文章（`QIANGGUO_ARTICLE`）
5. 知识管理（`KNOWLEDGE_UPLOAD_MATERIAL`）

**顶部搜索：** 横向蓝色 banner 大搜索框

**筛选条件：**
- 素材类型（全部/工作报告/通知/领导讲话/心得体会/工作方案/调研报告/其他）
- ☑ 已添加到知识管理
- ☑ 自主上传
- 排序（文件类型/上传时间-倒序/正序）

**导入/新建按钮下拉：** 导入本地文件 / 导入本地文件夹 / 新建文件夹

**素材卡片 hover 操作（3个图标）：**
1. 添加到知识管理
2. 移动到（文件夹）
3. 删除

**分页：** 12/24/36/48/60 条/页

### 4.5 智能排版

**上传弹窗：**
- 排版格式选择（下拉，默认「通用格式-无红头」）
- 拖拽/点击上传区
- 支持格式：doc/docx/txt/md/wps
- 单次1个文件，最大10MB

**任务流：** 上传 → 创建任务 → 状态轮询（`getSmartLayoutStatus`）→ 显示「智能排版中」 → 完成后显示结果卡片

**结果卡片操作：** 重新排版 / 导出 / 删除

### 4.6 文风模板（完整流程已验证）

**列表页（`/writer/document-list/style`）：**
- 分页：10/20/50/100 条/页
- 搜索框
- 「+ 新建文风」按钮

**文风卡片状态：**
- 生成中：显示百分比进度条 + 「文风正在生成中」
- 生成完成：显示词云图

**文风卡片 hover 操作（2个图标）：**
1. 编辑（✏️）
2. 删除（🗑️，弹确认对话框）

**新建/编辑文风模板弹窗字段：**
- 文风标题（必填，0/50字符限制）
- 文风素材（必填，0-10份，限制提示「训练文本少于100字或英文时训练不生效」）
- 素材搜索框
- 「+ 文风素材 0/10」按钮（下拉菜单）

**素材来源下拉（5项）：**
1. 上传本地文稿
2. 从素材库添加
3. 从知识库添加
4. 手动输入文本 → 右侧全屏抽屉（大文本框）
5. 从历史记录添加

**保存后行为：**
- 新建：触发词云生成任务（异步），卡片显示进度 → 完成显示词云
- 编辑：若修改素材则重新生成词云

**完整 API：** `add` / `update` / `delete` / `pageList` / `detail` / `query`

### 4.7 回收站

- 搜索框
- 空态插画 + 文案
- 卡片操作：恢复文件（`IconRestore`）/ 彻底删除
- 分页（24条/页）

---

## 5. 数据模型

### 5.1 文稿（Document v1）

```typescript
interface Document {
  id: string;
  title: string;
  contentHtml: string;
  contentText: string;       // 用于列表摘要
  category: WritingCategory; // SPEECH | WORK_REPORT | ... | UPLOAD_TEMPLATE_WRITE
  wordCount: number;
  isImportedKnowledge: boolean;
  parseStatus: 'PENDING' | 'PROCESSING' | 'SUCCESS' | 'FAILED';
  exportTaskStatus?: string;
  version?: number;
  createdAt: string;
  updatedAt: string;
  deletedAt?: string;        // 软删除
}
```

### 5.2 素材（Document v2）

```typescript
interface Material {
  id: string;
  title: string;
  materialType: MaterialType; // PERSONAL_MATERIAL | QIANGGUO_ARTICLE | ...
  source: string;             // 自主上传 | ...
  channel: ChannelType;
  folderId?: string;
  category?: string;          // 工作报告 | 通知 | 领导讲话 | 心得体会 | 工作方案 | 调研报告 | 其他
  contentPreview: string;
  wordCount: number;
  fileId?: string;
  isImportedKnowledge: boolean;
  tags?: string[];
  createdAt: string;
  deletedAt?: string;
}
```

### 5.3 文风模板（WritingStyle）

```typescript
interface WritingStyle {
  id: string;
  title: string;              // 最长50字
  status: 'PENDING' | 'TRAINING' | 'READY' | 'FAILED';
  progress: number;           // 0-100
  materialIds: string[];      // 关联素材，最多10个
  wordCloud?: WordCloudItem[];// 生成完成后的词云数据
  stylePrompt?: string;       // 训练结果提示词
  materialCount: number;      // 已选素材数
  createdAt: string;
  updatedAt: string;
}
```

### 5.4 智能排版任务

```typescript
interface SmartLayoutTask {
  id: string;
  sourceFileId: string;
  templateId: string;         // 格式模板ID
  title: string;
  status: 'PENDING' | 'PROCESSING' | 'SUCCESS' | 'FAILED';
  progress?: number;
  contentPreview?: string;
  outputDocId?: string;
  wordCount?: number;
  errorMessage?: string;
  createdAt: string;
  updatedAt: string;
}
```

### 5.5 异步任务（通用）

```sql
CREATE TABLE async_tasks (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,           -- EXPORT_WORD | EXPORT_PDF | SMART_LAYOUT | STYLE_TRAIN
  subject_id TEXT,              -- 关联文档/模板 ID
  status TEXT NOT NULL,         -- PENDING | PROCESSING | SUCCESS | FAILED
  progress INTEGER DEFAULT 0,
  input_json TEXT,
  output_json TEXT,             -- 包含 taskUuid 等下载凭证
  error_message TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

---

## 6. 前端技术栈

| 项目 | 技术 |
|---|---|
| 框架 | Vue 3 + Composition API |
| 构建工具 | Vite（懒加载 chunk 命名含版本号 `.1.22.0.js`） |
| UI 框架 | Element Plus |
| 富文本编辑器 | TinyMCE（配置了中文公文专用字体） |
| HTTP 客户端 | axios（统一实例 `lr`，baseURL 为空即同域） |
| 认证 | localStorage token + 请求头 `Geekseek-Authorization` |
| 状态管理 | Pinia（推测，bundle 中存在 store 模式） |
| 词云 | 前端渲染词云组件（`useRenderWordCloud` hook） |
| 语音识别 | WebSocket + FunASR 服务 |
| 文件预览 | kkFileView（`/geekseek/aiwriter/kkfile/preview`） |

---

## 7. 复刻建议架构

### 7.1 前端

```
src/
├── router/          # Vue Router，路由同上
├── stores/          # Pinia stores
│   ├── user.ts      # 用户信息、token
│   ├── document.ts  # 文稿列表、当前文稿
│   ├── material.ts  # 素材库
│   ├── taskPolling.ts  # 异步任务轮询
│   └── editor.ts    # 编辑器状态
├── api/             # axios 接口封装，按模块分文件
├── views/
│   ├── DocumentList/   # 创作中心
│   ├── Library/        # 素材文稿
│   ├── Typed/          # 智能排版
│   ├── StyleManage/    # 文风模板
│   ├── Dustbin/        # 回收站
│   └── Editor/         # TinyMCE 编辑器
└── components/
    ├── WritingDialog/  # 多步创作向导（交代→参考→提纲）
    ├── DocCard/        # 文稿卡片
    ├── AIToolPanel/    # 右侧AI工具面板
    └── StyleMaterial/  # 文风素材选择
```

### 7.2 后端服务拆分建议

- **Auth Service** — token 签发、校验、SMS 验证码
- **Config Service** — uiConfig / writingConfig / moduleList / templateConfig
- **Document Service** — v1 文稿 CRUD、版本、知识管理标记
- **Material Service** — v2 素材库、文件夹树、channel 查询
- **File Service** — 上传、下载、kkFileView 代理
- **Export Task Service** — Word/PDF 导出异步任务
- **Smart Layout Service** — 排版任务、格式模板管理
- **Writing Style Service** — `writingStyle/v1/*` 全部接口，词云生成
- **Text Correct Service** — 智能校对
- **AI Writing Service** — 交互式写作向导、全文生成（SSE/流式）
- **Chat Service** — 小知AI对话

### 7.3 复刻优先级

1. **P0**：账号初始化（getMyInfo + uiConfig + menuList + writingConfig）
2. **P0**：文稿列表 + 编辑器（TinyMCE）+ 保存 + 重命名
3. **P1**：导出 Word/PDF（异步任务轮询）
4. **P1**：素材库（上传 + 列表 + channel 筛选）
5. **P1**：回收站（软删除 + 恢复 + 永久删除）
6. **P2**：智能排版（上传 + 格式模板 + 任务轮询）
7. **P2**：文风模板（完整 writingStyle/v1 CRUD + 词云生成）
8. **P2**：内容优化（润色/扩写/缩写/改写）
9. **P3**：智能校对（textCorrector 接口）
10. **P3**：小知AI对话（chat 接口）
11. **P3**：交互式创作向导（多步提纲生成）
12. **P3**：引用溯源、标点转换、联网检索等编辑器工具

---

## 8. 站内已产生的测试数据副作用

| 类型 | 名称 | 状态 |
|---|---|---|
| 我的文稿 | `gai_cn_safe_upload_test` | 155字，存在 |
| 我的文稿 | `通用模板-无红头` | 1414字，已加入知识管理 |
| 我的文稿 | `未命名` | 0字，存在 |
| 素材文稿 | `gai_cn_safe_upload_test` | 存在 |
| 智能排版 | `gai_cn_safe_upload_test` | 存在 |
| 文风模板 | `测试文风模板–请删除` | 词云已生成，存在 |
| 文风模板 | `测试文风2–请删除` | 已删除 ✓ |
| 导出文件 | `通用模板-无红头.docx` | 已下载到本地 |

---

## 9. 本地研究产物

| 文件 | 说明 |
|---|---|
| `chrome-net-export-log.json` | 脱敏 NetLog（含认证头，仅本机使用） |
| `gai_cn_safe_upload_test.txt` | 安全测试上传样本 |
| `/tmp/gai-index.js` | 前端主 bundle（约3MB） |
| `/tmp/gai-index.css` | 前端主 CSS |
| `gai_cn_writer_reverse_engineering_report.md` | 本报告 |
| `gai_cn_writer_test_handoff.md` | 第一轮研究交接文档 |

---

## 10. 仍需补充的缺口

1. ✅ **AI 写作生成接口** — 已确认：`/geekseek/aiwriter/article/v1/generate`（SSE 流式）
2. ✅ **编辑器内容优化 API** — 已确认：`/geekseek/aiwriter/article/v1/optimize`（type 参数区分润色/扩写等）
3. ✅ **回收站恢复/永久删除 API** — 恢复用 `document/v1/recycle`，永久删除用 `document/v2/delete`
4. ✅ **素材移动 API** — 已确认：`/geekseek/aiwriter/folder/v1/move`
5. ✅ **多步向导参考阶段接口** — `document/v2/semanticSearch`（智能推荐）+ `writingStyle/v1/downList`（文风下拉）
6. ✅ **多步向导提纲阶段接口** — `article/v1/outlineOrTitle/generateStream`（SSE 流式生成提纲+标题）
7. ✅ **敏感词检查接口** — `article/v1/checkSensitiveWord`（交代）+ `article/v1/checkOutlineSensitiveWord`（提纲）
8. **以稿写稿**（`REFER_BASED_WRITING`）完整参数结构 — 需实测
9. **文件夹完整 CRUD API** — 已知 `folder/v1/move`，还有 create/delete/rename/list 未探索
10. **知识库** tab 具体接口 — 未深入探索
11. **字数限制**等具体会员规则（已观察到「通根数量 ~3,000,000」）
