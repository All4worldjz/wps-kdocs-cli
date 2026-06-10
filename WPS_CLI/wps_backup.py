#!/usr/bin/env python3
"""
WPS 云盘 → 本地差量备份应用

用法:
  python3 wps_backup.py run              # 立即执行一次备份（含 .otl）
  python3 wps_backup.py run --dry-run    # 仅对比差异，不下载
  python3 wps_backup.py run --no-otl     # 跳过 .otl 备份
  python3 wps_backup.py backup-otl       # .otl 文件专项备份（缓存中转）
  python3 wps_backup.py backup-otl --dry-run  # 预览 .otl 匹配结果
  python3 wps_backup.py daemon           # 守护模式（后台持续运行）
  python3 wps_backup.py install          # 生成 launchd 定时任务配置
  python3 wps_backup.py status           # 查看备份状态
  python3 wps_backup.py log              # 查看最近日志
"""

import json
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from wps_backup import config
from wps_backup.engine import BackupEngine
from wps_backup.state import BackupState
from wps_backup.scheduler import daemon_mode, generate_launchd_plist
from wps_backup.logger import setup_logger
from wps_backup.otl_engine import run_otl_backup
from wps_backup import kdocs_engine

logger = setup_logger()


def cmd_run(args):
    """立即执行一次差量备份（含 .otl 专项）"""
    # 1) 常规文件备份
    engine = BackupEngine(workers=args.workers)
    result = engine.run(max_files=args.max, dry_run=args.dry_run)
    regular_ok = result.failed == 0

    # 2) OTL 专项备份
    if not args.no_otl:
        logger.info("📋 开始 OTL 专项备份...")
        otl_result = run_otl_backup(dry_run=args.dry_run)
        otl_ok = len(otl_result.errors) == 0
    else:
        logger.info("📋 跳过 OTL 备份（--no-otl）")
        otl_ok = True

    return 0 if (regular_ok and otl_ok) else 1


def cmd_daemon(args):
    """守护模式"""
    daemon_mode()
    return 0


def cmd_install(args):
    """生成 launchd plist"""
    script = Path(__file__).resolve()
    generate_launchd_plist(str(script))
    return 0


def cmd_status(args):
    """查看备份状态"""
    state = BackupState()
    stats = state.stats()

    # OTL 状态
    from wps_backup.otl_engine import OTL_STATE_FILE
    otl_count = 0
    otl_content_count = 0
    if OTL_STATE_FILE.exists():
        try:
            with open(OTL_STATE_FILE, "r", encoding="utf-8") as f:
                otl_data = json.load(f)
            otl_count = len(otl_data)
            otl_last = max((v.get("backed_up_at", "") for v in otl_data.values()), default="从未")
            # 统计有 content_path 的记录
            otl_content_count = sum(1 for v in otl_data.values() if v.get("content_path"))
        except Exception:
            otl_count = 0
            otl_last = "从未"
    else:
        otl_last = "从未"

    # kdocs-cli 状态
    kdocs_ver = kdocs_engine.get_kdocs_version()
    kdocs_auth = "✅ 已认证" if kdocs_engine.check_kdocs_cli_available() else "❌ 未认证"

    # 内容备份统计
    content_count = 0
    if config.CONTENT_BACKUP_DIR.exists():
        content_count = sum(1 for _ in config.CONTENT_BACKUP_DIR.rglob("*.md"))

    print(f"""
📊 备份状态
═══════════════════════════════════════════════════
  上次备份: {stats.get('last_backup_at') or '从未'}
  快照记录: {stats.get('snapshot_count', 0)} 个文件
  总大小:   {stats.get('total_size', 0):,} bytes
  OTL 记录: {otl_count} 个文件 (内容备份: {otl_content_count})
  OTL 上次: {otl_last}
  内容备份: {content_count} 个 Markdown 文件
  kdocs-cli: {kdocs_ver} ({kdocs_auth})
  备份目录: {config.BACKUP_DIR}
  状态文件: {config.STATE_FILE}
  日志文件: {config.LOG_FILE}
═══════════════════════════════════════════════════
    """)
    return 0


def cmd_log(args):
    """查看最近日志"""
    n = args.n or 20
    if config.LOG_FILE.exists():
        lines = config.LOG_FILE.read_text(encoding="utf-8").strip().split("\n")
        for line in lines[-n:]:
            print(line)
    else:
        print("暂无日志")
    return 0


def cmd_backup_otl(args):
    """.otl 文件专项备份 — kdocs-cli 内容 + WPS Office 本地缓存实体"""
    # 临时禁用内容备份（如果 --no-content）
    if args.no_content:
        orig = config.OTL_CONTENT_BACKUP_ENABLED
        config.OTL_CONTENT_BACKUP_ENABLED = False
        result = run_otl_backup(dry_run=args.dry_run)
        config.OTL_CONTENT_BACKUP_ENABLED = orig
    else:
        result = run_otl_backup(dry_run=args.dry_run)
    return 0 if len(result.errors) == 0 else 1


def main():
    parser = argparse.ArgumentParser(
        description="WPS 云盘 → 本地差量备份",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s run               立即备份（含 .otl）
  %(prog)s run --dry-run     仅预览差异
  %(prog)s run --no-otl      跳过 .otl 备份
  %(prog)s daemon            守护模式
  %(prog)s install           安装 launchd 定时任务
  %(prog)s status            查看状态
  %(prog)s log -n 30         查看最近 30 行日志
        """,
    )
    sub = parser.add_subparsers(dest="command")

    p_run = sub.add_parser("run", help="立即执行备份（含 .otl 专项）")
    p_run.add_argument("--dry-run", action="store_true", help="仅对比差异，不下载")
    p_run.add_argument("--max", type=int, default=None, help="限制下载文件数（测试用）")
    p_run.add_argument("--workers", "-w", type=int, default=config.MAX_CONCURRENT,
                       help=f"并发线程数（默认: {config.MAX_CONCURRENT}）")
    p_run.add_argument("--no-otl", action="store_true", help="跳过 .otl 专项备份")

    sub.add_parser("daemon", help="守护模式（后台轮询，到时间自动备份）")
    sub.add_parser("install", help="生成 launchd 定时任务配置文件")
    sub.add_parser("status", help="查看备份状态")

    p_otl = sub.add_parser("backup-otl", help=".otl 文件专项备份（kdocs-cli 内容 + 缓存实体）")
    p_otl.add_argument("--dry-run", action="store_true", help="仅预览匹配结果")
    p_otl.add_argument("--no-content", action="store_true", help="跳过 kdocs-cli 内容备份")

    p_log = sub.add_parser("log", help="查看最近日志")
    p_log.add_argument("-n", type=int, default=20, help="行数")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    cmds = {
        "run": cmd_run,
        "daemon": cmd_daemon,
        "install": cmd_install,
        "status": cmd_status,
        "log": cmd_log,
        "backup-otl": cmd_backup_otl,
    }
    return cmds[args.command](args)


if __name__ == "__main__":
    sys.exit(main())