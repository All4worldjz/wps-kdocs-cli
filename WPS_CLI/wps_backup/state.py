"""
状态管理器 — 差量备份核心
通过 file_id + mtime 追踪每个文件，避免重复下载
"""

import json
import time
import threading
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

from . import config

@dataclass
class FileSnapshot:
    """单个文件的备份快照"""
    file_id: str
    drive_id: str
    name: str
    size: int
    mtime: int          # 远程修改时间（差量判断依据）
    local_path: str     # 本地存储路径
    local_hash: str     # 本地文件 SHA256
    link_url: str
    drive_name: str
    backed_up_at: str   # 备份时间戳
    retry_count: int = 0
    error_msg: str = ""

class BackupState:
    """线程安全的备份状态管理器"""

    def __init__(self, state_file: Path = config.STATE_FILE):
        self.state_file = state_file
        self._lock = threading.Lock()
        self.snapshots: dict[str, FileSnapshot] = {}  # key: "drive_id/file_id"
        self.meta = {
            "version": 1,
            "last_backup_at": None,
            "total_files": 0,
            "total_size": 0,
        }
        self._load()

    # ---- 持久化 ----

    def _load(self):
        if not self.state_file.exists():
            return
        try:
            with open(self.state_file, "r") as f:
                data = json.load(f)
            self.meta = data.get("meta", self.meta)
            for key, val in data.get("files", {}).items():
                self.snapshots[key] = FileSnapshot(**val)
        except Exception:
            pass  # 损坏则重新开始

    def _save(self):
        config.STATE_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "meta": self.meta,
            "files": {k: asdict(v) for k, v in self.snapshots.items()},
        }
        tmp = self.state_file.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(self.state_file)

    def save(self):
        with self._lock:
            self._save()

    # ---- 查询 ----

    def get_key(self, drive_id: str, file_id: str) -> str:
        return f"{drive_id}/{file_id}"

    def is_backed_up(self, drive_id: str, file_id: str) -> bool:
        return self.get_key(drive_id, file_id) in self.snapshots

    def get_snapshot(self, drive_id: str, file_id: str) -> Optional[FileSnapshot]:
        return self.snapshots.get(self.get_key(drive_id, file_id))

    def needs_update(self, drive_id: str, file_id: str, remote_mtime: int) -> bool:
        """判断文件是否需要重新下载（远程 mtime 比本地记录新）"""
        snap = self.get_snapshot(drive_id, file_id)
        if not snap:
            return True  # 新文件
        # 已知永久不可下载的格式，跳过重复尝试
        if snap.error_msg and ("无下载地址" in snap.error_msg or "不可下载" in snap.error_msg):
            return False
        return remote_mtime > snap.mtime

    # ---- 更新 ----

    def mark_backed_up(self, snapshot: FileSnapshot):
        with self._lock:
            key = self.get_key(snapshot.drive_id, snapshot.file_id)
            snapshot.backed_up_at = time.strftime("%Y-%m-%d %H:%M:%S")
            self.snapshots[key] = snapshot
            self.meta["last_backup_at"] = snapshot.backed_up_at
            self.meta["total_files"] = len(self.snapshots)
            self.meta["total_size"] = sum(s.size for s in self.snapshots.values())
            self._save()

    def mark_failed(self, drive_id: str, file_id: str, error: str,
                     name: str = "", size: int = 0, mtime: int = 0, drive_name: str = ""):
        with self._lock:
            key = self.get_key(drive_id, file_id)
            if key in self.snapshots:
                self.snapshots[key].retry_count += 1
                self.snapshots[key].error_msg = error
            else:
                # 为从未备份成功的文件也创建记录，避免每次都重试已知不可下载的文件
                self.snapshots[key] = FileSnapshot(
                    file_id=file_id, drive_id=drive_id,
                    name=name, size=size, mtime=mtime,
                    local_path="", local_hash="",
                    link_url="", drive_name=drive_name,
                    backed_up_at="", retry_count=1, error_msg=error,
                )
            self._save()

    def prune_stale(self, current_file_keys: set):
        """清理状态中已不存在的远程文件"""
        with self._lock:
            stale = set(self.snapshots.keys()) - current_file_keys
            for key in stale:
                del self.snapshots[key]
            if stale:
                self._save()
        return len(stale)

    def stats(self) -> dict:
        with self._lock:
            return {
                **self.meta,
                "snapshot_count": len(self.snapshots),
            }