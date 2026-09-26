"""
verify_fix.py 隔离性测试 — TDD

事故背景：verify_fix.check_state_logic() 直接使用生产 BackupState()，
把假记录（d1/f_spt、d1/f_pptx）写入真实 backup_state.json。
修复后应使用临时状态文件，生产状态保持字节级不变。
"""

import unittest

import verify_fix
from wps_backup import config


class TestVerifyFixIsolation(unittest.TestCase):

    def test_state_logic_check_does_not_pollute_production_state(self):
        state_file = config.STATE_FILE
        before = state_file.read_text(encoding="utf-8") if state_file.exists() else None

        self.assertTrue(verify_fix.check_state_logic())

        after = state_file.read_text(encoding="utf-8") if state_file.exists() else None
        self.assertEqual(before, after, "check_state_logic 不应修改生产 backup_state.json")
        if after:
            self.assertNotIn("f_spt", after)
            self.assertNotIn("f_pptx", after)


if __name__ == "__main__":
    unittest.main()
