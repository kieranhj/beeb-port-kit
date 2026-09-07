import os
import random
import tempfile
import unittest

from PIL import Image

from tests import paths  # noqa: F401  (adds the package root to sys.path)
from beeb_port_kit import modes
from beeb_port_kit.art import Sheet, ArtError, palette, sheets, guide


class Sheets(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.dir = self.td.name

    def tearDown(self):
        self.td.cleanup()

    def cells(self, sheet, seed=1):
        r = random.Random(seed)
        pool = sorted(sheet.allowed) if sheet.allowed else list(range(16))
        return [[[r.choice(pool) for _ in range(sheet.cell_w)] for _ in range(sheet.cell_h)]
                for _ in range(sheet.count)]

    def test_roundtrip_2to1_chars(self):
        sheet = Sheet(4, 8, 16, 16, path=os.path.join(self.dir, "chars.png"))
        pal = palette.seed(2)
        cells = self.cells(sheet)
        # under the seed palette 8-15 alias 0-7, so what comes back is the
        # lowest index: compare after folding
        sheets.write(sheet, cells, pal)
        back = sheets.read(sheet, pal=pal)
        fold = [[[c & 7 for c in row] for row in cell] for cell in cells]
        self.assertEqual(back, fold)
        with Image.open(sheet.path) as im:
            self.assertEqual(im.size, (128, 128))

    def test_roundtrip_exact_with_distinct_palette(self):
        pal = [(i * 16, 255 - i * 16, (i * 37) & 255) for i in range(16)]
        sheet = Sheet(12, 21, 8, 16, transparent=True, allowed=range(1, 16),
                      count=119, path=os.path.join(self.dir, "sprites.png"))
        cells = self.cells(sheet)
        cells[5] = None                                    # not drawn yet
        cells[6][0][0] = 0                                 # transparent pixel
        sheets.write(sheet, cells, pal)
        back = sheets.read(sheet, pal=pal)
        self.assertEqual(back, cells)
        self.assertIsNone(back[5])
        merged = sheets.merge(back, [[[7] * 12] * 21] * 119, log=None)
        self.assertEqual(merged[5], [[7] * 12] * 21)

    def test_roundtrip_1to1_mode1(self):
        pal = modes.default_palette(1)
        sheet = Sheet(8, 8, 8, 4, scale=(1, 1), mode=1,
                      path=os.path.join(self.dir, "m1.png"))
        r = random.Random(3)
        cells = [[[r.randrange(4) for _ in range(8)] for _ in range(8)] for _ in range(32)]
        sheets.write(sheet, cells, pal)
        with Image.open(sheet.path) as im:
            self.assertEqual(im.size, (64, 32))
        self.assertEqual(sheets.read(sheet, pal=pal), cells)
        packed = sheets.pack_cell(cells[0], mode=1)
        self.assertEqual(len(packed), 16)
        self.assertEqual(sheets.unpack_cell(packed, 8, 8, mode=1), cells[0])

    def test_pack_cell_mode2(self):
        cell = [[1, 2, 3, 4]] * 8
        packed = sheets.pack_cell(cell)
        self.assertEqual(packed, bytes([modes.mode2_byte(1, 2)] * 8
                                       + [modes.mode2_byte(3, 4)] * 8))
        self.assertEqual(sheets.unpack_cell(packed, 4, 8), cell)

    def test_refuses_half_width_pixel(self):
        sheet = Sheet(4, 8, 2, 1, path=os.path.join(self.dir, "bad.png"))
        pal = palette.seed(2)
        sheets.write(sheet, [[[1] * 4] * 8] * 2, pal)
        with Image.open(sheet.path) as src:
            im = src.convert("RGB")
        im.putpixel((9, 3), (0, 255, 0))           # cell 1, fat pixel 0, its right half
        im.save(sheet.path)
        with self.assertRaises(ArtError) as cm:
            sheets.read(sheet, pal=pal)
        self.assertIn("cell 1 pixel (0,3)", str(cm.exception))
        self.assertIn("not one colour", str(cm.exception))
        cells, errors = sheets.read(sheet, pal=pal, strict=False)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0][1:4], (1, 0, 3))

    def test_refuses_off_palette_and_disallowed(self):
        pal = palette.seed(2)
        sheet = Sheet(4, 8, 1, 1, allowed=(0, 12, 14, 15),
                      path=os.path.join(self.dir, "t.png"))
        sheets.write(sheet, [[[15] * 4] * 8], pal)
        with Image.open(sheet.path) as src:
            im = src.convert("RGB")
        for x in (0, 1):
            im.putpixel((x, 0), (255, 0, 0))       # red: entry 1, not allowed here
        for x in (2, 3):
            im.putpixel((x, 0), (1, 2, 3))         # not in the palette at all
        im.save(sheet.path)
        _, errors = sheets.read(sheet, pal=pal, strict=False)
        msgs = [e[4] for e in errors]
        self.assertTrue(any("may not use" in m for m in msgs), msgs)
        self.assertTrue(any("not in the palette" in m for m in msgs), msgs)

    def test_transparency_key_illegal_on_opaque_sheet(self):
        pal = palette.seed(2)
        sheet = Sheet(4, 8, 1, 1, path=os.path.join(self.dir, "o.png"))
        Image.new("RGB", sheet.size, sheet.key_transparent).save(sheet.path)
        with self.assertRaises(ArtError):
            sheets.read(sheet, pal=pal)

    def test_refuses_guide_layer(self):
        # a translucent file is a guide layer, never a sheet (guide.py)
        sheet = Sheet(4, 8, 1, 1, path=os.path.join(self.dir, 'g.png'))
        Image.new('RGBA', sheet.size, (0, 0, 0, 0)).save(sheet.path)
        with self.assertRaises(ArtError) as cm:
            sheets.read(sheet)
        self.assertIn('guide layer', str(cm.exception))
        Image.new('RGBA', sheet.size, (0, 0, 0, 255)).save(sheet.path)   # opaque RGBA is fine
        self.assertEqual(sheets.read(sheet), [[[0] * 4] * 8])

    def test_wrong_size(self):
        sheet = Sheet(4, 8, 1, 1, path=os.path.join(self.dir, "s.png"))
        Image.new("RGB", (8, 9)).save(sheet.path)
        with self.assertRaises(ArtError):
            sheets.read(sheet)


