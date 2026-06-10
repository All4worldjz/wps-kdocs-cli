"""
备份引擎 v3.0 — 多线程并发 + 断点续传 + 指数退避重试
"""

import json
import hashlib
import subprocess
import time
import urllib.request
import urllib.error
import re
import threading
import socket
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import config
from .state import BackupState, FileSnapshot
from .logger import setup_logger
from . import kdocs_engine

logger = setup_logger()

# ============================================================
# 数据结构
# ============================================================

@dataclass
class RemoteFile:
    file_id: str
    drive_id: str
    drive_name: str
    name: str
    size: int
    mtime: int
    link_url: str
    parent_id: str
    type: str

@dataclass
class BackupResult:
    total: int = 0
    new: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    content_backed_up: int = 0   # kdocs-cli 内容备份成功
    content_failed: int = 0      # kdocs-cli 内容备份失败
    errors: list = field(default_factory=list)

    def to_dict(self):
        return {
            "total": self.total, "new": self.new,
            "updated": self.updated, "skipped": self.skipped,
            "failed": self.failed,
            "content_backed_up": self.content_backed_up,
            "content_failed": self.content_failed,
            "errors": self.errors,
        }

# ============================================================
# 线程安全计数器
# ============================================================

class AtomicCounter:
    def __init__(self):
        self._lock = threading.Lock()
        self._value = 0

    def inc(self) -> int:
        with self._lock:
            self._value += 1
            return self._value

    @property
    def value(self) -> int:
        with self._lock:
            return self._value

# ============================================================
# CLI 封装
# ============================================================

def _cli(*args, timeout=60, retries=2):
    cmd = [config.CLI_BIN] + list(args)
    for attempt in range(retries + 1):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if r.returncode == 0:
                return json.loads(r.stdout)
            err = r.stderr.strip()
            if "401" in err or "expired" in err.lower():
                logger.info("Token 过期，自动刷新...")
                subprocess.run([config.CLI_BIN, "auth", "refresh", "--delegated"],
                             capture_output=True, timeout=30)
                continue
            if attempt < retries:
                time.sleep(2 ** attempt)
        except subprocess.TimeoutExpired:
            if attempt < retries:
                time.sleep(3)
        except json.JSONDecodeError:
            if attempt < retries:
                time.sleep(2)
    return None

