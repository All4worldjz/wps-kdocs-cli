# WPS CLI 工具集

**WPS 365 云盘本地备份 + 共享文件目录生成 + 日历 CalDAV 代理**

[![Python](https://img.shields.io/badge/Python-3.13%2B-blue)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey)](https://github.com/wps365-open/cli)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 项目简介

本项目是围绕 **WPS 365 开放平台** 构建的本地 CLI 工具集合，核心解决三个问题：

1. **云盘差量备份** — 通过 `wps365-cli` 调用 WPS Drive API，将云端文件增量下载到本地。支持多线程并发、断点续传、指数退避重试。
2. **共享文件目录生成** — 遍历所有云盘，按扩展名分类创建子目录索引，生成 `CATALOG.md`（不下载实体文件）。
3. **日历 CalDAV 代理** — 独立子项目（Go），解决 WPS 日历与 iOS/macOS/Android 系统日历的兼容性问题。

**v4.0 重大升级：** 引入 `kdocs-cli` 混合架构，新增文档内容备份层——将 docx/pdf/xlsx/ksheet/dbt/otl 转为 Markdown 备份，实现"实体文件 + 内容文本"双保险。

---

## 快速开始

### 前置条件

- Python 3.13+
- [wps365-cli](https://github.com/wps365-open/cli) — WPS 365 开放平台 CLI
- [kdocs-cli](https://bbs.wps.cn/topic/86117) — 金山文档 CLI（可选，用于内容备份）

### 安装

```bash
# 克隆仓库
git clone https://github.com/All4worldjz/wps-kdocs-cli.git
cd wps-kdocs-cli

# 安装 wps365-cli（macOS/Linux）
curl -fsSL https://raw.githubusercontent.com/wps365-open/cli/main/install.sh | bash

# 安装 kdocs-cli（详见 docs/kdocs-cli-setup.md）
# 或使用 Skill 包安装：
npx skills add kdocs-app/kdocs-skill@kdocs -y -g
bash ~/.agents/skills/kdocs/scripts/setup.sh
```

### 认证

```bash
# wps365-cli 认证
wps365-cli auth setup      # 交互式配置 client_id / client_secret
wps365-cli auth login --delegated

# kdocs-cli 认证
kdocs-cli auth login       # 浏览器 OAuth 登录
```

### 运行备份

```bash
# 立即执行一次完整备份（含 OTL 内容备份）
python3 wps_backup.py run

# Dry-run：仅对比差异，不下载
python3 wps_backup.py run --dry-run

# 跳过 OTL 专项备份
python3 wps_backup.py run --no-otl

# OTL 专项备份（kdocs-cli 内容 + 缓存实体）
python3 wps_backup.py backup-otl

# 查看备份状态
python3 wps_backup.py status

# 查看最近 30 行日志
python3 wps_backup.py log -n 30
```

### 生成共享文件目录

```bash
python3 sync_shared_files.py
# 输出到 wps_shared_files/CATALOG.md
```

---

## 项目结构

```
WPS_CLI/
├── wps_backup.py              # 主入口：备份 CLI
├── sync_shared_files.py       # 共享文件分类目录生成器
├── verify_fix.py              # 修复验证脚本
├── com.wps.backup.plist       # macOS launchd 定时任务配置
│
├── wps_backup/                # 备份核心 Python 包
│   ├── __init__.py
│   ├── config.py              # 路径、调度、并发、CLI 配置
│   ├── engine.py              # 备份引擎 v3.0（多线程、断点续传、重试）
│   ├── state.py               # 线程安全的增量状态管理器
│   ├── scheduler.py           # 守护模式 & launchd plist 生成
│   ├── otl_engine.py          # OTL 专项备份 v4.0（kdocs-cli + 缓存）
│   ├── kdocs_engine.py        # kdocs-cli 封装引擎
│   └── logger.py              # 统一日志（文件 + 控制台）
│
├── wps_backup_data/           # 备份存储目录（.gitignore 排除）
│   ├── 自动备份/               # 各盘文件按盘名子目录存放
│   ├── 我的企业文档/
│   ├── _otl_files/            # OTL 缓存实体备份
│   ├── _otl_content/          # OTL Markdown 内容备份（kdocs-cli）
│   ├── _content_backup/       # 其他文档 Markdown 内容备份
│   └── _otl_converted_docx/   # 手动导出的 OTL→docx 存放区
│
├── wps_backup_state/          # 状态与日志（.gitignore 排除）
│   ├── backup_state.json      # 差量备份状态
│   ├── _otl_state.json        # OTL 备份状态
│   └── backup.log             # 运行日志
│
├── wps_shared_files/          # 共享文件分类索引输出
│   ├── CATALOG.md             # 总索引
│   └── docx/、pptx/、pdf/ ...  # 按扩展名分类的占位目录
│
├── calendar_Sync/             # CalDAV 代理子项目（Go）
│   ├── AGENTS.md              # 子项目说明
│   ├── DESIGN.md              # 设计文档
│   ├── internal/              # Go 源码
│   └── proxy_code/            # 部署脚本
│
├── docs/
│   └── kdocs-cli-setup.md     # wps365-cli + kdocs-cli 安装配置指南
│
├── README.md                  # 本文件
├── ADP.md                     # 架构决策记录
├── HANDOFF.md                 # 交接文档
└── AGENTS.md                  # 项目规范与开发约定
```

---

## 核心特性

### 差量备份

- **多线程并发下载**：`ThreadPoolExecutor(max_workers=4)`，可通过 `--workers` 调整
- **断点续传**：对 >10MB 文件使用 HTTP `Range` 请求分段下载
- **指数退避重试**：单文件最多 5 次重试，405/429/500+ 自动重试
- **URL 串行化限流**：获取下载地址时加锁，间隔 200ms，避免 API 限流
- **同名文件隔离**：本地文件名格式 `{stem}_{file_id[:8]}{suffix}`，避免冲突
- **旧版自动迁移**：检测到旧版命名自动重命名为新格式

### OTL 专项备份（v4.0）

`.otl`（WPS 在线文档私有格式）无法通过 Drive API 直接下载，采用混合策略：

1. **kdocs-cli 内容备份**（新增，84% 覆盖率）：调用 `kdocs-cli drive read-file` 将 OTL 转为 Markdown
2. **缓存实体备份**（保留，11% 覆盖率）：扫描 WPS Office macOS 本地云同步缓存
3. **导出指南**：未缓存的文件生成 `EXPORT_GUIDE.md`，提示手动导出为 `.docx`

### 文档内容备份层（v4.0 新增）

下载实体文件后，自动触发 `kdocs-cli drive read-file` 将支持格式转为 Markdown：

| 格式 | 内容备份 | 实体备份 |
|------|---------|---------|
| docx/doc | ✅ Markdown | ✅ wps365-cli 下载 |
| pdf | ✅ Markdown | ✅ wps365-cli 下载 |
| xlsx/xls | ✅ Markdown | ✅ wps365-cli 下载 |
| ksheet | ✅ Markdown | ✅ wps365-cli 下载 |
| dbt | ✅ Markdown | ✅ wps365-cli 下载 |
| otl | ✅ Markdown | ❌ 需缓存中转 |
| pptx | ❌ 不支持 | ✅ wps365-cli 下载 |

内容备份文件包含 YAML frontmatter（file_id, drive_id, name, source_format, backup_at）。

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 主语言 | Python 3（纯标准库，无第三方依赖） |
| 外部依赖 | `wps365-cli`（Go 二进制）、`kdocs-cli`（Go 二进制） |
| 标准库 | `urllib.request`, `subprocess`, `threading`, `json`, `pathlib`, `xml.etree`, `signal`, `logging` |
| 调度 | macOS `launchd` 或 Python 守护模式 |
| 数据持久化 | JSON 文件（原子写入：先写 `.tmp` 再 `replace`） |
| 子项目 | Go（calendar_Sync CalDAV 代理） |

---

## 配置

通过环境变量覆盖默认配置：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `WPS_BACKUP_DIR` | `./wps_backup_data` | 备份存储根目录 |
| `WPS_BACKUP_STATE_DIR` | `./wps_backup_state` | 状态/日志目录 |
| `WPS_BACKUP_HOUR` | `20` | 每日备份触发小时 |
| `WPS_BACKUP_WORKERS` | `4` | 并发下载线程数 |

---

## 文档

| 文档 | 说明 |
|------|------|
| [`docs/kdocs-cli-setup.md`](docs/kdocs-cli-setup.md) | **wps365-cli + kdocs-cli 完整安装配置指南** |
| [`ADP.md`](ADP.md) | 架构决策记录（v2.0） |
| [`HANDOFF.md`](HANDOFF.md) | 当前状态与交接事项（v2.1） |
| [`AGENTS.md`](AGENTS.md) | 项目规范与开发约定 |
| [`calendar_Sync/AGENTS.md`](calendar_Sync/AGENTS.md) | CalDAV 代理子项目说明 |
| [`calendar_Sync/DESIGN.md`](calendar_Sync/DESIGN.md) | CalDAV 代理设计文档 |

---

## 故障排查

| 症状 | 可能原因 | 排查方法 |
|------|---------|---------|
| 认证失败 / 无法获取盘列表 | `wps365-cli` token 过期 | `wps365-cli auth status` → `wps365-cli auth refresh --delegated` |
| 大量文件失败 | 下载 URL 过期或网络抖动 | 查看 `backup.log` 中的错误码；引擎会自动重试 |
| .otl 文件无法备份 | WPS Office 未打开过该文件，缓存中不存在 | 在 WPS Office 中打开一次，或按 `EXPORT_GUIDE.md` 手动导出 |
| kdocs-cli 无法安装 | CDN DNS 不可解析 | 见 `docs/kdocs-cli-setup.md` §3.3 手动下载方案 |
| kdocs-cli Token 过期 | 长期未使用 | `kdocs-cli auth login` |
| 同名文件被覆盖 | 旧版本引擎未使用 file_id 隔离 | 检查本地路径是否包含 `_fileid[:8]` 后缀；引擎会自动迁移旧格式 |
| launchd 未按时执行 | plist 路径未加载或时间未到 | `launchctl list com.wps.backup` / `launchctl start com.wps.backup` |
| 状态文件损坏 | JSON 被意外截断 | 删除 `backup_state.json` 重新全量备份（或从备份恢复） |

---

## 安全注意事项

1. **认证 Token**：项目本身不存储密码，依赖 `wps365-cli` 和 `kdocs-cli` 管理 OAuth token，存储在系统 Keychain 中。
2. **日志安全**：`backup.log` 中可能包含文件名称、大小、下载 URL 等元数据，**不包含文件内容**。
3. **状态文件**：`backup_state.json` 和 `_otl_state.json` 包含文件元数据（文件名、link_url、hash），删除将导致下次全量重新下载。
4. **敏感数据清理**：代码库已清理所有硬编码凭证，推送前经过验证。新增文件时请遵循此规范。

---

## 贡献

欢迎提交 Issue 和 Pull Request。对于较大的改动，建议先通过 Issue 讨论。

---

## 许可证

本项目基于 MIT 许可证开源。

---

*最后更新: 2026-06-09*
