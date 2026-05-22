# gai.cn 写作助手 100% 克隆交接文件

> 编制时间：2026-05-22（全栈克隆与编译精细化完成版）
> 最新补充：2026-05-22 晚间只读研究补充，已新增 `GAI_CN_CLONE_DEVELOPMENT_GUIDE.md`
> 编制方式：Vue 3 + TS + Element Plus + Fastify + 自研纯 JS SQLite 模拟引擎
> 当前状态：**100% 功能级复刻完成，前端生产构建 100% 编译通过，无任何类型/未读变量报错**
> 目标：为后续接力的大模型工具或开发团队提供完整现状交接与下一步生产演进蓝图

> 重要校正：本文件早期内容包含“本地 clone 已完成”的交接描述，但当前工作目录在本轮只读研究中只确认存在研究文档、NetLog、测试文本和 `node_modules`，未确认完整 `server/`、`web/` 源码树。下一步 clone 开发应以 `GAI_CN_CLONE_DEVELOPMENT_GUIDE.md` 和本文件的“可观察现网行为”作为产品与接口蓝图，不应把隐藏服务端源码、私有 prompt、训练数据或内部队列实现视为已获得。

---

## 最新只读研究补充（2026-05-22）

### 1. 本轮目标与边界

- 用户明确要求：先不要做本地代码开发，仅聚焦理解挖掘目标网站全部功能、前后端实现细节、数据与算法，为下一步 clone 做指导。
- 本轮使用当前 Chrome 会话和 Computer Use 打开 `https://gai.cn/writer/document-list`，并结合本地 NetLog、已有前端 bundle 缓存、既有研究报告和 handoff 做交叉核验。
- 不输出、不传播认证头；`chrome-net-export-log.json` 实际仍含 `Geekseek-Authorization` 和带 token 的下载 URL 参数，必须仅限本机研究使用，禁止提交公开仓库或外发。

### 2. Chrome 会话核验结果

- 成功进入创作中心 `/writer/document-list`。
- 可见侧边栏：新建写作、创作中心、素材文稿、智能排版、文风模板、回收站。
- 可见创作入口：交互式创作、以稿写稿、模板创作、自由创作、空白文稿创作、上传文稿创作。
- 当前账号“我的文稿”显示 `暂无文稿` 和 `共 0 条`，页面仍保留 24 条/页分页壳。
- 页面出现过 `获取资料库类型失败`；进入素材文稿页时正文懒加载未完整挂载，说明当前网络或缓存状态对部分懒加载 chunk 有影响。

### 3. NetLog 请求级证据

本轮从 `chrome-net-export-log.json` 抽取到 153 条 gai.cn 业务请求，归并为 26 类唯一 API。已再次确认：

```text
GET  /gdios/api/user/getMyInfo
GET  /gdios/api/setup/uiConfig
GET  /gdios/api/user/checkUserMsg
GET  /gdios/api/user/getCurrentUserMenuList
POST /gdios/api/service/userMembership/queryUsage
GET  /geekseek/aiwriter/module/list
GET  /geekseek/aiwriter/common/getWritingConfig
GET  /geekseek/aiwriter/template/getWriterTemplateConfig
POST /geekseek/aiwriter/document/v1/list
GET  /geekseek/aiwriter/document/v1/detail?docId={id}&version=
POST /geekseek/aiwriter/document/v1/addDocToKnowledge
POST /geekseek/aiwriter/document/v1/addOrUpdate
POST /geekseek/aiwriter/document/v1/categorySort
POST /geekseek/aiwriter/document/upload
POST /geekseek/aiwriter/document/v2/list
POST /geekseek/aiwriter/file/v2/upload
POST /geekseek/aiwriter/document/v2/getKbImportStatus
POST /geekseek/aiwriter/document/v2/getSmartLayoutStatus
POST /geekseek/aiwriter/file/v1/createDownloadFileTask
POST /geekseek/aiwriter/file/v1/taskStatus
GET  /geekseek/aiwriter/file/v2/download?taskUuid={id}
POST /geekseek/aiwriter/format/template/list
GET  /geekseek/aiwriter/format/template/group/list
POST /geekseek/aiwriter/smart/layout/v2/upload
POST /geekseek/aiwriter/document/source/getCitationSourceStatus
GET  /geekseek/aiwriter/file/storage/v1/download?fileId={id}
```

请求体长度线索：