def _get_auth_token():
    try:
        r = subprocess.run([config.CLI_BIN, "auth", "token"],
                         capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None

# ============================================================
# 远程扫描
# ============================================================

def scan_remote_drives() -> list[dict]:
    data = _cli("drive", "list", "--allotee-type", "user",
                "--page-size", "50", "-o", "json")
    if not data:
        raise RuntimeError("无法获取盘列表（认证可能已过期）")
    return data.get("data", {}).get("items", [])

def scan_remote_files(drive_id: str, drive_name: str, parent_id: str = "0") -> list[RemoteFile]:
    result = []
    token = ""
    while True:
        args = ["drive", "files", "list", drive_id, parent_id,
                "--page-size", "100", "--with-permission", "-o", "json"]
        if token:
            args += ["--page-token", token]
        data = _cli(*args)
        if not data or data.get("code") != 0:
            break
        for item in data.get("data", {}).get("items", []):
            rf = RemoteFile(
                file_id=item["id"], drive_id=drive_id, drive_name=drive_name,
                name=item["name"], size=item.get("size", 0),
                mtime=item.get("mtime", 0), link_url=item.get("link_url", ""),
                parent_id=item.get("parent_id", "0"), type=item.get("type", "file"),
            )
            if rf.type == "file":
                ext = Path(rf.name).suffix.lower()
                if ext in SKIP_EXTS:
                    logger.debug(f"      跳过不可下载格式 ({ext}): {rf.name}")
                    continue
                result.append(rf)
            elif rf.type == "folder":
                result.extend(scan_remote_files(drive_id, drive_name, item["id"]))
        token = data.get("data", {}).get("next_page_token", "")
        if not token:
            break
    return result

# ============================================================
# 文件工具
# ============================================================

def sanitize(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\t\n\r]', '_', name.strip())[:200]

def compute_hash(filepath: Path) -> str:
    h = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""

def local_file_exists(local_path: Path, expected_size: int) -> bool:
    return local_path.exists() and local_path.stat().st_size == expected_size

def format_size(n: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB']:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"

def format_speed(bytes_per_sec: float) -> str:
    return f"{format_size(bytes_per_sec)}/s"

# ============================================================
# 下载引擎（多线程 + 断点续传 + 重试）
# ============================================================

# 不可通过 WPS Drive API 直接下载的私有格式
SKIP_EXTS = {".otl", ".spt", ".form"}

RETRYABLE_ERRORS = (
    urllib.error.URLError,
    socket.timeout,
    ConnectionResetError,
    BrokenPipeError,
    TimeoutError,
    ConnectionAbortedError,
)

def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in (405, 429, 500, 502, 503, 504)
    if isinstance(exc, RETRYABLE_ERRORS):
        return True
    msg = str(exc).lower()
    return any(kw in msg for kw in ("reset", "timeout", "refused", "unreachable"))

def get_download_url(drive_id: str, file_id: str) -> Optional[str]:
    for attempt in range(3):
        data = _cli("drive", "files", "download", drive_id, file_id, "-o", "json", timeout=30)
        if data and data.get("code") == 0:
            dl = data.get("data", {})
            return dl.get("url") or dl.get("download_url") or dl.get("downloadUri")
        if attempt < 2:
            time.sleep(1)
    return None

def _download_chunk(url: str, start: int, end: int, token: str) -> Optional[bytes]:
    """下载指定字节范围"""
    headers = {
        "User-Agent": "WPS-Backup/3.0",
        "Range": f"bytes={start}-{end}",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()

def download_with_resume(url: str, dest: Path, token: str,
                          max_retries: int = 5,
                          chunk_size: int = 10 * 1024 * 1024,
                          url_refresher=None) -> tuple[bool, int, str]:
    """
    带断点续传和重试的下载
    支持 url_refresher 回调：在 chunk 下载遇到 401/403/405 时刷新 URL
    返回: (成功, 文件大小, hash|error_msg)
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")

    # 检查是否有部分下载的临时文件
    resume_offset = 0
    if tmp.exists():
        resume_offset = tmp.stat().st_size
        if resume_offset > 0:
            logger.debug(f"      断点续传: 从 {format_size(resume_offset)} 继续")

    for attempt in range(max_retries):
        try:
            # 获取文件总大小（用 GET bytes=0-0 替代 HEAD，兼容签名 URL）
            headers = {"User-Agent": "WPS-Backup/3.0", "Range": "bytes=0-0"}
            if token:
                headers["Authorization"] = f"Bearer {token}"

            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                # Content-Range: bytes 0-0/12345 → 提取总大小
                content_range = resp.headers.get("Content-Range", "")
                if "/" in content_range:
                    total_size = int(content_range.split("/")[-1])
                else:
                    # 降级：读取 Content-Length 或直接读第一个字节
                    total_size = int(resp.headers.get("Content-Length", 0))
                    resp.read()  # 消费掉响应体

            # 下载主体（分段续传 + 逐块重试 + 中途 URL 刷新）
            bytes_downloaded = resume_offset
            mode = "ab" if resume_offset > 0 else "wb"

            with open(tmp, mode) as f:
                while bytes_downloaded < total_size:
                    chunk_end = min(bytes_downloaded + chunk_size - 1, total_size - 1)
                    chunk_ok = False

                    for chunk_attempt in range(3):
                        try:
                            chunk = _download_chunk(url, bytes_downloaded, chunk_end, token)
                            if chunk:
                                f.write(chunk)
                                f.flush()
                                bytes_downloaded += len(chunk)
                                chunk_ok = True
                                break
                        except urllib.error.HTTPError as e:
                            # 签名 URL 中途过期：尝试刷新 URL 后继续
                            if e.code in (401, 403, 405) and url_refresher:
                                new_url = url_refresher()
                                if new_url:
                                    url = new_url
                                    logger.debug(f"      下载中途刷新 URL，从 {format_size(bytes_downloaded)} 继续")
                                    continue  # 用新 URL 重试当前 chunk
                            if chunk_attempt < 2:
                                time.sleep(1 * (2 ** chunk_attempt))
                        except Exception:
                            if chunk_attempt < 2:
                                time.sleep(1 * (2 ** chunk_attempt))

                    if not chunk_ok:
                        raise IOError(f"Chunk {bytes_downloaded}-{chunk_end} failed after 3 retries")

                f.flush()
                # 验证大小
                if bytes_downloaded != total_size and total_size > 0:
                    raise IOError(f"Size mismatch: {bytes_downloaded} vs {total_size}")

            # 原子写入
            if not tmp.exists():
                raise IOError("临时文件在写入后丢失")
            tmp.replace(dest)
            file_hash = compute_hash(dest)
            return True, bytes_downloaded, file_hash

        except urllib.error.HTTPError as e:
            if e.code == 416:  # Range Not Satisfiable = 已经完整下载
                if tmp.exists():
                    tmp.replace(dest)
                    file_hash = compute_hash(dest)
                    return True, dest.stat().st_size, file_hash
                return False, 0, f"HTTP {e.code}"
            if not _is_retryable(e):
                return False, 0, f"HTTP {e.code} (不可重试)"
        except Exception as e:
            if not _is_retryable(e):
                # 清理临时文件
                if tmp.exists():
                    tmp.unlink(missing_ok=True)
                return False, 0, str(e)[:200]

        # 指数退避
        wait = min(2 ** attempt, 30)
        logger.debug(f"      重试 {attempt+1}/{max_retries}，等待 {wait}s...")
        time.sleep(wait)

    # 清理
    if tmp.exists():
        tmp.unlink(missing_ok=True)
    return False, 0, f"超过最大重试次数 ({max_retries})"

def _simple_download(url: str, dest: Path, token: str,
                        max_retries: int = 3) -> tuple[bool, int, str]:
    """小文件简单下载（流式写入 + 重试）"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")

    for attempt in range(max_retries):
        try:
            headers = {"User-Agent": "WPS-Backup/3.0"}
            if token:
                headers["Authorization"] = f"Bearer {token}"

            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=config.DOWNLOAD_TIMEOUT) as resp:
                with open(tmp, "wb") as f:
                    while True:
                        block = resp.read(65536)
                        if not block:
                            break
                        f.write(block)

            if not tmp.exists():
                return False, 0, "临时文件在写入后丢失"
            tmp.replace(dest)  # 原子写入

            file_hash = compute_hash(dest)
            return True, dest.stat().st_size, file_hash

        except urllib.error.HTTPError as e:
            if e.code == 416 and tmp.exists():
                tmp.replace(dest)
                return True, dest.stat().st_size, compute_hash(dest)
            if not _is_retryable(e):
                return False, 0, f"HTTP {e.code} (不可重试)"
        except Exception as e:
            if not _is_retryable(e):
                if tmp.exists():
                    tmp.unlink(missing_ok=True)
                return False, 0, str(e)[:200]

        wait = min(2 ** attempt, 10)
        logger.debug(f"      简单下载重试 {attempt+1}/{max_retries}，等待 {wait}s...")
        time.sleep(wait)

    if tmp.exists():
        tmp.unlink(missing_ok=True)
    return False, 0, f"超过最大重试次数 ({max_retries})"

# ============================================================
# 备份引擎（多线程版）
# ============================================================

class BackupEngine:
    def __init__(self, workers: int = None):
        self.state = BackupState()
        self.token = _get_auth_token()
        self.workers = workers or config.MAX_CONCURRENT
        self._result_lock = threading.Lock()
        self._url_lock = threading.Lock()
        self.kdocs_available = kdocs_engine.check_kdocs_cli_available()
        if self.kdocs_available:
            logger.info(f"   🔧 kdocs-cli 已就绪 ({kdocs_engine.get_kdocs_version()})")
        else:
            logger.info("   ⏭️  kdocs-cli 不可用，跳过内容备份")

    # ---- 多线程下载 worker ----

    def _get_download_url_throttled(self, drive_id: str, file_id: str) -> Optional[str]:
        """串行化获取下载URL，避免并发轰炸WPS API"""
        with self._url_lock:
            url = get_download_url(drive_id, file_id)
            if url:
                time.sleep(0.2)  # 每个URL请求间隔200ms
            return url

    def _download_worker(self, rf: RemoteFile, index: int, total: int,
                          result: BackupResult, counter: AtomicCounter,
                          start_time: float) -> None:
        """单个文件的下载任务"""
        name = rf.name
        snap = self.state.get_snapshot(rf.drive_id, rf.file_id)
        is_new = snap is None
        tag = "🆕" if is_new else "🔄"

        # 使用 file_id 前8位隔离同名文件，避免多线程竞争同一 tmp
        safe_name = sanitize(name)
        stem = Path(safe_name).stem
        suffix = Path(safe_name).suffix
        unique_name = f"{stem}_{rf.file_id[:8]}{suffix}"
        local_path = config.BACKUP_DIR / rf.drive_name / unique_name

        if local_file_exists(local_path, rf.size):
            local_hash = compute_hash(local_path)
            if local_hash:
                snap = FileSnapshot(
                    file_id=rf.file_id, drive_id=rf.drive_id,
                    name=name, size=rf.size, mtime=rf.mtime,
                    local_path=str(local_path), local_hash=local_hash,
                    link_url=rf.link_url, drive_name=rf.drive_name,
                    backed_up_at="",
                )
                self.state.mark_backed_up(snap)
                with self._result_lock:
                    result.skipped += 1
                return

        # Fallback: 旧版本备份使用的不带 file_id 的路径若存在，直接迁移到新路径
        old_path = config.BACKUP_DIR / rf.drive_name / safe_name
        if local_file_exists(old_path, rf.size):
            try:
                old_path.rename(local_path)
                local_hash = compute_hash(local_path)
                if local_hash:
                    snap = FileSnapshot(
                        file_id=rf.file_id, drive_id=rf.drive_id,
                        name=name, size=rf.size, mtime=rf.mtime,
                        local_path=str(local_path), local_hash=local_hash,
                        link_url=rf.link_url, drive_name=rf.drive_name,
                        backed_up_at="",
                    )
                    self.state.mark_backed_up(snap)
                    with self._result_lock:
                        result.skipped += 1
                    logger.info(f"   [{index}/{total}] ⏭️ {name} (历史文件已迁移)")
                    return
            except Exception:
                pass  # 迁移失败则继续正常下载

        # 下载，支持失败时刷新URL重试一次
        final_ok = False
        final_size = 0
        final_hash = ""
        for url_attempt in range(2):
            url = self._get_download_url_throttled(rf.drive_id, rf.file_id)
            if not url:
                if url_attempt == 0:
                    ext = Path(name).suffix.lower()
                    if ext in SKIP_EXTS:
                        logger.warning(f"   [{index}/{total}] ⏭️ {name} — 不可下载格式 ({ext})")
                    else:
                        logger.error(f"   [{index}/{total}] ❌ {name} — 无下载地址")
                    self.state.mark_failed(
                        rf.drive_id, rf.file_id, "无下载地址",
                        name=name, size=rf.size, mtime=rf.mtime, drive_name=rf.drive_name
                    )
                    with self._result_lock:
                        result.failed += 1
                        result.errors.append(f"{name}: 无下载地址")
                break

            # 下载（断点续传用于大文件）
            t0 = time.time()
            if rf.size > 10 * 1024 * 1024:  # >10MB 用断点续传
                ok, size, file_hash = download_with_resume(
                    url, local_path, self.token,
                    url_refresher=lambda: self._get_download_url_throttled(rf.drive_id, rf.file_id)
                )
            else:
                ok, size, file_hash = _simple_download(url, local_path, self.token)

            if ok:
                final_ok = True
                final_size = size
                final_hash = file_hash
                break

            # 失败分析：是否值得刷新URL重试
            err_lower = file_hash.lower()
            need_refresh = any(k in err_lower for k in ("405", "chunk", "expired", "token", "signature"))
            if url_attempt == 0 and need_refresh:
                logger.warning(f"   [{index}/{total}] ⚠️ {name} — {file_hash}，尝试刷新下载地址...")
                continue
            else:
                final_size = size
                final_hash = file_hash
                break

        if final_ok:
            snap = FileSnapshot(
                file_id=rf.file_id, drive_id=rf.drive_id,
                name=name, size=final_size, mtime=rf.mtime,
                local_path=str(local_path), local_hash=final_hash,
                link_url=rf.link_url, drive_name=rf.drive_name,
                backed_up_at="",
            )
            self.state.mark_backed_up(snap)

            # 内容备份（kdocs-cli）
            content_ok = False
            if (config.CONTENT_BACKUP_ENABLED and self.kdocs_available and
                    kdocs_engine.is_content_readable(Path(name).suffix)):
                try:
                    content_result = kdocs_engine.backup_file_content(
                        file_id=rf.file_id, name=name,
                        drive_id=rf.drive_id, drive_name=rf.drive_name,
                    )
                    if content_result.success:
                        content_ok = True
                        with self._result_lock:
                            result.content_backed_up += 1
                    else:
                        with self._result_lock:
                            result.content_failed += 1
                        logger.debug(f"   [{index}/{total}] ⚠️ 内容备份失败: {name} — {content_result.error}")
                except Exception as e:
                    with self._result_lock:
                        result.content_failed += 1
                    logger.debug(f"   [{index}/{total}] ⚠️ 内容备份异常: {name} — {e}")

            with self._result_lock:
                if is_new:
                    result.new += 1
                else:
                    result.updated += 1
            content_tag = " 📝" if content_ok else ""
            logger.info(f"   [{index}/{total}] ✅ {name} ({format_size(final_size)}){content_tag}")
        else:
            self.state.mark_failed(
                rf.drive_id, rf.file_id, final_hash,
                name=name, size=rf.size, mtime=rf.mtime, drive_name=rf.drive_name
            )
            with self._result_lock:
                result.failed += 1
                result.errors.append(f"{name}: {final_hash}")
            logger.error(f"   [{index}/{total}] ❌ {name} — {final_hash}")

        # 进度 & ETA
        done = counter.inc()
        if done % 10 == 0 or done == total:
            elapsed_total = time.time() - start_time
            remaining = (total - done) * (elapsed_total / done) if done > 0 else 0
            eta = time.strftime("%H:%M:%S", time.gmtime(remaining))
            with self._result_lock:
                logger.info(f"   📊 进度: {done}/{total} ({done*100//total}%) | ETA: {eta} | "
                           f"✅{result.new+result.updated} ⏭️{result.skipped} ❌{result.failed}")

    # ---- 主流程 ----

    def run(self, max_files: int = None, dry_run: bool = False) -> BackupResult:
        result = BackupResult()
        start = time.time()
        logger.info("=" * 60)
        logger.info(f"🚀 开始差量备份 (并发: {self.workers} 线程)")

        # Phase 1: 认证
        if not self.token:
            self.token = _get_auth_token()
        if not self.token:
            logger.error("❌ 无法获取认证 token")
            result.errors.append("认证失败")
            return result

        # Phase 2: 扫描远程
        logger.info("📡 扫描远程文件...")
        try:
            drives = scan_remote_drives()
        except RuntimeError as e:
            logger.error(f"❌ {e}")
            result.errors.append(str(e))
            return result

        all_remote: list[RemoteFile] = []
        for d in drives:
            files = scan_remote_files(d["id"], d["name"])
            all_remote.extend(files)
            logger.info(f"   📁 {d['name']}: {len(files)} 个文件")

        result.total = len(all_remote)
        logger.info(f"📊 远程共 {result.total} 个文件")

        # Phase 3: 差量对比
        current_keys = set()
        to_download: list[RemoteFile] = []

        for rf in all_remote:
            key = self.state.get_key(rf.drive_id, rf.file_id)
            current_keys.add(key)
            if self.state.needs_update(rf.drive_id, rf.file_id, rf.mtime):
                to_download.append(rf)
            else:
                result.skipped += 1

        pruned = self.state.prune_stale(current_keys)
        if pruned:
            logger.info(f"🧹 清理 {pruned} 条过期记录")

        logger.info(f"📊 差量: {result.skipped} 跳过 | {len(to_download)} 待下载")

        # Phase 4: 多线程下载
        if dry_run:
            logger.info("🔍 Dry-run 模式")
            for rf in to_download[:max_files] if max_files else to_download:
                snap = self.state.get_snapshot(rf.drive_id, rf.file_id)
                logger.info(f"   {'🆕' if not snap else '🔄'} {rf.name}")
                if snap:
                    result.updated += 1
                else:
                    result.new += 1
            return result

        download_list = to_download[:max_files] if max_files else to_download
        total_dl = len(download_list)
        counter = AtomicCounter()
        logger.info(f"⬇️  开始下载 {total_dl} 个文件 ({self.workers} 线程并发)...")

        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {
                executor.submit(
                    self._download_worker, rf, i + 1, total_dl,
                    result, counter, start
                ): rf
                for i, rf in enumerate(download_list)
            }
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    rf = futures[future]
                    logger.error(f"   ❌ 线程异常: {rf.name} — {e}")
                    with self._result_lock:
                        result.failed += 1

        # Phase 5: 内容备份汇总（dry-run 模式下跳过）
        if not dry_run and config.CONTENT_BACKUP_ENABLED and self.kdocs_available:
            logger.info(f"   📝 内容备份: {result.content_backed_up} 成功 | {result.content_failed} 失败")
            if result.content_backed_up > 0:
                logger.info(f"   📁 内容目录: {config.CONTENT_BACKUP_DIR}")

        # Phase 6: 汇总
        elapsed = time.time() - start
        total_size = sum(
            s.size for s in self.state.snapshots.values()
        )
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 备份完成 ({elapsed:.1f}s)")
        logger.info(f"   🆕 新增: {result.new} | 🔄 更新: {result.updated} | ⏭️ 跳过: {result.skipped} | ❌ 失败: {result.failed}")
        if result.content_backed_up > 0:
            logger.info(f"   📝 内容备份: {result.content_backed_up} 个文件")
        logger.info(f"   💾 总计: {len(self.state.snapshots)} 文件, {format_size(total_size)}")
        logger.info(f"   📁 {config.BACKUP_DIR}")
        logger.info(f"{'='*60}")
        return result