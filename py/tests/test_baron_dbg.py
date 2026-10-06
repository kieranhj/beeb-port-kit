import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

from tests import paths                                    # noqa: F401  (sys.path)
from beeb_port_kit import baron_dbg

TEMPLATE = Path(__file__).resolve().parents[2] / "template"


def parse_dbg(path):
    """ld65's debug file as {type: [fields]} - the same reading as beebgame's
    model.parse_dbg, so what this checks is what the analyses will see."""
    recs = {}
    for ln in Path(path).read_text(encoding="ascii").splitlines():
        t, _, rest = ln.partition("\t")
        d = {}
        for m in re.finditer(r'(\w+)=("[^"]*"|[^,]*)', rest):
            v = m.group(2)
            d[m.group(1)] = v[1:-1] if v.startswith('"') else v
        recs.setdefault(t, []).append(d)
    return recs


def row(addr, data, text):
    return "  %04X  %-26s  %s" % (addr, " ".join("%02X" % b for b in data), text)


class SplitTest(unittest.TestCase):

    def test_comments_colons_and_labels(self):
        s = baron_dbg.split_statements
        self.assertEqual(s("    lda #114 : ldx #1 : jsr osbyte   ; a call"),
                         ["lda #114", "ldx #1", "jsr osbyte"])
        self.assertEqual(s("\\ all comment"), [])
        self.assertEqual(s('.msg EQUS "a:b;c\\d", 13 \\ text'), [".msg", 'EQUS "a:b;c\\d", 13'])
        self.assertEqual(s("  .loop"), [".loop"])