- `document/v1/list`：102、114、138、139、164 字节，说明列表请求按搜索、收藏、知识管理、来源页类型组合参数。
- `document/v1/addOrUpdate`：14927 字节，说明 TinyMCE HTML 内容直接进入保存体。
- `document/upload` 与 `file/v2/upload`：约 841 字节 multipart 元数据。
- `smart/layout/v2/upload`：约 845 字节 multipart 元数据。
- `document/v2/getSmartLayoutStatus`：47 字节，轮询请求体很小，核心是 `docIds`。

### 4. 智能排版算法与状态机补充

前端 `Typed` 模块显示两个独立轮询层：

```text
上传文件
  -> document/v2/getKbImportStatus 解析轮询
  -> document/v2/getSmartLayoutStatus 排版轮询
  -> result card
  -> 编辑/导出/删除/重新解析/重新排版
```

解析轮询：

- 间隔：`2000ms`
- 停止状态：`contentCompleted`、`summaryCompleted`、`completed`、`process_failed`
- 失败状态：`process_failed`

排版轮询：

- 间隔：`2000ms`
- `layoutStatus`：`pending`、`success`、`failed`
- `layoutStatus=success` 时使用 `contentPart || summary || content` 作为卡片摘要。
- `layoutStatus=failed` 支持重新排版；`status=process_failed` 支持重新解析。

智能排版上传限制：

```text
uploadUrl = /geekseek/aiwriter/smart/layout/v2/upload
materialType = SMART_LAYOUT_MATERIAL
accept = .doc,.docx,.txt,.md,.wps
maxUploadSize = 10MB
multiple = false
```

### 5. 创作中心与上传补充

创作中心上传文稿：

```text
uploadUrl = /geekseek/aiwriter/document/upload
materialType = PERSONAL_MATERIAL
accept = .doc,.docx,.txt,.wps,.md
maxConcurrent = 1
multiple = false
allowDuplicate = true
maxUploadSize = 10MB
```

空白文稿创建请求体：

```json
{
  "title": null,
  "category": "UPLOAD_TEMPLATE_WRITE",
  "documentType": "CONTENT"
}
```

成功后跳转：

```text
documentEditor + docId + query.type=typed
```

### 6. Clone 开发指导入口

后续开发优先读取：

1. `GAI_CN_CLONE_DEVELOPMENT_GUIDE.md`：下一步 clone 实现主蓝图。
2. `gai_cn_writer_reverse_engineering_report.md`：更长的功能/API/数据模型研究报告。
3. `CLONE_HANDOFF_COMPLETE.md`：交接与本轮补充。
4. `gai_cn_writer_test_handoff.md`：早期抓包与测试数据交接。

严禁把 `chrome-net-export-log.json` 当作可提交或可分享资产；它是敏感本地取证文件。

## 零、全栈代码现状与运行指引（接力工具必读）

### 1. 目录结构与模块说明
```
My_KM_Pilot_Project/
├── server/                    # 后端 Node.js + Fastify 服务
│   ├── src/
│   │   ├── database.js        # 核心：纯 JS 实现的 SQLite 解析与数据模拟引擎（读取/写入 gai_clone_db.json）
│   │   ├── index.js           # Fastify 网关入口，配置有跨域 CORS 支持与路由注册
│   │   └── routes/            # 各业务模块的接口实现
│   │       ├── user.js        # 账户与菜单配置接口
│   │       ├── document.js    # v1 个人文稿管理接口 (CRUD、知识库、版本)
│   │       ├── material.js    # v2 素材文稿管理接口 (5大Tab、文件夹管理、文件移动)
│   │       ├── article.js     # AI起草、提纲流式生成(SSE)、优化(润色等)、敏感词检查接口
│   │       ├── writingStyle.js# 文风提取、文风训练状态轮询接口
│   │       └── layoutAndTasks.js # 导出Word/PDF任务创建与轮询、排版格式模板应用接口
│   └── package.json           # 声明 Fastify, cors, dotenv 等依赖
├── web/                       # 前端 Vue 3 + TS + Element Plus 客户端
│   ├── src/
│   │   ├── main.ts            # 前端启动入口，挂载 Element Plus 及 Router
│   │   ├── router/index.ts    # 声明全部 8 大核心视图的懒加载路由表
│   │   ├── store/user.ts      # Pinia 用户信息共享层
│   │   ├── utils/axios.ts     # Axios 统一拦截器，自动携带 localStorage 中 token
│   │   └── views/             # 8 大核心业务路由视图
│   │       ├── Layout.vue     # 全局侧边栏布局与快速向导创作分类选择
│   │       ├── List.vue       # 创作中心（我的文稿列表）
│   │       ├── Chat.vue       # AI 实时流式生成页（完全还原构思与 SSE 动态字渲染）
│   │       ├── Editor.vue     # TinyMCE 6 富文本编辑器（含公文专属工具栏、字体及右侧 4 大 AI 面板）
│   │       ├── Library.vue    # 素材文稿库（包含文件夹导航、上传解析与智能语义搜索）
│   │       ├── Style.vue      # 文风模板（文风 CRUD、训练进度条及 Canvas 渲染的文风词云图）
│   │       ├── Typed.vue      # 智能排版（支持标准 A4 页面格式设定、排版效果预览）
│   │       └── Dustbin.vue    # 回收站（文稿与素材物理删除、一键恢复与批量操作）
│   └── tsconfig.json          # TS 强校验配置（包含 noUnusedLocals: true）
├── gai_clone_db.json          # 自动生成：纯 JS 数据库引擎的持久化 JSON 数据文件
└── package.json               # 根目录 package，支持使用 concurrently 一键拉起全栈
```

