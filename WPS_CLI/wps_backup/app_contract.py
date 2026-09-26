"""
GUI App ↔ 引擎契约 — 运行记录、进度、取消、看门狗、调度判定、健康度

定时运行由 launchd agent 启动，GUI 读不到 stdout，一切经 STATE_DIR 文件交换：
  last_run.json            每次运行结束写入（exit 0/1/75/124/130）
  progress.json            运行中进度（结束即删除）
  runs.jsonl               最近运行历史（调度判定用）
  scheduler_heartbeat.json agent 每次触发写入（GUI 判断 agent 是否存活）
  force_run                GUI“立即备份”标记（scheduled 命令消费）
"""

import datetime as dt
import json
import os
import threading
from pathlib import Path
from typing import Callable, Optional

LAST_RUN_FILE = "last_run.json"
PROGRESS_FILE = "progress.json"
HISTORY_FILE = "runs.jsonl"
HEARTBEAT_FILE = "scheduler_heartbeat.json"
FORCE_MARKER = "force_run"

MAX_ERRORS = 20
MAX_HISTORY = 50
MAX_DAILY_ATTEMPTS = 3          # 定时备份失败后每小时重试，每天最多 3 次
STALE_HOURS = 36
REFRESH_WARN_DAYS = 30

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_LOCKED = 75
EXIT_TIMEOUT = 124
EXIT_CANCELLED = 130

# 全局取消信号：SIGTERM（GUI 取消）或看门狗超时时置位，下载 worker / OTL 循环检查
CANCEL = threading.Event()


# ---- JSON 文件 ----

