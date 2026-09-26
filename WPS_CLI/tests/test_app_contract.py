"""
GUI App 与引擎的机器可读契约 — TDD

GUI 不启动定时运行（由 launchd agent 启动），永远读不到 stdout；
因此所有结果必须经 STATE_DIR 中的文件与 `status --json` 暴露：
- last_run.json：每次运行结束原子写入（含被锁跳过 75、超时 124、取消 130）
- progress.json：运行中阶段与进度
- runs.jsonl：最近运行历史（调度判定“今天是否已成功/已重试几次”）
- scheduler_heartbeat.json：agent 每次触发都写，GUI 据此判断 agent 是否存活
"""

import datetime as dt
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from wps_backup import app_contract as ac


def _d(h, m=0, day=26):
    return dt.datetime(2026, 9, day, h, m)


class TestAtomicJson(unittest.TestCase):

    def test_write_and_read(self):
        p = Path(tempfile.mkdtemp()) / "x.json"
        ac.write_json_atomic(p, {"a": 1})
        self.assertEqual(ac.read_json(p), {"a": 1})
        self.assertFalse(p.with_suffix(".json.tmp").exists())

    def test_read_missing_or_corrupt_returns_default(self):
        d = Path(tempfile.mkdtemp())
        self.assertIsNone(ac.read_json(d / "nope.json"))
        (d / "bad.json").write_text("{")
        self.assertEqual(ac.read_json(d / "bad.json", default={}), {})


class TestRunRecorder(unittest.TestCase):

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.rec = ac.RunRecorder(self.dir, trigger="manual", clock=lambda: _d(20))

    def test_progress_then_last_run(self):
        self.rec.start()
        prog = ac.read_json(self.dir / ac.PROGRESS_FILE)
        self.assertTrue(prog["running"])
        self.assertEqual(prog["pid"], os.getpid())
        self.rec.update("download", 3, 10, "a.docx")
        prog = ac.read_json(self.dir / ac.PROGRESS_FILE)
        self.assertEqual((prog["phase"], prog["done"], prog["total"]), ("download", 3, 10))

        self.rec.finish(0, counts={"new": 2}, errors=["e"] * 30)
        last = ac.read_json(self.dir / ac.LAST_RUN_FILE)
        self.assertEqual(last["exit_code"], 0)
        self.assertEqual(last["trigger"], "manual")
        self.assertEqual(last["counts"], {"new": 2})
        self.assertEqual(len(last["errors"]), ac.MAX_ERRORS)
        self.assertEqual(last["error_count"], 30)
        self.assertFalse((self.dir / ac.PROGRESS_FILE).exists())

    def test_history_appended_and_capped(self):
        for i in range(ac.MAX_HISTORY + 5):
            ac.RunRecorder(self.dir, "schedule", clock=lambda: _d(20)).finish(0)
        hist = ac.read_history(self.dir)
        self.assertEqual(len(hist), ac.MAX_HISTORY)

    def test_skipped_run_recorded_without_touching_progress(self):
        """被锁跳过（75）也要写 last_run，但不能删掉正在运行进程的 progress.json"""
        ac.write_json_atomic(self.dir / ac.PROGRESS_FILE, {"running": True, "pid": 1})
        self.rec.finish(75, clear_progress=False)
        self.assertEqual(ac.read_json(self.dir / ac.LAST_RUN_FILE)["exit_code"], 75)
        self.assertTrue((self.dir / ac.PROGRESS_FILE).exists())