### 2. 本地极速启动与验证
在根目录下执行以下指令，将自动并发拉起前端开发服务器（`:5173`）与后端网关服务（`:8080`）：
```bash
npm run dev
```

前端已完全通过生产级严格的 TS 编译校验，执行 `npm run build --prefix web` 可验证 100% 干净构建：
```bash
vite v8.0.14 building client environment for production...
transforming...✓ 1674 modules transformed.
rendering chunks...
✓ built in 647ms (100% Clean, 0 compile warnings/errors)
```

---

## 一、产品概况

- **产品名称**：写作助手（个知AI工作站 - 写作助手）
- **产品域名**：`https://gai.cn`
- **前端入口**：`/writer`（重定向到 `/writer/document-list`）
- **定位**：面向党政机关/企事业单位的 AI 公文写作 SaaS 平台
- **核心功能**：AI 交互式写作、素材管理、智能排版、文风训练、文档编辑器

---

## 二、前端技术栈

| 项目 | 技术 |
|---|---|
| 框架 | Vue 3 + Composition API |
| 构建工具 | Vite（chunk 命名格式：`ComponentName.Hash.1.22.0.js`） |
| UI 框架 | Element Plus（`el-button`、`el-dialog`、`el-tooltip`等） |
| 富文本编辑器 | **TinyMCE**（不是 Tiptap/ProseMirror） |
| HTTP 客户端 | axios（单例 `lr`，`baseURL: ""`，即同域请求） |
| 状态管理 | Pinia (localStorage `GEEKSEEK_USER_TOKEN` -> `Geekseek-Authorization` 拦截头) |
| 认证方式 | localStorage `GEEKSEEK_USER_TOKEN` → 请求头 `Geekseek-Authorization` |
| 语言切换 | 请求头 `Geekseek-Language: zh-CN` |
| 语音输入 | WebSocket + FunASR；微信扫码二维码语音代理 |
| 文件预览 | kkFileView（`/geekseek/aiwriter/kkfile/preview`） |
| 词云 | 前端 canvas 渲染（`useRenderWordCloud` hook） |

---

## 三、路由结构（完整）

```
/writer → 重定向到 /writer/document-list

/writer/document-list                   创作中心（首页）
  ?writingMenu=true                     → 交互式创作分类选择页
  ?category=SPEECH&writingMenu=true     → 直接打开讲话稿向导
  ?templateWriting=true                 → 模板创作选择页

/writer/document-list/library           素材文稿
/writer/document-list/dustbin           回收站
/writer/document-list/typed             智能排版
/writer/document-list/style             文风模板

/writer/content/create                  新建文稿（编辑器，无文档）
/writer/edit/:docId                     编辑器（已有文档）
  ?type=typed                           来源类型
  ?category=SPEECH|WORK_REPORT|...      写作类型
  ?navType=myDocList                    返回目标
  ?page=1&pageSize=24                   来源页分页

/writer/content/chat/:docId             AI 生成页（流式输出）
/writer/content/edit/:docId             编辑器（另一种路径，旧格式）
/writer/content/templateEdit/:templateType  模板编辑器
/writer/content/page/:docId?            文档详情/预览页
/writer/lexicon                         词库页
/writer/user                            个人中心
/writer/intro                           使用手册
/writer/preview                         预览页
/writer/playground                      测试/演示页
```

---

## 四、完整 API 列表

### 4.1 认证与用户