class Palettes(unittest.TestCase):
    def test_save_load_and_reserved(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "pal.png")
            pal = palette.seed(2)
            palette.save(pal, p)
            self.assertEqual(palette.load(p), pal)
            bad = list(pal)
            bad[3] = palette.KEY_FALLBACK
            palette.save(bad, p)
            with self.assertRaises(palette.PaletteError):
                palette.load(p)
            # a custom key set moves the goalposts
            self.assertEqual(palette.load(p, keys=palette.reserved(key_fallback=(1, 1, 1))), bad)

    def test_lookup_lowest_wins(self):
        pal = palette.seed(2)
        self.assertEqual(palette.lookup(pal)[(0, 0, 0)], 0)
        self.assertEqual(palette.lookup(pal, range(1, 16))[(0, 0, 0)], 8)
        self.assertEqual(palette.lookup(pal, (0, 12, 14, 15))[(255, 255, 255)], 15)

    def test_fe21_and_nula(self):
        pal = palette.seed(2)
        b = palette.to_fe21(pal)
        self.assertEqual(len(b), 16)
        self.assertEqual(b[0], 0x07)               # logical 0 -> black (0 ^ 7)
        self.assertEqual(b[7], 0x70)               # logical 7 -> white
        self.assertEqual(b[8], 0x87)               # logical 8 -> black again
        n = palette.to_nula(pal)
        self.assertEqual(len(n), 32)
        self.assertEqual(n[2:4], bytes([0x1F, 0x00]))   # entry 1 red: [1<<4|15], [0<<4|0]
        with self.assertRaises(palette.PaletteError):
            palette.to_fe21([(1, 2, 3)] * 16)
        self.assertIn("GIMP Palette", palette.gpl(pal, "x"))
        self.assertEqual(len(palette.act(pal)), 768)


class Guide(unittest.TestCase):
    def test_grid(self):
        chars = Sheet(4, 8, 16, 16)
        im, nums = guide.grid(chars)
        self.assertEqual(im.size, chars.size)
        self.assertEqual(im.mode, "RGBA")
        self.assertFalse(nums, "an 8-pixel cell has no room for a numeral")
        self.assertEqual(im.getpixel((0, 0)), guide.EVERY4)
        self.assertEqual(im.getpixel((8, 5)), guide.MAJOR)
        self.assertEqual(im.getpixel((32, 5)), guide.EVERY4)
        sprites = Sheet(12, 21, 8, 16, count=119)
        im, nums = guide.grid(sprites)
        self.assertTrue(nums)
        self.assertEqual(im.getpixel((2, 1)), guide.LABEL)     # top bar of the '0'
        self.assertEqual(im.getpixel((2, 2)), guide.HALO)      # the hole inside it
        self.assertEqual(im.getpixel((4, 1)), guide.HALO)      # and the halo beside


if __name__ == "__main__":
    unittest.main()
