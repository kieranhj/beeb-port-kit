import random
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests import paths
from beeb_port_kit import zx0


def structured(n, seed=1):
    r = random.Random(seed)
    out = bytearray()
    while len(out) < n:
        k = r.random()
        if k < 0.4 and len(out) > 8:                    # a copy from earlier
            off = r.randint(1, min(len(out), 300))
            ln = r.randint(2, 40)
            for _ in range(ln):
                out.append(out[-off])
        elif k < 0.7:                                   # a run
            out += bytes([r.randrange(256)]) * r.randint(1, 60)
        else:                                           # literals
            out += bytes(r.randrange(256) for _ in range(r.randint(1, 20)))
    return bytes(out[:n])


class RoundTrip(unittest.TestCase):
    def test_random(self):
        r = random.Random(7)
        for n in (1, 2, 17, 300, 1500):
            data = bytes(r.randrange(256) for _ in range(n))
            self.assertEqual(zx0.decompress(zx0.compress(data)), data)

    def test_structured(self):
        for n in (64, 1000, 4000):
            data = structured(n)
            z = zx0.compress(data)
            self.assertLess(len(z), n, "structured data should shrink")
            self.assertEqual(zx0.decompress(z), data)

    def test_all_same(self):
        data = b"\x00" * 3000
        z = zx0.compress(data)
        self.assertLess(len(z), 20)
        self.assertEqual(zx0.decompress(z), data)

    @unittest.skipUnless(paths.ZX0_EXE.exists(), "reference zx0.exe not present")
    def test_matches_reference_exe(self):
        data = structured(3000, seed=3) + bytes(range(256)) * 2
        with tempfile.TemporaryDirectory() as td:
            src, dst = Path(td) / "in.bin", Path(td) / "out.zx0"
            src.write_bytes(data)
            subprocess.run([str(paths.ZX0_EXE), "-f", str(src), str(dst)],
                           check=True, capture_output=True)
            ref = dst.read_bytes()
        self.assertEqual(zx0.decompress(ref), data)
        self.assertEqual(zx0.compress(data), ref, "python stream differs from zx0.exe's")


if __name__ == "__main__":
    unittest.main()
