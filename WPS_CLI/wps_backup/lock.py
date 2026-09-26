"""
单实例运行锁 — 防止 launchd 定时任务与手动运行重叠，两个进程整体重写同一状态 JSON
"""

import fcntl
import os
from pathlib import Path
from typing import Optional

# 被锁跳过的退出码（EX_TEMPFAIL）：不能返回 0，否则 launchd “last exit code = 0” 会掩盖未运行
EXIT_LOCKED = 75


def acquire(path: Path) -> Optional[int]:
    """非阻塞获取排他锁；已被其他进程持有时返回 None。进程退出时内核自动释放。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    os.ftruncate(fd, 0)
    os.write(fd, str(os.getpid()).encode())
    return fd


def release(fd: int) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def holder_pid(path: Path) -> Optional[int]:
    """读取锁文件中记录的持锁进程 PID"""
    try:
        return int(Path(path).read_text().strip())
    except (OSError, ValueError):
        return None
