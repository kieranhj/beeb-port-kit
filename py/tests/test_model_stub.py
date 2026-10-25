"""dfs.model_stub: the !BOOT that runs the game on a Master and prints a
message anywhere else. Stepped in py65 (skipped without it) with OSBYTE 0
answering each model, and checked byte for byte against the 1942 port's
make_disc.model_stub, which shipped v1.0 (skipped without that repository).
lib/test/model_stub_test.mjs boots the same bytes on jsbeeb."""
import importlib.util
import unittest

from tests import paths
from beeb_port_kit import dfs

try:
    from py65.devices.mpu6502 import MPU
except ImportError:             # pragma: no cover
    MPU = None

OSBYTE, OSASCI = 0xFFF4, 0xFFE3


def run_stub(data, org, os_answer, max_steps=200_000):
    """Run the stub with OSBYTE 0 answering `os_answer`. Returns (where it
    ended: 'rts' or the jump target, the text printed, memory)."""
    mpu = MPU()
    mem = mpu.memory
    mem[org:org + len(data)] = list(data)
    mpu.sp = 0xF0
    mem[0x1F1], mem[0x1F2] = 0xFF, 0xFF     # the RTS to BASIC lands at &0000: a sentinel
    mpu.pc = org
    printed = bytearray()
    for _ in range(max_steps):
        pc = mpu.pc
        if pc in (OSBYTE, OSASCI):
            if pc == OSBYTE:
                assert (mpu.a, mpu.x, mpu.y) == (0, 1, 0xFF), "OSBYTE 0 with X = 1"
                mpu.x = os_answer
            else:
                printed.append(mpu.a)
            lo, hi = mem[mpu.sp + 1 & 0x1FF | 0x100], mem[mpu.sp + 2 & 0x1FF | 0x100]
            mpu.sp = (mpu.sp + 2) & 0xFF
            mpu.pc = ((hi << 8 | lo) + 1) & 0xFFFF
            continue
        if pc == 0x0000:
            return "rts", bytes(printed), mem
        if pc == 0x1234:
            return 0x1234, bytes(printed), mem
        mpu.step()
    raise AssertionError("the stub never finished")


@unittest.skipIf(MPU is None, "py65 not installed")
class Stepped(unittest.TestCase):
    image = bytes((i * 7 + 3) & 0xFF for i in range(1000))      # 3 pages and a part

    def build(self, **kw):
        return dfs.model_stub(self.image, 0x0E00, 0x1234, **kw)

    def test_master_and_compact_copy_and_jump(self):
        data, load, ex = self.build()
        self.assertEqual((load, ex), (dfs.STUB_ORG, dfs.STUB_ORG))
        for os_answer in (3, 5):
            end, printed, mem = run_stub(data, load, os_answer)
            self.assertEqual(end, 0x1234)
            self.assertEqual(printed, b"")
            self.assertEqual(bytes(mem[0x0E00:0x0E00 + len(self.image)]), self.image)

    def test_other_models_print_and_return(self):
        data, load, _ = self.build(text="No Master\nhere")
        for os_answer in (0, 1, 2, 4):
            end, printed, mem = run_stub(data, load, os_answer)
            self.assertEqual(end, "rts")
            self.assertEqual(printed, b"No Master\rhere\r")
            self.assertEqual(bytes(mem[0x0E00:0x0E00 + 16]), bytes(16))

    def test_accept_and_whole_pages(self):
        img = bytes(range(256)) * 2                     # rem = 0: the BEQ go path
        data, load, _ = dfs.model_stub(img, 0x1900, 0x1234, accept=(2,), org=0x6000)
        end, _, mem = run_stub(data, load, 2)
        self.assertEqual(end, 0x1234)
        self.assertEqual(bytes(mem[0x1900:0x1B00]), img)
        self.assertEqual(run_stub(data, load, 3)[0], "rts")

    def test_refusals(self):
        with self.assertRaises(dfs.DiscError):      # a B's DFS workspace
            self.build(org=0x1000)
        with self.assertRaises(dfs.DiscError):      # into MODE 7's screen
            dfs.model_stub(bytes(12000), 0x0E00, 0x1234)
        with self.assertRaises(dfs.DiscError):      # the copy runs over the stub
            dfs.model_stub(bytes(0x2000), 0x4000, 0x4000)
        with self.assertRaises(dfs.DiscError):      # above, but over the image still to copy
            dfs.model_stub(bytes(0x400), dfs.STUB_ORG + 0x100, 0x1234)
        with self.assertRaises(dfs.DiscError):
            self.build(text="x" * 300)
        with self.assertRaises(dfs.DiscError):
            self.build(accept=())


class Against1942(unittest.TestCase):
    """The bytes 1942 v1.0 shipped, from the same arguments."""

    def test_identical(self):
        path = paths.T1942_TOOLS / "make_disc.py"
        if not path.exists():
            self.skipTest("1942-beeb not found (T1942_BEEB)")
        spec = importlib.util.spec_from_file_location("make_disc_1942", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        image = bytes((i * 13 + 1) & 0xFF for i in range(0x1E00))
        theirs = mod.model_stub(image, 0x0E00, 0x0E42)
        ours = dfs.model_stub(image, 0x0E00, 0x0E42,
                              text=mod.STUB_TEXT.rstrip(b"\0"), org=mod.STUB_ORG, zp=mod.STUB_ZP)
        self.assertEqual(ours, theirs)


if __name__ == "__main__":
    unittest.main()
