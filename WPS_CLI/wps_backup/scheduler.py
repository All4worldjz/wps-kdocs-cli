"""
调度器 — 守护模式 & launchd 配置生成
"""

import time
import datetime
import signal
import sys
from pathlib import Path

from . import config
from .engine import BackupEngine
from .otl_engine import run_otl_backup
from .logger import setup_logger

logger = setup_logger()

PLIST_TEMPLATE = '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.wps.backup</string>

    <key>ProgramArguments</key>
    <array>
        <string>{python}</string>
        <string>{script}</string>
        <string>run</string>
    </array>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>{hour}</integer>
        <key>Minute</key>
        <integer>{minute}</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>{log_dir}/launchd_stdout.log</string>

    <key>StandardErrorPath</key>
    <string>{log_dir}/launchd_stderr.log</string>

    <key>RunAtLoad</key>
    <false/>

    <key>KeepAlive</key>
    <false/>
</dict>
</plist>'''


def generate_launchd_plist(script_path: str, output_path: str = None):
    """生成 macOS launchd 定时任务配置文件"""
    import os
    plist = PLIST_TEMPLATE.format(
        python=sys.executable,
        script=os.path.abspath(script_path),
        hour=config.SCHEDULE_HOUR,
        minute=config.SCHEDULE_MINUTE,
        log_dir=str(config.STATE_DIR),
    )
    if output_path is None:
        output_path = str(config.APP_ROOT / "com.wps.backup.plist")

    with open(output_path, "w") as f:
        f.write(plist)

    logger.info(f"✅ launchd plist 已生成: {output_path}")
    print(f"""
📋 安装 launchd 定时任务:

  cp {output_path} ~/Library/LaunchAgents/
  launchctl load ~/Library/LaunchAgents/com.wps.backup.plist

📋 管理命令:

  launchctl list com.wps.backup      # 查看状态
  launchctl unload ~/Library/LaunchAgents/com.wps.backup.plist  # 卸载
  launchctl start com.wps.backup     # 手动触发

⏰ 将在每日 {config.SCHEDULE_HOUR}:{config.SCHEDULE_MINUTE:02d} 自动执行
""")


def daemon_mode():
    """守护模式：在后台持续运行，到时间自动触发备份"""
    logger.info(f"🕐 守护模式启动，将在每日 {config.SCHEDULE_HOUR}:{config.SCHEDULE_MINUTE:02d} 执行备份")
    logger.info(f"   轮询间隔: {config.SCHEDULE_CHECK_INTERVAL}s")

    last_run_date = None
    shutdown = False

    def on_signal(sig, frame):
        nonlocal shutdown
        logger.info("收到终止信号，正在退出...")
        shutdown = True

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    while not shutdown:
        now = datetime.datetime.now()
        today_str = now.strftime("%Y-%m-%d")

        # 判断是否应该执行
        should_run = (
            last_run_date != today_str and
            now.hour >= config.SCHEDULE_HOUR and
            now.minute >= config.SCHEDULE_MINUTE
        )

        if should_run:
            logger.info(f"⏰ 到达预定时间，开始备份...")
            try:
                engine = BackupEngine()
                engine.run()
                logger.info("📋 开始 OTL 专项备份...")
                run_otl_backup()
                last_run_date = today_str
            except Exception as e:
                logger.error(f"备份异常: {e}")

        time.sleep(config.SCHEDULE_CHECK_INTERVAL)

    logger.info("守护模式已退出")