class TestShouldRunScheduled(unittest.TestCase):

    def _hist(self, *entries):
        return [{"started_at": s.isoformat(), "exit_code": c, "trigger": "schedule"} for s, c in entries]

    def test_before_schedule_hour_not_due(self):
        self.assertFalse(ac.should_run_scheduled(_d(19, 59), 20, []))

    def test_after_hour_no_run_today_is_due(self):
        self.assertTrue(ac.should_run_scheduled(_d(20), 20, self._hist((_d(20, day=25), 0))))

    def test_success_today_not_due(self):
        self.assertFalse(ac.should_run_scheduled(_d(22), 20, self._hist((_d(20), 0))))

    def test_success_before_schedule_hour_today_still_due(self):
        """早上手动跑过不算当天的定时备份"""
        self.assertTrue(ac.should_run_scheduled(_d(21), 20, self._hist((_d(9), 0))))

    def test_failures_retry_up_to_limit(self):
        h = self._hist((_d(20), 1), (_d(21), 1))
        self.assertTrue(ac.should_run_scheduled(_d(22), 20, h))
        h = self._hist((_d(20), 1), (_d(21), 1), (_d(22), 1))
        self.assertFalse(ac.should_run_scheduled(_d(23), 20, h))

    def test_lock_skips_do_not_count_as_attempts(self):
        h = self._hist((_d(20), 75), (_d(21), 75), (_d(22), 75))
        self.assertTrue(ac.should_run_scheduled(_d(23), 20, h))

    def test_catch_up_after_midnight_not_needed(self):
        """睡眠跨天：新的一天未到时间不补跑前一天（次日 20 点正常跑）"""
        self.assertFalse(ac.should_run_scheduled(_d(8, day=27), 20, []))


class TestHealth(unittest.TestCase):

    NOW = _d(21)

    def _status(self, **kw):
        base = {
            "last_run": {"exit_code": 0, "finished_at": _d(20, 30).isoformat()},
            "last_success_at": _d(20, 30).isoformat(),
            "auth": {"status": "valid", "refresh_token_expires_at": "2027-09-26T12:00:00+08:00",
                     "airpage_scope": True},
            "cli": {"path": "/x/wps365-cli", "found": True},
            "running": False,
        }
        base.update(kw)
        return base

    def test_ok(self):
        h = ac.compute_health(self._status(), now=self.NOW)
        self.assertEqual(h["level"], "ok", h)

    def test_last_run_failed_is_error(self):
        h = ac.compute_health(self._status(last_run={"exit_code": 1, "finished_at": _d(20).isoformat()}),
                              now=self.NOW)
        self.assertEqual(h["level"], "error")

    def test_lock_skip_is_not_error(self):
        h = ac.compute_health(self._status(last_run={"exit_code": 75, "finished_at": _d(20).isoformat()}),
                              now=self.NOW)
        self.assertEqual(h["level"], "ok")

    def test_stale_is_warn(self):
        h = ac.compute_health(self._status(last_success_at=_d(8, day=24).isoformat()), now=self.NOW)
        self.assertEqual(h["level"], "warn")

    def test_never_succeeded_is_warn(self):
        h = ac.compute_health(self._status(last_success_at=None, last_run=None), now=self.NOW)
        self.assertEqual(h["level"], "warn")

    def test_auth_expired_is_error(self):
        h = ac.compute_health(self._status(auth={"status": "expired"}), now=self.NOW)
        self.assertEqual(h["level"], "error")
        self.assertTrue(any("登录" in r for r in h["reasons"]))

    def test_refresh_expiring_soon_is_warn(self):
        h = ac.compute_health(self._status(auth={
            "status": "valid", "airpage_scope": True,
            "refresh_token_expires_at": "2026-10-10T00:00:00+08:00"}), now=self.NOW)
        self.assertEqual(h["level"], "warn")

    def test_cli_missing_is_error(self):
        h = ac.compute_health(self._status(cli={"found": False, "path": "wps365-cli"}), now=self.NOW)
        self.assertEqual(h["level"], "error")


class TestParseAuth(unittest.TestCase):

    def test_access_expired_but_refreshable(self):
        raw = {"delegated": {"status": "expired", "has_refresh": True,
                             "refresh_token_expires_at": "2027-09-26T12:38:50+08:00",
                             "granted_scopes": ["kso.drive.readwrite", "kso.airpage.readwrite"]}}
        a = ac.parse_auth_status(raw, now=_d(21))
        self.assertTrue(a["refreshable"])
        self.assertTrue(a["airpage_scope"])
        self.assertEqual(ac.compute_health({"auth": a, "cli": {"found": True},
                                            "last_success_at": _d(20).isoformat()},
                                           now=_d(21))["level"], "ok")

    def test_refresh_expired_not_refreshable(self):
        raw = {"delegated": {"status": "expired", "has_refresh": True,
                             "refresh_token_expires_at": "2026-01-01T00:00:00+08:00"}}
        self.assertFalse(ac.parse_auth_status(raw, now=_d(21))["refreshable"])

    def test_garbage(self):
        self.assertEqual(ac.parse_auth_status(None)["status"], "unknown")


