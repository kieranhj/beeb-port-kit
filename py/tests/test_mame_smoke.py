"""The template Lua harnesses through the runner, against a real MAME and 1942.

OPT-IN: set BEEB_KIT_MAME_SMOKE=1 (and MAME_DIR, if MAME is not where this machine
keeps it). Each case is a short MAME run, ~1-2 s at -nothrottle; the class refuses to
start if a MAME is already running. Output goes to a temporary directory. The 1942
addresses are passed as environment variables, as a project would pass its own, and
every expected value is a measurement already recorded in 1942-beeb's docs.
"""
import os
import tempfile
import unittest
from pathlib import Path

from tests import paths  # noqa: F401
from beeb_port_kit.mame import records, runner

MAME = Path(os.environ.get("MAME_DIR", r"C:\Users\khcon\OneDrive\Arcade\MAME"))
LUA = Path(__file__).resolve().parents[2] / "template" / "tools" / "mame"
ON = os.environ.get("BEEB_KIT_MAME_SMOKE") == "1" and (MAME / "roms" / "1942.zip").exists()


@unittest.skipUnless(ON, "opt-in: BEEB_KIT_MAME_SMOKE=1 with MAME and 1942.zip")
class Smoke1942(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if runner.already_running():
            raise unittest.SkipTest("a MAME is running; it would block these")
        cls.td = tempfile.TemporaryDirectory()

    @classmethod
    def tearDownClass(cls):
        cls.td.cleanup()

    def run_mame(self, name, script, **kw):
        out = os.path.join(self.td.name, name)
        runner.run(kw.pop("game", "1942"), out, script=str(LUA / script),
                   directory=str(MAME), timeout=kw.pop("timeout", 180),
                   log=lambda *a: None, **kw)
        return out

    def test_capture_with_hold_byte(self):
        # arcade-facts s28: holding ($E106) = 4 starts stage 5; ($E103) takes it at 638
        spec = "f:frame;g:bytes@e103,e106,e0d2,e0d3;obj:slots@e400,10,30,30"
        out = self.run_mame("cap", "capture_ram.lua", frames=700,
                            expects=["ram.bin", "schema.txt", "hold.txt"],
                            env={"CAPTURE_SPEC": spec, "MAME_PLUGINS": "hold_byte",
                                 "HOLD_ADDR": "e106", "HOLD_VALUE": "04",
                                 "HOLD_TAKEN_ADDR": "e103", "HOLD_TAKEN_VALUE": "04"})
        sch, path = records.load_capture(out, "ram.bin")
        recs = list(sch.read(path))
        self.assertEqual([recs[0]["f"], recs[-1]["f"]], [1, 700])
        self.assertEqual(next(r["f"] for r in recs if r["g"].at(0xE103) == 4), 638)

    def test_dips(self):
        # arcade-facts s34: DSWA $37, DSWB $DF under the hand-edited cfg
        out = self.run_mame("dips", "dips.lua", expects=["dips.txt"],
                            env={"DIPS_ADDRS": "c003-c004"})
        text = Path(out, "dips.txt").read_text()
        self.assertIn("ADDR $C003 = 37", text)
        self.assertIn("ADDR $C004 = DF", text)

    def test_force_fields_coin_and_start(self):
        spec = "f:frame;g:bytes@e000,e101"
        out = self.run_mame("coin", "capture_ram.lua", frames=400,
                            expects=["ram.bin", "force.txt"],
                            env={"CAPTURE_SPEC": spec, "MAME_PLUGINS": "force_input",
                                 "FORCE_FIELDS": "Coin 1@60-80;1 Player Start@150-170"})
        sch, path = records.load_capture(out, "ram.bin")
        recs = list(sch.read(path))
        # ($E000) bit 7 is "a game is on" (1942-beeb tools/mame/snd_ram.lua)
        self.assertFalse(recs[50]["g"].at(0xE000) & 0x80)
        self.assertTrue(recs[-1]["g"].at(0xE000) & 0x80)

    def test_invincible_patch_bookkeeping(self):
        out = self.run_mame("inv", "stop_at.lua", frames=60, expects=["patches.txt"],
                            env={"MAME_PLUGINS": "invincible",
                                 "INV_PATCHES": "2e8e:3aa5e0:3e0100,3396:3aa5e0:3e0100"})
        text = Path(out, "patches.txt").read_text()
        # 1942's two invincibility patches cancel each other's XOR and sum - which is
        # why they ran 400,000 frames past the ROM checksum (fullgame.lua)
        self.assertIn("XOR delta 00, sum delta 00", text.splitlines()[-1])

    def test_wrong_patch_is_refused(self):
        with self.assertRaises(runner.MameError) as e:
            self.run_mame("bad", "stop_at.lua", frames=60,
                          env={"MAME_PLUGINS": "invincible",
                               "INV_PATCHES": "2e8e:3aa5e1:3e0100"})
        self.assertIn("expected E1", str(e.exception))

    def test_lua_error_is_reported_not_hung(self):
        with self.assertRaises(runner.MameError) as e:
            self.run_mame("err", "capture_ram.lua", timeout=60, expects=["ram.bin"])
        self.assertIn("CAPTURE_SPEC is not set", str(e.exception))


if __name__ == "__main__":
    unittest.main()
