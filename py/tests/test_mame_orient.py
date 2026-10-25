import os
import random
import sys
import unittest
from pathlib import Path

from tests import paths  # noqa: F401  (puts py/ on sys.path)
from beeb_port_kit.mame import orient

T1942 = Path(os.environ.get("T1942_BEEB", r"C:\Users\khcon\OneDrive\BEEB\Repos\1942-beeb"))


def image(w, h, seed=1):
    r = random.Random(seed)
    return [[r.randrange(8) for _ in range(w)] for _ in range(h)]


class Mapping(unittest.TestCase):
    def test_inverse_every_rotation(self):
        img = image(7, 5)
        for rot in orient.ROTATIONS:
            self.assertEqual(orient.to_raw(orient.to_play(img, rot), rot), img, rot)
            pw, ph = orient.play_size(7, 5, rot)
            for y in range(ph):
                for x in range(pw):
                    rx, ry = orient.play_to_raw(x, y, 7, 5, rot)
                    self.assertEqual(orient.raw_to_play(rx, ry, 7, 5, rot), (x, y))

    def test_1942_rot270_as_measured(self):
        # 1942-beeb CLAUDE.md s2, measured 2026-09-07 at 96.3% against 46-48%:
        # play(x, y) = raw(255 - y, x), raw 256 wide x 224 high, play 224 x 256
        self.assertEqual(orient.play_size(256, 224, 270), (224, 256))
        for x, y in ((0, 0), (223, 0), (0, 255), (100, 37), (223, 255)):
            self.assertEqual(orient.play_to_raw(x, y, 256, 224, 270), (255 - y, x))
        # and the derived form the port uses: play X = tilemap Y - 16 (raw Y within
        # the visible area V 16-239), play Y = 255 - raw X
        for tilemap_y in (16, 100, 239):
            for raw_x in (0, 77, 255):
                self.assertEqual(orient.raw_to_play(raw_x, tilemap_y - 16, 256, 224, 270),
                                 (tilemap_y - 16, 255 - raw_x))

    def test_cell_rot270_is_90_anticlockwise(self):
        # 1942-beeb arcade.to_play: play[r][c] = raw[c][h - 1 - r]
        raw = image(16, 16, 3)
        play = orient.to_play(raw, 270)
        for r in range(16):
            for c in range(16):
                self.assertEqual(play[r][c], raw[c][15 - r])
        # anticlockwise: the raw top row becomes the play left column, read upward
        self.assertEqual([play[r][0] for r in range(16)], list(reversed(raw[0])))

    def test_mame_rot90_is_clockwise(self):
        raw = [[1, 2], [3, 4], [5, 6]]          # 2 wide, 3 high
        self.assertEqual(orient.to_play(raw, 90), [[5, 3, 1], [6, 4, 2]])
        self.assertEqual(orient.to_play(raw, 180), [[6, 5], [4, 3], [2, 1]])
        self.assertEqual(orient.to_play(raw, 270), [[2, 4, 6], [1, 3, 5]])

    def test_flips_follow_the_axes(self):
        # rotating a flipped cell must equal flipping the rotated cell by the mapped
        # bits - for every rotation, on a non-square cell (BUGS.md #1's other half)
        raw = image(5, 3, 9)
        for rot in orient.ROTATIONS:
            for fx in (0, 1):
                for fy in (0, 1):
                    pfx, pfy = orient.flips_to_play(fx, fy, rot)
                    self.assertEqual(orient.to_play(orient.flip(raw, fx, fy), rot),
                                     orient.flip(orient.to_play(raw, rot), pfx, pfy),
                                     (rot, fx, fy))
        self.assertEqual(orient.flips_to_play(1, 0, 270), (0, 1))
        self.assertEqual(orient.flips_to_play(1, 0, 180), (1, 0))

    def test_bad_rotation(self):
        with self.assertRaises(ValueError):
            orient.to_play([[0]], 45)


class ScoreAllFour(unittest.TestCase):
    def test_finds_the_rotation(self):
        raw = image(32, 24, 5)
        ref = orient.to_play(raw, 270)
        ref[0][0] = 99                          # a HUD pixel the rebuild does not draw
        best, scores = orient.score_rotations(raw, ref)
        self.assertEqual(best, 270)
        self.assertIsNone(scores[0])            # wrong shape
        self.assertGreater(scores[270], 0.99)
        self.assertLess(scores[90], 0.5)

    def test_symmetric_scene_refuses(self):
        # a flat sea: every rotation agrees, so nothing is measured
        raw = [[2] * 32 for _ in range(24)]
        with self.assertRaises(orient.NotDiscriminating):
            orient.score_rotations(raw, orient.to_play(raw, 270))

    def test_pil_images(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow absent")
        raw = image(10, 6, 2)
        ref = orient.to_play(raw, 90)
        im = Image.new("L", (6, 10))
        im.putdata([v for row in ref for v in row])
        self.assertEqual(orient.score_rotations(raw, im)[0], 90)


@unittest.skipUnless((T1942 / "tools" / "arcade.py").exists(), "1942-beeb not present")
class Against1942(unittest.TestCase):
    def test_to_play_and_flips_match_arcade_py(self):
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(T1942 / "tools"))
        try:
            import arcade
        finally:
            sys.path.pop(0)
        raw = image(16, 16, 11)
        self.assertEqual(orient.to_play(raw, 270), arcade.to_play(raw))
        for fx in (0, 1):
            for fy in (0, 1):
                self.assertEqual(orient.flips_to_play(fx, fy, 270),
                                 arcade.Roms.flips_to_play(fx, fy))


if __name__ == "__main__":
    unittest.main()
