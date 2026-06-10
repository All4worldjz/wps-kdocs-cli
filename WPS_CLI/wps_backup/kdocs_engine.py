"""
kdocs-cli 引擎封装 — 文档内容提取、搜索、OTL 内容备份
作为 wps365-cli 的补充，提供文档内容读取能力
"""

import json
import subprocess
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

from . import config
from .logger import setup_logger

logger = setup_logger()


@dataclass
class ContentBackupResult:
    """内容备份结果"""
    file_id: str
    name: str
    success: bool = False
    content_path: str = ""
    content_format: str = ""
    error: str = ""
    size: int = 0


@dataclass
class SearchResult:
    """搜索结果"""
    file_id: str
    name: str
    drive_id: str
    parent_id: str
    type: str
    size: int
    mtime: int
    link_url: str


# ============================================================
# CLI 封装
# ============================================================

def _kdocs_cli(*args, timeout: int = 60, retries: int = 2) -> Optional[dict]:
    """调用 kdocs-cli，自动处理认证和重试"""
    cmd = [config.KDOCS_CLI_BIN] + list(args)
    for attempt in range(retries + 1):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if r.returncode == 0:
                return json.loads(r.stdout)
            err = r.stderr.strip()
            # 认证过期处理
            if "400006" in err or "expired" in err.lower() or "过期" in err:
                logger.warning("kdocs-cli Token 过期，需要重新登录: kdocs-cli auth login")
                return None
            if attempt < retries:
                time.sleep(2 ** attempt)
        except subprocess.TimeoutExpired:
            if attempt < retries:
                time.sleep(3)
        except json.JSONDecodeError:
            if attempt < retries:
                time.sleep(2)
    return None


# ============================================================
# 文档内容读取
# ============================================================

def read_file_content(file_id: str, drive_id: str = "") -> Optional[dict]:
    """
    读取文档内容为 Markdown/结构化数据
    支持: docx, pdf, xlsx, ksheet, dbt, otl
    不支持: pptx
    """
    params = {"file_id": file_id}
    if drive_id:
        params["drive_id"] = drive_id

    data = _kdocs_cli("drive", "read-file", json.dumps(params), timeout=120)
    if not data:
        return None

    if data.get("code") != 0:
        logger.debug(f"read-file failed for {file_id}: {data.get('message')}")
        return None

    return data.get("data")


def is_content_readable(ext: str) -> bool:
    """判断文件扩展名是否支持内容读取"""
    return ext.lower() in {".docx", ".pdf", ".xlsx", ".ksheet", ".dbt", ".otl"}


def backup_file_content(file_id: str, name: str, drive_id: str = "",
                        drive_name: str = "", dry_run: bool = False) -> ContentBackupResult:
    """
    备份单个文件的内容为 Markdown
    """
    result = ContentBackupResult(file_id=file_id, name=name)
    ext = Path(name).suffix.lower()

    if not is_content_readable(ext):
        result.error = f"不支持内容读取的格式: {ext}"
        return result

    # 构建目标路径
    safe_name = _sanitize(name)
    stem = Path(safe_name).stem
    content_name = f"{stem}_{file_id[:8]}.md"
    dest_dir = config.CONTENT_BACKUP_DIR / (drive_name or "default")
    dest_path = dest_dir / content_name

    result.content_path = str(dest_path)
    result.content_format = "markdown"

    if dry_run:
        result.success = True
        return result

    # 读取内容
    content_data = read_file_content(file_id, drive_id)
    if not content_data:
        result.error = "无法读取文档内容"
        return result

    content = content_data.get("content", "")
    if not content:
        result.error = "文档内容为空"
        return result

    # 写入文件
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        # 添加 frontmatter
        frontmatter = f"""---
file_id: {file_id}
drive_id: {drive_id}
name: {name}
source_format: {ext}
backup_at: {time.strftime('%Y-%m-%d %H:%M:%S')}
---

"""
        dest_path.write_text(frontmatter + content, encoding="utf-8")
        result.success = True
        result.size = dest_path.stat().st_size
        logger.info(f"   📝 内容备份: {name} → {content_name}")
    except Exception as e:
        result.error = str(e)[:200]
        logger.error(f"   ❌ 内容备份失败: {name} — {e}")

    return result


