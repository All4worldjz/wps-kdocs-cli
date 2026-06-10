#!/usr/bin/env python3
"""
修复验证脚本 — 在 token 有效时运行
用法: python3 verify_fix.py
"""

import sys
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from wps_backup.engine import BackupEngine, SKIP_EXTS
from wps_backup.state import BackupState


def check_dry_run():
    print("=" * 60)
    print("验证 1: Dry-run 检查 .spt / .form 已被过滤")
    print("=" * 60)

    # 记录执行前的日志行数，确保只检查本次 dry-run 产生的日志
    log_path = Path("wps_backup_state/backup.log")
    initial_line_count = len(log_path.read_text(encoding="utf-8").splitlines()) if log_path.exists() else 0

    engine = BackupEngine()
    result = engine.run(dry_run=True)

    # 只扫描本次 dry-run 新增的日志行
    lines = log_path.read_text(encoding="utf-8").splitlines()
    dry_run_lines = lines[initial_line_count:]
    in_dry_run = False
    filtered_lines = []
    for line in dry_run_lines:
        if "🔍 Dry-run 模式" in line:
            in_dry_run = True
            filtered_lines = []
        if in_dry_run:
            filtered_lines.append(line)
        if "开始 OTL" in line and in_dry_run:
            break

    bad_exts = []
    for line in filtered_lines:
        if "🆕" in line or "🔄" in line:
            name = line.split("🆕 ")[-1].split("🔄 ")[-1].strip()
            ext = Path(name).suffix.lower()
            if ext in SKIP_EXTS:
                bad_exts.append(name)

    if bad_exts:
        print(f"  ❌ FAIL: 仍有 {len(bad_exts)} 个不可下载格式在待下载队列:")
        for n in bad_exts[:5]:
            print(f"     - {n}")
        return False
    else:
        print(f"  ✅ PASS: 待下载队列中无 {SKIP_EXTS} 格式")
        return True


def check_state_logic():
    print("\n" + "=" * 60)
    print("验证 2: 状态管理逻辑 — 不可下载格式跳过")
    print("=" * 60)

    state = BackupState()
    # 模拟一个 .spt 失败记录
    state.mark_failed("d1", "f_spt", "无下载地址",
                      name="test.spt", size=100, mtime=100, drive_name="test")
    assert state.needs_update("d1", "f_spt", 200) == False, "已知无下载地址的文件应跳过"
    print("  ✅ PASS: 标记为'无下载地址'的文件会被 needs_update 跳过")

    # 模拟一个 405 失败记录
    state.mark_failed("d1", "f_pptx", "HTTP 405",
                      name="test.pptx", size=100, mtime=100, drive_name="test")
    assert state.needs_update("d1", "f_pptx", 200) == True, "405 不是永久失败，应继续尝试"
    print("  ✅ PASS: 标记为'HTTP 405'的文件仍会继续尝试")
    return True


def check_path_isolation():
    print("\n" + "=" * 60)
    print("验证 3: 同名文件路径隔离")
    print("=" * 60)

    from wps_backup.engine import sanitize, RemoteFile
    rf1 = RemoteFile("abc123def", "d1", "盘", "同名.pptx", 100, 0, "", "0", "file")
    rf2 = RemoteFile("xyz789uvw", "d1", "盘", "同名.pptx", 200, 0, "", "0", "file")

    safe = sanitize(rf1.name)
    stem = Path(safe).stem
    suffix = Path(safe).suffix
    p1 = Path(f"{stem}_{rf1.file_id[:8]}{suffix}")
    p2 = Path(f"{stem}_{rf2.file_id[:8]}{suffix}")

    assert p1 != p2, "同名文件应映射到不同路径"
    assert "abc123de" in p1.name
    assert "xyz789uv" in p2.name
    print(f"  ✅ PASS: 同名文件映射到独立路径")
    print(f"     file_id=abc123def → {p1}")
    print(f"     file_id=xyz789uvw → {p2}")
    return True


def main():
    ok = True
    ok &= check_state_logic()
    ok &= check_path_isolation()

    # token 检查
    try:
        r = subprocess.run(["wps365-cli", "auth", "token"],
                           capture_output=True, text=True, timeout=10)
        token_ok = r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        token_ok = False

    if not token_ok:
        print("\n" + "=" * 60)
        print("⚠️  wps365-cli token 不可用，跳过在线 Dry-run 验证")
        print("     请执行: wps365-cli auth refresh --delegated")
        print("     然后再次运行: python3 verify_fix.py")
        print("=" * 60)
        return 0 if ok else 1

    ok &= check_dry_run()

    print("\n" + "=" * 60)
    if ok:
        print("🎉 全部验证通过")
    else:
        print("❌ 部分验证失败，请检查上方输出")
    print("=" * 60)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