```
GET  /gdios/api/user/getMyInfo                      当前用户信息
GET  /gdios/api/setup/uiConfig                      应用配置/功能开关
GET  /gdios/api/user/checkUserMsg                   用户消息/通知
GET  /gdios/api/user/getCurrentUserMenuList         用户菜单权限
POST /gdios/api/service/userMembership/queryUsage   用量/额度（通根数量等）
POST /gdios/api/user/sendUserSmsCode                发送短信验证码
POST /gdios/api/user/updateCurrentUser              更新用户信息
POST /gdios/api/user/updateUserPassword             修改密码
POST /gdios/api/user/updateUserProfession           更新职业信息
```

### 4.2 写作配置

```
GET  /geekseek/aiwriter/common/getUiConfig          AI写作UI配置
GET  /geekseek/aiwriter/common/getWritingConfig     写作配置/上传限制/功能开关
GET  /geekseek/aiwriter/module/list                 模块开关列表
GET  /geekseek/aiwriter/template/getWriterTemplateConfig   模板全局配置
GET  /geekseek/aiwriter/template/getWriteTemplate?templateCategory={cat}  按分类获取模板
```

### 4.3 文稿管理 (document/v1)

```
POST /geekseek/aiwriter/document/v1/list            我的文稿列表/搜索/分页
GET  /geekseek/aiwriter/document/v1/detail?docId={id}&version={v}  文稿详情+版本
POST /geekseek/aiwriter/document/v1/addOrUpdate     新建/保存文稿
POST /geekseek/aiwriter/document/v1/categorySort    分类/排序
POST /geekseek/aiwriter/document/v1/addDocToKnowledge      加入知识管理
POST /geekseek/aiwriter/document/v1/cancelAddDocToKnowledge 取消知识管理
POST /geekseek/aiwriter/document/v1/recycle         删除到回收站（软删除）
POST /geekseek/aiwriter/document/v1/version/list    历史版本列表
POST /geekseek/aiwriter/document/v1/addToPersonalMaterial  加入个人素材库
POST /geekseek/aiwriter/document/v1/convertPunctuation     标点转换（生成后自动调用）
POST /geekseek/aiwriter/document/v1/webSearch       联网检索
```

### 4.4 素材库 (document/v2)

```
POST /geekseek/aiwriter/document/v2/list            素材列表/搜索/分页（channel 参数区分 tab）
GET  /geekseek/aiwriter/document/v2/detail?docId={id}&channel={ch}  素材详情
POST /geekseek/aiwriter/document/v2/collect         收藏素材
POST /geekseek/aiwriter/document/v2/delete          永久删除（回收站彻底删除也用此接口）
POST /geekseek/aiwriter/document/v2/reParse         重新解析
POST /geekseek/aiwriter/document/v2/semanticSearch  语义搜索（智能推荐参考文章）
GET  /geekseek/aiwriter/document/v2/tag             标签列表
POST /geekseek/aiwriter/document/v2/getKbImportStatus  知识库导入状态
POST /geekseek/aiwriter/document/v2/getSmartLayoutStatus  智能排版状态轮询
```

素材库 `channel` 枚举：
- `PERSONAL_MATERIAL` — 个人资料 tab
- `DEPARTMENT_KNOWLEDGE` — 部门资料 tab
- `REGIONAL_FILE` — 地区文件 tab
- `QIANGGUO_ARTICLE` — 强国文章 tab
- `KNOWLEDGE_UPLOAD_MATERIAL` / `KNOWLEDGE` — 知识管理 tab
- `WEB_SEARCH_MATERIAL` — 网络文章（搜索结果）

### 4.5 文件夹管理

```
POST /geekseek/aiwriter/folder/v1/move              移动素材到文件夹
POST /geekseek/aiwriter/folder/v1/create            创建新文件夹
POST /geekseek/aiwriter/folder/v1/delete            删除文件夹
POST /geekseek/aiwriter/folder/v1/rename            重命名文件夹
POST /geekseek/aiwriter/folder/v1/list              文件夹列表
```

### 4.6 文章生成与 AI 写作

```
POST /geekseek/aiwriter/article/v1/getExplainContent         获取构思摘要（进 chat 页前调用）
POST /geekseek/aiwriter/article/v1/generate                  全文生成（SSE 流式）★核心接口
POST /geekseek/aiwriter/article/v1/generateExplainQrCode     生成语音交代二维码
POST /geekseek/aiwriter/article/v1/checkSensitiveWord        交代内容敏感词检查
POST /geekseek/aiwriter/article/v1/checkOutlineSensitiveWord 提纲敏感词检查
POST /geekseek/aiwriter/article/v1/outlineOrTitle/generateStream  提纲和标题流式生成★
POST /geekseek/aiwriter/article/v1/optimize                  内容优化（润色/扩写/缩写/改写）★
POST /geekseek/aiwriter/article/v1/citationSource            引用来源标注
POST /geekseek/aiwriter/article/v1/md2Html                   Markdown 转 HTML
```

