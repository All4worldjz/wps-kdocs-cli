# gai.cn 写作助手 Clone 开发指导文档

> 更新时间：2026-05-22
> 用途：作为下一步 100% 功能级 clone 开发的产品、前端、后端、数据流与算法实现蓝图。
> 边界：本文记录的是通过已登录 Chrome 会话、Computer Use、前端 bundle、NetLog 与既有 handoff 观察到的功能与行为。隐藏服务端源码、私有模型 prompt、训练数据、队列拓扑、模型供应商与私有算法不能仅凭浏览器会话完全还原，clone 时应按“可观察行为兼容 + 本地可控实现”复刻。

---

## 1. 克隆目标

目标站是 `https://gai.cn/writer/document-list` 的“写作助手”应用。它是一个面向公文/材料写作场景的 AI 写作平台，核心能力包括：

- 创作中心：选择创作方式、写作分类、查看我的文稿。
- 交互式创作：交代写作需求、选择参考素材、生成提纲、生成全文。
- 以稿写稿：上传或选择稿件作为蓝本二次创作。
- 模板创作：基于模板格式生成或编辑文稿。
- 自由创作：一句话生成文稿。
- 素材文稿：管理个人素材、部门资料、地区文件、强国文章、知识管理素材。
- 智能排版：上传文稿，选择格式模板，异步解析与排版，导出结果。
- 文风模板：用 1-10 份素材训练文风，生成词云和写作风格提示。
- 富文本编辑器：TinyMCE 编辑、保存、导出 Word/PDF、收藏、加入知识管理。
- AI 侧栏：内容优化、格式排版、智能校对、小知 AI 对话。
- 回收站：软删除、恢复、彻底删除。
- 个人中心/使用手册/词库/预览/测试页等辅助页面。

开发 clone 时优先目标不是像素级完全一致，而是：

1. URL、页面结构、主要交互和业务状态一致。
2. API 路径、请求方式、关键参数、返回形状兼容。
3. 异步任务、SSE、轮询、上传下载、编辑保存闭环一致。
4. 用可替代的本地算法实现服务端不可见能力。

---

## 2. 前端架构还原

### 2.1 技术栈

| 项目 | 观察结论 |
|---|---|
| 框架 | Vue 3 + Composition API |
| 构建 | Vite，chunk 名形如 `Component.Hash.1.22.0.js` |
| UI | Element Plus |
| 编辑器 | TinyMCE |
| 状态 | Pinia 风格 store |
| HTTP | axios 单例，同域 baseURL |
| 认证 | `localStorage['GEEKSEEK_USER_TOKEN']` -> `Geekseek-Authorization` 请求头 |
| 语言 | `Geekseek-Language: zh-CN` |
| 文件预览 | kkFileView 风格接口 |
| 词云 | `useRenderWordCloud` 前端 canvas/组件渲染 |
| 语音 | 微信扫码语音交代 + WebSocket/FunASR 线索 |

### 2.2 路由结构

```text
/writer
/writer/document-list
/writer/document-list?writingMenu=true
/writer/document-list?category=SPEECH&writingMenu=true
/writer/document-list?templateWriting=true
/writer/document-list/library
/writer/document-list/dustbin
/writer/document-list/typed
/writer/document-list/style
/writer/content/create
/writer/content/chat/:docId
/writer/content/edit/:docId
/writer/content/templateEdit/:templateType
/writer/content/page/:docId?
/writer/edit/:docId
/writer/lexicon
/writer/user
/writer/intro
/writer/preview
/writer/playground
/writer/playground/voice-test
/writer/playground/icon-list
```

注意：`/writer/edit/:docId` 与 `/writer/content/edit/:docId` 在现网/报告中都出现过，clone 应兼容两种路径。

### 2.3 全局初始化流程

应用启动后应并发/串行加载以下信息：

```text
GET  /gdios/api/user/getMyInfo
GET  /gdios/api/setup/uiConfig
GET  /gdios/api/user/checkUserMsg
GET  /gdios/api/user/getCurrentUserMenuList
POST /gdios/api/service/userMembership/queryUsage
GET  /geekseek/aiwriter/module/list
GET  /geekseek/aiwriter/common/getWritingConfig
GET  /geekseek/aiwriter/common/getUiConfig
GET  /geekseek/aiwriter/template/getWriterTemplateConfig
```

