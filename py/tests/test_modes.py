import importlib.util
import itertools
import random
import unittest

from tests import paths
from beeb_port_kit import modes


class PackUnpack(unittest.TestCase):
    def test_identity_every_mode(self):
        for mode, (P, B) in modes.MODE_INFO.items():
            for b in range(256):
                self.assertEqual(modes.pack_byte(modes.unpack_byte(b, mode), mode), b, mode)
            for pixels in itertools.product(range(1 << B), repeat=P):
                self.assertEqual(tuple(modes.unpack_byte(modes.pack_byte(pixels, mode), mode)),
                                 pixels, (mode, pixels))

    def test_documented_bit_positions(self):
        # MODE 1 pixel n: high bit at 7-n, low bit at 3-n (Paradroid)
        self.assertEqual(modes.mode1_byte([3, 0, 0, 0]), 0x88)
        self.assertEqual(modes.mode1_byte([0, 0, 0, 1]), 0x01)
        self.assertEqual(modes.unpack_mode1(0x88), [3, 0, 0, 0])
        # MODE 2 left pixel bits 7,5,3,1; right pixel 6,4,2,0 (Edge)
        self.assertEqual(modes.mode2_byte(15, 0), 0xAA)
        self.assertEqual(modes.mode2_byte(0, 15), 0x55)
        self.assertEqual(modes.mode2_byte(1, 8), 0x02 | 0x40)
        self.assertEqual(modes.mode2_unpack(0xAA), (15, 0))
        # MODE 0/4: bit 7 leftmost
        self.assertEqual(modes.pack_byte([1, 0, 0, 0, 0, 0, 0, 1], 0), 0x81)

    def test_out_of_range(self):
        with self.assertRaises(ValueError):
            modes.pack_byte([4, 0, 0, 0], 1)
        with self.assertRaises(ValueError):
            modes.pack_byte([0, 0, 0], 1)


class Dither(unittest.TestCase):
    def test_exact_colours(self):
        for c, rgb in enumerate(modes.BBC_RGB):
            self.assertEqual(modes.dither_pair(rgb), (c, c))

    def test_ordered_dark_first(self):
        for rgb in [(128, 128, 128), (128, 0, 0), (255, 128, 0), (0, 128, 255)]:
            a, b = modes.dither_pair(rgb)
            self.assertLessEqual(modes.BBC_LUMA[a], modes.BBC_LUMA[b])

    @unittest.skipUnless((paths.EDGE_TOOLS / "bbc.py").exists(), "edge-beeb not present")
    def test_matches_edge_bbc_py(self):
        spec = importlib.util.spec_from_file_location("edge_bbc", paths.EDGE_TOOLS / "bbc.py")
        edge = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(edge)
        from beeb_port_kit.cpc import cpcscr
        for rgb in cpcscr.FIRMWARE_RGB:                  # the 27 CPC colours
            self.assertEqual(modes.dither_pair(rgb), edge.dither_pair(rgb), rgb)
        self.assertEqual(modes.BBC_RGB, edge.BBC_RGB)
        self.assertEqual(modes.BBC_LUMA, edge.BBC_LUMA)
        for b in range(256):
            self.assertEqual(modes.mode2_unpack(b), edge.mode2_unpack(b))
            left, right = edge.mode2_unpack(b)
            self.assertEqual(modes.mode2_byte(left, right), edge.mode2_byte(left, right))

    @unittest.skipUnless((paths.PARADROID_TOOLS / "verify_bbc.py").exists(),
                         "paradroid not present")
    def test_matches_paradroid_unpack_mode1(self):
        src = (paths.PARADROID_TOOLS / "verify_bbc.py").read_text(encoding="latin-1")
        # lift the one function rather than import a script with side effects
        start = src.index("def unpack_mode1")
        end = src.index("\ndef ", start + 1)
        ns = {}
        exec(src[start:end], ns)
        for b in range(256):
            self.assertEqual(modes.unpack_mode1(b), ns["unpack_mode1"](b))


class Render(unittest.TestCase):
    def test_render_unrender_identity(self):
        r = random.Random(2)
        distinct = [(i * 17, 255 - i * 17, i) for i in range(16)]  # no aliasing
        for mode in modes.MODE_INFO:
            data = bytes(r.randrange(256) for _ in range(5 * 2 * 8))   # 5 cells, 2 rows
            im = modes.render(data, mode, 5, 2, palette=distinct)
            P = modes.pixels_per_byte(mode)
            sx, sy = modes.default_scale(mode)
            self.assertEqual(im.size, (5 * P * sx, 16 * sy))
            self.assertEqual(modes.unrender(im, mode, 5, 2, palette=distinct), data, mode)
        # and under the MOS default MODE 2 palette the fold is to 0-7
        data = bytes(r.randrange(256) for _ in range(16))
        back = modes.unrender(modes.render(data, 2, 2, 1), 2, 2, 1)
        for a, b in zip(data, back):
            self.assertEqual([c & 7 for c in modes.unpack_byte(a, 2)], modes.unpack_byte(b, 2))

    def test_render_1to1_and_custom_palette(self):
        data = bytes([modes.mode2_byte(3, 12)] * 8)
        pal = [(i, i, i) for i in range(16)]
        im = modes.render(data, 2, 1, 1, palette=pal, scale=(1, 1))
        self.assertEqual(im.size, (2, 8))
        self.assertEqual(im.getpixel((0, 0)), (3, 3, 3))
        self.assertEqual(im.getpixel((1, 7)), (12, 12, 12))
        self.assertEqual(modes.unrender(im, 2, 1, 1, palette=pal, scale=(1, 1)), data)

    def test_unrender_refuses_bad_pixels(self):
        from PIL import Image
        im = Image.new("RGB", (4, 8), (0, 0, 0))
        im.putpixel((0, 0), (255, 0, 0))            # half a 2:1 pixel
        with self.assertRaises(ValueError):
            modes.unrender(im, 2, 1, 1)
        im.putpixel((1, 0), (255, 0, 0))            # whole, but off-palette next
        im.putpixel((2, 3), (1, 2, 3))
        im.putpixel((3, 3), (1, 2, 3))
        with self.assertRaises(ValueError):
            modes.unrender(im, 2, 1, 1)


if __name__ == "__main__":
    unittest.main()
