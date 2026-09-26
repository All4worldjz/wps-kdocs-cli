"""
airpage（智能文档）引擎封装 — 通过 wps365-cli airpage 命令读取/导出 OTL 内容

背景：kdocs-cli 的 kdocs API 已拒绝企业账号（错误码 403001），
wps365-cli v0.3.3+ 的 airpage 命令可在企业账号下读取智能文档内容树
并导出 docx/json/pdf，作为 OTL 内容备份的主路径。
需要授权 scope: kso.airpage.readwrite
"""

import json
import re
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Optional

from . import config
from .logger import setup_logger
from . import wps_http

logger = setup_logger()

# airpage 所需的授权 scope
AIRPAGE_SCOPES = {"kso.airpage.readwrite", "kso.airpage.read"}


def _airpage_cli(*args, timeout: int = 60, retries: int = 2, runner=subprocess.run) -> Optional[dict]:
    """调用 wps365-cli airpage 子命令，返回解析后的 JSON；失败返回 None"""
    cmd = [config.CLI_BIN] + list(args)
    for attempt in range(retries + 1):
        try:
            r = runner(cmd, capture_output=True, text=True, timeout=timeout)
            if r.returncode == 0:
                return json.loads(r.stdout)
            err = (r.stderr or "").strip()
            if "401" in err or "expired" in err.lower():
                logger.info("wps365-cli token 过期，自动刷新...")
                runner([config.CLI_BIN, "auth", "refresh", "--delegated"],
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


def read_airpage_blocks(file_id: str, runner=subprocess.run) -> Optional[dict]:
    """读取智能文档完整内容树（airpage block get，block_id=doc）"""
    data = _airpage_cli("airpage", "block", "get", file_id, "-o", "json",
                        timeout=120, runner=runner)
    if not data or data.get("code") != 0:
        return None
    return data.get("data", {}).get("block")


def get_airpage_version(file_id: str, runner=subprocess.run) -> Optional[int]:
    """获取智能文档当前版本号（airpage get，导出时需要）"""
    data = _airpage_cli("airpage", "get", file_id, "-o", "json", runner=runner)
    if not data or data.get("code") != 0:
        return None
    return data.get("data", {}).get("version")


def check_airpage_available(runner=subprocess.run) -> bool:
    """检查 wps365-cli 已认证且 token 授予了 airpage scope"""
    try:
        r = runner([config.CLI_BIN, "auth", "status"],
                   capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return False
        data = json.loads(r.stdout)
        scopes = set(data.get("delegated", {}).get("granted_scopes") or [])
        return bool(scopes & AIRPAGE_SCOPES)
    except Exception:
        return False


def export_airpage_to_file(file_id: str, dest_path: Path, fmt: str = "docx",
                           runner=subprocess.run, fetcher=wps_http.open_url,
                           sleep=time.sleep, poll_interval: float = 2.0,
                           timeout: float = 120, download_timeout: float = 60) -> bool:
    """
    将智能文档导出为 docx/json/pdf 并下载到 dest_path。
    流程：airpage get（拿版本号）→ export create（建任务）→ export get（轮询）→ 下载。
    成功返回 True，任何一步失败返回 False（不抛异常，不影响主备份流程）。
    """
    version = get_airpage_version(file_id, runner=runner)
    if version is None:
        logger.warning(f"   ⚠️  无法获取文档版本，导出跳过: {file_id}")
        return False

    created = _airpage_cli("airpage", "export", "create", file_id,
                           "--format", fmt, "--version", str(version),
                           "-o", "json", timeout=60, runner=runner)
    if not created or created.get("code") != 0:
        logger.warning(f"   ⚠️  创建导出任务失败: {file_id}")
        return False
    key = created.get("data", {}).get("key", "")
    if not key:
        return False

    deadline = time.time() + timeout
    url = ""
    while time.time() <= deadline:
        task = _airpage_cli("airpage", "export", "get", file_id,
                            "--format", fmt, "--version", str(version),
                            "--task-id", key, "-o", "json",
                            timeout=60, runner=runner)
        status = (task or {}).get("data", {}).get("status", "")
        if status == "Completed":
            url = task["data"].get("url", "")
            break
        if status not in ("Building", ""):
            logger.warning(f"   ⚠️  导出任务失败({status}): {file_id}")
            return False
        sleep(poll_interval)
    if not url:
        logger.warning(f"   ⚠️  导出超时({timeout}s): {file_id}")
        return False

    dest_path = Path(dest_path)
    tmp_path = dest_path.with_suffix(dest_path.suffix + ".tmp")
    try:
        data = fetcher(url, timeout=download_timeout).read()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_bytes(data)
        tmp_path.replace(dest_path)
        logger.info(f"   📄 导出 {fmt}: {dest_path.name} ({len(data)} bytes)")
        return True
    except Exception as e:
        logger.warning(f"   ⚠️  导出下载失败: {file_id} — {e}")
        tmp_path.unlink(missing_ok=True)
        return False


# ============================================================
# OTL 内容备份主入口
# ============================================================

def backup_otl_via_airpage(file_id: str, name: str, drive_id: str = "",
                           drive_name: str = "", dry_run: bool = False,
                           export_docx: bool = True,
                           content_dir: Optional[Path] = None,
                           docx_dir: Optional[Path] = None,
                           runner=subprocess.run,
                           fetcher=wps_http.open_url,
                           sleep=time.sleep) -> "ContentBackupResult":
    """
    通过 airpage 备份 OTL 内容：块树 → Markdown（.md，带 frontmatter），
    可选导出 docx 实体（替代手动"下载为 docx"步骤）。
    docx 导出失败不影响 Markdown 备份结果。
    """
    from .kdocs_engine import ContentBackupResult

    result = ContentBackupResult(file_id=file_id, name=name, content_format="markdown")

    safe_name = re.sub(r'[\\/:*?"<>|\t\n\r]', '_', name.strip())[:200]
    stem = Path(safe_name).stem
    content_root = Path(content_dir) if content_dir else (config.BACKUP_DIR / "_otl_content")
    content_dir = content_root / (drive_name or "default")
    docx_dir = Path(docx_dir) if docx_dir else (config.BACKUP_DIR / "_otl_converted_docx")
    md_path = content_dir / f"{stem}_{file_id[:8]}.md"
    docx_path = docx_dir / f"{stem}_{file_id[:8]}.docx"
    result.content_path = str(md_path)

    if dry_run:
        result.success = True
        return result

    block = read_airpage_blocks(file_id, runner=runner)
    if not block:
        result.error = "airpage 无法读取 OTL 内容"
        return result

    content = blocks_to_markdown(block)
    if not content.strip():
        result.error = "OTL 内容为空"
        return result

    try:
        content_dir.mkdir(parents=True, exist_ok=True)
        frontmatter = f"""---
file_id: {file_id}
drive_id: {drive_id}
name: {name}
source_format: .otl
backend: airpage
backup_at: {time.strftime('%Y-%m-%d %H:%M:%S')}
---

"""
        md_path.write_text(frontmatter + content + "\n", encoding="utf-8")
        result.success = True
        result.size = md_path.stat().st_size
        logger.info(f"   📝 OTL 内容备份(airpage): {name} → {md_path.name}")
    except Exception as e:
        result.error = str(e)[:200]
        logger.error(f"   ❌ OTL 内容备份失败: {name} — {e}")
        return result

    if export_docx:
        if export_airpage_to_file(file_id, docx_path, fmt="docx",
                                  runner=runner, fetcher=fetcher, sleep=sleep):
            result.docx_path = str(docx_path)

    return result


def blocks_to_markdown(tree: dict) -> str:
    """将 airpage v2 块树（block get 返回的 block 对象）扁平化为 Markdown 文本"""
    lines: list[str] = []
    _walk_block(tree, lines)
    return "\n".join(line for line in lines if line != "")


def _walk_block(node: dict, lines: list[str]):
    """递归遍历块树。每个块是 {块类型: {attributes, block_id, elements?, children?}}"""
    if not isinstance(node, dict):
        return
    for block_type, body in node.items():
        if not isinstance(body, dict):
            continue
        lines.append(_render_block(block_type, body))
        for child in body.get("children", []):
            _walk_block(child, lines)


def _render_block(block_type: str, body: dict) -> str:
    """渲染单个块为一行文本"""
    if block_type == "picture":
        pic_id = body.get("attributes", {}).get("id", "")
        return f"![图片](attachment:{pic_id})"

    text = _elements_to_text(body.get("elements", []))
    if not text:
        return ""

    heading = body.get("attributes", {}).get("heading", 0)
    if isinstance(heading, int) and heading > 0:
        return "#" * min(heading, 6) + " " + text
    return text


def _elements_to_text(elements: list) -> str:
    """拼接块内行级元素：text → 文本内容；wps_user → @姓名"""
    parts: list[str] = []
    for elem in elements:
        if not isinstance(elem, dict):
            continue
        if "text" in elem:
            parts.append(elem["text"].get("attributes", {}).get("content", ""))
        elif "wps_user" in elem:
            name = elem["wps_user"].get("attributes", {}).get("name", "")
            parts.append(f"@{name}")
    return "".join(parts)


# ============================================================
# v5：官方 markdown_zip + docx 并行导出（直连 HTTP），产物级增量
# ============================================================
# 官方接口（CLI 本地 spec 未收录 markdown_zip，经 wps_http 直连调用）：
#   GET  /v7/airpage/{id}                         → data.version
#   POST /v7/airpage/{id}/export_to_markdown_zip  {"version": v}
#   POST /v7/airpage/{id}/export_to_docx          {"version": v}
#   POST /v7/airpage/{id}/export_task/query       {"format": f, "version": v}
# 导出结果按版本键在服务端缓存；markdown_zip = export.md + 图片（md 以 image_id=XXXX 引用 XXXX.ext）

import shutil
import zipfile
from dataclasses import dataclass

FORMAT_VERSION = 5
# 永久失败只认响应码（2026-09-26 实测：快捷方式/不存在/无权限均返回 403000001）。
# 同为 HTTP 403 的 token/scope 失效（400000003）、路由变化 404000001、5xx 都是临时失败，
# 若按 HTTP 状态判定会把全部文档错误标记为永久失败且不再重试。
PERMANENT_CODES = {403000001}
_IMG_RE = re.compile(r"(!\[[^\]]*\]\()([^)\s]*[?&]image_id=([A-Za-z0-9]+)[^)\s]*)((?:\s+\"[^\"]*\")?\))")


@dataclass
class V5Result:
    file_id: str
    version: Optional[str] = None
    content_path: Optional[str] = None
    docx_path: Optional[str] = None
    md_ok: bool = False
    docx_ok: bool = False
    md_error: str = ""
    docx_error: str = ""
    permanent: bool = False


def rewrite_image_links(md: str, asset_rel: str, images: dict) -> str:
    """把 `![alt](...image_id=XXXX...)` 改写为 `![alt](asset_rel/XXXX.ext)`；zip 中不存在的图片保留原链接"""
    def sub(m):
        name = images.get(m.group(3))
        return f"{m.group(1)}{asset_rel}/{name}{m.group(4)}" if name else m.group(0)
    return _IMG_RE.sub(sub, md)


def _paths(file_id, name, drive_name, content_root, docx_root):
    stem = Path(re.sub(r'[\\/:*?"<>|\t\n\r]', '_', name.strip())[:200]).stem
    base = f"{stem}_{file_id[:8]}"
    content_dir = Path(content_root or (config.BACKUP_DIR / "_otl_content")) / (drive_name or "default")
    docx_dir = Path(docx_root or (config.BACKUP_DIR / "_otl_converted_docx"))
    return base, content_dir / f"{base}.md", content_dir / f"{base}.assets", docx_dir / f"{base}.docx"


def _create_export(http, file_id, kind, version):
    path = {"markdown_zip": "export_to_markdown_zip", "docx": "export_to_docx"}[kind]
    status, body = http.api("POST", f"/v7/airpage/{file_id}/{path}", {"version": version})
    return (body.get("data") or {}) if status == 200 and isinstance(body, dict) and body.get("code") == 0 else None


def _await_exports(http, file_id, version, pending: dict, sleep, poll_timeout, poll_interval):
    """pending: kind -> 创建返回的 data。并行轮询，返回 kind -> (url | None, error)"""
    results = {}
    for kind, data in list(pending.items()):
        if data is None:
            results[kind] = (None, "创建导出任务失败")
            del pending[kind]
        elif data.get("status") == "Completed" and data.get("url"):
            results[kind] = (data["url"], "")
            del pending[kind]
    deadline = time.time() + poll_timeout
    while pending and time.time() < deadline:
        sleep(poll_interval)
        for kind in list(pending):
            status, body = http.api("POST", f"/v7/airpage/{file_id}/export_task/query",
                                    {"format": kind, "version": version})
            data = (body.get("data") or {}) if status == 200 and isinstance(body, dict) else {}
            st = data.get("status", "")
            if st == "Completed" and data.get("url"):
                results[kind] = (data["url"], "")
                del pending[kind]
            elif st == "Failed":
                results[kind] = (None, "导出任务失败")
                del pending[kind]
    for kind in pending:
        results[kind] = (None, f"导出超时（{poll_timeout}s）")
    return results


def _install_markdown(zip_path: Path, md_path: Path, assets_dir: Path, frontmatter: str) -> str:
    """解压 markdown_zip，改写图片链接，原子写入 md 与 assets；返回错误信息（空串 = 成功）"""
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        md_name = "export.md" if "export.md" in names else next((n for n in names if n.endswith(".md")), None)
        if not md_name:
            return "markdown_zip 中没有 md 文件"
        body = z.read(md_name).decode("utf-8", "ignore")
        if not body.strip():
            return "OTL 内容为空"
        images = {Path(n).stem: Path(n).name for n in names
                  if n != md_name and not n.endswith("/") and "/" not in n.strip("/")}
        tmp_assets = assets_dir.with_name(assets_dir.name + ".tmp")
        shutil.rmtree(tmp_assets, ignore_errors=True)
        if images:
            tmp_assets.mkdir(parents=True)
            for stem, fname in images.items():
                (tmp_assets / fname).write_bytes(z.read(fname))
    body = rewrite_image_links(body, assets_dir.name, images)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_md = md_path.with_suffix(".md.tmp")
    tmp_md.write_text(frontmatter + body.rstrip("\n") + "\n", encoding="utf-8")
    shutil.rmtree(assets_dir, ignore_errors=True)
    if images:
        tmp_assets.replace(assets_dir)
    tmp_md.replace(md_path)
    return ""


def backup_otl_v5(file_id: str, name: str, drive_id: str = "", drive_name: str = "",
                  want_md: bool = True, want_docx: bool = True, http=None, downloader=None,
                  content_root=None, docx_root=None, sleep=time.sleep,
                  poll_timeout: float = 300, poll_interval: float = 2.0) -> V5Result:
    """OTL v5 备份：只做需要的产物；md 与 docx 相互独立，任何失败都不破坏已有文件"""
    http = http or wps_http.client()
    downloader = downloader or (lambda url, dest: wps_http.download(url, dest))
    res = V5Result(file_id=file_id)
    base, md_path, assets_dir, docx_path = _paths(file_id, name, drive_name, content_root, docx_root)

    status, body = http.api("GET", f"/v7/airpage/{file_id}")
    if isinstance(body, dict) and body.get("code") in PERMANENT_CODES:
        res.permanent = True
        res.md_error = res.docx_error = f"无法读取文档（HTTP {status}，快捷方式或无权限）"
        return res
    version = ((body.get("data") or {}).get("version") if status == 200 and isinstance(body, dict) else None)
    if version is None:
        res.md_error = res.docx_error = f"获取文档版本失败（HTTP {status}）"
        return res
    res.version = str(version)

    pending = {}
    if want_md:
        pending["markdown_zip"] = _create_export(http, file_id, "markdown_zip", res.version)
    if want_docx:
        pending["docx"] = _create_export(http, file_id, "docx", res.version)
    results = _await_exports(http, file_id, res.version, pending, sleep, poll_timeout, poll_interval)

    if want_md:
        url, err = results["markdown_zip"]
        if url:
            zip_tmp = md_path.parent / f".{base}.zip.tmp"
            if downloader(url, zip_tmp):
                frontmatter = (f"---\nfile_id: {file_id}\ndrive_id: {drive_id}\nname: {name}\n"
                               f"source_format: .otl\nbackend: airpage-markdown-zip\n"
                               f"airpage_version: {res.version}\nformat: {FORMAT_VERSION}\n"
                               f"backup_at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n---\n\n")
                try:
                    err = _install_markdown(zip_tmp, md_path, assets_dir, frontmatter)
                except (zipfile.BadZipFile, OSError) as e:
                    err = f"markdown_zip 解包失败: {e}"
                zip_tmp.unlink(missing_ok=True)
            else:
                err = "markdown_zip 下载失败"
        res.md_ok = not err
        res.md_error = err
        if res.md_ok:
            res.content_path = str(md_path)
            logger.info(f"   📝 OTL(v5) {name} → {md_path.name}")
        elif err == "OTL 内容为空":
            res.permanent = True

    if want_docx:
        url, err = results["docx"]
        if url and not downloader(url, docx_path):
            err = "docx 下载失败"
        res.docx_ok = bool(url) and not err
        res.docx_error = err
        if res.docx_ok:
            res.docx_path = str(docx_path)
            logger.info(f"   📄 OTL(v5) docx → {docx_path.name}")
    return res