初始化配置应写入全局 store，控制：

- 是否显示个人中心。
- 是否显示帮助、反馈、联系入口。
- 是否开启智能校对、联网搜索、语音输入、知识库上传、事实核查。
- 素材上传格式、大小、并发。
- 文稿分类、素材类型、模板分类。
- SaaS 额度/通根数量。

### 2.4 axios 兼容层

clone 的 axios 实例要模拟现网行为：

```ts
headers = {
  'Geekseek-Authorization': localStorage.getItem('GEEKSEEK_USER_TOKEN') || '',
  'Geekseek-Language': 'zh-CN',
}
timeout = 1800000
```

响应形状统一使用：

```ts
interface ApiResponse<T> {
  result: number; // 0 表示成功
  data: T;
  msg?: string;
  message?: string;
}
```

响应拦截：

- `result === 0` 视为成功。
- `401` 或业务态未授权时跳转 `/logout` 或展示登录失效。
- `msg/message` 用于 Element Plus toast。

---

## 3. 页面功能规格

### 3.1 创作中心

主要区域：

- 左侧菜单：新建写作、创作中心、素材文稿、智能排版、文风模板、回收站。
- 开始创作：交互式创作、以稿写稿、模板创作、自由创作。
- 右上快捷入口：空白文稿创作、上传文稿创作。
- 素材文稿快捷卡：上传个人素材。
- 常用创作横向卡片：讲话稿、心得体会、工作报告、调研报告、通知、感谢信、会议纪要、年终总结、公众号文章、日报月报、培训心得等。
- 更多功能：智能排版、文风模板。
- 我的文稿：搜索、收藏筛选、知识管理筛选、分页、空态。

文稿卡动作：

- 收藏/取消收藏。
- 添加/取消添加到知识管理。
- 重命名。
- 导出 Word。
- 删除到回收站。

### 3.2 创作类型

分类枚举：

```text
SPEECH
REFLECTION
WORK_REPORT
RESEARCH_REPORT
NOTICE
THANK_YOU_LETTER
REFER_BASED_WRITING
FREE_WRITING
MEETING_SUMMARY
INDIVIDUAL_YEAR_END_REPORT
OFFICIAL_ACCOUNT_ARTICLE
DAILY_MONTHLY_REPORT
TRAINING_REFLECTION
QIANGGUO_ARTICLE
UPLOAD_TEMPLATE_WRITE
TEMPLATE_WRITE
```

多步向导类：

- 讲话稿、心得体会、工作报告、调研报告：交代 -> 参考 -> 提纲 -> 全文。
- 通知、感谢信：交代 -> 参考 -> 全文。

单步类：

- 自由创作、会议纪要、年终总结、公众号文章、日报月报、培训心得、强国文章、以稿写稿。

### 3.3 多步向导

步骤 1：交代

- 文本输入。
- 语音交代二维码。
- AI 优化交代。
- 联网搜索开关。
- 字数控制。
- 敏感词检查。

相关接口：

```text
POST /geekseek/aiwriter/article/v1/generateExplainQrCode
POST /geekseek/aiwriter/article/v1/checkSensitiveWord
POST /geekseek/aiwriter/article/v1/optimize
```

步骤 2：参考

- 从素材库、知识库、本地上传、历史记录添加参考。
- 智能推荐参考，基于交代内容做语义搜索。
- 选择参考文风。
- 支持点赞/点踩反馈。

相关接口：

```text
POST /geekseek/aiwriter/document/v2/semanticSearch
POST /geekseek/aiwriter/writingStyle/v1/downList
POST /geekseek/aiwriter/file/v2/upload
```

步骤 3：提纲

- 生成标题和提纲。
- 一级/二级标题模式。
- 添加、编辑、拖拽、删除节点。
- 对节点提出调整要求。
- 提纲敏感词检查。

相关接口：

```text
POST /geekseek/aiwriter/article/v1/outlineOrTitle/generateStream
POST /geekseek/aiwriter/article/v1/checkOutlineSensitiveWord
```

