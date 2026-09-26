"""
OTL 专项备份引擎 v4.1
混合策略：
1. 通过 wps365-cli API 获取所有 .otl 文件元数据
2. 【v4.1】通过 wps365-cli airpage 备份 OTL 内容（Markdown + 导出 docx），
   替代 kdocs-cli read-file（kdocs API 已拒绝企业账号，错误码 403001）
3. 【保留】kdocs-cli read-file 作为内容备份回退（个人账号可用时）
4. 【保留】从 WPS Office 本地云同步缓存中提取 .otl 原始文件（作为补充）
5. 对于仍无法备份的 .otl 文件，生成 kdocs.cn 导出链接清单
"""

import json
import os
import subprocess
import shutil
import time
import re
import threading
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field, asdict

from . import config
from .logger import setup_logger
from . import kdocs_engine
from . import airpage_engine
from .app_contract import CANCEL

logger = setup_logger()

# WPS Office 本地云同步缓存路径
WPS_CACHE_DIR = Path.home() / "Library/Containers/com.kingsoft.wpsoffice.mac/Data/Library/Application Support/Kingsoft/WPS Cloud Files/userdata/qing/filecache"
RENT_FILE = "rectfile2.xml"

OTL_BACKUP_DIR = config.BACKUP_DIR / "_otl_files"
OTL_CONTENT_DIR = config.BACKUP_DIR / "_otl_content"
OTL_CONVERTED_DIR = config.BACKUP_DIR / "_otl_converted_docx"
OTL_STATE_FILE = config.STATE_DIR / "_otl_state.json"


def is_permanent_otl_failure(name: str, error: str) -> bool:
    """服务端无内容可备的失败：.otl.link 快捷方式无法读取、文档本身为空"""
    return name.lower().endswith(".otl.link") or error == "OTL 内容为空"