class SmallProgramTest(unittest.TestCase):
    """A hand-written listing over three source files: an INCLUDE, a macro,
    `:`-separated statements, a scoped local label and a table of addresses."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = self.root = Path(self.tmp.name)
        (root / "src" / "lib").mkdir(parents=True)
        (root / "src" / "main.6502").write_text(
            '\\ main\n'                                   # 1
            'INCLUDE "lib/m.6502"\n'                      # 2
            'SECTION Code, org = &1900, filename = "Code"\n'  # 3
            '.start\n'                                    # 4
            '{\n'                                         # 5
            '    lda #1 : sta &70   ; two\n'              # 6
            '    POKE &71, 2\n'                           # 7
            '.loop\n'                                     # 8
            '    dec &70\n'                               # 9
            '    bne loop\n'                              # 10
            '    rts\n'                                   # 11
            '}\n'                                         # 12
            '.table EQUW start\n'                         # 13
            'ENDSECTION\n')                               # 14
        (root / "src" / "lib" / "m.6502").write_text(
            'MACRO POKE a, v\n'
            '    lda #v\n'
            '    sta a\n'
            'ENDMACRO\n')
        lst = "\n".join([
            "  0000                              INCLUDE \"lib/m.6502\"",
            'SECTION Code, org = &1900, filename = "Code"',
            row(0x1900, b"", ".start"),
            "{",
            row(0x1900, b"\xA9\x01", "lda #1"),
            row(0x1902, b"\x85\x70", "sta &70"),
            row(0x1904, b"", "POKE &71, 2"),
            row(0x1904, b"\xA9\x02", "lda #v"),
            row(0x1906, b"\x85\x71", "sta a"),
            row(0x1908, b"", ".loop"),
            row(0x1908, b"\xC6\x70", "dec &70"),
            row(0x190A, b"\xD0\xFC", "bne loop"),
            row(0x190C, b"\x60", "rts"),
            "}",
            row(0x190D, b"", ".table"),
            row(0x190D, b"\x00\x19", "EQUW start"),
            "ENDSECTION", ""])
        (root / "build").mkdir()
        (root / "build" / "game.lst").write_text(lst)
        (root / "build" / "game.symbols.json").write_text(json.dumps(
            {"src/main.6502": {"start": 0x1900, "table": 0x190D, "@0:1.loop": 0x1908}}))
        self.summary = baron_dbg.convert(root, root / "build/game.lst",
                                         root / "build/game.symbols.json", None,
                                         root / "build/out")
        self.dbg = parse_dbg(root / "build/out/game.dbg")

    def tearDown(self):
        self.tmp.cleanup()

    def where(self, addr):
        """(file, line) of the type-0 line whose span starts at addr, smallest first"""
        files = {int(f["id"]): f["name"] for f in self.dbg["file"]}
        spans = {int(s["id"]): (int(s["start"]), int(s["size"])) for s in self.dbg["span"]}
        hits = []
        for ln in self.dbg["line"]:
            if ln["type"] != "0" or "span" not in ln:
                continue
            for sp in ln["span"].split("+"):
                lo, n = spans[int(sp)]
                if lo <= addr - 0x1900 < lo + n:
                    hits.append((n, files[int(ln["file"])], int(ln["line"])))
        return min(hits)[1:] if hits else None

    def test_every_statement_placed(self):
        self.assertEqual(self.summary["unplaced"], 0)
        self.assertEqual(self.summary["emits"], 8)

    def test_lines(self):
        self.assertEqual(self.where(0x1900), ("src/main.6502", 6))     # lda #1 : ...
        self.assertEqual(self.where(0x1902), ("src/main.6502", 6))     # ... : sta &70
        self.assertEqual(self.where(0x1904), ("src/main.6502", 7))     # the macro's call
        self.assertEqual(self.where(0x1906), ("src/main.6502", 7))
        self.assertEqual(self.where(0x190A), ("src/main.6502", 10))
        self.assertEqual(self.where(0x190D), ("src/main.6502", 13))

    def test_statements_file_spells_ca65(self):
        text = (self.root / "build/out/stmts.s").read_text().splitlines()
        self.assertEqual(text[2], "lda #v")
        self.assertEqual(text[-1], ".word start")

    def test_the_table_references_start(self):
        syms = {s["name"]: s for s in self.dbg["sym"]}
        self.assertIn("ref", syms["start"])
        self.assertEqual(syms["loop"].get("parent"), "0")             # scoped
        self.assertNotIn("parent", syms["start"])

    def test_image_without_disc_comes_from_the_listing(self):
        img = (self.root / "build/out/seg_Code.bin").read_bytes()
        self.assertEqual(img, bytes.fromhex("A90185 70A90285 71C670D0FC60 0019".replace(" ", "")))


@unittest.skipUnless((TEMPLATE / "build" / "game.lst").exists(), "build the template first")
class TemplateTest(unittest.TestCase):
    """The template's own build: every statement placed, and - when
    tools/analyse.py has fetched the pinned analyses - beebgame's model reads
    the result as the instructions the listing says it has."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        b = TEMPLATE / "build"
        cls.out = Path(cls.tmp.name)
        cls.s = baron_dbg.convert(TEMPLATE, b / "game.lst", b / "game.symbols.json",
                                  b / "game-raw.ssd", cls.out)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_placed(self):
        self.assertEqual(self.s["unplaced"], 0)
        self.assertEqual(self.s["notes"], [])

    def test_upstream_model_reads_it(self):
        ups = sorted((TEMPLATE / "build" / "dataflow-upstream").glob("*/model.py"))
        if not ups:
            self.skipTest("run tools/analyse.py once to fetch the analyses")
        sys.path.insert(0, str(ups[-1].parent))
        try:
            import model
            P = model.Program(str(TEMPLATE), str(self.out))
        finally:
            sys.path.pop(0)
        from beeb_port_kit import listing
        n = sum(1 for L in listing.parse(TEMPLATE / "build" / "game.lst") if L.is_instruction)
        self.assertEqual(len(P.insns), n)
        self.assertEqual(P.bad, [])
        self.assertFalse([x for x in P.notes if "STALE" in x or "MISSING" in x])


if __name__ == "__main__":
    unittest.main()