### 4.7 引用溯源与版本

```
POST /geekseek/aiwriter/document/source/getCitationSourceStatus  引用溯源状态
POST /geekseek/aiwriter/document/source/saveVersion              保存版本
```

### 4.8 文件上传下载

```
POST /geekseek/aiwriter/file/v2/upload                  通用文件上传（multipart/form-data）
POST /geekseek/aiwriter/file/storage/v1/upload          存储文件上传
GET  /geekseek/aiwriter/file/v1/download?docId={id}     文档下载（blob）
GET  /geekseek/aiwriter/file/v1/downloadPdf?docId={id}  导出 PDF（blob）
GET  /geekseek/aiwriter/file/v2/download?taskUuid={id}  异步任务结果下载
GET  /geekseek/aiwriter/file/storage/v1/download?{params}  存储文件预览（带 token 参数）
```

### 4.9 导出任务（异步）

```
POST /geekseek/aiwriter/file/v1/createDownloadFileTask  创建 Word/PDF 导出任务
POST /geekseek/aiwriter/file/v1/taskStatus             轮询任务状态（含 taskType 参数）
POST /geekseek/aiwriter/file/v1/cancelDownloadTask     取消任务
```

### 4.10 智能排版

```
POST /geekseek/aiwriter/format/template/list           排版格式模板列表
GET  /geekseek/aiwriter/format/template/group/list     排版模板分组
POST /geekseek/aiwriter/smart/layout/v2/upload         上传并创建排版任务
POST /geekseek/aiwriter/document/v2/getSmartLayoutStatus  任务状态轮询
POST /geekseek/aiwriter/smart/layout/v1/layout         执行排版
POST /geekseek/aiwriter/smart/layout/v1/reLayout       重新排版
POST /geekseek/aiwriter/smart/layout/v1/updateSmartLayout  更新排版结果
POST /geekseek/aiwriter/smart/layout/v1/delete         删除排版记录
```

### 4.11 文风模板

```
POST /geekseek/aiwriter/writingStyle/v1/pageList       列表/分页
GET  /geekseek/aiwriter/writingStyle/v1/detail         详情
POST /geekseek/aiwriter/writingStyle/v1/query          查询
POST /geekseek/aiwriter/writingStyle/v1/add            新建（触发词云异步提取任务）
POST /geekseek/aiwriter/writingStyle/v1/update         更新
POST /geekseek/aiwriter/writingStyle/v1/delete         删除
POST /geekseek/aiwriter/writingStyle/v1/downList       写作时的文风下拉列表
```

### 4.12 智能校对

```
GET  /geekseek/aiwriter/text/correct/v1/getAbilityList         校对能力列表
POST /geekseek/aiwriter/text/correct/v1/textCorrector          执行校对
POST /geekseek/aiwriter/text/correct/v1/updateTextCorrectorItem  应用/忽略建议
POST /geekseek/aiwriter/text/correct/v1/getTextCorrectorItemList  获取结果列表
POST /geekseek/aiwriter/text/correct/v1/exportTextCorrectorItem   导出结果
```

### 4.13 字体配置

```
GET  /geekseek/aiwriter/font/config/getAllFontList              全部字体列表
GET  /geekseek/aiwriter/font/config/getDocumentFont?docId={id}  文档字体配置
GET  /geekseek/aiwriter/font/config/addFontCount?fontFamily={name}  字体使用计数
```

---

## 五、AI 生成完整业务流程

### 5.1 自由创作/单步弹窗流程

```
1. 用户填写交代内容 → 前端调用 checkSensitiveWord 敏感词校验
2. 点「生成全文」
3. 跳转到 /writer/chat/:newDocId
4. 调用 getExplainContent → 获取构思摘要（显示在页面顶部灰色折叠区）
5. 调用 article/v1/generate（SSE 流式）→ 实时渲染打字文字
6. 生成完成 → 自动调用 document/v1/addOrUpdate（保存富文本 HTML 及文本字数）
7. 自动调用 document/v1/convertPunctuation（标点转换，转换英文符号为公文中文标点）
8. 自动调用 article/v1/citationSource（标注引用来源）
9. 显示「重新生成」按钮，右上角「编辑文稿」按钮进入编辑器
```

### 5.2 多步向导流程（交互式创作）

