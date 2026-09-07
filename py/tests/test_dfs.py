import unittest

from tests import paths
from beeb_port_kit import dfs, zx0, zx02


class Catalogue(unittest.TestCase):
    def files(self):
        return {"!BOOT": dfs.Entry("!BOOT", b"*RUN GAME\r", 0, 0),
                "GAME": dfs.Entry("GAME", bytes(range(256)) * 3 + b"xyz", 0x1900, 0x1912),
                "BANK0": dfs.Entry("BANK0", b"\xAA" * 1000, 0xFFFF8000, 0xFFFF8000)}

    def test_build_and_read_back(self):
        img = dfs.build_image(self.files(), ["!BOOT", "GAME"], b"EDGE", cycle=5, opt=3)
        self.assertEqual(len(img) % dfs.SECTOR, 0)
        # 2 catalogue sectors + 1 + 4 + 4 data sectors
        self.assertEqual(len(img), (2 + 1 + 4 + 4) * dfs.SECTOR)
        back = dfs.read_image(img)
        self.assertEqual(back.title, b"EDGE")
        self.assertEqual(back.cycle, 5)
        self.assertEqual(back.opt, 3)
        self.assertEqual(list(back.files), ["!BOOT", "GAME", "BANK0"])
        for name, f in self.files().items():
            self.assertEqual(back.files[name].data, f.data, name)
            self.assertEqual(back.files[name].load, f.load & 0x3FFFF, name)
            self.assertEqual(back.files[name].exec, f.exec & 0x3FFFF, name)
        # the old dict shape still works
        cat = dfs.read_catalogue(img)
        self.assertEqual(cat["GAME"]["load"], 0x1900)

    def test_layout_order_and_padding(self):
        img = dfs.build_image(self.files(), ["BANK0", "!BOOT"], b"T")
        # BANK0 first at sector 2, then !BOOT at 6, then GAME (unlisted) at 7
        self.assertEqual(img[2 * 256:2 * 256 + 4], b"\xAA" * 4)
        self.assertEqual(img[6 * 256:6 * 256 + 4], b"*RUN")
        self.assertEqual(img[6 * 256 + 10:7 * 256], bytes(246), "sector padding is zero")
        self.assertEqual(img[7 * 256:7 * 256 + 3], b"\x00\x01\x02")

    def test_pad_to_200k(self):
        img = dfs.build_image(self.files(), [], b"T")
        p = dfs.pad(img)
        self.assertEqual(len(p), 200 * 1024)
        self.assertEqual(p[:len(img)], img)
        self.assertEqual(dfs.read_image(p).files["GAME"].data, self.files()["GAME"].data)

    def test_limits(self):
        many = {f"F{i}": dfs.Entry(f"F{i}", b"x") for i in range(32)}
        with self.assertRaises(dfs.DiscError):
            dfs.build_image(many)
        with self.assertRaises(dfs.DiscError):
            dfs.build_image({"TOOLONGNAME": dfs.Entry("TOOLONGNAME", b"x")})
        with self.assertRaises(dfs.DiscError):
            dfs.build_image({"BIG": dfs.Entry("BIG", bytes(800 * 256))})


