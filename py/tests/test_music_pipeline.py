"""template/tools/music_extract.py -> music_convert.py -> music_pack.py, end to end, on a
SYNTHETIC AY log made here (no original's music is in the kit): a bass line that changes
channel part-way through tune 1, an arpeggio, drums and a long noise bed, an envelope used as
a timbre, two tunes ended by silencing frames. Each step runs as its command line does."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests import paths  # noqa: F401

HAVE_NUMPY = importlib.util.find_spec("numpy") is not None
TOOLS = Path(__file__).resolve().parents[2] / "template" / "tools"


def load(name):
    spec = importlib.util.spec_from_file_location(name, TOOLS / (name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def jload(p):
    return json.loads(Path(p).read_text())


def jdump(x, p):
    Path(p).write_text(json.dumps(x))


def synth_rows():
    """[(field, regs R0-R12)] a player-like frame a field, and the silences"""
    out, field = [], 0
    arp = [180, 143, 120]                       # C: a major arpeggio, a note a field
    bass = [900, 800, 700, 600]                 # under the SN's floor at 1 MHz (N = 2P > 1023)
    for tune, n in ((1, 360), (2, 240)):
        for i in range(n):
            g = [0] * 13
            mix = 0b111000                      # tones on, noise off
            if tune == 1 and i < 200:           # bass on A, a lead on B
                a, b = bass[(i // 8) % 4], 250 + (i % 32)
            else:                               # B has the bass, A the lead
                a, b = 250 + (i % 32), bass[(i // 8) % 4]
            g[0:2], g[2:4], g[4:6] = [a & 255, a >> 8], [b & 255, b >> 8], \
                [arp[i % 3] & 255, arp[i % 3] >> 8]
            g[8], g[9], g[10] = 13, 12, 9
            drum = i % 16 < 2 or 100 <= i < 112 # a hit every 16 fields; a 12-field bed
            if drum:
                mix &= ~(1 << 5)                # noise on C
                g[6] = 6 if i < 100 or i >= 112 else 20
            if tune == 2 and 40 <= i < 80:      # B through the envelope, as a timbre
                g[9] = 0x10
                g[11], g[12] = (b // 32) & 255, 0
            g[7] = mix
            out.append((field, g))
            field += 1
        out.append((field, [0] * 13))           # the silencing frame
        field += 21                             # 20 fields of nothing
    return out


def write_ay5(path):
    with open(path, "w") as f:
        f.write("# field line T reg value\n")
        for k, (field, g) in enumerate(synth_rows()):
            if k == 0:
                f.write(f"{field} 2 0 13 12\n")
            for r, v in enumerate(g):
                f.write(f"{field} 2 {8 * r} {r} {v}\n")


def run(*args):
    p = subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True)
    if p.returncode:
        raise AssertionError(p.stdout + p.stderr)
    return p.stdout


@unittest.skipUnless(HAVE_NUMPY, "numpy not installed")
class Pipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import numpy as np
        cls.np = np
        cls.tmp = tempfile.TemporaryDirectory()
        d = cls.d = Path(cls.tmp.name)
        write_ay5(d / "ay.log")
        cls.extract_out = run(TOOLS / "music_extract.py", d / "ay.log", d, "--music-time")
        cls.tunes = jload(d / "tunes.json")
        t2 = cls.tunes[1]["row"]
        cfg = {"ay_clock": 1_000_000, "drum_max": 4,
               "bass_sections": [[0, 0], [200, 1], [t2, 1]],
               "pack": {"cuts": {"1": [150]}, "bank": 600}}
        jdump(cfg, d / "cfg.json")
        cls.report = run(TOOLS / "music_convert.py", d, "--config", d / "cfg.json",
                         "--report-bass", "--window", "50")
        cls.convert_out = run(TOOLS / "music_convert.py", d, "--config", d / "cfg.json",
                              "--seconds", "4")
        cls.seq_out = run(TOOLS / "music_pack.py", d, "--seq", d / "data", "--config",
                          d / "cfg.json")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_extract_finds_the_tunes(self):
        self.assertEqual([(t["row"], t["rows"]) for t in self.tunes], [(0, 361), (381, 241)])
        rows = self.np.load(self.d / "ay_fields.npy")
        self.assertEqual(rows.shape, (622, 14))
        self.assertEqual(int(rows[0][13]), 12)
        self.assertTrue((rows[361:381] == 0).all())

    def test_report_finds_the_hand_over(self):
        line = [x for x in self.report.splitlines() if x.startswith("suggested")][0]
        secs = json.loads(line.split(":", 1)[1])
        self.assertEqual(secs, [[0, 0], [200, 1], [381, 1]])

    def test_convert(self):
        sn = self.np.load(self.d / "sn_fields.npy")
        self.assertEqual(sn.shape, (622, 8))
        info = jload(self.d / "convert.json")["tunes"]
        self.assertEqual([s["bass"] for s in info[0]["sections"]], [0, 1])
        st = info[0]["sections"][0]["stats"]
        self.assertGreater(st["periodic"], 0)
        self.assertGreater(st["bass_cut"], 0)       # the drum hits
        self.assertGreater(st["drum_cut"], 0)       # the 12-field bed handed back
        self.assertTrue((self.d / "ay.wav").exists() and (self.d / "sn.wav").exists())
        # the envelope channel became a tone at full volume (attenuation 0)
        self.assertEqual(int(sn[381 + 50][7]), 0)   # B is the bass there: periodic noise

    def test_pack_chunks_and_decodes(self):
        mp = load("music_pack")
        sn = self.np.load(self.d / "sn_fields.npy")
        hdr = (self.d / "data" / "music_seq.6502").read_text()
        names = [x.split("_SIZE")[0].lower() for x in hdr.splitlines() if "_SIZE" in x]
        self.assertEqual(names[:2], ["tune1a", "tune1b"])
        for t in self.tunes:
            parts = sorted((self.d / "data").glob(f"tune{t['tune']}*.bin"))
            data = b"".join(p.read_bytes() for p in parts)
            self.assertTrue(all(len(p.read_bytes()) <= 600 for p in parts))
            n, _ = mp.decode(data, sn, t["row"])
            self.assertEqual(n, t["rows"])
        # tune 1 cut at row 150 exactly
        first = mp.records((self.d / "data" / "tune1a.bin").read_bytes())
        self.assertLessEqual(len(first), 150)
        rows = jload(self.d / "sn_rows.json")["rows"]
        self.assertEqual(len(rows), 622)
        self.assertTrue(all(r == [] for r in rows[361:381]))

    def test_decode_catches_a_wrong_byte(self):
        mp = load("music_pack")
        sn = self.np.load(self.d / "sn_fields.npy")
        data = bytearray((self.d / "data" / "tune2.bin").read_bytes()
                         if (self.d / "data" / "tune2.bin").exists()
                         else (self.d / "data" / "tune2a.bin").read_bytes())
        data[2] ^= 1                                # an attenuation or tone in record 0
        with self.assertRaises(AssertionError):
            mp.decode(bytes(data), sn, self.tunes[1]["row"])

    def test_silent_build(self):
        cfg = {"tunes": self.tunes, "pack": {"cuts": {"1": [150]}, "bank": 600}}
        jdump(cfg, self.d / "silent.json")
        run(TOOLS / "music_pack.py", "--silent", self.d / "silent", "--config",
            self.d / "silent.json")
        a = (self.d / "silent" / "tune1a.bin").read_bytes()
        self.assertEqual(a, bytes(150))

    def test_tunes_report(self):
        out = run(TOOLS / "music_pack.py", self.d, "--tunes")
        self.assertIn("tune 2", out)
        self.assertTrue((self.d / "whole.bin").exists())

    def test_single_stream(self):
        out = run(TOOLS / "music_pack.py", self.d, self.d / "one.bin", "--max", "1000")
        self.assertIn("decodes back", out)
        self.assertLessEqual(len((self.d / "one.bin").read_bytes()), 1000)


class EnvelopeShapes(unittest.TestCase):
    @unittest.skipUnless(HAVE_NUMPY, "numpy not installed")
    def test_shapes(self):
        import numpy as np
        mc = load("music_convert")
        s = np.arange(48)
        saw = mc.env_level(12, s)                   # /|/|
        self.assertEqual(list(saw[:17]), list(range(16)) + [0])
        tri = mc.env_level(14, s)                   # /\/\
        self.assertEqual(list(tri[15:18]), [15, 15, 14])
        self.assertEqual(list(mc.env_level(9, s)[14:18]), [1, 0, 0, 0])     # \___
        self.assertEqual(list(mc.env_level(13, s)[30:34]), [15, 15, 15, 15])  # /~~~
        self.assertEqual(list(mc.env_level(11, s)[16:18]), [15, 15])         # \~~~


if __name__ == "__main__":
    unittest.main()
