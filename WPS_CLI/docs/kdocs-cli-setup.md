# WPS CLI 与 kdocs-cli 安装配置与使用指南

**文档版本:** 2.0
**日期:** 2026-06-09
**适用平台:** macOS (Apple Silicon / Intel) / Linux / Windows
**wps365-cli 版本:** v0.1.0+
**kdocs-cli 版本:** v2.5.8

---

## 目录

1. [概述与工具对比](#1-概述与工具对比)
2. [wps365-cli 安装配置](#2-wps365-cli-安装配置)
3. [kdocs-cli 安装配置](#3-kdocs-cli-安装配置)
4. [kdocs-cli 认证配置](#4-kdocs-cli-认证配置)
5. [kdocs-cli 基础使用](#5-kdocs-cli-基础使用)
6. [wps365-cli 基础使用](#6-wps365-cli-基础使用)
7. [在 WPS 备份工具中的使用](#7-在-wps-备份工具中的使用)
8. [故障排查](#8-故障排查)
9. [参考链接](#9-参考链接)

---

## 1. 概述与工具对比

### 1.1 两款 CLI 工具的定位

| 工具 | 定位 | 官方链接 |
|------|------|----------|
| **wps365-cli** | WPS 365 开放平台官方 CLI，面向开发者与 AI Agent 的命令行入口。覆盖日历、协作、通讯录、邮箱、云文档、多维表、会议等 7 大业务域，未覆盖的接口通过 `api get|post` 直接访问。 | https://github.com/wps365-open/cli |
| **kdocs-cli** | 金山文档官方 CLI，采用预编译原生二进制分发，支持 amd64 与 arm64 双架构，无需运行时环境。核心定位是让 AI Agent 与开发者通过终端操控金山文档全产品线（云文档、智能文档、多维表、表格、文字、PDF、演示文稿、知识库等）。 | https://bbs.wps.cn/topic/86117 |

### 1.2 功能对比

| 维度 | wps365-cli | kdocs-cli |
|------|-----------|-----------|
| **开发语言** | Go | Go |
| **开源协议** | MIT | 未开源 |
| **发布方式** | GitHub 开源 + Release 二进制 | 官方二进制（CDN 分发） |
| **认证** | OAuth2 delegated / app 双模式 | 独立 OAuth（系统密钥链） |
| **盘列表** | ✅ `drive list` | ❌ 无此 API |
| **文件下载** | ✅ 实体文件下载 | ✅ 实体下载 + 内容读取 |
| **文档内容读取** | ❌ 不支持 | ✅ `read-file` 转 Markdown |
| **全文搜索** | 基础搜索 | ✅ 文件名 + 内容全文搜索 |
| **Token 互通** | ❌ 不互通 | ❌ 需单独登录 |
| **智能文档(OTL)** | ❌ 无对应功能 | ✅ 块级操作(5类) |
| **多维表** | ✅ CRUD + 视图 + 仪表盘 | ✅ 四维管理 |
| **表格操作** | ❌ 无对应功能 | ✅ 工作表+范围 |
| **文字文档** | ❌ 无对应功能 | ✅ 段落读写+格式 |
| **PDF 操作** | ❌ 无对应功能 | ✅ 页数+提取 |
| **演示文稿** | ❌ 无对应功能 | ✅ JSAPI引擎 |
| **知识库** | ❌ 无对应功能 | ✅ 空间+文档管理 |
| **网页剪藏** | ❌ 否 | ✅ 是 |
| **即时通讯** | ✅ 消息收发+群聊+撤回 | ❌ 否 |
| **日程日历** | ✅ 日程+忙闲+批量操作 | ❌ 否 |
| **会议管理** | ✅ 预约+参会人+纪要+录制 | ❌ 否 |
| **通讯录** | ✅ 用户+搜索+部门管理 | ❌ 否 |
| **邮箱** | ✅ 收发+文件夹+草稿+邮件组 | ❌ 否 |
| **自升级回滚** | ❌ 否 | ✅ 是 |
| **API 兜底** | ✅ `api get/post` 全覆盖 | ❌ 否 |

### 1.3 为什么需要同时使用两款工具

两款工具同属金山生态，功能互补：

- **wps365-cli**：负责横向协作——盘列表扫描、实体文件下载、日程、会议、通讯录、邮箱、即时通讯
- **kdocs-cli**：负责文档纵深——文档内容提取（Markdown）、全文搜索、智能文档/多维表/表格/文字/PDF/演示文稿操作、知识库管理

在备份场景中，wps365-cli 负责**盘列表扫描**和**实体文件下载**，kdocs-cli 负责**文档内容提取**和**全文搜索**（kdocs-cli 无盘列表 API）。二者搭配形成文档编辑与协作联动的完整闭环。

---

## 2. wps365-cli 安装配置

### 2.1 前置条件

- WPS 365 开放平台账号（企业管理员或开发者）
- 已创建应用并获取 `client_id` 和 `client_secret`
- 已配置 OAuth2 回调地址（如 `http://localhost:18365/callback`）

> **如何创建应用？** 访问 [WPS 365 开放平台](https://open.wps.cn/) → 开发者中心 → 创建应用 → 获取 `client_id` 和 `client_secret` → 配置回调地址。

### 2.2 安装（推荐方式）

**macOS / Linux：**

```bash
# 一键安装（自动检测平台、下载、校验、配置 PATH）
curl -fsSL https://raw.githubusercontent.com/wps365-open/cli/main/install.sh | bash
```

**Windows（PowerShell）：**

```powershell
irm https://raw.githubusercontent.com/wps365-open/cli/main/install.ps1 | iex
```

**Windows（Git Bash）：**

```bash
curl -fsSL https://raw.githubusercontent.com/wps365-open/cli/main/install.sh | bash
```

**高级选项：**

```bash
# 安装指定版本
curl -fsSL https://raw.githubusercontent.com/wps365-open/cli/main/install.sh | WPS365_VERSION=v0.0.2 bash

# 自定义安装目录
curl -fsSL https://raw.githubusercontent.com/wps365-open/cli/main/install.sh | WPS365_INSTALL_DIR=~/.local/bin bash
```

**PowerShell 高级选项：**

```powershell
# 安装指定版本
$env:WPS365_VERSION="v0.0.2"; irm https://raw.githubusercontent.com/wps365-open/cli/main/install.ps1 | iex

# 自定义安装目录
$env:WPS365_INSTALL_DIR="C:\tools"; irm https://raw.githubusercontent.com/wps365-open/cli/main/install.ps1 | iex
```

### 2.3 手动下载安装

如果自动安装失败，可从 GitHub Release 页面手动下载：

1. 访问 https://github.com/wps365-open/cli/releases
2. 下载对应平台的二进制包（如 `wps365-cli-darwin-arm64.tar.gz`）
3. 解压并放到 PATH 目录（如 `/usr/local/bin/` 或 `~/.local/bin/`）
4. 赋予执行权限：`chmod +x wps365-cli`

### 2.4 验证安装

```bash
# 检查版本
wps365-cli --version
# 预期输出: wps365-cli version 0.1.0

# 检查帮助
wps365-cli --help

# 检查是否在 PATH 中
which wps365-cli
```

### 2.5 认证配置（三步开始）

#### 第一步：配置 OAuth 客户端凭证

**交互式引导（推荐）：**

```bash
wps365-cli auth setup
```

按提示输入 `client_id`、`client_secret` 和回调地址，凭证自动保存到系统 Keychain。

**手动配置文件方式：**

```bash
# 创建配置目录
mkdir -p ~/Library/Application\ Support/wps365-cli

# 编辑配置文件
cat > ~/Library/Application\ Support/wps365-cli/config.json << 'EOF'
{
  "client_id": "你的client_id",
  "client_secret": "你的client_secret",
  "redirect_uri": "http://localhost:18365/callback"
}
EOF
```

**环境变量方式（适合 CI/CD）：**

```bash
export WPS365_CLIENT_ID="你的client_id"
export WPS365_CLIENT_SECRET="你的client_secret"
export WPS365_REDIRECT_URI="http://localhost:18365/callback"
```

#### 第二步：登录授权

**用户身份登录（delegated 模式，代表用户操作）：**

```bash
# 指定权限范围登录
wps365-cli auth login --scopes "kso.user_base.read,kso.calendar.read"

# 或授权所有常用权限
wps365-cli auth login --delegated
```

执行后会自动打开浏览器完成 OAuth 授权，Token 保存到系统 Keychain。

**应用身份登录（app 模式，适合服务端调用）：**

```bash
wps365-cli auth login --app
```

**非交互式场景（CI/CD）：**

```bash
export WPS365_CLIENT_ID="<client-id>"
export WPS365_CLIENT_SECRET="<client-secret>"
wps365-cli auth login --app
```

#### 第三步：验证并开始使用

```bash
# 查看当前用户信息
wps365-cli user me

# 查看认证状态
wps365-cli auth status
```

### 2.6 认证管理常用命令

| 命令 | 说明 | 使用场景 |
|------|------|----------|
| `auth setup` | 配置 OAuth 客户端凭证 | 首次使用，交互式引导 |
| `auth login` | 登录授权 | `--scopes` 指定权限；`--app` 切换应用身份 |
| `auth status` | 查看认证状态 | 检查 token 是否有效、过期时间、认证模式 |
| `auth token` | 输出当前 access token | 将 token 传递给其他工具或脚本 |
| `auth refresh` | 手动刷新 token | 主动刷新即将过期的 token |
| `auth logout` | 删除本地 token | 退出登录，支持 `--app` / `--delegated` 选择性删除 |
| `auth clean` | 清理所有认证数据 | 凭证损坏或需要完全重置时使用 |

```bash
# 将 token 传给 curl 使用
curl -H "Authorization: Bearer $(wps365-cli auth token)" https://open.wps.cn/v7/users/current

# 手动刷新 token
wps365-cli auth refresh --delegated

# 退出登录（保留凭证，下次可直接 login）
wps365-cli auth logout

# 完全重置（清除所有 token、凭证和自动密钥）
wps365-cli auth clean --force
```

### 2.7 认证模式说明

| 模式 | 说明 | 获取方式 |
|------|------|----------|
| `delegated` | 用户授权身份，适用于当前用户、个人待办等用户态接口 | `auth login --scopes "..."` |
| `app` | 应用身份，适用于服务端调用或应用态接口 | `auth login --app` |

命令根据底层 OpenAPI `security` 自动选择认证模式，`--token-type` 可显式覆盖。不兼容时直接报错，不静默切换。

### 2.8 常用命令速查

#### 双轨命令体系

**精装命令（语义化参数，对人类与脚本友好）：**

```bash
# 用户信息
wps365-cli user me

# 日历操作
wps365-cli calendar events create primary \
  --name "周会" --from "2024-01-15T14:00:00+08:00" --to "2024-01-15T15:00:00+08:00"
wps365-cli calendar list

# 即时通讯
wps365-cli im messages send --to u1 --to u2 --text "hello"

# 云文档
wps365-cli drive list --allotee-type user --page-size 50 -o json
wps365-cli drive files list <drive_id> <parent_id> --page-size 100 -o json
wps365-cli drive files download <drive_id> <file_id> -o json
wps365-cli drive files search <drive_id> --keyword "报告" -o json

# 多维表
wps365-cli sheet tables list <table_id>
wps365-cli sheet records create <table_id> --data '{...}'

# 会议
wps365-cli meeting create --name "项目评审" --start "2024-01-15T14:00:00+08:00"

# 通讯录
wps365-cli contact users search --keyword "张三"

# 邮箱
wps365-cli mail folders list
wps365-cli mail messages list --folder-id "inbox"
```

**通用 API 调用（兜底全量 API）：**

```bash
# 直接调用任意 WPS 365 开放平台端点
wps365-cli api get "/v7/users/current"
wps365-cli api post "/v7/calendars/create" --data '{"summary": "项目日历"}'
```

#### 输出格式

```bash
-o json      # JSON（默认）
-o yaml      # YAML
-o table     # 易读表格
-o tsv       # Tab 分隔（适合管道处理）
```

```bash
wps365-cli -o yaml user me
wps365-cli -o table calendar list
```

#### Dry Run（预览请求不实际发送）

```bash
wps365-cli --dry-run user me
wps365-cli --dry-run api get "/v7/users/current"
wps365-cli --dry-run -o json im messages send --to u1 --text "hello"
```

### 2.9 环境变量全表

| 变量 | 用途 |
|------|------|
| `WPS365_CLIENT_ID` | OAuth 客户端 ID |
| `WPS365_CLIENT_SECRET` | OAuth 客户端密钥 |
| `WPS365_AUTH` | 默认认证模式（`app` / `delegated`） |
| `WPS365_ACCESS_TOKEN` | 直接注入 access token（跳过存储和刷新） |
| `WPS365_API_BASE` | API 基础地址 |
| `WPS365_AUTH_URL` | 自定义 OAuth 授权端点 |
| `WPS365_TOKEN_URL` | 自定义 OAuth token 端点 |
| `WPS365_REDIRECT_URI` | OAuth 回调地址 |
| `WPS365_CONFIG_DIR` | 配置文件目录 |
| `WPS365_KEYRING_BACKEND` | 凭证存储后端（`keychain` / `file`） |
| `WPS365_KEYRING_PASSWORD` | 文件后端加密密码 |
| `WPS365_OUTPUT` | 默认输出格式 |
| `WPS365_QUIET` | 静默 stderr 信息输出 |

### 2.10 安全与凭证存储

`client_secret` 和 token 存储在安全后端，明文永远不落盘：

- **钥匙串**（macOS/Windows 默认）：使用系统 Keychain / Credential Manager
- **加密文件**（Linux 默认）：AES-256-GCM 加密。未设置 `WPS365_KEYRING_PASSWORD` 时自动生成随机密钥并持久化到本地

Token 生命周期完全自动管理：
- access token 过期前 10 秒主动刷新
- 401 响应时透明刷新并重试
- delegated token 通过 refresh_token 刷新；refresh token 过期时提示重新 `auth login`
- app token 过期时自动通过 client_credentials 重新获取

### 2.11 wps365-cli 故障排查

| 问题 | 原因 | 解决 |
|------|------|------|
| `context deadline exceeded` | 网络超时或 Token 刷新失败 | 检查网络，重试 `auth refresh --delegated` |
| `401 Unauthorized` | Token 过期 | 执行 `wps365-cli auth refresh --delegated` |
| `无法获取盘列表` | 应用权限不足 | 检查 WPS 开放平台应用的权限配置 |
| 安装脚本执行失败 | 网络问题或权限不足 | 手动下载 Release 二进制包 |
| `auth setup` 无响应 | 终端不支持交互 | 使用环境变量或手动配置文件方式 |

---

## 3. kdocs-cli 安装配置

### 3.1 前置条件

- 已安装 `curl` 或 `wget`
- 已安装 `npx` (Node.js npm) — 用于通过 skills.sh 获取 Skill 包
- **macOS 额外要求**：系统密钥链可用（`security` 命令）

### 3.2 推荐安装流程（通过 Skill 包）

```bash
# Step 1: 通过 skills.sh 安装金山文档 Skill 包（含安装脚本）
npx skills add kdocs-app/kdocs-skill@kdocs -y -g

# Step 2: 执行安装脚本
bash ~/.agents/skills/kdocs/scripts/setup.sh
```

安装脚本会自动：
1. 读取 `SKILL.md` 中的版本号
2. 从 CDN 下载对应平台的二进制包
3. 校验 SHA256
4. 解压到 `~/.local/bin/`
5. 添加到 PATH

### 3.3 网络问题处理（CDN 不可解析）

**问题现象：**
```
curl: (6) Could not resolve host: wpsai.wpscdn.cn
```

**原因：** `wpsai.wpscdn.cn` 在某些网络环境下 DNS 无法解析。

**解决方案：**

```bash
# 方法 1: 使用中国 DNS 解析获取实际 IP
dig @114.114.114.114 +short wpsai.wpscdn.cn
# 输出示例: wpsai.wpscdn.cn.download.ks-cdn.com. → l5.gslb.ksyuncdn.com. → 122.189.32.35

# 方法 2: 手动下载并安装
cdn_ip="122.189.32.35"
version="2.5.8"
os="darwin"    # linux / windows
arch="arm64"   # amd64

curl -sL -H "Host: wpsai.wpscdn.cn" \
  "https://${cdn_ip}/skillhub/pro/v${version}/releases/kdocs-cli-${version}-${os}-${arch}.tar.gz" \
  -o /tmp/kdocs-cli.tar.gz --insecure

# 解压并安装
mkdir -p ~/.local/bin
tar -xzf /tmp/kdocs-cli.tar.gz -C /tmp/
cp /tmp/kdocs-cli ~/.local/bin/
chmod +x ~/.local/bin/kdocs-cli

# 验证
kdocs-cli version
```

### 3.4 验证安装

```bash
# 检查版本
kdocs-cli version
# 预期输出: 2.5.8

# 检查帮助
kdocs-cli --help

# 检查认证状态
kdocs-cli auth status
```

---

## 4. kdocs-cli 认证配置

### 4.1 首次登录

```bash
# 浏览器 OAuth 登录（推荐）
kdocs-cli auth login
```

执行后会输出授权链接，在浏览器中打开并完成 WPS 账号登录。
登录成功后，Token 自动保存到系统密钥链。

**macOS 密钥链存储位置：**
- 工具：`security find-generic-password -s kdocs-cli`
- 实际存储在 macOS Keychain 中，跨会话持久化

### 4.2 手动设置 Token

如果你已有 Token（例如从其他渠道获取）：

```bash
kdocs-cli auth set-token "<your-token>"
```

**stdin 模式（避免 Shell 转义问题）：**
```bash
echo "<your-token>" | kdocs-cli auth set-token -
```

### 4.3 检查认证状态

```bash
kdocs-cli auth status
```

**预期输出：**
```json
{
  "authenticated": true,
  "keychain": {
    "available": true,
    "backend": "system keychain",
    "consistent": true,
    "token": "UWvehh2R...bw=="
  },
  "source": "system keychain",
  "token": "UWvehh2R...bw=="
}
```

### 4.4 退出登录

```bash
kdocs-cli auth logout
```

---

## 5. kdocs-cli 基础使用

kdocs-cli 覆盖九大服务模块共计 93 个工具：

| 模块 | 能力 |
|------|------|
| **云文档(drive)** | 搜索（文件名与全文双模式）、创建、读取（自动转 Markdown）、移动、跨盘复制、删除、回收站恢复、权限设置、分享链接 |
| **智能文档(otl)** | 块级查询、插入、更新、删除、Markdown/HTML 格式转换 |
| **多维表(dbsheet)** | 数据表、字段、记录、视图四维管理，覆盖 Schema 设计到数据 CRUD 完整链路 |
| **表格(sheet)** | 工作表与范围数据操作 |
| **文字文档(wps)** | 段落读写、查找替换、对齐缩进等原子能力 |
| **PDF** | 页数查询与页面提取 |
| **演示文稿(wpp)** | JSAPI 执行引擎支持幻灯片增删与形状插入 |
| **知识库(kwiki)** | 空间与文档管理 |
| **网页剪藏** | 抓取网页内容自动保存为智能文档 |

### 5.1 文件搜索

```bash
# 按文件名搜索
kdocs-cli drive search-files '{"type":"file_name","keyword":"报告","page_size":10}'

# 全文搜索（搜索文档内容）
kdocs-cli drive search-files '{"type":"content","keyword":"人工智能","page_size":10}'

# 全局搜索
kdocs-cli drive search-files '{"type":"all","keyword":"项目","page_size":10}'
```

### 5.2 列出文件夹内容

```bash
# 需要知道 drive_id 和 parent_id
kdocs-cli drive list-files '{"drive_id":"2276735429","parent_id":"0","count":5}'
```

**注意：** kdocs-cli 没有 `list_drives` API，盘 ID 需通过其他方式获取（如 wps365-cli 或从已有文件中提取）。

### 5.3 读取文档内容

```bash
# 读取 docx 为 Markdown
kdocs-cli drive read-file '{"file_id":"xxx"}'

# 读取 OTL 为 Markdown
kdocs-cli drive read-file '{"file_id":"xxx"}'
```

**支持的格式：** docx, pdf, xlsx, ksheet, dbt, otl
**不支持的格式：** pptx

### 5.4 获取下载链接

```bash
kdocs-cli drive download-file '{"file_id":"xxx"}'
```

### 5.5 智能文档(OTL)操作

```bash
# 块级查询
kdocs-cli otl query '{"file_id":"xxx","block_id":"xxx"}'

# 块级插入
kdocs-cli otl insert '{"file_id":"xxx","content":"# 标题\n正文"}'

# 块级更新
kdocs-cli otl update '{"file_id":"xxx","block_id":"xxx","content":"新内容"}'

# 块级删除
kdocs-cli otl delete '{"file_id":"xxx","block_id":"xxx"}'

# 格式转换（Markdown / HTML）
kdocs-cli otl convert '{"file_id":"xxx","format":"markdown"}'
```

### 5.6 多维表(dbsheet)操作

```bash
# 列出数据表
kdocs-cli dbsheet tables '{"file_id":"xxx"}'

# 列出字段
kdocs-cli dbsheet fields '{"file_id":"xxx","table_id":"xxx"}'

# 查询记录
kdocs-cli dbsheet records '{"file_id":"xxx","table_id":"xxx","page_size":10}'

# 创建记录
kdocs-cli dbsheet create-record '{"file_id":"xxx","table_id":"xxx","fields":{...}}'

# 更新记录
kdocs-cli dbsheet update-record '{"file_id":"xxx","record_id":"xxx","fields":{...}}'

# 删除记录
kdocs-cli dbsheet delete-record '{"file_id":"xxx","record_id":"xxx"}'
```

### 5.7 演示文稿(wpp)操作

```bash
# 通过 JSAPI 引擎执行操作
kdocs-cli wpp execute '{"file_id":"xxx","action":"add_slide","params":{...}}'
```

### 5.8 网页剪藏

```bash
# 抓取网页内容保存为智能文档
kdocs-cli clip '{"url":"https://example.com","title":"网页标题"}'
```

### 5.9 参数输入方式

kdocs-cli 支持四种参数输入方式，零配置即可上手：

1. **键值对**：`kdocs-cli drive search-files type=file_name keyword=报告 page_size=10`
2. **JSON**：`kdocs-cli drive search-files '{"type":"file_name","keyword":"报告"}'`
3. **stdin 管道**：`echo '{"type":"file_name"}' | kdocs-cli drive search-files -`
4. **文件引用**：`kdocs-cli drive search-files @params.json`

### 5.10 版本检查与升级

```bash
# 检查当前版本
kdocs-cli version

# 检查是否有新版本
kdocs-cli upgrade --check

# 升级（注意：当前网络环境可能失败）
kdocs-cli upgrade -y

# 回滚（如果升级失败）
kdocs-cli upgrade --rollback
```

**升级失败处理：** 参见 3.3 节手动下载安装流程。

---

## 6. wps365-cli 基础使用

### 6.1 云文档操作

```bash
# 获取盘列表
wps365-cli drive list --allotee-type user --page-size 50 -o json

# 列出文件夹内容
wps365-cli drive files list <drive_id> <parent_id> --page-size 100 -o json

# 获取文件下载链接
wps365-cli drive files download <drive_id> <file_id> -o json

# 搜索文件
wps365-cli drive files search <drive_id> --keyword "报告" -o json

# 上传文件
wps365-cli drive files upload <drive_id> <parent_id> /path/to/file

# 批量操作
wps365-cli drive files batch-copy <drive_id> --file-ids "id1,id2" --target-parent-id "xxx"
```

### 6.2 日历操作

```bash
# 查询日历列表
wps365-cli calendar list

# 创建日程
wps365-cli calendar events create primary \
  --name "周会" \
  --from "2024-01-15T14:00:00+08:00" \
  --to "2024-01-15T15:00:00+08:00"

# 查询忙闲状态
wps365-cli calendar freebusy \
  --users "user1@example.com,user2@example.com" \
  --from "2024-01-15T09:00:00+08:00" \
  --to "2024-01-15T18:00:00+08:00"
```

### 6.3 即时通讯

```bash
# 发送消息
wps365-cli im messages send --to u1 --to u2 --text "hello"

# 回复消息
wps365-cli im messages reply --message-id "xxx" --text "收到"

# 创建群聊
wps365-cli im chats create --name "项目群" --members "u1,u2,u3"

# 群成员管理
wps365-cli im chats members add --chat-id "xxx" --members "u4,u5"
```

### 6.4 会议管理

```bash
# 预约会议
wps365-cli meeting create \
  --name "项目评审" \
  --start "2024-01-15T14:00:00+08:00" \
  --duration 60 \
  --attendees "u1,u2,u3"

# 查询会议列表
wps365-cli meeting list --start "2024-01-01" --end "2024-01-31"

# 获取会议纪要
wps365-cli meeting minutes get --meeting-id "xxx"
```

### 6.5 通讯录

```bash
# 查询当前用户
wps365-cli user me

# 搜索用户
wps365-cli contact users search --keyword "张三"

# 按部门查询
wps365-cli contact departments list
wps365-cli contact departments members --dept-id "xxx"
```

### 6.6 邮箱

```bash
# 列出文件夹
wps365-cli mail folders list

# 列出邮件
wps365-cli mail messages list --folder-id "inbox" --page-size 20

# 发送邮件
wps365-cli mail messages send \
  --to "recipient@example.com" \
  --subject "主题" \
  --body "正文内容"
```

### 6.7 通用 API 调用

```bash
# GET 请求
wps365-cli api get "/v7/users/current"

# POST 请求
wps365-cli api post "/v7/calendars/create" --data '{"summary": "项目日历"}'

# 带查询参数
wps365-cli api get "/v7/drive/files" --query '{"drive_id":"xxx","parent_id":"0"}'
```

---

## 7. 在 WPS 备份工具中的使用

### 7.1 自动集成

升级后的 `wps_backup.py` 已自动集成两款 CLI：

```bash
# 常规备份（自动触发内容备份）
python3 wps_backup.py run

# OTL 专项备份（kdocs-cli 内容 + 缓存实体）
python3 wps_backup.py backup-otl

# 跳过 kdocs-cli 内容备份（纯缓存模式）
python3 wps_backup.py backup-otl --no-content

# 查看状态（含两款 CLI 信息）
python3 wps_backup.py status
```

### 7.2 内容备份目录结构

```
wps_backup_data/
├── 自动备份/                    # 实体文件备份（wps365-cli）
├── 我的企业文档/
├── _otl_files/                  # OTL 缓存实体备份
├── _otl_content/                # OTL Markdown 内容备份（kdocs-cli）
│   └── 我的企业文档/
│       └── 文件名_fileid[:8].md
├── _content_backup/             # 其他文档 Markdown 内容备份
│   └── 我的企业文档/
│       └── 文件名_fileid[:8].md
└── _otl_converted_docx/         # 手动导出 docx
```

### 7.3 内容备份文件格式

每个 Markdown 文件包含 YAML frontmatter：

```markdown
---
file_id: xxx
drive_id: xxx
name: 文件名.docx
source_format: .docx
backup_at: 2026-06-09 23:01:47
---

文档内容（Markdown 格式）...
```

### 7.4 两款 CLI 的协作流程

```bash
# 1. 获取盘列表（wps365-cli）
wps365-cli drive list --allotee-type user --page-size 50 -o json

# 2. 使用盘 ID 进行 kdocs-cli 操作
kdocs-cli drive list-files '{"drive_id":"从上面获取的ID","parent_id":"0","count":10}'

# 3. 读取文档内容（kdocs-cli）
kdocs-cli drive read-file '{"file_id":"xxx"}'

# 4. 下载实体文件（wps365-cli）
wps365-cli drive files download <drive_id> <file_id> -o json
```

---

## 8. 故障排查

### 8.1 wps365-cli 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `context deadline exceeded` | 网络超时或 Token 刷新失败 | 检查网络，重试 `auth refresh --delegated` |
| `401 Unauthorized` | Token 过期 | 执行 `wps365-cli auth refresh --delegated` |
| `无法获取盘列表` | 应用权限不足 | 检查 WPS 开放平台应用的权限配置 |
| 安装脚本执行失败 | 网络问题或权限不足 | 手动下载 Release 二进制包 |
| `auth setup` 无响应 | 终端不支持交互 | 使用环境变量或手动配置文件方式 |

### 8.2 kdocs-cli 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `无法解析主机 wpsai.wpscdn.cn` | DNS 问题 | 使用中国 DNS 或手动下载 |
| `Token 已过期或无效 (400006)` | Token 过期 | 执行 `kdocs-cli auth login` |
| `tool not found: xxx` | kdocs-cli 版本过旧 | 升级到最新版本 |
| `暂不支持的文件类型：.pptx` | read-file 不支持 PPT | 仅下载实体文件，无法提取内容 |
| `无法读取 OTL 内容` | 文件是 .otl.link 快捷方式 | 属于预期行为，跳过即可 |

### 8.3 诊断命令

```bash
# ===== wps365-cli 诊断 =====
wps365-cli auth status
wps365-cli --version
wps365-cli --help

# ===== kdocs-cli 诊断 =====
kdocs-cli auth status
kdocs-cli version
kdocs-cli --help

# ===== 网络连通性测试 =====
ping wpsai.wpscdn.cn 2>/dev/null || echo "CDN 不可达"
curl -I https://github.com/wps365-open/cli 2>/dev/null | head -1

# ===== API 调用测试 =====
wps365-cli --dry-run user me
kdocs-cli drive search-files '{"type":"file_name","keyword":"test","page_size":1}'
```

### 8.4 认证问题速查

```bash
# 检查 wps365-cli 认证
wps365-cli auth status
wps365-cli auth token

# 检查 kdocs-cli 认证
kdocs-cli auth status

# 重新登录（两款工具需分别操作）
wps365-cli auth login --delegated
kdocs-cli auth login

# 完全重置认证
wps365-cli auth clean --force
kdocs-cli auth logout
```

---

## 9. 参考链接

### 官方资源

- **wps365-cli GitHub 仓库**：https://github.com/wps365-open/cli
  - Release 下载：https://github.com/wps365-open/cli/releases
  - 安装脚本：https://raw.githubusercontent.com/wps365-open/cli/main/install.sh
  - PowerShell 安装脚本：https://raw.githubusercontent.com/wps365-open/cli/main/install.ps1
- **kdocs-cli 深度解析**：https://bbs.wps.cn/topic/86117
- **金山文档 Skill 架构升级说明**：https://bbs.wps.cn/topic/86103
- **Skills Marketplace**：https://lobehub.com/zh-TW/skills/234194027-cpu-xianclaw-kdocs
- **WPS 365 开放平台**：https://open.wps.cn/

### 对比参考

- **六款办公 CLI 工具全景对比**：https://bbs.wps.cn/topic/86117
  - 对比维度：kdocs-cli、WPS 365 CLI、钉钉悟空 CLI、飞书 lark-cli、企微 wecom-cli、Google gws
  - 涵盖：开发语言、开源协议、核心服务数、可用工具数、认证方式、文档能力、协作能力等 26 个维度

---

*本文档基于 wps365-cli v0.1.0+ 和 kdocs-cli v2.5.8 编写。如版本升级导致命令变化，请以各工具 `--help` 实际输出为准。*