步骤 4：全文

- 进入 `/writer/content/chat/:docId`。
- 先获取构思摘要，再 SSE 生成全文。
- 完成后保存文稿、标点转换、引用溯源。

相关接口：

```text
POST /geekseek/aiwriter/article/v1/getExplainContent
POST /geekseek/aiwriter/article/v1/generate
POST /geekseek/aiwriter/document/v1/addOrUpdate
POST /geekseek/aiwriter/document/v1/convertPunctuation
POST /geekseek/aiwriter/article/v1/citationSource
POST /geekseek/aiwriter/article/v1/md2Html
```

### 3.4 Chat 生成页

状态机建议：

```text
idle -> explaining -> generating -> saving -> postProcessing -> done
                                   -> failed
                                   -> aborted
```

SSE 数据建议兼容：

- 普通 chunk：追加到 Markdown/HTML 缓冲区。
- `[DONE]`：结束生成。
- 失败事件：显示失败态并允许重新生成。
- 用户点击停止：AbortController 中断。

页面动作：

- 重新生成。
- 编辑文稿，跳转编辑器。
- 展示引用来源和生成说明。

### 3.5 编辑器

顶部：

- 返回面包屑。
- 标题 inline 编辑。
- 收藏/知识管理状态。
- 保存状态。
- 更多菜单：另存为模板、重置模板。
- 导出 Word/PDF。
- 保存按钮。

TinyMCE 工具栏：

```text
undo redo | blocks | fontfamily fontsize |
bold italic underline strikethrough |
forecolor backcolor |
alignleft aligncenter alignright alignjustify |
lineheight outdent indent |
removeformat code
```

字体：

```text
FangSong_GB2312
FZXiaoBiaoSong-B05S
JXBS
SimHei
KaiTi
KaiTi_GB2312
FZShuSong-Z01
FZMeiHei-M07S
Alimama ShuHeiTi
```

动态字体算法：

1. 从字体配置接口取得字体列表。
2. 检查 `document.fonts` 中是否已加载。
3. 构造 `/assets/font/{fontFileName}` URL。
4. `new FontFace(fontFamily, url, { display: 'swap' }).load()`。
5. 成功后 `document.fonts.add(fontFace)`。
6. 根据扩展名生成 `@font-face format(...)`。

自动保存：

- 编辑内容与标题变化后 debounce 保存，约 1000ms。
- 新文稿第一次保存成功后替换路由到编辑页。
- 保存体包含 `title`、`docId`、`content`、`saveType: HTML`、`category`、`documentType`。

右侧 AI 面板：

- 内容优化：润色、扩写、缩写、改写、解释、事实核查。
- 格式排版：通用格式、法定格式、自定格式。
- 智能校对：全文校对、建议列表、应用/忽略、导出。
- 小知 AI：对话输入、附件、个人资料、联网、事实核查、开启新对话。

### 3.6 素材文稿

频道：

```text
PERSONAL_MATERIAL
DEPARTMENT_KNOWLEDGE
REGIONAL_FILE
QIANGGUO_ARTICLE
KNOWLEDGE_UPLOAD_MATERIAL
KNOWLEDGE
WEB_SEARCH_MATERIAL
```

功能：

- 大搜索框。
- 素材类型筛选。
- 已添加知识管理筛选。
- 自主上传筛选。
- 文件类型/上传时间排序。
- 导入本地文件。
- 导入本地文件夹。
- 新建文件夹。
- 卡片收藏、添加知识管理、移动到文件夹、删除。
- 分页 12/24/36/48/60。

### 3.7 智能排版

上传限制：

- `materialType=SMART_LAYOUT_MATERIAL`
- 单文件。
- 最大 10MB。
- 支持 `.doc,.docx,.txt,.md,.wps`。

排版模板：

```text
POST /geekseek/aiwriter/format/template/list
GET  /geekseek/aiwriter/format/template/group/list
```

任务流：

```text
upload -> parse polling -> layout polling -> result card -> export/edit/delete
```

解析轮询：

```text
POST /geekseek/aiwriter/document/v2/getKbImportStatus
interval = 2000ms
stop when status in contentCompleted | summaryCompleted | completed | process_failed
```

