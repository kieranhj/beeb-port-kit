import importlib.util
import json
import os
import unittest
import zipfile
from pathlib import Path

from tests import paths  # noqa: F401
from beeb_port_kit.mame import z80sub

HAVE_Z80 = importlib.util.find_spec("z80") is not None
T1942 = Path(os.environ.get("T1942_BEEB", r"C:\Users\khcon\OneDrive\BEEB\Repos\1942-beeb"))
MAME = Path(os.environ.get("MAME_DIR", r"C:\Users\khcon\OneDrive\Arcade\MAME"))
ZIP1942 = MAME / "roms" / "1942.zip"
RIP = T1942 / "tools" / "output" / "snd" / "rip"

BOOT = bytes([0xF3,                    # 0000 di
              0x31, 0x00, 0xF0,        # 0001 ld sp,$F000
              0xED, 0x56,              # 0004 im 1
              0xFB,                    # 0006 ei
              0x18, 0xFE])             # 0007 jr $0007
SHORT = bytes([0xF5,                   # 0038 push af
               0x3A, 0x00, 0x60,       # 0039 ld a,($6000)    the latch, MMIO read
               0x32, 0x01, 0x80,       # 003C ld ($8001),a    a chip port, MMIO write
               0x21, 0x00, 0x40,       # 003F ld hl,$4000
               0x34,                   # 0042 inc (hl)        counts IRQs, like 1942's
               0xF1, 0xFB, 0xC9])      # 0043 pop af : ei : ret
LONG = bytes([0x21, 0x00, 0x40,        # 0038 ld hl,$4000
              0x34,                    # 003B inc (hl)
              0x0E, 0x08,              # 003C ld c,8
              0x06, 0x00,              # 003E ld b,0
              0x10, 0xFE,              # 0040 djnz $0040      ~3,300 T a pass
              0x0D,                    # 0042 dec c
              0x20, 0xF9,              # 0043 jr nz,$003E     8 passes: > one period
              0xFB, 0xC9])             # 0045 ei : ret


def rom(handler):
    img = bytearray(0x100)
    img[0:len(BOOT)] = BOOT
    img[0x38:0x38 + len(handler)] = handler
    return bytes(img)


def idle(c):
    return c.pc == 0x0007 and c.iff1


@unittest.skipUnless(HAVE_Z80, "the z80 package is not installed (pip install z80)")
class Synthetic(unittest.TestCase):
    def make(self, handler, latch):
        port = []
        cpu = z80sub.SubCPU([(0, rom(handler))], clock=3_000_000, irq_hz=240,
                            reads={0x6000: lambda a: latch[0]},
                            writes={0x8001: lambda a, v: port.append(v)})
        cpu.boot(1000, until=idle)
        return cpu, port

    def test_held_irq_and_mmio(self):
        latch = [0x11]
        cpu, port = self.make(SHORT, latch)
        self.assertEqual(cpu.ticks_per_irq, 12500)
        for i in range(10):
            if i == 5:
                latch[0] = 0x22
            cpu.step()
        self.assertEqual(cpu.m.memory[0x4000], 10)
        self.assertEqual(port, [0x11] * 5 + [0x22] * 5)
        self.assertEqual(cpu.merged, 0)
        self.assertEqual(cpu.m.memory[0x8001], 0x22)     # stored as well

    def test_long_handler_merges_assertions(self):
        cpu, _ = self.make(LONG, [0])
        for _ in range(12):
            cpu.step()
        # each handler outlasts its period, so some assertions are lost whole -
        # counted, not silently folded into the next period
        self.assertGreater(cpu.merged, 0)
        self.assertEqual(cpu.irq, 12)

    def test_boot_that_does_not_idle_raises(self):
        cpu = z80sub.SubCPU([(0, rom(SHORT))], 3_000_000, 240)
        with self.assertRaises(RuntimeError):
            cpu.boot(1000, until=lambda c: c.pc == 0x1234)

    def test_clone_is_independent_and_identical(self):
        cpu, _ = self.make(SHORT, [3])
        for _ in range(5):
            cpu.step()
        twin = cpu.clone()
        for _ in range(5):
            cpu.step()
            twin.step()
        self.assertEqual(cpu.ram(0x4000, 0x4010), twin.ram(0x4000, 0x4010))
        twin.m.memory[0x4000] = 0xEE
        self.assertNotEqual(cpu.m.memory[0x4000], 0xEE)

    def test_disassemble(self):
        img = rom(SHORT)
        lines = z80sub.disassemble(lambda a: img[a] if a < len(img) else 0, 0, 5)
        self.assertEqual([a for a, _, _ in lines], [0, 1, 4, 6, 7])
        self.assertEqual(lines[2][1], b"\xED\x56")
        self.assertIn("im", lines[2][2].lower())

    def test_ay_ports(self):
        irq = [0]
        ay = z80sub.AYPorts(lambda: irq[0])
        ay.sel(0, 7)
        ay.data(1, 0x3E)
        irq[0] = 2
        ay.sel(0, 20)              # no such register: logged, not stored
        ay.data(1, 1)
        self.assertEqual(ay.regs[7], 0x3E)
        self.assertEqual(ay.log, [(0, 7, 0x3E), (2, 20, 1)])


