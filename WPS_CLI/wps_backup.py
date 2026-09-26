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

import datetime
import json
import os
import signal
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
from wps_backup import lock
from wps_backup import app_contract as ac

RUN_LOCK_FILE = config.STATE_DIR / ".run.lock"

logger = setup_logger()


def do_backup(args, progress=None):
    """执行一次差量备份（含 .otl 专项），返回 (exit_code, counts, errors)"""
    # 1) 常规文件备份
    engine = BackupEngine(workers=args.workers, progress=progress)
    result = engine.run(max_files=args.max, dry_run=args.dry_run)
    # 认证失败 / 扫描失败只记录在 errors 中（failed 为 0），也必须返回非零退出码
    regular_ok = result.failed == 0 and not result.errors
    counts = {"total": result.total, "new": result.new, "updated": result.updated,
              "skipped": result.skipped, "failed": result.failed}
    errors = list(result.errors)

    # 2) OTL 专项备份
    otl_ok = True
    if not args.no_otl and not ac.CANCEL.is_set():
        logger.info("📋 开始 OTL 专项备份...")
        otl_result = run_otl_backup(dry_run=args.dry_run, progress=progress,
                                    api_files=engine.otl_files, scan_complete=engine.scan_complete)
        otl_ok = len(otl_result.errors) == 0
        counts.update({"otl_total": otl_result.total,
                       "otl_content_backed_up": otl_result.content_backed_up,
                       "otl_content_failed": otl_result.content_failed,
                       "otl_docx_exported": otl_result.docx_exported})
        errors += [f"OTL: {e}" for e in otl_result.errors]
    elif args.no_otl:
        logger.info("📋 跳过 OTL 备份（--no-otl）")

    return (0 if (regular_ok and otl_ok) else 1), counts, errors


def run_recorded(args, trigger: str) -> int:
    """在运行锁、SIGTERM 取消、看门狗与运行记录（last_run.json 等）下执行备份。
    GUI 依赖这些文件判断结果；dry-run 不记录（否则会被当作当天已成功）。"""
    if args.dry_run:
        fd = lock.acquire(RUN_LOCK_FILE)
        if fd is None:
            logger.error(f"⏭️  另一个备份进程正在运行（PID {lock.holder_pid(RUN_LOCK_FILE)}），本次跳过")
            return lock.EXIT_LOCKED
        try:
            return do_backup(args)[0]
        finally:
            lock.release(fd)

    rec = ac.RunRecorder(config.STATE_DIR, trigger)
    fd = lock.acquire(RUN_LOCK_FILE)
    if fd is None:
        msg = f"另一个备份进程正在运行（PID {lock.holder_pid(RUN_LOCK_FILE)}），本次跳过"
        logger.error(f"⏭️  {msg}")
        rec.finish(lock.EXIT_LOCKED, errors=[msg], clear_progress=False)
        return lock.EXIT_LOCKED

    def hard_exit(code):
        logger.error(f"⏱️  运行超过 {config.RUN_TIMEOUT}s 且取消后仍未结束，强制退出")
        rec.finish(code, errors=["运行超时，强制退出"])
        os._exit(code)

    signal.signal(signal.SIGTERM, lambda *_: ac.CANCEL.set())
    watchdog = ac.Watchdog(config.RUN_TIMEOUT, on_hard_exit=hard_exit)
    rec.start()
    watchdog.start()
    code, counts, errors = ac.EXIT_FAILED, {}, []
    try:
        code, counts, errors = do_backup(args, progress=rec.update)
    except Exception as e:
        logger.exception(f"❌ 备份异常: {e}")
        errors = [f"异常: {e}"]
    finally:
        watchdog.stop()
        if watchdog.timed_out:
            code = ac.EXIT_TIMEOUT
        elif ac.CANCEL.is_set():
            code = ac.EXIT_CANCELLED
        rec.finish(code, counts, errors)
        lock.release(fd)
    return code


def cmd_run(args):
    """立即执行一次差量备份（含 .otl 专项）"""
    return run_recorded(args, trigger="manual")


def cmd_scheduled(args):
    """由 App 的 launchd agent 每小时触发：到点且当天未成功才运行；force_run 标记（GUI“立即备份”）优先"""
    now = datetime.datetime.now()
    ac.write_json_atomic(config.STATE_DIR / ac.HEARTBEAT_FILE,
                         {"at": now.isoformat(timespec="seconds"), "pid": os.getpid()})
    marker = config.STATE_DIR / ac.FORCE_MARKER
    force = marker.exists()
    if force:
        marker.unlink(missing_ok=True)
    elif not ac.should_run_scheduled(now, config.SCHEDULE_HOUR, ac.read_history(config.STATE_DIR)):
        return 0
    logger.info(f"⏰ {'手动触发（App）' if force else '定时触发'}备份")
    run_args = argparse.Namespace(dry_run=False, max=None, workers=config.MAX_CONCURRENT, no_otl=False)
    return run_recorded(run_args, trigger="manual" if force else "schedule")


def cmd_daemon(args):
    """守护模式"""
    daemon_mode()
    return 0


def cmd_install(args):
    """生成 launchd plist（已被 WPS Backup.app 取代）"""
    app_plist = Path.home() / "Library/LaunchAgents/cc.all4world.wpsbackup.scheduler.plist"
    if app_plist.exists():
        print(f"⚠️  WPS Backup.app 已接管定时任务（{app_plist}）。\n"
              f"   再安装 com.wps.backup 会产生第二个计划（每晚一个以 75 退出）。已取消。")
        return 1
    script = Path(__file__).resolve()
    generate_launchd_plist(str(script))
    return 0


def cmd_status(args):
    """查看备份状态"""
    if getattr(args, "json", False):
        st = ac.collect_status(config.STATE_DIR, config.CLI_BIN, config.SCHEDULE_HOUR)
        state = BackupState()
        st["snapshot"] = state.stats()
        st["backup_dir"] = str(config.BACKUP_DIR)
        st["log_file"] = str(config.LOG_FILE)
        print(json.dumps(st, ensure_ascii=False, indent=2))
        return 0
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
    p_status = sub.add_parser("status", help="查看备份状态")
    p_status.add_argument("--json", action="store_true", help="机器可读输出（供 GUI）")
    sub.add_parser("scheduled", help="供 App agent 每小时调用：到点/被请求时才运行")

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
        "scheduled": cmd_scheduled,
    }
    if args.command in ("backup-otl",):
        fd = lock.acquire(RUN_LOCK_FILE)
        if fd is None:
            logger.error(f"⏭️  另一个备份进程正在运行（PID {lock.holder_pid(RUN_LOCK_FILE)}，"
                         f"{RUN_LOCK_FILE}），本次跳过")
            return lock.EXIT_LOCKED
        try:
            return cmds[args.command](args)
        finally:
            lock.release(fd)
    return cmds[args.command](args)


if __name__ == "__main__":
    sys.exit(main())