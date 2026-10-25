import os
import tempfile
import time
import unittest

from tests import paths  # noqa: F401
from beeb_port_kit.mame import runner

CFG = """<?xml version="1.0"?>
<mameconfig version="10">
    <system name="1942">
        <input>
            <port tag=":DSWA" type="DIPSWITCH" mask="192" defvalue="64" value="0" />
            <port tag=":DSWB" type="DIPSWITCH" mask="96" defvalue="96" value="64" />
            <port tag=":DSWB" type="DIPSWITCH" mask="16" defvalue="16" value="16" />
            <port tag=":P1" type="P1_JOYSTICK_RIGHT" mask="1" defvalue="1">
                <newseq type="standard">KEYCODE_X</newseq>
            </port>
        </input>
    </system>
</mameconfig>
"""


class Command(unittest.TestCase):
    def test_headless_defaults(self):
        cmd = runner.build_command("mame", "1942", script="x/cap.lua", playback="k.inp")
        self.assertEqual(cmd[:3], ["mame", "1942", "-skip_gameinfo"])
        for flag in ("-nothrottle", "-autoboot_script", "-playback"):
            self.assertIn(flag, cmd)
        self.assertEqual(cmd[cmd.index("-video") + 1], "none")
        self.assertEqual(cmd[cmd.index("-sound") + 1], "none")
        self.assertTrue(os.path.isabs(cmd[cmd.index("-autoboot_script") + 1]))
        self.assertNotIn("\\", cmd[cmd.index("-autoboot_script") + 1])

    def test_video_for_snapshots(self):
        self.assertNotIn("-video", runner.build_command("mame", "g", script="s.lua",
                                                        video=True))

    def test_debug_never_with_debugger_none(self):
        cmd = runner.build_command("mame", "g", debugscript="cmds.txt")
        self.assertIn("-debug", cmd)
        self.assertNotIn("-debugger", cmd)
        with self.assertRaises(runner.MameError):
            runner.build_command("mame", "g", debugscript="c.txt",
                                 extra=["-debugger", "none"])

    def test_record(self):
        cmd = runner.build_command("mame", "g", script="s.lua", record="mine.inp")
        self.assertEqual(cmd[cmd.index("-record") + 1], "mine.inp")


class Outputs(unittest.TestCase):
    def test_absent_stale_fresh(self):
        with tempfile.TemporaryDirectory() as td:
            old = os.path.join(td, "old.bin")
            open(old, "wb").close()
            past = time.time() - 3600
            os.utime(old, (past, past))
            started = time.time()
            open(os.path.join(td, "new.bin"), "wb").close()
            bad = dict(runner.check_outputs(td, ["old.bin", "new.bin", "gone.bin"], started))
            self.assertIn("STALE", bad["old.bin"])
            self.assertEqual(bad["gone.bin"], "absent")
            self.assertNotIn("new.bin", bad)


class Cfg(unittest.TestCase):
    def test_overrides(self):
        with tempfile.TemporaryDirectory() as td:
            os.makedirs(os.path.join(td, "cfg"))
            with open(os.path.join(td, "cfg", "1942.cfg"), "w") as f:
                f.write(CFG)
            ov = runner.cfg_overrides(td, "1942")
            # 1942-beeb arcade-facts s34: five lives and EASY, set by hand
            self.assertEqual(ov, [(":DSWA", "DIPSWITCH", 0xC0, 0x40, 0x00),
                                  (":DSWB", "DIPSWITCH", 0x60, 0x60, 0x40)])
            self.assertEqual(runner.cfg_overrides(td, "1943"), [])


class Refusals(unittest.TestCase):
    def test_nothing_to_run(self):
        with self.assertRaises(runner.MameError):
            runner.run("1942", "out")

    def test_no_mame_dir(self):
        old = os.environ.pop("MAME_DIR", None)
        try:
            with self.assertRaises(runner.MameError):
                runner.mame_dir(None)
        finally:
            if old is not None:
                os.environ["MAME_DIR"] = old


if __name__ == "__main__":
    unittest.main()
