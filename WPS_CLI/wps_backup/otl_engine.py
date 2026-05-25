"""
OTL 专项备份引擎
策略：
1. 通过 WPS CLI API 获取所有 .otl 文件元数据（Drive API 不支持直接下载 .otl）
2. 从 WPS Office 本地云同步缓存中提取最近打开过的 .otl 文件
3. 通过文件名+大小+时间的匹配，将缓存文件重命名为原始文件名归档
4. 对于未缓存的 .otl 文件，生成 kdocs.cn 导出链接清单
"""

import json
import os
import subprocess
import shutil
import time
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field, asdict

from . import config
from .logger import setup_logger

logger = setup_logger()

# WPS Office 本地云同步缓存路径
WPS_CACHE_DIR = Path.home() / "Library/Containers/com.kingsoft.wpsoffice.mac/Data/Library/Application Support/Kingsoft/WPS Cloud Files/userdata/qing/filecache"
RENT_FILE = "rectfile2.xml"

OTL_BACKUP_DIR = config.BACKUP_DIR / "_otl_files"
OTL_CONVERTED_DIR = config.BACKUP_DIR / "_otl_converted_docx"
OTL_STATE_FILE = config.STATE_DIR / "_otl_state.json"


class OTLBackupState:
    """OTL 备份增量状态管理器"""

    def __init__(self, state_file: Path = OTL_STATE_FILE):
        self.state_file = state_file
        self.records: dict[str, dict] = {}  # file_id -> {mtime, path, backed_up_at}
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
        config.STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = self.state_file.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.records, f, ensure_ascii=False, indent=2)
        tmp.replace(self.state_file)

    def needs_update(self, file_id: str, remote_mtime: int) -> bool:
        rec = self.records.get(file_id)
        if not rec:
            return True
        return remote_mtime > rec.get("mtime", 0)

    def mark_backed_up(self, file_id: str, mtime: int, local_path: str):
        self.records[file_id] = {
            "mtime": mtime,
            "path": local_path,
            "backed_up_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._save()

    def prune_stale(self, current_file_ids: set):
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
    cached: int = 0       # 缓存中命中的文件
    copied: int = 0       # 成功从缓存复制的文件
    not_cached: int = 0   # 未在缓存中的文件（需手动导出）
    errors: list = field(default_factory=list)


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
        except subprocess.TimeoutExpired:
            if attempt < retries:
                time.sleep(3)
        except json.JSONDecodeError:
            if attempt < retries:
                time.sleep(2)
    return None


def list_otl_files(drive_id: str = "Q53zypp", drive_name: str = "", parent_id: str = "0") -> list[OTLFileInfo]:
    """
    通过 WPS CLI 递归扫描指定盘下所有 .otl 文件
    """
    result = []
    _recurse_otl(drive_id, drive_name or drive_id, parent_id, result)
    return result


def list_otl_files_all_drives() -> list[OTLFileInfo]:
    """扫描所有盘中的 .otl 文件"""
    result = []
    try:
        data = _cli("drive", "list", "--allotee-type", "user",
                    "--page-size", "50", "-o", "json")
        if not data or data.get("code") != 0:
            logger.warning("无法获取盘列表，将使用默认盘")
            result.extend(list_otl_files())
            return result

        drives = data.get("data", {}).get("items", [])
        for d in drives:
            drive_id = d.get("id", "")
            drive_name = d.get("name", "")
            if not drive_id:
                continue
            files = list_otl_files(drive_id, drive_name)
            result.extend(files)
            logger.info(f"   📁 {drive_name}: {len(files)} 个 .otl")
    except Exception as e:
        logger.error(f"扫描多盘失败: {e}，回退到默认盘")
        result.extend(list_otl_files())
    return result


def _recurse_otl(drive_id: str, drive_name: str, parent_id: str,
                  result: list[OTLFileInfo]):
    """递归扫描目录树中的 .otl 文件"""
    token = ""
    while True:
        args = ["drive", "files", "list", drive_id, parent_id,
                "--filter-exts", "otl", "--page-size", "200",
                "--with-permission", "-o", "json"]
        if token:
            args += ["--page-token", token]
        data = _cli(*args)
        if not data or data.get("code") != 0:
            break

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

    # 同时扫描子文件夹（也过滤 .otl）
    sub_args = ["drive", "files", "list", drive_id, parent_id,
                "--page-size", "200", "-o", "json"]
    sub_data = _cli(*sub_args)
    if sub_data and sub_data.get("code") == 0:
        for item in sub_data.get("data", {}).get("items", []):
            if item.get("type") == "folder":
                _recurse_otl(drive_id, drive_name, item["id"], result)


# ---- WPS Office 本地缓存解析 ----

def find_cache_root() -> Optional[Path]:
    """查找 WPS Office 云同步缓存根目录"""
    if not WPS_CACHE_DIR.exists():
        return None
    # 找到用户 ID 子目录
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
    """
    列出缓存中所有 kdocsfile 目录及其 content.otl 路径
    返回: {directory_name: content.otl_path}
    """
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


def _get_dest_path(api_file: OTLFileInfo, state: "OTLBackupState" = None) -> Path:
    """生成备份目标路径，处理重名"""
    # 如果状态中有记录且路径仍有效，复用原路径
    if state:
        rec = state.records.get(api_file.file_id)
        if rec:
            old_path = Path(rec["path"])
            if old_path.exists():
                return old_path

    base = OTL_BACKUP_DIR / api_file.safe_name
    if not base.exists():
        return base
    # 如果已存在同名文件（但不是当前文件的历史备份），追加 file_id 前 8 位区分
    stem = base.stem
    suffix = base.suffix
    unique_name = f"{stem}_{api_file.file_id[:8]}{suffix}"
    return OTL_BACKUP_DIR / unique_name


def match_cache_to_api(
    api_files: list[OTLFileInfo],
    cache_entries: list[CacheFileEntry],
    cache_otl_map: dict[str, Path],
) -> list[tuple[OTLFileInfo, Path]]:
    """
    将 API 文件列表与缓存文件进行匹配
    匹配策略（按优先级）：
    1. 精确文件名匹配（name → rectfile2.xml）+ 大小验证
    2. 模糊大小匹配（size ± 15%）
    返回: [(api_file_info, cache_content_otl_path), ...]
    """
    matched = []

    # 构建缓存条目索引：按文件名
    cache_by_name: dict[str, CacheFileEntry] = {}
    for ce in cache_entries:
        cache_by_name[ce.name.lower()] = ce

    # 对缓存中的每个 content.otl，获取文件大小和时间用于模糊匹配
    cache_file_stats: list[tuple[Path, int, int]] = []
    for dirname, otl_path in cache_otl_map.items():
        try:
            stat = otl_path.stat()
            cache_file_stats.append((otl_path, stat.st_size, int(stat.st_mtime)))
        except OSError:
            pass

    # 按大小排序，便于优先匹配大小相近的
    cache_file_stats.sort(key=lambda x: x[1])

    # 匹配
    used_cache_paths = set()

    def _find_best_size_match(api_file: OTLFileInfo, min_ratio: float, max_ratio: float) -> Optional[Path]:
        """在剩余缓存文件中找大小最接近的"""
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

        # Step 1: 精确文件名匹配（rectfile2.xml 中出现过该文件名）
        ce = cache_by_name.get(api_file.name.lower())
        if ce:
            # 在剩余缓存中找大小最接近的（放宽到 0.5x ~ 2.0x，因为 .otl API size 不稳定）
            matched_path = _find_best_size_match(api_file, 0.5, 2.0)

        # Step 2: 如果名字匹配未找到合适大小，尝试纯大小匹配
        if not matched_path:
            matched_path = _find_best_size_match(api_file, 0.85, 1.15)

        if matched_path:
            matched.append((api_file, matched_path))
            used_cache_paths.add(matched_path)

    return matched


# ---- 备份主逻辑 ----

class OTLEngine:
    """OTL 文件备份引擎"""

    def __init__(self, target_drive_id: str = None):
        self.target_drive_id = target_drive_id
        OTL_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        OTL_CONVERTED_DIR.mkdir(parents=True, exist_ok=True)

    def run(self, dry_run: bool = False) -> OTLBackupResult:
        result = OTLBackupResult()
        start = time.time()

        logger.info("=" * 60)
        logger.info("📋 OTL 专项备份 (WPS Office 缓存中转)")

        # ---- Phase 1: API 扫描 ----
        logger.info("📡 扫描 WPS Drive .otl 文件...")
        try:
            if self.target_drive_id:
                api_files = list_otl_files(self.target_drive_id)
            else:
                api_files = list_otl_files_all_drives()
        except Exception as e:
            logger.error(f"❌ API 扫描失败: {e}")
            result.errors.append(f"API 扫描失败: {e}")
            return result

        result.total = len(api_files)
        logger.info(f"📊 远程共 {result.total} 个 .otl 文件")

        # ---- Phase 2: 缓存扫描 ----
        logger.info("🔍 扫描 WPS Office 本地缓存...")
        cache_root = find_cache_root()
        if not cache_root:
            logger.warning("⚠️  未找到 WPS Office 云同步缓存")
            logger.warning("   请确保 WPS Office 已登录并打开过 .otl 文件")
            result.not_cached = result.total
            self._generate_export_guide(api_files, result)
            return result

        cache_entries = parse_rectfile2(cache_root)
        cache_otl_map = list_cache_otl_files(cache_root)
        logger.info(f"   缓存条目: {len(cache_entries)} | 实际文件: {len(cache_otl_map)}")

        # ---- Phase 3: 匹配 ----
        matched = match_cache_to_api(api_files, cache_entries, cache_otl_map)
        matched_ids = {m[0].file_id for m in matched}
        result.cached = len(matched_ids)
        result.not_cached = result.total - result.cached

        logger.info(f"📊 匹配结果: {result.cached} 已缓存 | {result.not_cached} 需手动导出")

        # ---- Phase 4: 复制缓存文件（增量） ----
        if dry_run:
            logger.info("🔍 Dry-run 模式：预览匹配结果")
            for api_file, cache_path in matched:
                logger.info(f"   📋 {api_file.name}")
                logger.info(f"      缓存: {cache_path}")
                logger.info(f"      大小: {api_file.size:,} bytes")
                logger.info(f"      链接: {api_file.link_url}")
            self._generate_export_guide(
                [f for f in api_files if f.file_id not in matched_ids],
                result,
            )
            return result

        logger.info(f"📋 开始复制缓存文件到备份目录...")
        state = OTLBackupState()
        for api_file, cache_path in matched:
            try:
                dest = _get_dest_path(api_file, state)
                # 增量检查：已备份且 mtime 未变更则跳过
                if not state.needs_update(api_file.file_id, api_file.mtime):
                    logger.info(f"   ⏭️  {api_file.name} (已是最新)")
                    continue

                shutil.copy2(str(cache_path), str(dest))
                # 更新文件修改时间以匹配远程
                if api_file.mtime > 0:
                    os_time = api_file.mtime
                    try:
                        os.utime(str(dest), (os_time, os_time))
                    except OSError as e:
                        logger.warning(f"   ⚠️  无法设置时间戳 {api_file.name}: {e}")
                state.mark_backed_up(api_file.file_id, api_file.mtime, str(dest))
                result.copied += 1
                logger.info(f"   ✅ {api_file.name} ({api_file.size:,} bytes)")
            except Exception as e:
                result.errors.append(f"{api_file.name}: {e}")
                logger.error(f"   ❌ {api_file.name}: {e}")

        # ---- Phase 5: 清理已不存在的文件记录 ----
        current_ids = {f.file_id for f in api_files}
        state.prune_stale(current_ids)

        # ---- Phase 6: 未缓存文件清单 ----
        uncached = [f for f in api_files if f.file_id not in matched_ids]
        self._generate_export_guide(uncached, result)

        # ---- 汇总 ----
        elapsed = time.time() - start
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 OTL 备份完成 ({elapsed:.1f}s)")
        logger.info(f"   📋 总数: {result.total}")
        logger.info(f"   💾 从缓存复制: {result.copied}/{result.cached}")
        logger.info(f"   ⏭️ 跳过: {result.cached - result.copied}")
        logger.info(f"   🔗 需手动导出: {result.not_cached}")
        logger.info(f"   📁 备份目录: {OTL_BACKUP_DIR}")
        logger.info(f"{'='*60}")

        return result

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

def run_otl_backup(drive_id: str = None, dry_run: bool = False):
    engine = OTLEngine(target_drive_id=drive_id)
    return engine.run(dry_run=dry_run)