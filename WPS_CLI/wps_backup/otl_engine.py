"""
OTL 专项备份引擎 v4.0
混合策略：
1. 通过 wps365-cli API 获取所有 .otl 文件元数据
2. 【新增】通过 kdocs-cli read-file 将 OTL 内容转为 Markdown 备份（无需本地缓存）
3. 【保留】从 WPS Office 本地云同步缓存中提取 .otl 原始文件（作为补充）
4. 对于仍无法备份的 .otl 文件，生成 kdocs.cn 导出链接清单
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
from . import kdocs_engine

logger = setup_logger()

# WPS Office 本地云同步缓存路径
WPS_CACHE_DIR = Path.home() / "Library/Containers/com.kingsoft.wpsoffice.mac/Data/Library/Application Support/Kingsoft/WPS Cloud Files/userdata/qing/filecache"
RENT_FILE = "rectfile2.xml"

OTL_BACKUP_DIR = config.BACKUP_DIR / "_otl_files"
OTL_CONTENT_DIR = config.BACKUP_DIR / "_otl_content"
OTL_CONVERTED_DIR = config.BACKUP_DIR / "_otl_converted_docx"
OTL_STATE_FILE = config.STATE_DIR / "_otl_state.json"


class OTLBackupState:
    """OTL 备份增量状态管理器"""

    def __init__(self, state_file: Path = OTL_STATE_FILE):
        self.state_file = state_file
        self.records: dict[str, dict] = {}  # file_id -> {mtime, path, backed_up_at, content_path}
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

    def mark_backed_up(self, file_id: str, mtime: int, local_path: str = "", content_path: str = ""):
        self.records[file_id] = {
            "mtime": mtime,
            "path": local_path,
            "content_path": content_path,
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
    content_backed_up: int = 0   # kdocs-cli read-file 成功备份
    content_skipped: int = 0      # 内容已是最新
    content_failed: int = 0       # 内容备份失败
    cached: int = 0               # 缓存中命中的文件
    copied: int = 0               # 成功从缓存复制的文件
    not_cached: int = 0           # 未在缓存中的文件
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


# ---- WPS Office 本地缓存解析（保留作为补充） ----

def find_cache_root() -> Optional[Path]:
    """查找 WPS Office 云同步缓存根目录"""
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


# ---- 备份主逻辑 v4.0 ----

class OTLEngine:
    """OTL 文件备份引擎 v4.0 — 混合策略（kdocs-cli 内容 + 缓存实体）"""

    def __init__(self, target_drive_id: str = None):
        self.target_drive_id = target_drive_id
        OTL_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        OTL_CONTENT_DIR.mkdir(parents=True, exist_ok=True)
        OTL_CONVERTED_DIR.mkdir(parents=True, exist_ok=True)
        self.kdocs_available = kdocs_engine.check_kdocs_cli_available()
        if self.kdocs_available:
            logger.info(f"   🔧 kdocs-cli 已就绪 ({kdocs_engine.get_kdocs_version()})")
        else:
            logger.warning("   ⚠️  kdocs-cli 未认证，将回退到纯缓存模式")

    def run(self, dry_run: bool = False) -> OTLBackupResult:
        result = OTLBackupResult()
        start = time.time()

        logger.info("=" * 60)
        logger.info("📋 OTL 专项备份 v4.0 (kdocs-cli 内容 + 缓存实体)")

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

        # ---- Phase 2: kdocs-cli 内容备份（新增） ----
        if config.OTL_CONTENT_BACKUP_ENABLED and self.kdocs_available:
            logger.info("📝 通过 kdocs-cli 备份 OTL 内容...")
            state = OTLBackupState()
            for api_file in api_files:
                # 增量检查
                if not state.needs_update(api_file.file_id, api_file.mtime):
                    result.content_skipped += 1
                    continue

                if dry_run:
                    logger.info(f"   🔍 [dry-run] {api_file.name}")
                    result.content_backed_up += 1
                    continue

                # 使用 kdocs-cli 备份 OTL 内容
                content_result = kdocs_engine.backup_otl_content(
                    file_id=api_file.file_id,
                    name=api_file.name,
                    drive_id=api_file.drive_id,
                    drive_name=api_file.drive_name,
                    dry_run=dry_run,
                )

                if content_result.success:
                    result.content_backed_up += 1
                    # 更新状态
                    state.mark_backed_up(
                        api_file.file_id, api_file.mtime,
                        content_path=content_result.content_path
                    )
                else:
                    result.content_failed += 1
                    logger.warning(f"   ⚠️  OTL 内容备份失败: {api_file.name} — {content_result.error}")

            logger.info(f"   📝 内容备份: {result.content_backed_up} 成功 | {result.content_skipped} 跳过 | {result.content_failed} 失败")
        else:
            logger.info("   ⏭️  OTL 内容备份已禁用或 kdocs-cli 不可用")

        # ---- Phase 3: 缓存扫描（保留作为补充） ----
        logger.info("🔍 扫描 WPS Office 本地缓存...")
        cache_root = find_cache_root()
        if not cache_root:
            logger.warning("⚠️  未找到 WPS Office 云同步缓存")
            # 如果没有缓存且 kdocs-cli 也不可用，则生成导出指南
            if not self.kdocs_available:
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

                        # 获取已有的 content_path（如果有）
                        rec = state.records.get(api_file.file_id, {})
                        content_path = rec.get("content_path", "")
                        state.mark_backed_up(api_file.file_id, api_file.mtime, str(dest), content_path)
                        result.copied += 1
                        logger.info(f"   ✅ {api_file.name} (缓存复制)")
                    except Exception as e:
                        result.errors.append(f"{api_file.name}: {e}")
                        logger.error(f"   ❌ {api_file.name}: {e}")

        # ---- Phase 5: 清理已不存在的文件记录 ----
        current_ids = {f.file_id for f in api_files}
        state = OTLBackupState()
        state.prune_stale(current_ids)

        # ---- Phase 6: 未缓存文件清单（仅当 kdocs-cli 也失败时） ----
        if not self.kdocs_available:
            uncached = [f for f in api_files]
            self._generate_export_guide(uncached, result)

        # ---- 汇总 ----
        elapsed = time.time() - start
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 OTL 备份完成 ({elapsed:.1f}s)")
        logger.info(f"   📋 总数: {result.total}")
        if config.OTL_CONTENT_BACKUP_ENABLED and self.kdocs_available:
            logger.info(f"   📝 内容备份: {result.content_backed_up} 成功 | {result.content_skipped} 跳过 | {result.content_failed} 失败")
        logger.info(f"   💾 缓存复制: {result.copied}/{result.cached}")
        if result.not_cached > 0:
            logger.info(f"   🔗 未缓存: {result.not_cached}")
        logger.info(f"   📁 内容目录: {OTL_CONTENT_DIR}")
        logger.info(f"   📁 缓存目录: {OTL_BACKUP_DIR}")
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