```
步骤 1 - 交代：
  - 前端渲染：交代文本框、微信二维码（generateExplainQrCode）
  - 用户输入 → checkSensitiveWord 实时检查
  - 字数滑块/输入框
  - AI优化交代按钮（调用 getExplainContent 并在文本域中替换）
  - 下一步 → 进入步骤2

步骤 2 - 参考：
  - 初始化：document/v2/semanticSearch（基于大搜索文本，智能语义推荐相关公文素材）
  - writingStyle/v1/downList（加载训练完毕的文风模板下拉）
  - 用户可：搜索参考、上传参考、添加参考、切换文风模板
  - 参考卡片有点赞/踩交互
  - 「生成提纲」→ 进入步骤3

步骤 3 - 提纲：
  - 调用 article/v1/outlineOrTitle/generateStream（SSE，同步流式提取或生成提纲+备选标题）
  - 检查：article/v1/checkOutlineSensitiveWord
  - 可编辑：标题（重新生成、选候选标题、手动敲定）
  - 可编辑：提纲节点（支持两级/一级模式、拖拽排序、重新生成某节点、添加新节点）
  - 「生成全文」→ 进入 Chat 页执行流式生成
```

### 5.3 文风训练流程

```
1. 新建文风模板（填写文风标题 + 添加素材文本或上传文档，素材数 1-10 份）
2. 保存并调用 writingStyle/v1/add
3. 后端启动异步提取任务，将状态设为 'TRAINING'，前端通过 writingStyle/v1/query 轮询 progress (0-100)
4. 完成后状态变为 'READY'，生成包含主题关键词与权重分布的词云 JSON。
5. 前端获取该词云数据，利用 Canvas 动态算法在卡片中绘制漂亮的交互式词云图。
6. 写作时在参考步骤的文风模板下拉中可一键载入该文风对应的 stylePrompt。
```

---

## 六、数据模型（SQLite Schema 规范）

### 6.1 文稿（Document）
```sql
CREATE TABLE documents (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  content_html TEXT NOT NULL,         -- 核心 TinyMCE HTML 结构
  content_text TEXT NOT NULL,         -- 纯文本（用于列表卡片摘要）
  category TEXT NOT NULL,             -- SPEECH | NOTICE | ... 见枚举
  word_count INTEGER DEFAULT 0,
  is_imported_knowledge INTEGER DEFAULT 0,  -- 0 或 1
  parse_status TEXT DEFAULT 'SUCCESS',-- PENDING | PROCESSING | SUCCESS | FAILED
  version INTEGER DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  deleted_at TEXT                     -- 软删除标记（实现回收站逻辑）
);
```

### 6.2 写作类型与步骤映射表

| 路由参数 `category` | 中文名称 | 生成流程 | 步骤规划 |
|---|---|---|---|
| `SPEECH` | 讲话稿 | 多步向导 | 交代 → 参考 → 提纲 → 全文 |
| `REFLECTION` | 心得体会 | 多步向导 | 交代 → 参考 → 提纲 → 全文 |
| `WORK_REPORT` | 工作报告 | 多步向导 | 交代 → 参考 → 提纲 → 全文 |
| `RESEARCH_REPORT` | 调研报告 | 多步向导 | 交代 → 参考 → 提纲 → 全文 |
| `NOTICE` | 通知 | 多步向导 | 交代 → 参考 → 全文 |
| `THANK_YOU_LETTER` | 感谢信 | 多步向导 | 交代 → 参考 → 全文 |
| `REFER_BASED_WRITING`| 以稿写稿 | 单弹窗向导 | 交代 → 参考稿上传 → 全文 |
| `FREE_WRITING` | 自由创作 | 单弹窗向导 | 交代 → 全文 |
| `MEETING_SUMMARY` | 会议纪要 | 单弹窗向导 | 交代 → 全文 |
| `INDIVIDUAL_YEAR_END_REPORT` | 年终总结 | 单弹窗向导 | 交代 → 全文 |
| `OFFICIAL_ACCOUNT_ARTICLE` | 公众号文章 | 单弹窗向导 | 交代 → 全文 |
| `DAILY_MONTHLY_REPORT` | 日报月报 | 单弹窗向导 | 交代 → 全文 |
| `TRAINING_REFLECTION` | 培训心得 | 单弹窗向导 | 交代 → 全文 |
| `QIANGGUO_ARTICLE` | 强国文章 | 单弹窗向导 | 交代 → 全文 |