# ============================================================
# OTL 内容备份（替代缓存中转方案）
# ============================================================

def backup_otl_content(file_id: str, name: str, drive_id: str = "",
                       drive_name: str = "", dry_run: bool = False) -> ContentBackupResult:
    """
    备份 OTL 文件内容为 Markdown
    这是 otl_engine.py 缓存中转方案的替代/补充
    """
    result = ContentBackupResult(file_id=file_id, name=name)

    # 构建目标路径
    safe_name = _sanitize(name)
    stem = Path(safe_name).stem
    content_name = f"{stem}_{file_id[:8]}.md"
    dest_dir = config.BACKUP_DIR / "_otl_content" / (drive_name or "default")
    dest_path = dest_dir / content_name

    result.content_path = str(dest_path)
    result.content_format = "markdown"

    if dry_run:
        result.success = True
        return result

    # 读取 OTL 内容
    content_data = read_file_content(file_id, drive_id)
    if not content_data:
        result.error = "无法读取 OTL 内容"
        return result

    content = content_data.get("content", "")
    if not content:
        result.error = "OTL 内容为空"
        return result

    # 写入文件
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        frontmatter = f"""---
file_id: {file_id}
drive_id: {drive_id}
name: {name}
source_format: .otl
backup_at: {time.strftime('%Y-%m-%d %H:%M:%S')}
---

"""
        dest_path.write_text(frontmatter + content, encoding="utf-8")
        result.success = True
        result.size = dest_path.stat().st_size
        logger.info(f"   📝 OTL 内容备份: {name} → {content_name}")
    except Exception as e:
        result.error = str(e)[:200]
        logger.error(f"   ❌ OTL 内容备份失败: {name} — {e}")

    return result


# ============================================================
# 搜索
# ============================================================

def search_files(keyword: str, file_type: str = "file", count: int = 100,
                 drive_ids: list = None) -> list[SearchResult]:
    """
    搜索文件（按文件名或全文）
    """
    params = {
        "type": "file_name",
        "keyword": keyword,
        "page_size": count,
        "file_type": file_type,
    }
    if drive_ids:
        params["drive_ids"] = drive_ids

    data = _kdocs_cli("drive", "search-files", json.dumps(params), timeout=60)
    if not data or data.get("code") != 0:
        return []

    items = data.get("data", {}).get("data", {}).get("items", [])
    results = []
    for item in items:
        file_info = item.get("file", item)
        results.append(SearchResult(
            file_id=file_info.get("id", ""),
            name=file_info.get("name", ""),
            drive_id=file_info.get("drive_id", ""),
            parent_id=file_info.get("parent_id", ""),
            type=file_info.get("type", "file"),
            size=file_info.get("size", 0),
            mtime=file_info.get("mtime", 0),
            link_url=file_info.get("link_url", ""),
        ))
    return results


# ============================================================
# 工具函数
# ============================================================

def _sanitize(name: str) -> str:
    """清理文件名中的非法字符"""
    import re
    return re.sub(r'[\\/:*?"<>|\t\n\r]', '_', name.strip())[:200]


def check_kdocs_cli_available() -> bool:
    """检查 kdocs-cli 是否可用且已认证"""
    try:
        r = subprocess.run([config.KDOCS_CLI_BIN, "auth", "status"],
                          capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return False
        data = json.loads(r.stdout)
        return data.get("authenticated", False)
    except Exception:
        return False


def get_kdocs_version() -> str:
    """获取 kdocs-cli 版本"""
    try:
        r = subprocess.run([config.KDOCS_CLI_BIN, "version"],
                          capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:
        return "not installed"
