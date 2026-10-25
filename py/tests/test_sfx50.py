"""beeb_port_kit.sfx50: the ramp fitter for lib/sfx50.6502."""
import json
import tempfile
import unittest
from pathlib import Path

from tests import paths
from beeb_port_kit import sfx50

DATA = Path(__file__).resolve().parent / "data"


def tone_writes(ch, periods, amps):
    """MOS-style chip writes, one field (two ticks) per (period, amplitude): latch + data byte
    for the period, an attenuation latch for the amplitude, all on the odd tick."""
    w = []
    for f, (p, a) in enumerate(zip(periods, amps)):
        t = 2 * f + 1
        w += [[t, 0x80 | ch << 5 | (p & 15)], [t, (p >> 4) & 63], [t, 0x90 | ch << 5 | (15 - a)]]
    return w


class Channels(unittest.TestCase):
    def test_sound_to_chip(self):
        # SOUND 0 is the noise (chip 3); SOUND 1-3 are tones 2-0; &10 (flush) bits ignored
        self.assertEqual([sfx50.chip_channel(c) for c in (0, 1, 2, 3, 0x10, 0x13)], [3, 2, 1, 0, 3, 0])


class Fit(unittest.TestCase):
    def test_one_linear_sweep_is_one_ramp(self):
        periods = [200 + 5 * k for k in range(20)]
        amps = [15 - k // 2 for k in range(20)]
        s, rs = sfx50.fit(tone_writes(1, periods, amps), 1)
        self.assertEqual(len(s), 20)
        self.assertEqual(len(rs), 1)
        n, p, dp, a, dv = rs[0]
        self.assertEqual((n, p, dp, a), (20, 200, 5, 15))
        for (pp, aa), (q, b) in zip(sfx50.play(rs), s):
            self.assertLessEqual(abs(pp - q), 2)
            self.assertLessEqual(abs(aa - b), 1)

    def test_a_jump_splits_the_ramp(self):
        periods = [100] * 8 + [400] * 8
        s, rs = sfx50.fit(tone_writes(0, periods, [12] * 16), 0)
        self.assertEqual([r[0] for r in rs], [8, 8])
        self.assertEqual([r[1] for r in rs], [100, 400])

    def test_silence_ends_the_effect(self):
        s, rs = sfx50.fit(tone_writes(2, [300] * 10, [10] * 6 + [0] * 4), 2)
        self.assertEqual(len(s), 6)

    def test_bytes_and_play_agree(self):
        rs = [(3, 0x1C2, 14, 4, -12)]
        self.assertEqual(sfx50.ramp_bytes(rs), bytes([3, 0xC2, 0x01, 14, 0x48, 244, 0]))
        self.assertEqual(sfx50.play(rs), [(450, 4), (464, 3), (478, 3)])

    def test_pad_end(self):
        w = tone_writes(1, [200 + 5 * k for k in range(20)], [12] * 20)
        _, rs = sfx50.fit(w, 1)
        _, padded = sfx50.fit(w, 1, pad_end=True)
        self.assertEqual(padded[-1][0], rs[-1][0] + 1)
        self.assertEqual(sfx50.play(padded)[:-1], sfx50.play(rs))
        long = [(255, 100, 1, 10, 0)]
        self.assertEqual(len(sfx50.play(long + [(1, 355, 0, 10, 0)])), 256)

    def test_amplitude_clamps_as_the_driver(self):
        # a negative step past 0 stops at 0; a positive one past &FF becomes &F8 (15)
        self.assertEqual([a for _, a in sfx50.play([(4, 0, 0, 1, -16)])], [1, 0, 0, 0])
        self.assertEqual([a for _, a in sfx50.play([(3, 0, 0, 15, 16)])], [15, 15, 15])


class StrykersSample(unittest.TestCase):
    """Two effects of Stryker's Run's capture, vendored (tests/data), against the ramps its
    generated src/sfx_data.6502 has for them."""
    def test_sample(self):
        eff = sfx50.load(DATA / "sfx50_capture_sample.json")
        got = {name: sfx50.ramp_bytes(sfx50.fit(w, ch)[1]) for name, ch, _, w in eff}
        self.assertEqual(got["00"], bytes([17, 0x07, 0x00, 0, 0xF8, 0, 0]))
        self.assertEqual(got["20"], bytes([15, 0xB8, 0x00, 6, 0xF8, 253,
                                           16, 0x1B, 0x01, 10, 0xC8, 249,
                                           5, 0xC2, 0x01, 14, 0x48, 244, 0]))


@unittest.skipUnless((paths.STRYKERS / "tools" / "sfx-mos320.json").exists(), "Stryker's Run not on this machine")
class StrykersWhole(unittest.TestCase):
    """The whole capture: every line of every effect, and the tables, as Stryker's Run's own
    tools/sfx50.py wrote them into src/sfx_data.6502 (padded since 2026-10-25, its BUGS #18)."""
    def test_reproduces_sfx_data(self):
        eff = sfx50.load(paths.STRYKERS / "tools" / "sfx-mos320.json", DATA / "sfx50_strykers_effects.json")
        text, size = sfx50.render(eff, "sfx-mos320.json", "sfx_data.6502", pad_end=True)
        self.assertEqual(size, 158)
        want = (paths.STRYKERS / "src" / "sfx_data.6502").read_text().splitlines()
        got = text.splitlines()

        def body(lines):
            i = next(k for k, l in enumerate(lines) if l.startswith(".sfx_effect_00"))
            j = next(k for k, l in enumerate(lines) if l.startswith((".sfx_effect_channel", "IF GAMEPLAY")))
            return lines[i:j]
        self.assertEqual(body(got), body(want))
        tables = [l for l in want if l.startswith("    EQUB") and ("sfx_effect_" in l or l.count(",") == 7)
                  and "_40" not in l]
        for l in tables[-3:]:
            self.assertIn(l, got)


if __name__ == "__main__":
    unittest.main()
