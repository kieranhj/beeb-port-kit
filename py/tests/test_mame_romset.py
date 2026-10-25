import os
import sys
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path

from tests import paths  # noqa: F401
from beeb_port_kit.mame import romset
from beeb_port_kit.mame.romset import GfxLayout, rgn_frac

T1942 = Path(os.environ.get("T1942_BEEB", r"C:\Users\khcon\OneDrive\BEEB\Repos\1942-beeb"))
MAME = Path(os.environ.get("MAME_DIR", r"C:\Users\khcon\OneDrive\Arcade\MAME"))
ZIP1942 = MAME / "roms" / "1942.zip"

# A cut of `mame -listxml 1942` (0.177): names, sizes, CRCs and attributes - facts
# about the set, no ROM data.
LISTXML = """<?xml version="1.0"?>
<mame build="0.177">
 <machine name="1942" sourcefile="1942.cpp">
  <description>1942 (Revision B)</description>
  <rom name="srb-03.m3" size="16384" crc="d9dafcc3" region="maincpu" offset="0"/>
  <rom name="srb-04.m4" size="16384" crc="da0cf924" region="maincpu" offset="4000"/>
  <rom name="srb-05.m5" size="16384" crc="d102911c" region="maincpu" offset="10000"/>
  <rom name="srb-06.m6" size="8192" crc="466f8248" region="maincpu" offset="14000"/>
  <rom name="srb-07.m7" size="16384" crc="0d31038c" region="maincpu" offset="18000"/>
  <rom name="sr-01.c11" size="16384" crc="bd87f06b" region="audiocpu" offset="0"/>
  <chip type="cpu" tag="maincpu" name="Z80" clock="4000000"/>
  <chip type="cpu" tag="audiocpu" name="Z80" clock="3000000"/>
  <chip type="audio" tag="ay1" name="AY-3-8910A" clock="1500000"/>
  <display tag="screen" type="raster" rotate="270" width="256" height="224" refresh="60.000000" />
  <dipswitch name="Difficulty" tag="DSWB" mask="96">
   <dipvalue name="Very Difficult" value="0"/>
   <dipvalue name="Difficult" value="32"/>
   <dipvalue name="Easy" value="64"/>
   <dipvalue name="Normal" value="96" default="yes"/>
  </dipswitch>
 </machine>
</mame>"""


def zip_of(path, files):
    with zipfile.ZipFile(path, "w") as z:
        for n, d in files.items():
            z.writestr(n, d)


class ListXml(unittest.TestCase):
    def test_parse(self):
        m = romset.parse_listxml(LISTXML, "1942")
        self.assertEqual([r.name for r in m.roms][:2], ["srb-03.m3", "srb-04.m4"])
        self.assertEqual(m.roms[2].offset, 0x10000)        # offsets are HEX in listxml
        self.assertEqual(m.cpu("maincpu")["clock"], 4_000_000)
        self.assertEqual(m.cpu("audiocpu")["clock"], 3_000_000)
        self.assertEqual(m.displays[0]["rotate"], "270")
        d = m.dipswitches[0]
        self.assertEqual((d["tag"], d["mask"], d["default"]), ("DSWB", 0x60, 0x60))
        self.assertEqual(d["values"][0x40], "Easy")

    def test_unknown_machine(self):
        with self.assertRaises(romset.RomError):
            romset.parse_listxml(LISTXML, "1943")


class Set(unittest.TestCase):
    def test_check_region_and_errors(self):
        a, b = bytes(range(256)) * 4, b"\x55" * 512
        roms = [romset.RomInfo("a.bin", 1024, "%08x" % zlib.crc32(a), "cpu", 0),
                romset.RomInfo("b.bin", 512, None, "cpu", 0x800)]
        with tempfile.TemporaryDirectory() as td:
            z = os.path.join(td, "g.zip")
            zip_of(z, {"a.bin": a, "b.bin": b})
            rs = romset.RomSet([z], roms)
            reg = rs.region("cpu", fill=0xEE)
            self.assertEqual(len(reg), 0xA00)
            self.assertEqual(reg[:1024], a)
            self.assertEqual(reg[0x400:0x800], b"\xEE" * 0x400)
            self.assertEqual(reg[0x800:], b)
            # wrong size, wrong CRC, missing - all named in one error
            zip_of(z, {"a.bin": a[:-1], "c.bin": b})
            with self.assertRaises(romset.RomError) as e:
                romset.RomSet([z], roms)
            self.assertIn("a.bin is 1023 bytes", str(e.exception))
            self.assertIn("a.bin CRC", str(e.exception))
            self.assertIn("b.bin missing", str(e.exception))

    def test_clone_reads_parent_zip(self):
        with tempfile.TemporaryDirectory() as td:
            clone, parent = os.path.join(td, "c.zip"), os.path.join(td, "p.zip")
            zip_of(clone, {"own.bin": b"\x01" * 16})
            zip_of(parent, {"shared.bin": b"\x02" * 16})
            rs = romset.RomSet([clone, parent], romset.rom_list([("own.bin", 16),
                                                                  ("shared.bin", 16)]))
            self.assertEqual(rs["shared.bin"], b"\x02" * 16)

    def test_banked(self):
        lo, b0, b1 = b"\x10" * 0x8000, b"\xB0" * 0x4000, b"\xB1" * 0x2000
        m = romset.Banked({0: lo}, [b0, b1])
        self.assertEqual(m.read(0x1234), 0x10)
        self.assertEqual(m.read(0x8000, 0), 0xB0)
        self.assertEqual(m.read(0x9FFF, 1), 0xB1)
        self.assertEqual(m.read(0xA000, 1), 0xFF)   # 8K bank in a 16K window
        with self.assertRaises(romset.RomError):
            m.read(0xE000)                          # RAM is not ROM
        self.assertEqual(m.fetcher(1)(0x8001), 0xB1)


