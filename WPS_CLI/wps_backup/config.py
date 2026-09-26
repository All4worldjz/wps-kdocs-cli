"""
WPS 云盘 → 本地备份应用 — 配置
"""

import os
from pathlib import Path

# ---- 路径配置（环境变量优先，派生路径必须在覆盖之后计算） ----
import sys as _sys
APP_ROOT = Path(__file__).resolve().parent.parent  # WPS_CLI/
# 在 `python -m unittest` 下默认使用临时目录，避免测试写入生产日志/状态（GUI 会展示这些内容）
_UNDER_UNITTEST = bool(_sys.argv) and "unittest" in _sys.argv[0]
if _UNDER_UNITTEST:
    import tempfile as _tempfile
    _TEST_ROOT = Path(_tempfile.gettempdir()) / f"wps_backup_test_{os.getpid()}"
_DEFAULT_BACKUP = (_TEST_ROOT / "data") if _UNDER_UNITTEST else (APP_ROOT / "wps_backup_data")
_DEFAULT_STATE = (_TEST_ROOT / "state") if _UNDER_UNITTEST else (APP_ROOT / "wps_backup_state")
BACKUP_DIR = Path(os.environ.get("WPS_BACKUP_DIR", str(_DEFAULT_BACKUP)))
STATE_DIR  = Path(os.environ.get("WPS_BACKUP_STATE_DIR", str(_DEFAULT_STATE)))
STATE_FILE = STATE_DIR / "backup_state.json"          # 差量状态
LOG_FILE   = STATE_DIR / "backup.log"                 # 运行日志

# ---- 调度配置 ----
SCHEDULE_HOUR = int(os.environ.get("WPS_BACKUP_HOUR", "20"))  # 每天执行时间（24小时制）
SCHEDULE_MINUTE = 0
SCHEDULE_CHECK_INTERVAL = 60  # 守护模式轮询间隔（秒）
RUN_TIMEOUT = int(os.environ.get("WPS_BACKUP_RUN_TIMEOUT", str(6 * 3600)))  # 单次运行看门狗（秒）

# ---- 备份配置 ----
MAX_RETRIES = 5               # 单文件最大重试次数（含 chunk 重试）
REQUEST_DELAY = 0.1           # API 请求间隔（秒）
DOWNLOAD_TIMEOUT = 600        # 整体下载超时（秒）
CHUNK_SIZE = 10 * 1024 * 1024 # 断点续传块大小 (10MB)
MAX_CONCURRENT = int(os.environ.get("WPS_BACKUP_WORKERS", "4"))  # 并发下载线程数

# ---- CLI 配置 ----
def resolve_cli_bin(name: str, env_var: str, home: Path = None) -> str:
    """解析 CLI 绝对路径：环境变量 > ~/.local/bin > PATH > 裸命令名。
    launchd 的 PATH 不含 ~/.local/bin；/usr/local/bin 下是旧版 v0.1.0，不能优先。"""
    import shutil
    override = os.environ.get(env_var)
    if override:
        return override
    local = (home or Path.home()) / ".local" / "bin" / name
    if local.is_file() and os.access(local, os.X_OK):
        return str(local)
    return shutil.which(name) or name

CLI_BIN = resolve_cli_bin("wps365-cli", "WPS365_CLI_BIN")
KDOCS_CLI_BIN = resolve_cli_bin("kdocs-cli", "KDOCS_CLI_BIN")

# ---- 内容备份配置 ----
CONTENT_BACKUP_ENABLED = True       # 是否启用文档内容备份（Markdown）
CONTENT_BACKUP_FORMATS = {".docx", ".doc", ".pdf", ".xlsx", ".xls", ".ksheet", ".dbt", ".otl"}
CONTENT_BACKUP_DIR = BACKUP_DIR / "_content_backup"  # 内容备份目录

# ---- OTL 备份配置 ----
OTL_CONTENT_BACKUP_ENABLED = True   # 备份 OTL 内容（airpage 优先，kdocs-cli 回退）

# ---- airpage OTL 备份配置（v4.1）----
# kdocs API 已拒绝企业账号（403001），OTL 内容备份改走 wps365-cli airpage
AIRPAGE_OTL_CONTENT_ENABLED = os.environ.get("WPS_AIRPAGE_OTL_CONTENT", "1") not in ("0", "false")
AIRPAGE_EXPORT_DOCX_ENABLED = os.environ.get("WPS_AIRPAGE_EXPORT_DOCX", "1") not in ("0", "false")
# v5：OTL 导出并发数（官方导出接口限频策略为“无”；服务端按版本缓存结果）
OTL_WORKERS = int(os.environ.get("WPS_OTL_WORKERS", "4"))

# ---- WPS Office 本地缓存扫描（OTL 实体补充）----
# 缓存位于 ~/Library/Containers，受 macOS 隐私保护；无权限时自动跳过（见 otl_engine.cache_dir_accessible）
OTL_CACHE_SCAN_ENABLED = os.environ.get("WPS_OTL_CACHE_SCAN", "1") not in ("0", "false")