def write_json_atomic(path: Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def read_json(path: Path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def read_history(state_dir: Path) -> list:
    out = []
    try:
        for line in (Path(state_dir) / HISTORY_FILE).read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    except OSError:
        pass
    return out


# ---- 运行记录 ----

class RunRecorder:
    def __init__(self, state_dir: Path, trigger: str, clock: Callable = dt.datetime.now):
        self.dir = Path(state_dir)
        self.trigger = trigger
        self.clock = clock
        self.started_at = clock().isoformat(timespec="seconds")
        self._lock = threading.Lock()
        self._progress = {}

    def start(self):
        self._progress = {"running": True, "pid": os.getpid(), "trigger": self.trigger,
                          "started_at": self.started_at, "phase": "starting",
                          "done": 0, "total": 0, "current": ""}
        write_json_atomic(self.dir / PROGRESS_FILE, self._progress)

    def update(self, phase: str, done: int = 0, total: int = 0, current: str = ""):
        with self._lock:
            self._progress.update({"phase": phase, "done": done, "total": total,
                                   "current": current,
                                   "updated_at": self.clock().isoformat(timespec="seconds")})
            write_json_atomic(self.dir / PROGRESS_FILE, self._progress)

    def finish(self, exit_code: int, counts: dict = None, errors: list = None,
               clear_progress: bool = True):
        errors = errors or []
        record = {
            "trigger": self.trigger,
            "started_at": self.started_at,
            "finished_at": self.clock().isoformat(timespec="seconds"),
            "exit_code": exit_code,
            "counts": counts or {},
            "error_count": len(errors),
            "errors": [str(e)[:300] for e in errors[:MAX_ERRORS]],
        }
        write_json_atomic(self.dir / LAST_RUN_FILE, record)
        self._append_history(record)
        if clear_progress:
            try:
                (self.dir / PROGRESS_FILE).unlink()
            except FileNotFoundError:
                pass
        return record

    def _append_history(self, record: dict):
        hist = read_history(self.dir)
        hist.append({k: record[k] for k in ("trigger", "started_at", "finished_at", "exit_code")})
        hist = hist[-MAX_HISTORY:]
        tmp = self.dir / (HISTORY_FILE + ".tmp")
        tmp.write_text("".join(json.dumps(h, ensure_ascii=False) + "\n" for h in hist),
                       encoding="utf-8")
        tmp.replace(self.dir / HISTORY_FILE)


# ---- 调度判定 ----

def should_run_scheduled(now: dt.datetime, schedule_hour: int, history: list,
                         max_attempts: int = MAX_DAILY_ATTEMPTS) -> bool:
    """agent 每小时触发一次；到点后当天没有成功的运行才执行，失败每小时重试至多 max_attempts 次。
    被锁跳过（75）不计为尝试。"""
    window_start = now.replace(hour=schedule_hour, minute=0, second=0, microsecond=0)
    if now < window_start:
        return False
    attempts = 0
    for h in history:
        try:
            started = dt.datetime.fromisoformat(h["started_at"])
        except (KeyError, ValueError):
            continue
        if started.tzinfo:
            started = started.replace(tzinfo=None)
        if started < window_start:
            continue
        code = h.get("exit_code")
        if code == EXIT_OK:
            return False
        if code != EXIT_LOCKED:
            attempts += 1
    return attempts < max_attempts


def next_scheduled_time(now: dt.datetime, schedule_hour: int) -> dt.datetime:
    t = now.replace(hour=schedule_hour, minute=0, second=0, microsecond=0)
    return t if t > now else t + dt.timedelta(days=1)


# ---- 取消与看门狗 ----

class Watchdog:
    """运行超时：先置位 CANCEL 让 worker 收尾；grace 后仍未退出则硬退出（锁随进程释放）"""

    def __init__(self, timeout: float, grace: float = 300,
                 on_hard_exit: Callable[[int], None] = None):
        self.timeout = timeout
        self.grace = grace
        self.timed_out = False
        self.on_hard_exit = on_hard_exit or os._exit
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        if self._stop.wait(self.timeout):
            return
        self.timed_out = True
        CANCEL.set()
        if self._stop.wait(self.grace):
            return
        self.on_hard_exit(EXIT_TIMEOUT)


# ---- 健康度 ----

def _parse_time(s) -> Optional[dt.datetime]:
    if not s:
        return None
    try:
        t = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    return t.astimezone().replace(tzinfo=None) if t.tzinfo else t


def compute_health(status: dict, now: dt.datetime = None) -> dict:
    """level: ok / warn / error，reasons 为中文说明（GUI 直接展示）"""
    now = now or dt.datetime.now()
    errors, warns = [], []

    cli = status.get("cli") or {}
    if not cli.get("found"):
        errors.append(f"找不到 wps365-cli（{cli.get('path')}）")

    auth = status.get("auth") or {}
    if auth.get("status") != "valid" and not auth.get("refreshable"):
        errors.append("wps365-cli 登录已失效，需要重新登录")
    else:
        if auth.get("airpage_scope") is False:
            warns.append("登录缺少 kso.airpage.readwrite 权限，OTL 文档无法备份")
        exp = _parse_time(auth.get("refresh_token_expires_at"))
        if exp and exp - now < dt.timedelta(days=REFRESH_WARN_DAYS):
            warns.append(f"登录将于 {exp:%Y-%m-%d} 过期，请提前重新登录")

    last = status.get("last_run") or {}
    code = last.get("exit_code")
    if code == EXIT_FAILED:
        errors.append(f"上次备份有失败（{last.get('error_count', 0)} 项）")
    elif code == EXIT_TIMEOUT:
        errors.append("上次备份超时被终止")
    elif code == EXIT_CANCELLED:
        warns.append("上次备份被取消")

    ok_at = _parse_time(status.get("last_success_at"))
    if not status.get("running"):
        if ok_at is None:
            warns.append("尚无成功的备份记录")
        elif now - ok_at > dt.timedelta(hours=STALE_HOURS):
            warns.append(f"已超过 {STALE_HOURS} 小时没有成功备份（上次 {ok_at:%m-%d %H:%M}）")

    level = "error" if errors else ("warn" if warns else "ok")
    return {"level": level, "reasons": errors + warns}


# ---- 状态汇总（status --json）----

AIRPAGE_SCOPE = "kso.airpage.readwrite"


def parse_auth_status(raw: Optional[dict], now: dt.datetime = None) -> dict:
    """从 `wps365-cli auth status` JSON 提取 delegated 登录状态。
    access token 仅 2 小时有效，过期但 refresh token 有效时视为可用（refreshable）。"""
    now = now or dt.datetime.now()
    d = (raw or {}).get("delegated") if isinstance(raw, dict) else None
    if not isinstance(d, dict):
        return {"status": "unknown", "refreshable": False,
                "refresh_token_expires_at": None, "airpage_scope": None}
    exp = _parse_time(d.get("refresh_token_expires_at"))
    scopes = d.get("granted_scopes") or []
    return {
        "status": d.get("status", "unknown"),
        "refreshable": bool(d.get("has_refresh")) and exp is not None and exp > now,
        "refresh_token_expires_at": d.get("refresh_token_expires_at"),
        "airpage_scope": AIRPAGE_SCOPE in scopes,
    }


def _pid_alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError):
        return False


def collect_status(state_dir: Path, cli_bin: str, schedule_hour: int,
                   runner=None, now: dt.datetime = None) -> dict:
    import subprocess
    runner = runner or subprocess.run
    now = now or dt.datetime.now()
    state_dir = Path(state_dir)

    progress = read_json(state_dir / PROGRESS_FILE)
    running = bool(progress and progress.get("running") and _pid_alive(progress.get("pid")))

    history = read_history(state_dir)
    last_success = next((h.get("finished_at") for h in reversed(history)
                         if h.get("exit_code") == EXIT_OK), None)

    cli = {"path": cli_bin, "found": os.path.isfile(cli_bin) and os.access(cli_bin, os.X_OK),
           "version": None}
    auth_raw = None
    try:
        r = runner([cli_bin, "version"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            first = (r.stdout or "").strip().splitlines()[:1]
            cli["version"] = first[0].split(":", 1)[-1].strip() if first else None
        r = runner([cli_bin, "auth", "status"], capture_output=True, text=True, timeout=15)
        if r.returncode == 0:
            auth_raw = json.loads(r.stdout)
    except Exception:
        pass

    status = {
        "generated_at": now.isoformat(timespec="seconds"),
        "state_dir": str(state_dir),
        "running": running,
        "progress": progress if running else None,
        "last_run": read_json(state_dir / LAST_RUN_FILE),
        "last_success_at": last_success,
        "heartbeat": read_json(state_dir / HEARTBEAT_FILE),
        "schedule_hour": schedule_hour,
        "next_run_at": next_scheduled_time(now, schedule_hour).isoformat(timespec="seconds"),
        "cli": cli,
        "auth": parse_auth_status(auth_raw, now=now),
    }
    status["health"] = compute_health(status, now=now)
    return status