排版轮询：

```text
POST /geekseek/aiwriter/document/v2/getSmartLayoutStatus
interval = 2000ms
layoutStatus = pending | success | failed
```

操作：

```text
POST /geekseek/aiwriter/smart/layout/v1/layout
POST /geekseek/aiwriter/smart/layout/v1/reLayout
POST /geekseek/aiwriter/smart/layout/v1/updateSmartLayout
POST /geekseek/aiwriter/smart/layout/v1/delete
POST /geekseek/aiwriter/document/v2/reParse
```

### 3.8 文风模板

列表：

- 搜索。
- 分页 10/20/50/100。
- 新建文风。
- 卡片显示训练进度或词云。
- hover 编辑/删除。

新建/编辑弹窗：

- 标题必填，最多 50 字。
- 素材 1-10 份。
- 素材来源：
  - 上传本地文稿。
  - 从素材库添加。
  - 从知识库添加。
  - 手动输入文本。
  - 从历史记录添加。

手动输入文本算法：

1. 输入文本不能为空。
2. 文件名取文本去掉换行和 tab 后的前 10 字。
3. 替换非法文件名字符 `[<>:"/\\|?*]` 为 `_`。
4. 后缀 `.txt`。
5. 用 Blob 生成 File。
6. 通过隐藏上传组件走 `WRITING_STYLE_MATERIAL` 上传。

文风训练：

```text
POST /geekseek/aiwriter/writingStyle/v1/add
POST /geekseek/aiwriter/writingStyle/v1/update
POST /geekseek/aiwriter/writingStyle/v1/query
GET  /geekseek/aiwriter/writingStyle/v1/detail
POST /geekseek/aiwriter/writingStyle/v1/pageList
POST /geekseek/aiwriter/writingStyle/v1/delete
POST /geekseek/aiwriter/writingStyle/v1/downList
```

状态：

```text
PENDING -> TRAINING -> READY
FAILED
progress: 0..100
```

clone 算法建议：

- 读取素材文本。
- 分词或按中文 2-4 字词频统计。
- 去除停用词和标点。
- 生成 `{ text, value }[]`。
- 用最高频词构造 `stylePrompt`，例如“行文正式、结构完整、偏公文表达、常用词包括...”。
- 前端 canvas/词云组件按 value 映射字体大小。

### 3.9 回收站

功能：

- 搜索。
- 卡片展示软删除文稿/素材。
- 恢复：`document/v1/recycle`，参数中 `delete=0`。
- 彻底删除：`document/v2/delete`。
- 批量全选/删除。

---

## 4. API 总表

### 4.1 用户与配置

```text
GET  /gdios/api/user/getMyInfo
GET  /gdios/api/setup/uiConfig
GET  /gdios/api/user/checkUserMsg
GET  /gdios/api/user/getCurrentUserMenuList
POST /gdios/api/service/userMembership/queryUsage
POST /gdios/api/user/sendUserSmsCode
POST /gdios/api/user/updateCurrentUser
POST /gdios/api/user/updateUserPassword
POST /gdios/api/user/updateUserProfession
GET  /geekseek/aiwriter/common/getUiConfig
GET  /geekseek/aiwriter/common/getWritingConfig
GET  /geekseek/aiwriter/module/list
```

### 4.2 文稿

```text
POST /geekseek/aiwriter/document/v1/list
GET  /geekseek/aiwriter/document/v1/detail?docId={id}&version={v}
POST /geekseek/aiwriter/document/v1/addOrUpdate
POST /geekseek/aiwriter/document/v1/categorySort
POST /geekseek/aiwriter/document/v1/addDocToKnowledge
POST /geekseek/aiwriter/document/v1/cancelAddDocToKnowledge
POST /geekseek/aiwriter/document/v1/recycle
POST /geekseek/aiwriter/document/v1/version/list
POST /geekseek/aiwriter/document/v1/addToPersonalMaterial
POST /geekseek/aiwriter/document/v1/convertPunctuation
POST /geekseek/aiwriter/document/v1/webSearch
POST /geekseek/aiwriter/document/source/getCitationSourceStatus
POST /geekseek/aiwriter/document/source/saveVersion
POST /geekseek/aiwriter/document/upload
POST /geekseek/aiwriter/document/writerTemplateUpload
```

