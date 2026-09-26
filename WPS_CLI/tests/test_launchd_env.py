"""
launchd 运行环境测试 — TDD

Bug（2026-07-28/29 起）：launchd 的默认 PATH 为 /usr/bin:/bin:/usr/sbin:/sbin，
不含 ~/.local/bin，config.CLI_BIN = "wps365-cli" 为裸命令名，
定时任务报 "No such file or directory: 'wps365-cli'"，整条备份链路静默失效。
另：/usr/local/bin/wps365-cli 是旧版 v0.1.0（命令名不同），不能优先于 ~/.local/bin。
"""

import importlib
import os
import plistlib
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from wps_backup import config


def _make_exe(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


class TestResolveCliBin(unittest.TestCase):

    def setUp(self):
        self.home = Path(tempfile.mkdtemp())

    def test_env_override_wins(self):
        with mock.patch.dict(os.environ, {"WPS365_CLI_BIN": "/opt/x/wps365-cli"}):
            self.assertEqual(
                config.resolve_cli_bin("wps365-cli", "WPS365_CLI_BIN", home=self.home),
                "/opt/x/wps365-cli")

    def test_local_bin_preferred_over_path(self):
        """~/.local/bin 必须优先于 PATH 中的 /usr/local/bin 旧版"""
        _make_exe(self.home / ".local/bin/wps365-cli")
        other = Path(tempfile.mkdtemp())
        _make_exe(other / "wps365-cli")
        with mock.patch.dict(os.environ, {"PATH": str(other)}, clear=False):
            os.environ.pop("WPS365_CLI_BIN", None)
            self.assertEqual(
                config.resolve_cli_bin("wps365-cli", "WPS365_CLI_BIN", home=self.home),
                str(self.home / ".local/bin/wps365-cli"))

    def test_minimal_launchd_path_still_resolves_absolute(self):
        """launchd 最小 PATH 下仍解析为绝对路径"""
        _make_exe(self.home / ".local/bin/wps365-cli")
        with mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}):
            os.environ.pop("WPS365_CLI_BIN", None)
            resolved = config.resolve_cli_bin("wps365-cli", "WPS365_CLI_BIN", home=self.home)
        self.assertTrue(os.path.isabs(resolved))

    def test_fallback_to_bare_name_when_not_found(self):
        with mock.patch.dict(os.environ, {"PATH": "/nonexistent"}):
            os.environ.pop("WPS365_CLI_BIN", None)
            self.assertEqual(
                config.resolve_cli_bin("wps365-cli", "WPS365_CLI_BIN", home=self.home),
                "wps365-cli")

    def test_module_constants_are_absolute_on_this_machine(self):
        """本机 ~/.local/bin 已安装两个 CLI 时，config 常量必须是绝对路径"""
        importlib.reload(config)
        for name, val in (("wps365-cli", config.CLI_BIN), ("kdocs-cli", config.KDOCS_CLI_BIN)):
            if (Path.home() / ".local/bin" / name).exists():
                self.assertEqual(val, str(Path.home() / ".local/bin" / name))


class TestPlistEnvironment(unittest.TestCase):

    def test_plist_sets_path_with_local_bin_first(self):
        from wps_backup import scheduler
        out = Path(tempfile.mkdtemp()) / "com.wps.backup.plist"
        with mock.patch("builtins.print"):
            scheduler.generate_launchd_plist("/x/wps_backup.py", str(out))
        with open(out, "rb") as f:
            pl = plistlib.load(f)
        path = pl["EnvironmentVariables"]["PATH"].split(":")
        self.assertEqual(path[0], str(Path.home() / ".local/bin"))
        self.assertIn("/usr/bin", path)
        self.assertEqual(pl["EnvironmentVariables"]["HOME"], str(Path.home()))


class TestCliMissingBinary(unittest.TestCase):

    def test_engine_cli_missing_binary_returns_none(self):
        """二进制缺失时 _cli 返回 None 并记录清晰错误，而不是抛出 FileNotFoundError"""
        from wps_backup import engine
        with mock.patch.object(config, "CLI_BIN", "/nonexistent/wps365-cli"), \
             self.assertLogs("wps_backup", level="ERROR") as cm:
            self.assertIsNone(engine._cli("drive", "list", retries=0))
        self.assertTrue(any("wps365-cli" in m for m in cm.output))

    def test_otl_cli_missing_binary_returns_none(self):
        from wps_backup import otl_engine
        with mock.patch.object(config, "CLI_BIN", "/nonexistent/wps365-cli"), \
             self.assertLogs("wps_backup", level="ERROR"):
            self.assertIsNone(otl_engine._cli("drive", "list", retries=0))


if __name__ == "__main__":
    unittest.main()
