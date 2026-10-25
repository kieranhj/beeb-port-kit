import os
import tempfile
import unittest
from pathlib import Path

from tests import paths  # noqa: F401  (puts py/ on the path)
from beeb_port_kit import check_decisions as cd

GOOD = """# Decisions

| # | Date | Status | Decision | Where |
|---|---|---|---|---|
| 1 | 2026-09-07 | **AGREED** 2026-09-07 | Target the Master | `docs/layer-0.md` |
| 2 | 2026-09-08 | SUPERSEDED by 3 | Panel above | - |
| 3 | 2026-09-08 | TAKEN while away, for review | Panel below, a \\| in the text | - |
| 4 | 2026-09-09 | OPEN | Two phases? | - |

## Rejected, do not re-litigate

| What | Why | When |
|---|---|---|
| A HAL | deleted | 2026-08 |
"""


class CheckDecisions(unittest.TestCase):
    def lines(self, text):
        return text.split("\n")

    def test_good_table_holds(self):
        bad, nums = cd.check(self.lines(GOOD))
        self.assertEqual(bad, [])
        self.assertEqual(nums, [1, 2, 3, 4])
        self.assertEqual(cd.columns(self.lines(GOOD)),
                         ["#", "Date", "Status", "Decision", "Where"])

    def test_the_three_rendering_faults(self):
        text = GOOD.replace("| 2 | 2026-09-08 |", "\n| 2 | 2026-09-08 |")
        text = text.replace("Two phases? | - |", "Two phases? | -")
        text = text.replace("Target the Master |", "Target | the Master |")
        bad, _ = cd.check(self.lines(text))
        joined = "\n".join(bad)
        self.assertIn("BLANK LINE", joined)
        self.assertIn("NO TRAILING PIPE", joined)
        self.assertIn("6 cells against the header's 5", joined)

    def test_fix_repairs_without_changing_text(self):
        text = GOOD.replace("| 2 | 2026-09-08 |", "\n| 2 | 2026-09-08 |")
        text = text.replace("Two phases? | - |", "Two phases? | -")
        fixed = cd.fix(self.lines(text))
        bad, nums = cd.check(fixed)
        self.assertEqual(bad, [])
        self.assertEqual(nums, [1, 2, 3, 4])
        self.assertIn("## Rejected, do not re-litigate", fixed)

    def test_numbering(self):
        text = GOOD.replace("| 3 | 2026-09-08 |", "| 2 | 2026-09-08 |")
        bad, _ = cd.check(self.lines(text))
        self.assertIn("decision 3 is missing", bad)
        self.assertIn("decision 2 appears more than once", bad)

    def test_statuses(self):
        for old, new, want in [
            ("| OPEN |", "| ANSWERED |", "not one of"),
            ("SUPERSEDED by 3", "SUPERSEDED", "without 'by N'"),
            ("SUPERSEDED by 3", "SUPERSEDED by 9", "not a row"),
        ]:
            bad, _ = cd.check(self.lines(GOOD.replace(old, new)))
            self.assertTrue(any(want in b for b in bad), (new, bad))

    def test_no_status_column_is_not_checked(self):
        text = "| # | Date | Decision |\n|---|---|---|\n| 1 | d | ANSWERED, as 1942 wrote it |\n"
        self.assertEqual(cd.check(self.lines(text))[0], [])

    def test_template_table_holds(self):
        tpl = Path(__file__).resolve().parents[2] / "template" / "docs" / "decisions.md"
        if not tpl.exists():
            self.skipTest("no template beside py/")
        bad, nums = cd.check(tpl.read_text(encoding="utf-8").split("\n"))
        self.assertEqual(bad, [])
        self.assertTrue(nums)

    def test_cli_fix_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "decisions.md")
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(GOOD.replace("| 2 | 2026-09-08 |", "\n| 2 | 2026-09-08 |"))
            self.assertEqual(cd.main([p]), 1)
            self.assertEqual(cd.main([p, "--fix"]), 0)
            self.assertEqual(cd.main([p]), 0)


if __name__ == "__main__":
    unittest.main()
