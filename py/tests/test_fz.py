"""template/tools/fz.py: the FZ codec round trip, its window and max_len limits, and the
in-place gap proved by decoding in one buffer. Synthetic data only."""
import importlib.util
import random
import unittest
from pathlib import Path

from tests import paths  # noqa: F401

TOOLS = Path(__file__).resolve().parents[2] / "template" / "tools"
spec = importlib.util.spec_from_file_location("fz", TOOLS / "fz.py")
fz = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fz)


def synth(n, seed):
    r = random.Random(seed)
    vocab = [bytes(r.randrange(256) for _ in range(r.randrange(3, 12))) for _ in range(30)]
    out = bytearray()
    while len(out) < n:
        k = r.randrange(10)
        if k < 7:
            out += r.choice(vocab)
        elif k < 9:
            out += bytes(r.randrange(256) for _ in range(r.randrange(1, 200)))
        else:
            out += bytes([r.randrange(256)]) * r.randrange(2, 300)
    return bytes(out[:n])


def offsets_and_lengths(z):
    p, res = 0, []
    while z[p] != fz.END:
        t = z[p]
        if t < 0x80:
            res.append(("L", t + 1, None))
            p += t + 2
        elif t < 0xC0:
            res.append(("N", (t & 0x3F) + 2, z[p + 1] + 1))
            p += 2
        else:
            res.append(("F", (t & 0x3F) + 3, (z[p + 1] | z[p + 2] << 8) + 1))
            p += 3
    return res


class FZ(unittest.TestCase):
    def test_round_trip(self):
        for seed, n in ((1, 0), (2, 1), (3, 5000), (4, 20000)):
            d = synth(n, seed)
            z = fz.compress(d)
            self.assertEqual(fz.decompress(z), d)
            self.assertEqual(z[-1], fz.END)
        self.assertLess(len(fz.compress(bytes(4096))), 4096 // 60 * 2 + 4)

    def test_window_and_max_len(self):
        d = synth(12000, 5)
        z = fz.compress(d, window=1024, max_len=40)
        self.assertEqual(fz.decompress(z), d)
        for kind, length, off in offsets_and_lengths(z):
            self.assertLessEqual(length, 40)
            if off is not None:
                self.assertLessEqual(off, 1024)
        z = fz.compress(d, max_len=200)            # literals still stop at 128
        self.assertEqual(fz.decompress(z), d)

    def test_in_place(self):
        for seed in range(6, 12):
            d = synth(3000 + 500 * seed, seed)
            z = fz.compress(d)
            g = fz.in_place_gap(z, len(d))
            self.assertTrue(fz.in_place_check(z, d, g), seed)

    def test_estimate_tracks_tokens(self):
        d = synth(4000, 13)
        z = fz.compress(d)
        t = fz.tokens(z)
        self.assertEqual(sum(x[1] for x in t), len(d))
        self.assertGreater(fz.est_cycles(z, len(d)), 18 * len(d))


if __name__ == "__main__":
    unittest.main()