class Streams(unittest.TestCase):
    """Both codecs, since the kit ships a depacker for each: new ports are
    ZX02, the two shipping discs are ZX0."""

    CODECS = (zx0, zx02)

    def test_in_place_delta_known_stream(self):
        # 64 distinct literals then one long copy back over them: the copy
        # runs the writer to the very end of the raw output while the reader
        # has consumed all of the stream but its end marker, so the worst
        # overtake is (raw - packed), at the last byte.
        raw = bytes(range(64)) * 40                      # 2560 bytes
        for codec in self.CODECS:
            with self.subTest(codec=codec.__name__):
                packed = codec.compress(raw)
                delta = dfs.in_place_delta(packed, raw, codec)
                self.assertGreater(delta, 0)
                # worst gap = (len(raw) - 1) - (bytes consumed before the end
                # marker); the exact figure is what the decode walk says, and
                # it is at most the whole gap.
                self.assertLessEqual(delta, len(raw) - len(packed) + 2)
                self.assertGreaterEqual(delta, len(raw) - len(packed) - 2)

    def test_in_place_delta_literal_stream(self):
        # Incompressible data: the writer trails the reader by the flag bytes,
        # so the margin is small, and never larger than the flag overhead.
        import random
        r = random.Random(5)
        raw = bytes(r.randrange(256) for _ in range(500))
        for codec in self.CODECS:
            with self.subTest(codec=codec.__name__):
                packed = codec.compress(raw)
                self.assertLessEqual(dfs.in_place_delta(packed, raw, codec), 4)

    def test_in_place_delta_disagreement(self):
        raw = b"abc" * 100
        for codec in self.CODECS:
            with self.subTest(codec=codec.__name__):
                packed = codec.compress(raw)
                with self.assertRaises(dfs.DiscError):
                    dfs.in_place_delta(packed, raw + b"!", codec)

    def test_in_place_delta_default_codec_is_zx02(self):
        raw = bytes(range(64)) * 20
        packed = zx02.compress(raw)
        self.assertEqual(dfs.in_place_delta(packed, raw),
                         dfs.in_place_delta(packed, raw, zx02))

    @unittest.skipUnless((paths.PARADROID_TOOLS / "make_disc.py").exists(), "paradroid not present")
    def test_in_place_delta_matches_paradroid(self):
        import importlib.util
        import sys
        sys.path.insert(0, str(paths.PARADROID_TOOLS))
        spec = importlib.util.spec_from_file_location("para_make_disc",
                                                      paths.PARADROID_TOOLS / "make_disc.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for raw in (bytes(range(64)) * 40, b"hello " * 200 + bytes(range(256))):
            packed = zx0.compress(raw)
            self.assertEqual(dfs.in_place_delta(packed, raw, zx0),
                             mod.in_place_delta(packed, raw))

    def test_check_stream(self):
        raw = bytes(range(256)) * 8
        for codec in self.CODECS:
            with self.subTest(codec=codec.__name__):
                packed = codec.compress(raw)
                # disjoint: fine
                info = dfs.check_stream("A", 0x3000, packed, 0x8000, raw,
                                        top=0x8000, codec=codec)
                self.assertEqual(info["headroom"], 0x8000 - 0x3000 - len(packed))
                # overlapping, not in place: refused
                with self.assertRaises(dfs.DiscError):
                    dfs.check_stream("A", 0x3100, packed, 0x3000, raw, codec=codec)
                # overlapping, in place, high enough: allowed
                need = 0x3000 + dfs.in_place_delta(packed, raw, codec)
                info = dfs.check_stream("A", need, packed, 0x3000, raw,
                                        in_place=True, codec=codec)
                self.assertEqual(info["in_place_margin"], 0)
                with self.assertRaises(dfs.DiscError):
                    dfs.check_stream("A", need - 1, packed, 0x3000, raw,
                                     in_place=True, codec=codec)
                # past the top
                with self.assertRaises(dfs.DiscError):
                    dfs.check_stream("A", 0x7F00, packed, 0x8000, raw,
                                     top=0x8000, codec=codec)

    def test_compress_helper(self):
        raw = b"hello world " * 50
        exe = paths.ZX02_EXE if paths.ZX02_EXE.exists() else None
        packed = dfs.compress(raw, exe)                       # ZX02 by default
        self.assertEqual(zx02.decompress(packed), raw)
        exe0 = paths.ZX0_EXE if paths.ZX0_EXE.exists() else None
        packed0 = dfs.compress(raw, exe0, codec=zx0)
        self.assertEqual(zx0.decompress(packed0), raw)


if __name__ == "__main__":
    unittest.main()
