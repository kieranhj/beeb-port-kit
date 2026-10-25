import io
import unittest

from tests import paths  # noqa: F401
from beeb_port_kit.mame.probe import Score, Unread


def verdict(s):
    out = io.StringIO()
    code = s.finish(out)
    return code, out.getvalue()


class Verdicts(unittest.TestCase):
    def test_all_match_passes(self):
        s = Score("t")
        for i in range(10):
            s.compare("rule", i, i, key=i)
        s.exclude("a freeze flag was set", 3)
        code, text = verdict(s)
        self.assertEqual(code, 0)
        self.assertIn("10 of      10", text)
        self.assertIn("a freeze flag was set", text)
        self.assertIn("PASS", text)

    def test_one_wrong_fails_and_is_printed(self):
        s = Score("t")
        for i in range(100):
            s.compare("rule", i, i if i != 57 else -1, key=("frame", i))
        code, text = verdict(s)
        self.assertEqual(code, 1)
        self.assertIn("WRONG rule  ('frame', 57)  (57, -1)", text)
        self.assertIn("a residual you cannot explain", text)

    def test_first_n_only(self):
        s = Score("t", first=3)
        for i in range(10):
            s.observe("r", False, key=i)
        self.assertEqual(len(s.wrongs["r"]), 3)
        self.assertEqual(s.rules["r"][1], 10)

    def test_zero_samples_fail(self):
        self.assertEqual(verdict(Score("empty"))[0], 1)
        s = Score("t")
        s.compare("ran", 1, 1)
        s.rules["never ran"] = [0, 0, 0]
        code, text = verdict(s)
        self.assertEqual(code, 1)
        self.assertIn("ran over nothing", text)

    def test_exclusion_needs_a_reason(self):
        with self.assertRaises(ValueError):
            Score("t").exclude("  ")


class Torn(unittest.TestCase):
    def test_torn_then_match(self):
        s = Score("t")
        for ok in (True, False, True, True):
            s.observe("ram", ok, torn_ok=True)
        self.assertEqual(s.rules["ram"], [3, 0, 1])
        self.assertEqual(verdict(s)[0], 0)

    def test_torn_then_wrong_is_wrong(self):
        # a model error propagates; a torn snapshot does not
        s = Score("t")
        for ok in (True, False, False, True):
            s.observe("ram", ok, torn_ok=True)
        self.assertEqual(s.rules["ram"][1], 1)       # the first of the pair
        self.assertEqual(s.rules["ram"][2], 1)       # the second, followed by a match
        self.assertEqual(verdict(s)[0], 1)

    def test_torn_at_the_end_is_wrong(self):
        s = Score("t")
        s.observe("ram", True, torn_ok=True)
        s.observe("ram", False, torn_ok=True)
        self.assertEqual(verdict(s)[0], 1)


class Coverage(unittest.TestCase):
    def test_required_path_never_taken(self):
        s = Score("t")
        s.compare("r", 1, 1)
        s.cover("left edge", 4)
        s.require("left edge", 2)
        s.require("right edge")
        code, text = verdict(s)
        self.assertEqual(code, 1)
        self.assertIn("never covered: right edge", text)
        s.cover("right edge")
        self.assertEqual(verdict(s)[0], 0)


class UnreadPaths(unittest.TestCase):
    def test_unread_is_wrong_not_skipped(self):
        def model():
            raise Unread("$19CC's jr z: the path this model does not follow")
        s = Score("t")
        s.model("bank", lambda: 2, 2)
        s.model("bank", model, 0, key="stage 4")
        code, text = verdict(s)
        self.assertEqual(code, 1)
        self.assertIn("UNREAD", text)


if __name__ == "__main__":
    unittest.main()
