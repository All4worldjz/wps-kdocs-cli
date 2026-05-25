#!/usr/bin/env python3
"""
WPS 共享文件分类目录生成器
- 列出所有盘的共享文件
- 按文件类型(扩展名)创建子文件夹
- 生成 CATALOG.md 索引
- 不下载文件，不解析内容
"""

import json, subprocess, sys, time, re, os
from pathlib import Path
from collections import defaultdict

OUTPUT_DIR = Path("/Users/whoami2028/Workshop/GITREPO/WPS_CLI") / "wps_shared_files"
CLI = "wps365-cli"

def cli(*args, timeout=60):
    r = subprocess.run([CLI] + list(args), capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        print(f"  CLI错误: {r.stderr.strip()[:200]}")
        return None
    return json.loads(r.stdout)

def list_all(drive_id, parent_id="0"):
    """遍历盘下所有文件（含分页）"""
    items = []
    token = ""
    while True:
        args = ["drive", "files", "list", drive_id, parent_id,
                "--page-size", "100", "--with-permission", "-o", "json"]
        if token:
            args += ["--page-token", token]
        data = cli(*args)
        if not data or data["code"] != 0:
            break
        batch = data.get("data", {}).get("items", [])
        items.extend(batch)
        # 递归子目录
        for f in batch:
            if f.get("type") == "folder":
                items.extend(list_all(drive_id, f["id"]))
        token = data.get("data", {}).get("next_page_token", "")
        if not token:
            break
    return items

def classify(name):
    """按扩展名分类"""
    ext = Path(name).suffix.lower()
    if not ext:
        ext = "_n/a"
    return ext.lstrip(".")

def main():
    print("=" * 60)
    print("  WPS 共享文件分类目录生成")
    print("=" * 60)

    # 1. 获取盘
    print("\n📁 获取盘列表...")
    drives = cli("drive", "list", "--allotee-type", "user", "--page-size", "50", "-o", "json")
    if not drives:
        print("❌ 失败")
        sys.exit(1)
    drives = drives["data"]["items"]
    print(f"  找到 {len(drives)} 个盘")

    # 2. 收集所有共享文件
    all_shared = []
    for d in drives:
        did, dname = d["id"], d["name"]
        print(f"\n  🔍 扫描: {dname} ({did})")
        items = list_all(did)
        shared = [i for i in items if i.get("shared") and i.get("type") == "file"]
        print(f"    共 {len(items)} 条目, 共享 {len(shared)} 个")
        for f in shared:
            f["_drive_name"] = dname
        all_shared.extend(shared)

    print(f"\n📊 总计 {len(all_shared)} 个共享文件\n")

    if not all_shared:
        print("❌ 无共享文件")
        sys.exit(0)

    # 3. 按扩展名分类
    by_ext = defaultdict(list)
    for f in all_shared:
        ext = classify(f["name"])
        by_ext[ext].append(f)

    # 4. 创建目录结构
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("📂 创建分类目录:")
    for ext in sorted(by_ext.keys()):
        subdir = OUTPUT_DIR / ext
        subdir.mkdir(parents=True, exist_ok=True)
        print(f"  📁 {ext}/  ({len(by_ext[ext])} 个文件)")

    # 5. 在每个子目录下创建 .filelist （文件清单）
    for ext, files in by_ext.items():
        subdir = OUTPUT_DIR / ext
        filelist_path = subdir / ".filelist"
        with open(filelist_path, "w", encoding="utf-8") as f:
            f.write(f"# {ext} 文件清单 ({len(files)} 个)\n\n")
            for i, fi in enumerate(files, 1):
                name = fi["name"]
                size = fi.get("size", 0)
                mtime = fi.get("mtime", 0)
                ts = time.strftime('%Y-%m-%d %H:%M', time.localtime(mtime)) if mtime else "?"
                link = fi.get("link_url", "")
                f.write(f"{i:03d}. {name}\n")
                f.write(f"    大小: {size:,} bytes | 时间: {ts} | 盘: {fi['_drive_name']}\n")
                if link:
                    f.write(f"    链接: {link}\n")
                f.write("\n")

    # 6. 生成 CATALOG.md
    catalog = OUTPUT_DIR / "CATALOG.md"
    lines = [
        f"# WPS 共享文件目录\n",
        f"生成: {time.strftime('%Y-%m-%d %H:%M:%S')}\n",
        f"文件数: {len(all_shared)} | 分类: {len(by_ext)} 种\n\n",
        "---\n\n",
        "## 分类概览\n\n",
        "| 类型 | 数量 | 目录 |\n|------|------|------|\n",
    ]
    for ext in sorted(by_ext.keys()):
        lines.append(f"| .{ext} | {len(by_ext[ext])} | [{ext}/]({ext}/) |\n")

    lines.append("\n---\n\n")
    lines.append("## 文件详情\n\n")

    for ext in sorted(by_ext.keys()):
        lines.append(f"### .{ext} ({len(by_ext[ext])} 个)\n\n")
        for i, fi in enumerate(by_ext[ext], 1):
            name = fi["name"]
            size = fi.get("size", 0)
            mtime = fi.get("mtime", 0)
            ts = time.strftime('%Y-%m-%d %H:%M', time.localtime(mtime)) if mtime else "?"
            link = fi.get("link_url", "")
            drive = fi["_drive_name"]

            lines.append(f"**{i}. {name}**\n\n")
            lines.append(f"- 📁 盘: `{drive}`\n")
            lines.append(f"- 📏 大小: {size:,} bytes\n")
            lines.append(f"- 🕐 时间: {ts}\n")
            if link:
                lines.append(f"- 🔗 链接: {link}\n")
            lines.append("\n")

    with open(catalog, "w", encoding="utf-8") as f:
        f.write("".join(lines))

    print(f"\n{'='*60}")
    print(f"✅ 完成!")
    print(f"   📄 索引: {catalog}")
    print(f"   📁 目录: {OUTPUT_DIR}")
    print(f"   子目录: {len(by_ext)} 个类型")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()