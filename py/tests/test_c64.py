import unittest

from tests import paths
from beeb_port_kit import c64


class Decode(unittest.TestCase):
    def test_multicolour_byte(self):
        # %10 11 00 01 -> 2, 3, 0, 1
        self.assertEqual(c64.multicolour_pixels(0b10110001), [2, 3, 0, 1])
        self.assertEqual(c64.c64_pixels(0xFF), [3, 3, 3, 3])
        self.assertEqual(c64.c64_pixels(0x40), [1, 0, 0, 0])

    def test_hires_byte(self):
        self.assertEqual(c64.hires_pixels(0x81), [1, 0, 0, 0, 0, 0, 0, 1])

    def test_sprite_block(self):
        block = bytes([0x80, 0x00, 0x01] + [0] * 60)
        rows = c64.decode_sprite(block)
        self.assertEqual(len(rows), 21)
        self.assertEqual(len(rows[0]), 24)
        self.assertEqual(rows[0][0], 1)
        self.assertEqual(rows[0][23], 1)
        self.assertEqual(sum(map(sum, rows)), 2)
        mc = c64.decode_sprite(block, multicolour=True)
        self.assertEqual(len(mc[0]), 12)
        self.assertEqual(mc[0], [2] + [0] * 10 + [1])

    def test_readers(self):
        dump = bytes(range(64)) * 3
        frames = c64.read_sprites(dump)
        self.assertEqual(len(frames), 3)
        self.assertEqual(len(frames[0]), 63)
        self.assertEqual(frames[1][0], 0)
        chars = c64.read_charset(bytes(range(256)) * 8, 256)
        self.assertEqual(len(chars), 256)
        self.assertEqual(chars[1], bytes(range(8, 16)))
        self.assertEqual(c64.decode_char(chars[1])[0], [0, 0, 0, 0, 1, 0, 0, 0])
        self.assertEqual(c64.decode_char(bytes([0x81]) * 8, multicolour=True)[3], [2, 0, 0, 1])
        tiles = c64.read_table(bytes(32), 16)
        self.assertEqual(len(tiles), 2)
        addr, body = c64.strip_load_address(b"\x00\x20abc")
        self.assertEqual((addr, body), (0x2000, b"abc"))
        with self.assertRaises(ValueError):
            c64.read_sprites(dump, 4)

    def test_pepto(self):
        self.assertEqual(len(c64.C64_RGB), 16)
        self.assertEqual(c64.C64_RGB[1], (255, 255, 255))
        self.assertEqual(c64.C64_RGB[6], (0x35, 0x28, 0x79))


ACME = """\
FRAMES = $07

col_decode  !byte $01, $02, $03    ; a comment, $ff
            !byte 4, FRAMES + 1
            ; a comment line
other_label !byte $ee
"""

TASS = """\
table:
        .BYTE $10, $20
        .byte 30
next:   .BYTE $ff
"""


class Tables(unittest.TestCase):
    def test_acme(self):
        self.assertEqual(c64.parse_c64_table(ACME, "col_decode"), [1, 2, 3, 4, 8])
        self.assertEqual(c64.parse_c64_table(ACME, "col_decode", 3), [1, 2, 3])
        with self.assertRaises(ValueError):
            c64.parse_c64_table(ACME, "col_decode", 9)
        with self.assertRaises(ValueError):
            c64.parse_c64_table(ACME, "missing")

    def test_tass(self):
        self.assertEqual(c64.parse_c64_table(TASS, "table"), [0x10, 0x20, 30])
        self.assertEqual(c64.parse_c64_table(TASS, "next"), [0xFF])

    def test_listing(self):
        lst = ("C000 01 02+     .BYTE $01, $02\n"
               "C000            .BYTE $03\n"          # continuation, same address
               "C003 A9 00      LDA #$00\n"
               "C005 FF         .BYTE 255\n")
        mem, filled = c64.parse_listing(lst)
        self.assertEqual(list(mem[0xC000:0xC006]), [1, 2, 3, 0, 0, 255])
        self.assertEqual(list(filled[0xC000:0xC006]), [1, 1, 1, 0, 0, 1])

    @unittest.skipUnless((paths.EDGE_TOOLS.parent / "source_c64" / "edge_grinder.asm").exists(),
                         "edge-beeb not present")
    def test_edge_source(self):
        src = paths.EDGE_TOOLS.parent / "source_c64" / "edge_grinder.asm"
        t = c64.parse_c64_table(str(src), "col_decode", 256)
        self.assertEqual(len(t), 256)
        self.assertTrue(all(0 <= v < 256 for v in t))


if __name__ == "__main__":
    unittest.main()
