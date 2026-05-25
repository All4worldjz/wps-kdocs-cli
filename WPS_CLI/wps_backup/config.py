"""
WPS 云盘 → 本地备份应用 — 配置
"""

import os
from pathlib import Path

# ---- 路径配置 ----
APP_ROOT = Path(__file__).resolve().parent.parent  # WPS_CLI/
BACKUP_DIR = APP_ROOT / "wps_backup_data"           # 备份存储目录
STATE_DIR  = APP_ROOT / "wps_backup_state"           # 状态/日志目录
STATE_FILE = STATE_DIR / "backup_state.json"          # 差量状态
LOG_FILE   = STATE_DIR / "backup.log"                 # 运行日志

# ---- 调度配置 ----
SCHEDULE_HOUR = 20          # 每天执行时间（24小时制）
SCHEDULE_MINUTE = 0
SCHEDULE_CHECK_INTERVAL = 60  # 守护模式轮询间隔（秒）

# ---- 备份配置 ----
MAX_RETRIES = 5               # 单文件最大重试次数（含 chunk 重试）
REQUEST_DELAY = 0.1           # API 请求间隔（秒）
DOWNLOAD_TIMEOUT = 600        # 整体下载超时（秒）
CHUNK_SIZE = 10 * 1024 * 1024 # 断点续传块大小 (10MB)
MAX_CONCURRENT = 4            # 并发下载线程数

# ---- CLI 配置 ----
CLI_BIN = "wps365-cli"

# ---- 环境变量覆盖 ----
BACKUP_DIR = Path(os.environ.get("WPS_BACKUP_DIR", str(BACKUP_DIR)))
STATE_DIR  = Path(os.environ.get("WPS_BACKUP_STATE_DIR", str(STATE_DIR)))
SCHEDULE_HOUR = int(os.environ.get("WPS_BACKUP_HOUR", str(SCHEDULE_HOUR)))
MAX_CONCURRENT = int(os.environ.get("WPS_BACKUP_WORKERS", str(MAX_CONCURRENT)))