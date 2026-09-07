import unittest

from tests import paths  # noqa: F401  (adds the package root to sys.path)
from beeb_port_kit.cpc import cpcscr, dsk


class Screens(unittest.TestCase):
    def test_byte_roundtrip(self):
        for mode, ppb in enumerate(cpcscr.PIXELS_PER_BYTE):
            for b in range(256):
                pens = cpcscr.decode_byte(b, mode)
                self.assertEqual(len(pens), ppb)
                self.assertEqual(cpcscr.encode_byte(pens, mode), b, (mode, b))

    def test_mode0_known(self):
        # pen 15 left, pen 0 right: bits 7,3,5,1 set
        self.assertEqual(cpcscr.encode_byte([15, 0], 0), 0xAA)
        self.assertEqual(cpcscr.decode_byte(0x55, 0), [0, 15])

    def test_colours(self):
        self.assertEqual(len(cpcscr.FIRMWARE_RGB), 27)
        self.assertEqual(cpcscr.ga_rgb(0x54), (0, 0, 0))        # GA &54 is black
        self.assertEqual(cpcscr.ga_rgb(0x4B), (255, 255, 255))  # &4B bright white

    def test_interleave(self):
        scr = bytearray(0x4000)
        scr[0x800 * 3 + 80 * 2 + 5] = 0xC0                     # line 19 (=2*8+3), byte 5
        rows = cpcscr.screen_pixels(bytes(scr), 2, lines=200)
        self.assertEqual(rows[19][40:42], [1, 1])
        self.assertEqual(sum(map(sum, rows)), 2)


class Amsdos(unittest.TestCase):
    def test_header(self):
        h = bytearray(128)
        h[18] = 2
        h[21:23] = (0x4000).to_bytes(2, "little")
        h[24:26] = (0x100).to_bytes(2, "little")
        h[26:28] = (0x4000).to_bytes(2, "little")
        s = sum(h[:67])
        h[67] = s & 0xFF
        h[68] = s >> 8
        data = bytes(h) + b"x" * 0x100
        self.assertEqual(dsk.amsdos_header(data), (2, 0x4000, 0x100, 0x4000))
        self.assertEqual(dsk.strip_amsdos(data), b"x" * 0x100)
        self.assertIsNone(dsk.amsdos_header(b"y" * 300))


if __name__ == "__main__":
    unittest.main()