class OTLBackupState:
    """OTL 备份增量状态管理器"""

    def __init__(self, state_file: Path = OTL_STATE_FILE):
        self.state_file = state_file
        self.records: dict[str, dict] = {}  # file_id -> {mtime, path, backed_up_at, content_path}
        self._lock = threading.RLock()      # v5：OTL 阶段并发写状态
        self._load()

    def _load(self):
        if not self.state_file.exists():
            return
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                self.records = json.load(f)
        except Exception:
            self.records = {}

    def _save(self):
        with self._lock:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.state_file.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.records, f, ensure_ascii=False, indent=2)
            tmp.replace(self.state_file)

    # ---- v5：产物级增量 ----

    @staticmethod
    def _exists(path) -> bool:
        return bool(path) and Path(path).exists()

    def plan_v5(self, file_id: str, remote_mtime: int, want_docx: bool) -> tuple:
        """返回 (需要 md, 需要 docx)。永久失败在 mtime 变化前跳过；旧格式（<5）一次性升级 md；只补缺失产物"""
        rec = self.records.get(file_id)
        if not rec:
            return True, want_docx
        changed = remote_mtime > rec.get("mtime", 0)
        if rec.get("permanent") and not changed:
            return False, False
        if changed:
            return True, want_docx
        need_md = (rec.get("format", 0) < airpage_engine.FORMAT_VERSION
                   or not self._exists(rec.get("content_path")) or bool(rec.get("md_error")))
        need_docx = want_docx and not self._exists(rec.get("docx_path"))
        return need_md, need_docx

    def record_v5(self, file_id: str, mtime: int, res, did_md: bool, did_docx: bool):
        with self._lock:
            rec = dict(self.records.get(file_id, {}))
            for k in ("path", "content_path", "docx_path"):
                rec.setdefault(k, "")
            rec["mtime"] = mtime
            if res.version:
                rec["airpage_version"] = res.version
            if did_md:
                rec["md_error"] = res.md_error
                if res.md_ok:
                    rec["content_path"] = res.content_path
                    rec["format"] = airpage_engine.FORMAT_VERSION
            if did_docx:
                rec["docx_error"] = res.docx_error
                if res.docx_ok:
                    rec["docx_path"] = res.docx_path
            rec["permanent"] = bool(res.permanent)
            if res.permanent:
                rec["error_msg"] = res.md_error
            elif res.md_ok or (not did_md and not rec.get("md_error")):
                rec.pop("error_msg", None)
            rec["backed_up_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            self.records[file_id] = rec
            self._save()

    def needs_update(self, file_id: str, remote_mtime: int) -> bool:
        rec = self.records.get(file_id)
        if not rec:
            return True
        if rec.get("error_msg") and not rec.get("permanent"):
            return True  # 临时失败：每次重试
        return remote_mtime > rec.get("mtime", 0)

    def mark_backed_up(self, file_id: str, mtime: int, local_path: str = "",
                       content_path: str = "", docx_path: str = ""):
        """合并写入（保留 v5 字段 format/airpage_version/permanent 等），清除失败标记"""
        with self._lock:
            rec = dict(self.records.get(file_id, {}))
            rec.update({
                "mtime": mtime,
                "path": local_path or rec.get("path", ""),
                "content_path": content_path or rec.get("content_path", ""),
                "docx_path": docx_path or rec.get("docx_path", ""),
                "backed_up_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            for k in ("error_msg", "permanent", "failed_at"):
                rec.pop(k, None)
            self.records[file_id] = rec
            self._save()

    def mark_failed(self, file_id: str, mtime: int, error: str, name: str = ""):
        """记录内容备份失败。永久失败（.otl.link 快捷方式 / 空文档）在 mtime 变化前不再重试；
        保留此前成功备份的路径字段。"""
        rec = dict(self.records.get(file_id, {}))
        rec.setdefault("path", "")
        rec.setdefault("content_path", "")
        rec.setdefault("docx_path", "")
        rec.update({
            "mtime": mtime,
            "error_msg": error,
            "permanent": is_permanent_otl_failure(name, error),
            "failed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        self.records[file_id] = rec
        self._save()

    def prune_stale(self, current_file_ids: set):
        """清理远程已不存在的记录。
        防护：远程扫描结果为空但本地有记录时，视为扫描异常，跳过清理。"""
        if not current_file_ids and self.records:
            logger.warning("⚠️  远程扫描结果为空，跳过状态清理（防止扫描异常清空增量状态）")
            return
        stale = set(self.records.keys()) - current_file_ids
        if stale:
            for fid in stale:
                del self.records[fid]
            self._save()


@dataclass
class OTLFileInfo:
    """从 WPS Drive API 获取的 .otl 文件信息"""
    file_id: str
    drive_id: str
    drive_name: str
    name: str
    size: int
    mtime: int
    link_id: str
    link_url: str

    @property
    def safe_name(self) -> str:
        return re.sub(r'[\\/:*?"<>|\t\n\r]', '_', self.name.strip())[:200]


@dataclass
class CacheFileEntry:
    """WPS Office 缓存中的文件条目（来自 rectfile2.xml）"""
    name: str
    file_id: str          # kdocs 内部 fileId（数字）
    group_id: str
    access_time: int      # 毫秒时间戳
    device_name: str      # 原始设备名（如"我的企业文档"）


@dataclass
class OTLBackupResult:
    total: int = 0
    content_backed_up: int = 0   # 内容备份成功（airpage / kdocs-cli）
    content_skipped: int = 0      # 内容已是最新
    content_failed: int = 0       # 内容备份失败
    docx_exported: int = 0        # airpage 导出 docx 成功数
    cached: int = 0               # 缓存中命中的文件
    copied: int = 0               # 成功从缓存复制的文件
    not_cached: int = 0           # 未在缓存中的文件
    errors: list = field(default_factory=list)


def select_content_backend(airpage_available: bool, kdocs_available: bool) -> Optional[str]:
    """选择 OTL 内容备份后端：airpage 优先（企业账号可用），kdocs-cli 回退"""
    if config.AIRPAGE_OTL_CONTENT_ENABLED and airpage_available:
        return "airpage"
    if kdocs_available:
        return "kdocs"
    return None


# ---- WPS CLI 封装 ----

def _cli(*args, timeout=60, retries=2):
    """复用主引擎的 CLI 调用逻辑"""
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
        except FileNotFoundError:
            logger.error(f"❌ 找不到 wps365-cli 可执行文件: {config.CLI_BIN}（设置 WPS365_CLI_BIN 或安装到 ~/.local/bin）")
            return None
        except subprocess.TimeoutExpired:
            if attempt < retries:
                time.sleep(3)
        except json.JSONDecodeError:
            if attempt < retries:
                time.sleep(2)
    return None


class ScanIncompleteError(RuntimeError):
    """扫描不完整：partial 为已成功扫描到的文件，调用方可继续使用但不得据此 prune"""

    def __init__(self, msg: str, partial: list):
        super().__init__(msg)
        self.partial = partial


def list_otl_files(drive_id: str = "Q53zypp", drive_name: str = "", parent_id: str = "0") -> list[OTLFileInfo]:
    """
    通过 WPS CLI 递归扫描指定盘下所有 .otl 文件
    """
    result = []
    _recurse_otl(drive_id, drive_name or drive_id, parent_id, result)
    return result


def list_otl_files_all_drives() -> list[OTLFileInfo]:
    """扫描所有盘中的 .otl 文件"""
    """扫描所有盘中的 .otl 文件。任一盘失败抛 ScanIncompleteError（携带部分结果）。
    不再回退到硬编码默认盘：部分结果会让 prune_stale 误删其他盘的记录。"""
    result = []
    data = _cli("drive", "list", "--allotee-type", "user",
                "--page-size", "50", "-o", "json")
    if not data or data.get("code") != 0:
        raise ScanIncompleteError("无法获取盘列表（认证或 CLI 异常）", [])

    failed = []
    for d in data.get("data", {}).get("items", []):
        drive_id = d.get("id", "")
        drive_name = d.get("name", "")
        if not drive_id:
            continue
        try:
            files = list_otl_files(drive_id, drive_name)
        except RuntimeError as e:
            logger.error(f"   ❌ {drive_name}: {e}")
            failed.append(drive_name or drive_id)
            continue
        result.extend(files)
        logger.info(f"   📁 {drive_name}: {len(files)} 个 .otl")
    if failed:
        raise ScanIncompleteError(f"部分盘扫描失败: {', '.join(failed)}", result)
    return result


def _recurse_otl(drive_id: str, drive_name: str, parent_id: str,
                  result: list[OTLFileInfo]):
    """递归扫描目录树中的 .otl 文件"""
    token = ""
    while True:
        args = ["drive", "file", "list", drive_id, parent_id,
                "--filter-exts", "otl", "--page-size", "200",
                "--with-permission", "-o", "json"]
        if token:
            args += ["--page-token", token]
        data = _cli(*args)
        if not data or data.get("code") != 0:
            raise RuntimeError(f"扫描 .otl 失败: {drive_name}/{parent_id}")

        for item in data.get("data", {}).get("items", []):
            info = OTLFileInfo(
                file_id=item["id"],
                drive_id=drive_id,
                drive_name=drive_name,
                name=item["name"],
                size=item.get("size", 0),
                mtime=item.get("mtime", 0),
                link_id=item.get("link_id", ""),
                link_url=item.get("link_url", ""),
            )
            result.append(info)

        token = data.get("data", {}).get("next_page_token", "")
        if not token:
            break

    # 同时扫描子文件夹（分页：目录项 >200 时后续页中的文件夹也要递归）
    token = ""
    while True:
        sub_args = ["drive", "file", "list", drive_id, parent_id,
                    "--page-size", "200", "-o", "json"]
        if token:
            sub_args += ["--page-token", token]
        sub_data = _cli(*sub_args)
        if not sub_data or sub_data.get("code") != 0:
            raise RuntimeError(f"列出子目录失败: {drive_name}/{parent_id}")
        for item in sub_data.get("data", {}).get("items", []):
            if item.get("type") == "folder":
                _recurse_otl(drive_id, drive_name, item["id"], result)
        token = sub_data.get("data", {}).get("next_page_token", "")
        if not token:
            break


# ---- WPS Office 本地缓存解析（保留作为补充） ----

def cache_dir_accessible(path: Path, timeout: int = 15, popen=subprocess.Popen) -> bool:
    """在带超时的子进程中探测目录可读性。
    ~/Library/Containers 受 macOS“App 数据”隐私保护（TCC）：launchd 等无终端环境下
    opendir 会阻塞等待授权弹窗，直接在主进程访问会导致备份永久挂起。"""
    import sys
    probe = "import os,sys; p=sys.argv[1]; os.path.isdir(p) and os.listdir(p)"
    try:
        proc = popen([sys.executable, "-c", probe, str(path)],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        return False
    try:
        return proc.wait(timeout=timeout) == 0
    except subprocess.TimeoutExpired:
        proc.kill()  # 不再 wait：阻塞在 TCC 的进程可能无法及时回收
        logger.warning(f"⚠️  访问 WPS Office 缓存超时（疑似 macOS App 数据权限拦截），跳过缓存阶段。"
                       f"如需启用：为 {sys.executable} 授予“完全磁盘访问权限”，或设 WPS_OTL_CACHE_SCAN=0 关闭")
        return False


def find_cache_root() -> Optional[Path]:
    """查找 WPS Office 云同步缓存根目录"""
    if not config.OTL_CACHE_SCAN_ENABLED:
        return None
    if not cache_dir_accessible(WPS_CACHE_DIR):
        return None
    if not WPS_CACHE_DIR.exists():
        return None
    for d in WPS_CACHE_DIR.iterdir():
        if d.is_dir() and d.name.startswith("."):
            kdocs = d / "kdocsfile"
            if kdocs.exists():
                return d
    return None


def parse_rectfile2(cache_root: Path) -> list[CacheFileEntry]:
    """解析 rectfile2.xml 获取缓存文件列表"""
    entries = []
    xml_path = cache_root / RENT_FILE
    if not xml_path.exists():
        logger.warning(f"rectfile2.xml 不存在: {xml_path}")
        return entries

    try:
        tree = ET.parse(str(xml_path))
        root = tree.getroot()
        for file_elem in root.findall(".//file"):
            name = file_elem.get("name", "")
            if not name.lower().endswith(".otl"):
                continue
            entries.append(CacheFileEntry(
                name=name,
                file_id=file_elem.get("fileId", ""),
                group_id=file_elem.get("groupId", ""),
                access_time=int(file_elem.get("accessTime", "0")),
                device_name=file_elem.get("originalDeviceName", ""),
            ))
    except Exception as e:
        logger.error(f"解析 rectfile2.xml 失败: {e}")

    return entries


def list_cache_otl_files(cache_root: Path) -> dict[str, Path]:
    """列出缓存中所有 kdocsfile 目录及其 content.otl 路径"""
    result = {}
    kdocs_dir = cache_root / "kdocsfile"
    if not kdocs_dir.exists():
        return result

    for entry in kdocs_dir.iterdir():
        if not entry.is_dir():
            continue
        content_otl = entry / "data" / "sync" / "content.otl"
        if content_otl.exists():
            result[entry.name] = content_otl
    return result


def match_cache_to_api(
    api_files: list[OTLFileInfo],
    cache_entries: list[CacheFileEntry],
    cache_otl_map: dict[str, Path],
) -> list[tuple[OTLFileInfo, Path]]:
    """将 API 文件列表与缓存文件进行匹配"""
    matched = []
    cache_by_name: dict[str, CacheFileEntry] = {}
    for ce in cache_entries:
        cache_by_name[ce.name.lower()] = ce

    cache_file_stats: list[tuple[Path, int, int]] = []
    for dirname, otl_path in cache_otl_map.items():
        try:
            stat = otl_path.stat()
            cache_file_stats.append((otl_path, stat.st_size, int(stat.st_mtime)))
        except OSError:
            pass

    cache_file_stats.sort(key=lambda x: x[1])
    used_cache_paths = set()

    def _find_best_size_match(api_file: OTLFileInfo, min_ratio: float, max_ratio: float) -> Optional[Path]:
        if api_file.size <= 0:
            return None
        best_path = None
        best_diff = float('inf')
        for otl_path, cache_size, _ in cache_file_stats:
            if otl_path in used_cache_paths:
                continue
            ratio = cache_size / api_file.size
            if min_ratio <= ratio <= max_ratio:
                diff = abs(ratio - 1.0)
                if diff < best_diff:
                    best_diff = diff
                    best_path = otl_path
        return best_path

    for api_file in api_files:
        matched_path = None
        ce = cache_by_name.get(api_file.name.lower())
        if ce:
            matched_path = _find_best_size_match(api_file, 0.5, 2.0)
        if not matched_path:
            matched_path = _find_best_size_match(api_file, 0.85, 1.15)

        if matched_path:
            matched.append((api_file, matched_path))
            used_cache_paths.add(matched_path)

    return matched


def _get_dest_path(api_file: OTLFileInfo, state: "OTLBackupState" = None) -> Path:
    """生成备份目标路径，处理重名"""
    if state:
        rec = state.records.get(api_file.file_id)
        if rec:
            old_path = Path(rec["path"])
            if old_path.exists():
                return old_path

    base = OTL_BACKUP_DIR / api_file.safe_name
    if not base.exists():
        return base
    stem = base.stem
    suffix = base.suffix
    unique_name = f"{stem}_{api_file.file_id[:8]}{suffix}"
    return OTL_BACKUP_DIR / unique_name


# ---- 备份主逻辑 v4.1 ----

class OTLEngine:
    """OTL 文件备份引擎 v4.1 — 混合策略（airpage 内容 + docx 导出 + 缓存实体）"""

    def __init__(self, target_drive_id: str = None, progress=None):
        self._result_lock = threading.Lock()
        self.target_drive_id = target_drive_id
        self.progress = progress
        OTL_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        OTL_CONTENT_DIR.mkdir(parents=True, exist_ok=True)
        OTL_CONVERTED_DIR.mkdir(parents=True, exist_ok=True)
        self.airpage_available = (
            airpage_engine.check_airpage_available()
            if config.AIRPAGE_OTL_CONTENT_ENABLED else False
        )
        if self.airpage_available:
            logger.info("   🔧 airpage 已就绪（wps365-cli，企业账号可用）")
        self.kdocs_available = kdocs_engine.check_kdocs_cli_available()
        if self.kdocs_available:
            logger.info(f"   🔧 kdocs-cli 已就绪 ({kdocs_engine.get_kdocs_version()})")
        if not self.airpage_available and not self.kdocs_available:
            logger.warning("   ⚠️  airpage / kdocs-cli 均不可用，将回退到纯缓存模式")

    def run(self, dry_run: bool = False, api_files: list = None,
            scan_complete: bool = True) -> OTLBackupResult:
        """api_files：主引擎一次遍历时收集的 .otl 条目（v5，免二次扫描）；None 时自行扫描"""
        result = OTLBackupResult()
        start = time.time()

        logger.info("=" * 60)
        logger.info("📋 OTL 专项备份 v5 (官方 markdown_zip + docx 并行导出，产物级增量)")

        # ---- Phase 1: API 扫描（v5：优先复用主引擎扫描结果） ----
        if api_files is not None:
            logger.info(f"📡 复用主引擎扫描结果（{len(api_files)} 个 .otl，免二次扫描）")
            if not scan_complete:
                result.errors.append("主引擎扫描不完整，OTL 状态不清理")
        else:
            logger.info("📡 扫描 WPS Drive .otl 文件...")
            try:
                if self.target_drive_id:
                    api_files = list_otl_files(self.target_drive_id)
                else:
                    api_files = list_otl_files_all_drives()
            except ScanIncompleteError as e:
                scan_complete = False
                api_files = e.partial
                logger.error(f"❌ API 扫描不完整: {e}")
                result.errors.append(f"API 扫描不完整: {e}")
                if not api_files:
                    return result
            except Exception as e:
                logger.error(f"❌ API 扫描失败: {e}")
                result.errors.append(f"API 扫描失败: {e}")
                return result

        result.total = len(api_files)
        logger.info(f"📊 远程共 {result.total} 个 .otl 文件")

        # ---- Phase 2: 内容备份（v4.1: airpage 优先，kdocs-cli 回退） ----
        backend = select_content_backend(self.airpage_available, self.kdocs_available)
        if config.OTL_CONTENT_BACKUP_ENABLED and backend == "airpage":
            self._run_v5(api_files, result, dry_run)
        elif config.OTL_CONTENT_BACKUP_ENABLED and backend:
            logger.info(f"📝 通过 {backend} 备份 OTL 内容...")
            state = OTLBackupState()
            for i, api_file in enumerate(api_files, 1):
                if CANCEL.is_set():
                    result.errors.append("运行被取消或超时")
                    break
                if self.progress:
                    self.progress("otl", i, len(api_files), api_file.name)
                # 增量检查
                if not state.needs_update(api_file.file_id, api_file.mtime):
                    result.content_skipped += 1
                    continue

                if dry_run:
                    logger.info(f"   🔍 [dry-run] {api_file.name}")
                    result.content_backed_up += 1
                    continue

                content_result = self._backup_content(api_file, dry_run=dry_run)

                if content_result and content_result.success:
                    result.content_backed_up += 1
                    if content_result.docx_path:
                        result.docx_exported += 1
                    # 更新状态
                    state.mark_backed_up(
                        api_file.file_id, api_file.mtime,
                        content_path=content_result.content_path,
                        docx_path=content_result.docx_path,
                    )
                else:
                    result.content_failed += 1
                    err = content_result.error if content_result else "无可用后端"
                    logger.warning(f"   ⚠️  OTL 内容备份失败: {api_file.name} — {err}")
                    if content_result:
                        state.mark_failed(api_file.file_id, api_file.mtime, err, name=api_file.name)

            logger.info(f"   📝 内容备份({backend}): {result.content_backed_up} 成功 | "
                        f"{result.content_skipped} 跳过 | {result.content_failed} 失败"
                        + (f" | 📄 docx 导出 {result.docx_exported}" if result.docx_exported else ""))
        else:
            logger.info("   ⏭️  OTL 内容备份已禁用或无可用后端（airpage / kdocs-cli）")

        # ---- Phase 3: 缓存扫描（保留作为补充） ----
        logger.info("🔍 扫描 WPS Office 本地缓存...")
        cache_root = find_cache_root()
        if not cache_root:
            logger.warning("⚠️  未找到 WPS Office 云同步缓存")
            # 如果没有缓存且无任何内容备份后端，则生成导出指南
            if not self.airpage_available and not self.kdocs_available:
                result.not_cached = result.total
                self._generate_export_guide(api_files, result)
                return result
        else:
            cache_entries = parse_rectfile2(cache_root)
            cache_otl_map = list_cache_otl_files(cache_root)
            logger.info(f"   缓存条目: {len(cache_entries)} | 实际文件: {len(cache_otl_map)}")

            # Phase 4: 匹配并复制缓存文件
            matched = match_cache_to_api(api_files, cache_entries, cache_otl_map)
            matched_ids = {m[0].file_id for m in matched}
            result.cached = len(matched_ids)
            result.not_cached = result.total - result.cached

            logger.info(f"📊 缓存匹配: {result.cached} 已缓存 | {result.not_cached} 未缓存")

            if dry_run:
                for api_file, cache_path in matched:
                    logger.info(f"   📋 {api_file.name}")
                    logger.info(f"      缓存: {cache_path}")
            else:
                state = OTLBackupState()
                for api_file, cache_path in matched:
                    try:
                        dest = _get_dest_path(api_file, state)
                        if not state.needs_update(api_file.file_id, api_file.mtime):
                            logger.info(f"   ⏭️  {api_file.name} (已是最新)")
                            continue

                        shutil.copy2(str(cache_path), str(dest))
                        if api_file.mtime > 0:
                            try:
                                os.utime(str(dest), (api_file.mtime, api_file.mtime))
                            except OSError as e:
                                logger.warning(f"   ⚠️  无法设置时间戳 {api_file.name}: {e}")

                        # 获取已有的 content_path / docx_path（如果有）
                        rec = state.records.get(api_file.file_id, {})
                        content_path = rec.get("content_path", "")
                        docx_path = rec.get("docx_path", "")
                        state.mark_backed_up(api_file.file_id, api_file.mtime, str(dest),
                                             content_path, docx_path)
                        result.copied += 1
                        logger.info(f"   ✅ {api_file.name} (缓存复制)")
                    except Exception as e:
                        result.errors.append(f"{api_file.name}: {e}")
                        logger.error(f"   ❌ {api_file.name}: {e}")

        # ---- Phase 5: 清理已不存在的文件记录 ----
        if scan_complete:
            current_ids = {f.file_id for f in api_files}
            state = OTLBackupState()
            state.prune_stale(current_ids)
        else:
            logger.warning("⚠️  扫描不完整，跳过 OTL 状态清理")

        # ---- Phase 6: 未缓存文件清单（仅当无任何内容备份后端时） ----
        if not self.airpage_available and not self.kdocs_available:
            uncached = [f for f in api_files]
            self._generate_export_guide(uncached, result)

        # ---- 汇总 ----
        elapsed = time.time() - start
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 OTL 备份完成 ({elapsed:.1f}s)")
        logger.info(f"   📋 总数: {result.total}")
        if config.OTL_CONTENT_BACKUP_ENABLED and (self.airpage_available or self.kdocs_available):
            logger.info(f"   📝 内容备份: {result.content_backed_up} 成功 | {result.content_skipped} 跳过 | {result.content_failed} 失败")
            if result.docx_exported:
                logger.info(f"   📄 docx 导出: {result.docx_exported} → {OTL_CONVERTED_DIR}")
        logger.info(f"   💾 缓存复制: {result.copied}/{result.cached}")
        if result.not_cached > 0:
            logger.info(f"   🔗 未缓存: {result.not_cached}")
        logger.info(f"   📁 内容目录: {OTL_CONTENT_DIR}")
        logger.info(f"   📁 缓存目录: {OTL_BACKUP_DIR}")
        logger.info(f"{'='*60}")

        return result

    # ---- v5：产物级增量 + 有界并发 ----

    def _run_v5(self, api_files: list, result: OTLBackupResult, dry_run: bool):
        state = OTLBackupState()
        want_docx = config.AIRPAGE_EXPORT_DOCX_ENABLED
        jobs = []
        for f in api_files:
            need_md, need_docx = state.plan_v5(f.file_id, f.mtime, want_docx)
            if need_md or need_docx:
                jobs.append((f, need_md, need_docx))
            else:
                result.content_skipped += 1
        logger.info(f"📝 airpage v5：{len(jobs)} 个需处理 | {result.content_skipped} 个已是最新"
                    f"（并发 {config.OTL_WORKERS}）")
        if dry_run:
            for f, need_md, need_docx in jobs:
                logger.info(f"   🔍 [dry-run] {f.name}（md={need_md} docx={need_docx}）")
            result.content_backed_up = len(jobs)
            return

        done = [0]
        transient = []

        def work(f, need_md, need_docx):
            if CANCEL.is_set():
                return
            res = airpage_engine.backup_otl_v5(
                file_id=f.file_id, name=f.name, drive_id=f.drive_id, drive_name=f.drive_name,
                want_md=need_md, want_docx=need_docx,
                content_root=OTL_CONTENT_DIR, docx_root=OTL_CONVERTED_DIR)
            # markdown_zip 临时失败 → 回退旧的块树转换，保证至少有文本备份
            if need_md and not res.md_ok and not res.permanent:
                legacy = airpage_engine.backup_otl_via_airpage(
                    file_id=f.file_id, name=f.name, drive_id=f.drive_id, drive_name=f.drive_name,
                    export_docx=False, content_dir=OTL_CONTENT_DIR)
                if legacy and legacy.success:
                    logger.info(f"   ↩️  {f.name}: markdown_zip 失败（{res.md_error}），已回退块树转换")
                    res.content_path, res.md_ok = legacy.content_path, True
                    res.md_error = f"已回退块树转换: {res.md_error}"
            state.record_v5(f.file_id, f.mtime, res, did_md=need_md, did_docx=need_docx)
            with self._result_lock:
                done[0] += 1
                if need_md:
                    if res.md_ok:
                        result.content_backed_up += 1
                    elif not res.permanent:
                        result.content_failed += 1
                if need_docx and res.docx_ok:
                    result.docx_exported += 1
                if not res.permanent and ((need_md and not res.md_ok) or (need_docx and not res.docx_ok)):
                    transient.append(f"{f.name}: {res.md_error or res.docx_error}")
                    logger.warning(f"   ⚠️  {f.name}: md={res.md_error or 'ok'} docx={res.docx_error or 'ok'}")
                if self.progress:
                    self.progress("otl", done[0], len(jobs), f.name)

        with ThreadPoolExecutor(max_workers=max(1, config.OTL_WORKERS)) as pool:
            futures = [pool.submit(work, *j) for j in jobs]
            for fut in as_completed(futures):
                try:
                    fut.result()
                except Exception as e:
                    logger.error(f"   ❌ OTL 处理异常: {e}")
                    with self._result_lock:
                        result.content_failed += 1
        if CANCEL.is_set():
            result.errors.append("运行被取消或超时")
        if transient:
            # 临时失败必须非零退出：App 显示、定时任务每小时重试（每天 ≤3 次）
            result.errors.append(f"OTL 临时失败 {len(transient)} 个（下次运行重试）: "
                                 + "；".join(transient[:3]))
        logger.info(f"   📝 内容备份(airpage v5): {result.content_backed_up} 成功 | "
                    f"{result.content_skipped} 跳过 | {result.content_failed} 失败 | "
                    f"📄 docx {result.docx_exported}")

    def _backup_content(self, api_file: OTLFileInfo, dry_run: bool = False):
        """按后端可用性分发 OTL 内容备份：airpage 优先，kdocs-cli 回退"""
        backend = select_content_backend(self.airpage_available, self.kdocs_available)
        if backend == "airpage":
            return airpage_engine.backup_otl_via_airpage(
                file_id=api_file.file_id, name=api_file.name,
                drive_id=api_file.drive_id, drive_name=api_file.drive_name,
                dry_run=dry_run, export_docx=config.AIRPAGE_EXPORT_DOCX_ENABLED,
            )
        if backend == "kdocs":
            return kdocs_engine.backup_otl_content(
                file_id=api_file.file_id, name=api_file.name,
                drive_id=api_file.drive_id, drive_name=api_file.drive_name,
                dry_run=dry_run,
            )
        return None

    def _generate_export_guide(self, uncached: list[OTLFileInfo],
                                 result: OTLBackupResult):
        """生成未缓存文件的 kdocs.cn 导出指南"""
        if not uncached:
            return

        guide_path = OTL_BACKUP_DIR / "EXPORT_GUIDE.md"
        lines = [
            "# OTL 文件手动导出指南\n",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
            f"共 {len(uncached)} 个文件未在 WPS Office 本地缓存中，需要手动导出。\n\n",
            "## 操作步骤\n\n",
            "1. 点击下方链接，在浏览器中打开文件\n",
            "2. 在 WPS 在线编辑器中：**文件 → 下载为 → Microsoft Word (.docx)**\n",
            "3. 将下载的 .docx 文件放入 `_otl_converted_docx/` 目录\n\n",
            "---\n\n",
            "## 文件清单\n\n",
        ]

        total_size = 0
        for i, f in enumerate(uncached, 1):
            size_mb = f.size / 1024 / 1024
            total_size += f.size
            lines.append(f"### {i}. {f.name}\n\n")
            lines.append(f"- 📏 大小: {f.size:,} bytes ({size_mb:.1f} MB)\n")
            lines.append(f"- 🕐 修改时间: {datetime.fromtimestamp(f.mtime).strftime('%Y-%m-%d %H:%M')}\n")
            lines.append(f"- 🔗 在线编辑: [{f.link_url}]({f.link_url})\n")
            lines.append(f"- 📁 所在盘: {f.drive_name}\n")
            lines.append("\n")

        lines.append(f"\n---\n\n")
        lines.append(f"📊 总计: {len(uncached)} 个文件, {total_size/1024/1024:.1f} MB\n")

        with open(guide_path, "w", encoding="utf-8") as f:
            f.write("".join(lines))

        logger.info(f"   📄 导出指南已生成: {guide_path}")


# ---- 兼容入口（供 wps_backup.py 调用） ----

def run_otl_backup(drive_id: str = None, dry_run: bool = False, progress=None,
                   api_files: list = None, scan_complete: bool = True):
    engine = OTLEngine(target_drive_id=drive_id, progress=progress)
    return engine.run(dry_run=dry_run, api_files=api_files, scan_complete=scan_complete)
