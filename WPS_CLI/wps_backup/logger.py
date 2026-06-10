"""
日志模块
"""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from . import config

def setup_logger(name: str = "wps_backup", log_file: Path = config.LOG_FILE) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 文件 handler（轮转，单文件 10MB，保留 5 个历史）
    log_file.parent.mkdir(parents=True, exist_ok=True)
    fh = RotatingFileHandler(
        str(log_file), maxBytes=10 * 1024 * 1024, backupCount=5,
        encoding="utf-8"
    )
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # 控制台 handler
    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    return logger