class Layout(unittest.TestCase):
    def test_planes_are_msb_first(self):
        # 8x1, 2bpp, plane offsets {0, 8}: byte 0 is the HIGH plane (BUGS.md #2)
        lay = GfxLayout(8, 1, planes=[0, 8], xoffs=list(range(8)), yoffs=[0], inc=16)
        self.assertEqual(lay.decode(bytes([0b10100000, 0b11000000]), 0),
                         [[3, 1, 2, 0, 0, 0, 0, 0]])
        # the bit-reversed reading would give 3, 2, 1: the shape is the same, which is
        # why a render does not catch it
        self.assertEqual(lay.decode(bytes([0, 0, 0xFF, 0x00]), 1), [[2] * 8])

    def test_rgn_frac_and_count(self):
        self.assertEqual(rgn_frac(1, 3, 0xC000), 0xC000 * 8 // 3)
        n = 0xC000
        tile = GfxLayout(16, 16, [rgn_frac(i, 3, n) for i in range(3)],
                         list(range(8)) + [128 + i for i in range(8)],
                         [8 * i for i in range(16)], 256)
        self.assertEqual(tile.count(bytes(n)), 512)     # 1942: 512 tiles


class Palette(unittest.TestCase):
    def test_weighted_and_lookup(self):
        w = (0x0E, 0x1F, 0x43, 0x8F)                     # 1942's, from MAME
        self.assertEqual(romset.weighted(0, w), 0)
        self.assertEqual(romset.weighted(15, w), 0xFF)  # 0x0E+0x1F+0x43+0x8F = 0xFF
        self.assertEqual(romset.weighted(0b0101, w), 0x0E + 0x43)
        pal = romset.prom_palette([15, 0], [0, 15], [1, 2], w)
        self.assertEqual(pal, [(0xFF, 0, 0x0E), (0, 0xFF, 0x1F)])
        lut = bytes(range(16)) * 4
        self.assertEqual(romset.lookup(lut, 2, 3, pens=4, base=0x80), 0x80 | 11)
        self.assertEqual(romset.lookup(lut, 0x42, 3, pens=4, set_mask=0x3F), 11)


@unittest.skipUnless(ZIP1942.exists() and (T1942 / "tools" / "arcade.py").exists(),
                     "1942.zip or 1942-beeb not present")
class Against1942(unittest.TestCase):
    """The generic decoder, given 1942's gfx_layouts as DATA, against 1942-beeb's
    hand-written decoders (scored there at 97.74% against a real frame)."""

    @classmethod
    def setUpClass(cls):
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(T1942 / "tools"))
        try:
            import arcade
        finally:
            sys.path.pop(0)
        cls.ref = arcade.Roms(str(ZIP1942))
        cls.arcade = arcade

    def test_three_layouts(self):
        a, ref = self.arcade, self.ref
        char = GfxLayout(8, 8, [4, 0], [0, 1, 2, 3, 8, 9, 10, 11],
                         [16 * i for i in range(8)], 128)
        tn = len(ref.tiles)
        tile = GfxLayout(16, 16, [rgn_frac(0, 3, tn), rgn_frac(1, 3, tn), rgn_frac(2, 3, tn)],
                         list(range(8)) + [128 + i for i in range(8)],
                         [8 * i for i in range(16)], 256)
        sn = len(ref.sprites)
        half = rgn_frac(1, 2, sn)
        spr = GfxLayout(16, 16, [half + 4, half, 4, 0], list(a.Roms.XS),
                        [16 * i for i in range(16)], 512)
        for n in range(0, 512, 7):
            self.assertEqual(char.decode(ref.chars, n), ref.char(n), "char %d" % n)
            self.assertEqual(tile.decode(ref.tiles, n), ref.tile(n), "tile %d" % n)
            self.assertEqual(spr.decode(ref.sprites, n), ref.sprite(n), "sprite %d" % n)
        self.assertEqual(spr.count(ref.sprites), 512)

    def test_palette_and_listxml_set(self):
        ref = self.ref
        w = (0x0E, 0x1F, 0x43, 0x8F)
        pal = romset.prom_palette(ref.files["sb-5.e8"], ref.files["sb-6.e9"],
                                  ref.files["sb-7.e10"], w)
        self.assertEqual(pal, ref.palette)
        for cs in range(32):
            for pen in range(8):
                i = romset.lookup(ref.tilelut, cs, pen, pens=8, base=(2 << 4), set_mask=0x1F)
                self.assertEqual(pal[i], ref.tile_rgb(cs, pen, bank=2))
        m = romset.parse_listxml(LISTXML, "1942")
        rs = romset.RomSet([str(ZIP1942)], m.roms)       # names, sizes AND CRCs
        cpu = rs.region("maincpu", fill=0xFF)
        self.assertEqual(len(cpu), 0x1C000)              # 112K, arcade-facts s7
        banked = romset.Banked({0: cpu[:0x8000]},
                               [cpu[0x10000:0x14000], cpu[0x14000:0x16000],
                                cpu[0x18000:0x1C000]])
        self.assertEqual(banked.read(0x0000), 0xF3)      # di: the reset vector
        self.assertEqual(banked.read(0xA000, 1), 0xFF)   # srb-06 is 8K: reads $FF above


if __name__ == "__main__":
    unittest.main()
