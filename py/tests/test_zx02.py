import random
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests import paths
from beeb_port_kit import zx02
from tests.test_zx0 import structured


class RoundTrip(unittest.TestCase):
    def test_random(self):
        r = random.Random(7)
        for n in (1, 2, 17, 300, 1500):
            data = bytes(r.randrange(256) for _ in range(n))
            self.assertEqual(zx02.decompress(zx02.compress(data)), data)

    def test_structured(self):
        for n in (64, 1000, 4000):
            data = structured(n)
            z = zx02.compress(data)
            self.assertLess(len(z), n, "structured data should shrink")
            self.assertEqual(zx02.decompress(z), data)

    def test_all_same(self):
        # ZX02's gamma is 8-bit, so a 3000-byte run costs a few more matches
        # than ZX0's does. Still tiny; this is the case where ZX0 wins.
        data = b"\x00" * 3000
        z = zx02.compress(data)
        self.assertLess(len(z), 40)
        self.assertEqual(zx02.decompress(z), data)

    def test_long_match_lengths(self):
        # lengths either side of the 8-bit wrap (256 encodes as 0)
        for ln in (254, 255, 256, 257, 512):
            data = bytes(range(64)) + bytes(range(64)) * (ln // 64 + 2)
            self.assertEqual(zx02.decompress(zx02.compress(data)), data)

    @unittest.skipUnless(paths.ZX02_EXE.exists(), "reference zx02.exe not present")
    def test_matches_reference_exe(self):
        data = structured(3000, seed=3) + bytes(range(256)) * 2
        with tempfile.TemporaryDirectory() as td:
            src, dst = Path(td) / "in.bin", Path(td) / "out.zx02"
            src.write_bytes(data)
            subprocess.run([str(paths.ZX02_EXE), "-f", str(src), str(dst)],
                           check=True, capture_output=True)
            ref = dst.read_bytes()
        mine = zx02.compress(data)
        self.assertEqual(zx02.decompress(ref), data)
        # The released v2 exe pads a trailing 0 on some inputs where zx02.py
        # stops one byte earlier; both streams decode to the same bytes and
        # the depacker stops at the end marker either way. Anything else is a
        # format disagreement and must fail.
        self.assertIn(ref, (mine, mine + b"\x00"),
                      "python stream differs from zx02.exe's by more than the pad")


if __name__ == "__main__":
    unittest.main()