class TestCollectStatus(unittest.TestCase):

    def test_collect_combines_files_and_health(self):
        d = Path(tempfile.mkdtemp())
        rec = ac.RunRecorder(d, "schedule", clock=lambda: _d(20))
        rec.finish(0, counts={"new": 1})
        ac.write_json_atomic(d / ac.HEARTBEAT_FILE, {"at": _d(21).isoformat()})
        auth_json = json.dumps({"delegated": {"status": "valid", "has_refresh": True,
                                              "refresh_token_expires_at": "2027-09-26T00:00:00+08:00",
                                              "granted_scopes": ["kso.airpage.readwrite"]}})

        def runner(cmd, **kw):
            out = auth_json if "auth" in cmd else "cli: 0.3.6\n"
            return mock.Mock(returncode=0, stdout=out)

        exe = d / "wps365-cli"
        exe.write_text("#!/bin/sh\n")
        exe.chmod(0o755)
        st = ac.collect_status(d, cli_bin=str(exe), schedule_hour=20, runner=runner, now=_d(21))
        self.assertEqual(st["last_run"]["exit_code"], 0)
        self.assertEqual(st["last_success_at"], _d(20).isoformat(timespec="seconds"))
        self.assertEqual(st["cli"]["version"], "0.3.6")
        self.assertFalse(st["running"])
        self.assertEqual(st["next_run_at"], _d(20, day=27).isoformat(timespec="seconds"))
        self.assertEqual(st["health"]["level"], "ok")

    def test_stale_progress_of_dead_pid_is_not_running(self):
        d = Path(tempfile.mkdtemp())
        ac.write_json_atomic(d / ac.PROGRESS_FILE, {"running": True, "pid": 999999})
        st = ac.collect_status(d, cli_bin="/nonexistent", schedule_hour=20,
                               runner=mock.Mock(side_effect=FileNotFoundError), now=_d(21))
        self.assertFalse(st["running"])
        self.assertEqual(st["health"]["level"], "error")


class TestCancelAndWatchdog(unittest.TestCase):

    def tearDown(self):
        ac.CANCEL.clear()

    def test_watchdog_sets_cancel_and_calls_hard_exit_after_grace(self):
        exited = threading.Event()
        codes = []
        wd = ac.Watchdog(timeout=0.05, grace=0.05,
                         on_hard_exit=lambda c: (codes.append(c), exited.set()))
        wd.start()
        self.assertTrue(exited.wait(2))
        self.assertTrue(ac.CANCEL.is_set())
        self.assertTrue(wd.timed_out)
        self.assertEqual(codes, [ac.EXIT_TIMEOUT])

    def test_watchdog_cancelled_before_timeout(self):
        wd = ac.Watchdog(timeout=0.2, grace=0.05, on_hard_exit=lambda c: self.fail("should not exit"))
        wd.start()
        wd.stop()
        threading.Event().wait(0.4)
        self.assertFalse(ac.CANCEL.is_set())


class TestEngineHonoursCancel(unittest.TestCase):

    def tearDown(self):
        ac.CANCEL.clear()

    def test_download_worker_returns_immediately_when_cancelled(self):
        from wps_backup import engine
        from wps_backup.engine import AtomicCounter, BackupResult, RemoteFile
        eng = engine.BackupEngine.__new__(engine.BackupEngine)
        eng.state = mock.Mock()
        eng._result_lock = threading.Lock()
        ac.CANCEL.set()
        rf = RemoteFile("f", "d", "D", "a.docx", 1, 1, "", "0", "file")
        res = BackupResult()
        eng._download_worker(rf, 1, 1, res, AtomicCounter(), 0)
        eng.state.get_snapshot.assert_not_called()


class TestTestIsolation(unittest.TestCase):

    def test_tests_do_not_write_production_state_dir(self):
        from wps_backup import config
        prod = Path(__file__).resolve().parent.parent / "wps_backup_state"
        self.assertNotEqual(config.STATE_DIR.resolve(), prod.resolve())


if __name__ == "__main__":
    unittest.main()