### 4.3 素材与知识

```text
POST /geekseek/aiwriter/document/v2/list
GET  /geekseek/aiwriter/document/v2/detail?docId={id}&channel={ch}
POST /geekseek/aiwriter/document/v2/collect
POST /geekseek/aiwriter/document/v2/delete
POST /geekseek/aiwriter/document/v2/reParse
POST /geekseek/aiwriter/document/v2/semanticSearch
GET  /geekseek/aiwriter/document/v2/tag
POST /geekseek/aiwriter/document/v2/getKbImportStatus
POST /geekseek/aiwriter/document/v2/getSmartLayoutStatus
POST /geekseek/aiwriter/folder/v1/move
POST /geekseek/aiwriter/folder/v1/create
POST /geekseek/aiwriter/folder/v1/delete
POST /geekseek/aiwriter/folder/v1/rename
POST /geekseek/aiwriter/folder/v1/list
GET  /geekseek/aiwriter/knowledge/v1/*
GET  /geekseek/aiwriter/knowledge/v2/*
```

### 4.4 AI 文章与互动

```text
POST /geekseek/aiwriter/article/v1/getExplainContent
POST /geekseek/aiwriter/article/v1/generate
POST /geekseek/aiwriter/article/v1/generateExplainQrCode
POST /geekseek/aiwriter/article/v1/checkSensitiveWord
POST /geekseek/aiwriter/article/v1/checkOutlineSensitiveWord
POST /geekseek/aiwriter/article/v1/outlineOrTitle/generateStream
POST /geekseek/aiwriter/article/v1/optimize
POST /geekseek/aiwriter/article/v1/citationSource
POST /geekseek/aiwriter/article/v1/md2Html
POST /geekseek/aiwriter/interactive/chat/v1/*
```

### 4.5 文件、导出、预览

```text
POST /geekseek/aiwriter/file/v2/upload
POST /geekseek/aiwriter/file/storage/v1/upload
GET  /geekseek/aiwriter/file/v1/download?docId={id}
GET  /geekseek/aiwriter/file/v1/downloadPdf?docId={id}
GET  /geekseek/aiwriter/file/v2/download?taskUuid={id}
GET  /geekseek/aiwriter/file/storage/v1/download?fileId={id}
POST /geekseek/aiwriter/file/v1/createDownloadFileTask
POST /geekseek/aiwriter/file/v1/taskStatus
POST /geekseek/aiwriter/file/v1/cancelDownloadTask
GET  /geekseek/aiwriter/kkfile/preview
```

安全注意：现网有下载 URL 把 `Geekseek-Authorization` 放在 query 中的情况。clone 实现不要把 token 写入日志、浏览器历史或可分享链接。

### 4.6 排版、文风、校对、字体

```text
POST /geekseek/aiwriter/format/template/list
GET  /geekseek/aiwriter/format/template/group/list
POST /geekseek/aiwriter/smart/layout/v2/upload
POST /geekseek/aiwriter/smart/layout/v1/layout
POST /geekseek/aiwriter/smart/layout/v1/reLayout
POST /geekseek/aiwriter/smart/layout/v1/updateSmartLayout
POST /geekseek/aiwriter/smart/layout/v1/delete

POST /geekseek/aiwriter/writingStyle/v1/pageList
GET  /geekseek/aiwriter/writingStyle/v1/detail
POST /geekseek/aiwriter/writingStyle/v1/query
POST /geekseek/aiwriter/writingStyle/v1/add
POST /geekseek/aiwriter/writingStyle/v1/update
POST /geekseek/aiwriter/writingStyle/v1/delete
POST /geekseek/aiwriter/writingStyle/v1/downList

GET  /geekseek/aiwriter/text/correct/v1/getAbilityList
POST /geekseek/aiwriter/text/correct/v1/textCorrector
POST /geekseek/aiwriter/text/correct/v1/updateTextCorrectorItem
POST /geekseek/aiwriter/text/correct/v1/getTextCorrectorItemList
POST /geekseek/aiwriter/text/correct/v1/exportTextCorrectorItem

GET  /geekseek/aiwriter/font/config/getAllFontList
GET  /geekseek/aiwriter/font/config/getDocumentFont?docId={id}
GET  /geekseek/aiwriter/font/config/addFontCount?fontFamily={name}
```