@unittest.skipUnless(HAVE_Z80 and ZIP1942.exists() and (RIP / "cmd11.json").exists(),
                     "z80, 1942.zip or 1942-beeb's rips not present")
class Against1942(unittest.TestCase):
    """1942's sound CPU on the generic SubCPU, against the rip 1942-beeb's own
    sound_rip.py made (which probe_sound.py scored against MAME at 0 wrong)."""

    def rip(self, cmd, limit):
        with zipfile.ZipFile(ZIP1942) as z:
            image = z.read("sr-01.c11")
        latch, cpu_irq = [0], [0]
        ay = [z80sub.AYPorts(lambda: cpu_irq[0]), z80sub.AYPorts(lambda: cpu_irq[0])]
        cpu = z80sub.SubCPU([(0, image)], clock=3_000_000, irq_hz=240,
                            reads={0x6000: lambda a: latch[0]},
                            writes={0x8000: ay[0].sel, 0x8001: ay[0].data,
                                    0xC000: ay[1].sel, 0xC001: ay[1].data})
        cpu.boot(2_000_000, until=lambda c: c.pc in (0x64, 0x65) and c.iff1)
        with open(RIP / ("cmd%02X.json" % cmd)) as f:
            rip = json.load(f)
        latch[0] = cmd
        rows = rip["rows"][:limit]
        cpu.lates = []
        for i, row in enumerate(rows):
            cpu.lates.append(cpu.step())
            cpu_irq[0] = cpu.irq
            self.assertEqual(ay[0].regs[:14], row["ay1"], "$%02X AY1 after IRQ %d" % (cmd, i + 1))
            self.assertEqual(ay[1].regs[:14], row["ay2"], "$%02X AY2 after IRQ %d" % (cmd, i + 1))
        return cpu, len(rows)

    def test_gun_register_for_register(self):
        cpu, n = self.rip(0x05, 10000)
        self.assertEqual(n, 154)

    def test_stage_music_register_for_register(self):
        # $11 holds interrupts off for up to 3,067 T on 905 of its first 2,400 IRQs
        # (measured 2026-10-25): the lateness accounting is what keeps it in step
        cpu, n = self.rip(0x11, 2400)
        self.assertEqual(n, 2400)
        self.assertGreater(max(cpu.lates), 3000)

    def test_name_entry_merges_an_assertion(self):
        # $17 loses one IRQ assertion WHOLE in its first 2,400 (measured 2026-10-25)
        cpu, n = self.rip(0x17, 2400)
        self.assertGreater(cpu.merged, 0)


if __name__ == "__main__":
    unittest.main()
