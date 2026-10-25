import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

from tests import paths  # noqa: F401
from beeb_port_kit import ay2sn
from beeb_port_kit.ay2sn import Converter, sn_atten

HAVE_NUMPY = importlib.util.find_spec("numpy") is not None
T1942 = Path(os.environ.get("T1942_BEEB", r"C:\Users\khcon\OneDrive\BEEB\Repos\1942-beeb"))
RIP = T1942 / "tools" / "output" / "snd" / "rip"

MIX_TONE_A = 0b111110          # tone A on; every other tone and all noise off
OFF = [0] * 7 + [0xFF] + [0] * 8


def regs(**kw):
    """An AY register file: a=(period, vol), b=..., c=..., mix=, noise=."""
    g = list(OFF)
    mix = 0xFF
    for ch, name in enumerate("abc"):
        if name in kw:
            p, v = kw[name]
            g[2 * ch], g[2 * ch + 1], g[8 + ch] = p & 0xFF, p >> 8, v
            mix &= ~(1 << ch)
    g[7] = kw.get("mix", mix) & 0xFF
    g[6] = kw.get("noise", 0)
    return g


class Rules(unittest.TestCase):
    def test_volume_table(self):
        self.assertEqual(sn_atten(15), 0)
        self.assertEqual(sn_atten(0), 15)
        self.assertEqual([sn_atten(v) for v in range(16)],
                         sorted([sn_atten(v) for v in range(16)], reverse=True))

    def test_periods_hand_computed(self):
        # N = P x SN / (2 AY)
        self.assertEqual(Converter(1_500_000).sn_period(300), 400)   # 1942: x 4/3
        self.assertEqual(Converter(1_500_000).sn_period(3), 4)
        self.assertEqual(Converter(2_000_000).sn_period(500), 500)   # x 1
        self.assertEqual(Converter(1_000_000).sn_period(100), 200)   # x 2
        c = Converter(1_773_400)                                     # a Spectrum 128's AY
        for p in (50, 213, 700):
            n = c.sn_period(p)
            self.assertLess(abs(c.sn_hz(n) - c.ay_hz(p)) / c.ay_hz(p), 0.01)

    def test_noise_rate_by_frequency(self):
        c = Converter(1_500_000)                # SN rates 7812.5, 3906.25, 1953.125 Hz
        self.assertEqual(c.noise_rate(12), 0)   # 7812.5 Hz exactly
        self.assertEqual(c.noise_rate(24), 1)   # 3906.25
        self.assertEqual(c.noise_rate(31), 1)   # 3024: nearer 3906 than 1953
        self.assertEqual(c.noise_rate(1), 0)
        self.assertEqual(Converter(1_000_000).noise_rate(31), 2)   # 2016 Hz


class Convert(unittest.TestCase):
    def one(self, *rows_per_field, **kw):
        c = Converter(1_500_000, irqs_per_field=1)
        return c.convert([list(r) for r in rows_per_field], **kw)

    def test_single_tone(self):
        st, stats = self.one([regs(a=(300, 15))])
        self.assertEqual(st, [[400, 0, 0, 15, 0, 15, -1, 15]])
        self.assertEqual(stats["chips"], [0])

    def test_bass_becomes_periodic_noise(self):
        # P 1000 -> N 1333 > 1023: tone 2 at round(1333 / 15), noise %011
        st, stats = self.one([regs(a=(1000, 15))])
        self.assertEqual(st[0][4:], [89, 15, 3, 0])
        self.assertEqual(st[0][0:2], [0, 15])
        self.assertEqual(stats["periodic"], 1)

    def test_drum_wins_and_the_bass_drops_an_octave(self):
        g = regs(a=(1000, 15), b=(100, 10), noise=12)
        g[7] &= ~(1 << 4)                     # noise on channel B as well
        st, stats = self.one([g])
        self.assertEqual(st[0][0:2], [666, 0])     # 1333 >> 1
        self.assertEqual(st[0][6], 4 | 0)          # white noise, rate 0
        self.assertEqual(stats["octave"], 1)

    def test_three_loudest_and_sticky(self):
        two = lambda va, vb, vc, vd: [regs(a=(100, va), b=(200, vb), c=(300, vc)),
                                      regs(a=(400, vd))]
        st, stats = self.one(two(15, 14, 13, 2), two(15, 14, 2, 13))
        self.assertEqual(stats["dropped"], 2)
        # field 0: A, B, C of chip 0 in slots 0-2
        self.assertEqual(st[0][0:6:2], [133, 267, 400])
        # field 1: chip 0's C drops out, chip 1's A takes ITS slot; A and B stay put
        self.assertEqual(st[1][0:6:2], [133, 267, 533])

    def test_tn_noise(self):
        g = regs(a=(300, 15))
        g[7] &= ~(1 << 3)                     # noise on channel A too
        self.assertEqual(self.one([g])[0][0][0:2], [400, 0])
        st, _ = self.one([g], tn_noise=True)
        self.assertEqual(st[0][0:2], [0, 15])
        self.assertEqual(st[0][6], 4 | 0)

    def test_fields_and_loop(self):
        c = Converter(1_500_000, irqs_per_field=4)
        rows = [[regs(a=(100 + i, 15))] for i in range(16)]
        f, lf = c.fields(rows)
        self.assertEqual([r[0][0] for r in f], [103, 107, 111, 115])
        f, lf = c.fields(rows, loop=(4, 8))
        self.assertEqual((len(f), lf), (3, 1))

    def test_atten_add(self):
        st, _ = self.one([regs(a=(300, 15))], atten_add=3)
        self.assertEqual(st[0][1], 3)
        self.assertEqual(st[0][3], 15)


@unittest.skipUnless((RIP / "sn11.json").exists(), "1942-beeb's rips not present")
class Against1942(unittest.TestCase):
    """Every command 1942-beeb converted, through the generic converter at 1942's
    clocks, against the sn*.json its own tools/ay2sn.py wrote."""

    def test_every_command(self):
        c = Converter(1_500_000)
        n = 0
        for p in sorted(RIP.glob("sn*.json")):
            cmd = p.stem[2:]
            with open(RIP / ("cmd%s.json" % cmd)) as f:
                rip = json.load(f)
            with open(p) as f:
                want = json.load(f)
            e = rip["end"]
            loop = (e["loop_start"] - 1, e["loop_len"]) if e["kind"] == "loop" else None
            rows = [[r["ay1"], r["ay2"]] for r in rip["rows"]]
            got, st = c.convert(rows, loop=loop)
            self.assertEqual(got, want["fields"], "command $%s" % cmd)
            self.assertEqual(st["loop"], want["stats"]["loop"], "command $%s" % cmd)
            n += 1
        self.assertGreater(n, 20)


@unittest.skipUnless(HAVE_NUMPY, "numpy absent")
class Render(unittest.TestCase):
    def test_render_and_wav(self):
        c = Converter(1_500_000)
        rows = [[regs(a=(300, 15))] for _ in range(40)]
        st, _ = c.convert(rows)
        sn = ay2sn.render_sn(st, c)
        ay = ay2sn.render_ay(rows, c)
        self.assertEqual(len(sn), 10 * 882)
        self.assertAlmostEqual(len(ay), len(sn), delta=2)
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "x.wav")
            ay2sn.write_wav(path, sn)
            self.assertEqual(os.path.getsize(path), 44 + 2 * len(sn))


if __name__ == "__main__":
    unittest.main()