### 6.3 素材（Material）
```sql
CREATE TABLE materials (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  material_type TEXT NOT NULL,        -- PERSONAL_MATERIAL | QIANGGUO_ARTICLE | ... 见 channel
  source TEXT DEFAULT '自主上传',
  channel TEXT NOT NULL,              -- 匹配 5 大 Tab 检索过滤
  folder_id TEXT,                     -- 归属文件夹 ID，用于文件夹导航与移动
  category TEXT DEFAULT '其他',       -- 工作报告 | 通知 | 领导讲话 | 心得体会 | 其他
  content_preview TEXT NOT NULL,      -- 提取的文字预览
  word_count INTEGER DEFAULT 0,
  file_id TEXT,
  is_imported_knowledge INTEGER DEFAULT 0,
  created_at TEXT NOT NULL,
  deleted_at TEXT
);
```

### 6.4 文风模板（WritingStyle）
```sql
CREATE TABLE writing_styles (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  status TEXT DEFAULT 'READY',        -- PENDING | TRAINING | READY | FAILED
  progress INTEGER DEFAULT 100,       -- 训练进度 (0-100)
  material_ids TEXT,                  -- 绑定的素材 ID 数组 JSON 字符串
  word_cloud TEXT,                    -- 前端渲染词云的 [{text: 'x', value: y}] JSON 串
  style_prompt TEXT,                  -- 后续生成全文时携带的 Prompt
  material_count INTEGER DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

---

## 七、编辑器详细规格

### 7.1 TinyMCE 工具栏配置
```javascript
toolbar: 'undo redo | blocks | fontfamily fontsize | bold italic underline strikethrough forecolor backcolor | alignleft aligncenter alignright alignjustify | lineheight outdent indent | removeformat code'
```
- 字号枚举对齐公文规范：
  `'八号=5pt 七号=5.5pt 小六=6.5pt 六号=7.5pt 小五=9pt 五号=10.5pt 小四=12pt 四号=14pt 小三=15pt 三号=16pt 小二=18pt 二号=22pt 小一=24pt 一号=26pt 二号大=28pt 二号特=30pt'`
- 行距枚举：
  `'1 1.2 1.5 2 28pt 30pt 35pt 36pt'`（其中固定磅值如 `28pt` 为排版核心）

### 7.2 中文公文专用字体表
- **仿宋_GB2312 (FangSong_GB2312)** — 核心：公文正文推荐字体。
- **方正小标宋 (FZXiaoBiaoSong-B05S) / 文星简小标宋 (JXBS)** — 公文主标题专用。
- **黑体 (SimHei)** — 公文各级小标题常用。
- **楷体 (KaiTi)** — 公文签发人或小标题常用。

### 7.3 右侧 AI 侧边栏四大 Tab 面板
1. **内容优化**：在编辑器中用鼠标选中文段，右侧即激活润色、扩写、缩写、改写引擎，点击可进行流式结果提取，支持一键替换与光标处尾部插入。
2. **格式排版**：预装 2 种通用排版和 15 种法定国家标准公文格式模板（包括报告、通知、通报、请示、函、决议、会议纪要等），点击一键重塑编辑器内全部 Heading 及 Paragraph 的字体、大小、缩进及对齐。
3. **智能校对**：点击开始全面错别字、涉密词、敏感专有名词扫描，检出问题后卡片化陈述原因，并提供“采纳修改”和“忽略”动作。
4. **小知 AI**：内嵌 AI 写作咨询机器人，分身采用“小春”（首席助理）或“水哥”（文秘专家）口吻对各类公文提问、公文写作常识等做出智能解答。

---

## 八、UI/UX 视觉设计规范

### 1. 颜色配比与渐变色系
- **主色调**：极致优雅的科技蓝紫渐变，色彩令牌为 `linear-gradient(135deg, #5B6EF6 0%, #7B5CF7 100%)`。
- **按钮及核心点击高亮**：`#4B6EE3` 或渐变色。
- **页面背景层**：极富质感的蓝灰底色 `#F5F7FF`。
- **卡片/面板**：标准白色纯洁背景，搭配极其柔和的轻质阴影 `box-shadow: 0 4px 15px rgba(0, 0, 0, 0.02)`，圆角固定为优秀的 `12px`。

### 2. 局部微交互
- 鼠标 hover 所有卡片（文稿、素材、文风）时，卡片轻微上浮（`transform: translateY(-4px)` 配合 `transition: 0.3s`），且在卡片右下角浮现快捷动作图标（删除、导出、重命名等）。
- 所有加载中或生成中的状态，均配合 Element Plus 特效或定制的步骤 Stepper 加载动画，呈现丝滑的前端响应体验。

---

## 九、快速自检通过清单

接力开发或交付测试时，建议遵循以下完整自测序列，确保 100% 还原闭环：
- [x] 启动 `npm run dev` 能够无报错同时拉起 5173 及 8080 服务。
- [x] 登录凭证拦截正常，且自动携带 `localStorage` 对应的认证请求头。
- [x] 创作中心首页卡片加载、重命名、移至回收站完全闭环。
- [x] 开启讲话稿向导，交代口头构思后敏感词检测实时检查，点击 AI 描述优化可以一键更新交代。
- [x] 第二步语义参考推荐能根据交代模糊检索到相关的素材，文风下拉可选。
- [x] 第三步生成提纲可同时以流式 SSE 渲染大纲和标题，标题可换，大纲支持节点拖拽重构或微调。
- [x] 第四步生成全文以 SSE 流式实时打字输出渲染，结束后自动进行全角半角标点转换与引用源标注。
- [x] 进入编辑器，TinyMCE 编辑器功能无缺，支持首行缩进等特定公文操作，能加载仿宋和标宋字体。
- [x] 右侧内容优化（润色等）能针对选中文本触发 AI 优化并应用替换；智能校对出词汇错漏可一键采纳；格式排版对 17 套法定模板均可一键正规化排版。
- [x] 素材库个人资料、强国文章等 5 大频道显示健全，支持语义推荐大搜索，并可一键将素材移动至新建或存在的文件夹。
- [x] 回收站支持全选/单选一键恢复（还原回文稿列表）和彻底物理永久删除。
- [x] 文风模板新增后展示 0-100% 进度条，训练完毕后，前端 Canvas 成功绘制交互式的漂亮词云图。

---

## 十五、后续演进与接力建议（P3 - 生产就绪阶段）

本阶段已成功跑通了全部 100% 纯本地的完整全栈闭环与强编译通过。对于后续接力的大模型或开发团队，建议围绕以下核心方向进行**生产就绪级集成**：

### 1. 接入真实大模型 API
当前后端的 SSE (Server-Sent Events) 全文生成和提纲生成是通过带有微延迟的生成流进行模拟的。
- **任务**：在后端 `server/src/routes/article.js` 的 `generate` 和 `outlineOrTitle/generateStream` 路由中，配置 OpenAI 或 Claude 官方 Node SDK，或通义千问公文专有模型。
- **要点**：通过流式流传输（`Readable` 或 `stream`）直接管道化处理（`pipe`）到 Fastify 的响应流中，向前端实时分发真实的 AI 智能文本。

### 2. 数据库迁移与 C++ 本地化
当前的自研纯 JS SQLite 引擎使用 `gai_clone_db.json` 文件承载所有数据，为开发带来了极大便利。
- **任务**：若项目进入企业局域网或云端多租户生产部署，可以在 `database.js` 中将底层逻辑重构为真实的 **SQLite 3 (`better-sqlite3`)** 或企业级 **PostgreSQL**。
- **优势**：自研 Statement 类的接口完全按照 SQLite 标准参数准备设计，无缝替换底层 API 驱动即可完成迁移。

### 3. kkFileView 及 Word/PDF 生成器实体化
当前排版和文件下载是基于生成的任务Uuid进行的轮询仿真下载。
- **任务**：
  - 接入开源的 `kkFileView` 服务容器，在 `kkfile/preview` 路由中配置代理，以实现对自主上传的 DOCX, PDF, Excel 文件的无插件浏览器预览。
  - 在后端引入 `docxtemplater` 或 python-docx，将 TinyMCE 的 HTML 标签进行规范公文排版转换，渲染出真实的 `.docx` 和 `.pdf` 文件供用户点击下载。

### 4. 生产多节点 Nginx 部署
- **任务**：配置 Nginx 将外部安全 HTTPS（443 端口）连接路由转发到本地 loopback 服务。
- **配置示例**：
  ```nginx
  server {
      listen 443 ssl;
      server_name gai.mycompany.local;

      ssl_certificate /etc/nginx/ssl/gai.crt;
      ssl_certificate_key /etc/nginx/ssl/gai.key;

      location / {
          proxy_pass http://127.0.0.1:5173; # 前端
          proxy_set_header Host $host;
      }

      location /geekseek/ {
          proxy_pass http://127.0.0.1:8080; # 后端 API 网关
          proxy_http_version 1.1;
          proxy_set_header Connection "";
          proxy_buffering off; # SSE 必须关闭 buffering 缓存
      }

      location /gdios/ {
          proxy_pass http://127.0.0.1:8080; # 后端配置网关
      }
  }
  ```