---

## 5. 数据模型建议

### 5.1 Document

```ts
interface Document {
  docId: string;
  title: string;
  html: string;
  content: string;
  contentPart: string;
  category: string;
  documentType: 'CONTENT' | 'MATERIAL';
  collect: 0 | 1;
  importedKnowledge: boolean | 0 | 1 | '0' | '1';
  wordCount: number;
  version?: number;
  templateType?: string;
  fromSmartLayout?: 0 | 1;
  status?: 'pending' | 'processing' | 'contentCompleted' | 'summaryCompleted' | 'completed' | 'process_failed';
  layoutStatus?: 'pending' | 'success' | 'failed' | null;
  documentGenerationConfig?: DocumentGenerationConfig;
  createTime: string;
  updateTime: string;
  delete?: 0 | 1;
}
```

### 5.2 DocumentGenerationConfig

```ts
interface DocumentGenerationConfig {
  category: string;
  explain: string;
  title: string;
  refers: ReferenceItem[];
  outlineList: OutlineNode[];
  outlineMode: 'NONE' | 'FIRST_LEVEL' | 'SECOND_LEVEL';
  wordCount: number;
  writingStyleId?: string;
  webSearch?: boolean;
}
```

### 5.3 Material

```ts
interface Material {
  docId: string;
  title: string;
  filename: string;
  channel: string | number;
  materialType: string;
  source?: string;
  folderId?: string | number;
  tagIds?: string[];
  contentPart?: string;
  summary?: string;
  content?: string;
  wordCount: number;
  collect: 0 | 1;
  importedKnowledge: boolean | 0 | 1 | '0' | '1';
  status?: string;
  parseStatus?: string;
  createTime: string;
  updateTime: string;
}
```

### 5.4 WritingStyle

```ts
interface WritingStyle {
  id: string;
  name: string;
  status: 'PENDING' | 'TRAINING' | 'READY' | 'FAILED';
  progress: number;
  writingStyleDocList: Array<{
    docId: string;
    filename: string;
    channel: string | number;
    materialType?: string;
    content?: string;
    time?: string;
    uid?: string;
  }>;
  wordCloud: Array<{ text: string; value: number }>;
  stylePrompt: string;
  createTime: string;
  updateTime: string;
}
```

### 5.5 AsyncTask

```ts
interface AsyncTask {
  taskUuid: string;
  taskType: number | string;
  subjectId?: string;
  status: 'PENDING' | 'PROCESSING' | 'SUCCESS' | 'FAILED';
  progress: number;
  inputJson: unknown;
  outputJson?: unknown;
  errorMessage?: string;
  createTime: string;
  updateTime: string;
}
```

---

## 6. 服务端实现建议

建议拆分模块：

```text
auth/config
document
material
folder
file
exportTask
smartLayout
writingStyle
textCorrect
aiArticle
interactiveChat
font
template
```

必须优先做：

1. 统一响应结构和错误码。
2. 认证中间件兼容 `Geekseek-Authorization`。
3. 文稿 CRUD 和列表分页。
4. TinyMCE HTML 保存和读取。
5. 上传文件抽文本。
6. SSE 生成流。
7. 异步任务轮询。
8. Word/PDF 导出。

### 6.1 SSE 格式建议

```text
event: message
data: {"content":"...","status":"generating"}

event: done
data: [DONE]
```

也可兼容纯 `data: ...`。前端解析时应容忍：

- JSON chunk。
- 文本 chunk。
- `[DONE]`。
- 异常断流。

### 6.2 AI 生成算法替代

在没有现网私有模型/prompt 的情况下，本地 clone 可按下列策略实现：

- 模板化公文结构生成：标题、开头、主体、措施、结尾。
- 分类 prompt：不同 category 使用不同结构。
- 参考素材融合：提取素材摘要，按相似度插入段落。
- 文风融合：把 `stylePrompt` 作为系统/开发提示。
- 字数控制：按目标 wordCount 调节段落数和每段长度。
- 引用溯源：给引用段落打 `[n]` 标记，映射到 reference list。
- 标点转换：英文标点到中文全角标点、空格清理。

### 6.3 语义搜索算法替代

可本地实现：

1. 对交代文本和素材标题/摘要分词。
2. TF-IDF 或 BM25 打分。
3. 加权字段：标题 3，标签 2，摘要 1，正文 0.5。
4. 返回 topN，保留 `docId`、`channel`、`materialType`、`document`。

### 6.4 智能校对算法替代

先实现规则引擎：

- 敏感词字典。
- 常见错别字表。
- 重复标点、空格、英文标点。
- 公文格式词汇建议。
- 数字/单位格式。

返回建议：

```ts
interface CorrectItem {
  id: string;
  type: string;
  position: number;
  original: string;
  suggestion: string;
  reason: string;
  status: 'pending' | 'accepted' | 'ignored';
}
```

### 6.5 智能排版算法替代

实现步骤：

1. 上传文件抽取纯文本和基础段落。
2. 识别标题、一级标题、二级标题、正文、落款、日期。
3. 根据模板配置映射字体、字号、行距、缩进。
4. 生成 HTML 供 TinyMCE 展示。
5. 导出时转换为 DOCX/PDF。

模板配置建议：

```ts
interface FormatTemplate {
  id: string;
  name: string;
  group: 'common' | 'legal' | 'custom';
  config: {
    title: TextStyle;
    heading1: TextStyle;
    heading2: TextStyle;
    paragraph: TextStyle;
    page: PageStyle;
  };
}
```

---

## 7. 开发优先级

### P0：可进入、可保存、可展示

- 应用壳、侧边栏、路由。
- 初始化接口。
- 文稿列表、空态、分页。
- 新建空白文稿。
- 编辑器加载和保存。
- 基础上传和素材列表。

### P1：核心业务闭环

- 交互式创作四步。
- SSE 生成全文。
- 引用溯源基础实现。
- 导出 Word/PDF 任务。
- 回收站。
- 素材 channel、搜索、收藏、知识管理。

### P2：高级能力

- 智能排版完整任务流。
- 文风模板 CRUD、训练进度、词云。
- 内容优化。
- 智能校对。
- 文件夹 CRUD。

### P3：增强体验

- 小知 AI 多轮对话。
- 微信语音交代。
- kkFileView 预览。
- 个人中心、短信、额度、会员。
- 多语言和部署模式。

---

## 8. 验收清单

- 首页所有入口可见、可跳转。
- 初始化接口不会报错。
- 没有 token 时进入登录/降级态，有 token 时加载用户信息。
- 文稿可新建、保存、重命名、删除、恢复、彻底删除。
- 编辑器可加载 HTML，字体/字号/行距/缩进可用。
- Word/PDF 导出任务可创建、轮询、下载。
- 上传素材后可解析、列表展示、搜索、移动文件夹。
- 智能排版有上传、模板选择、解析中、排版中、成功、失败、重新解析、重新排版、导出。
- 文风模板有新增、编辑、删除、训练进度、词云、写作时下拉选择。
- 内容优化支持选中文本、返回结果、插入、替换、重新生成。
- 校对支持全文检查、定位、应用、忽略、导出。
- SSE 生成可停止、失败重试、完成保存。
- NetLog 或其他调试文件中的认证头不会被写入日志或提交。

---

## 9. 已知缺口与风险

- 真实后端私有 prompt、模型、训练语料不可见，只能行为兼容。
- 以稿写稿 `REFER_BASED_WRITING` 的完整请求体仍需进一步抓包。
- 文件夹 create/delete/rename/list 已由前端行为和文案推断，但仍需实测请求体。
- 知识库 tab 的 v1/v2 具体接口尚未完全拆开。
- 部分懒加载 chunk 在当前 Chrome 会话中出现加载/缓存失败，后续需重新抓取完整 bundle。
- 当前 `chrome-net-export-log.json` 含认证头和 token query，必须本地保管，禁止提交到公开仓库。
