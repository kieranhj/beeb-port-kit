import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

from tests import paths                                    # noqa: F401  (sys.path)
from beeb_port_kit import beebasm_dataflow as bd

KIT = Path(__file__).resolve().parents[2]
REPOS = KIT.parent
PROJECTS = {
    "Paradroid": (Path(os.environ.get("PARADROID_BEEB", REPOS / "Paradroid")), "build/paradroid.lst", ("src",)),
    "Edge Grinder": (Path(os.environ.get("EDGE_BEEB", REPOS / "edge-beeb")), "build/EDGE.lst", ("src", "lib")),
}


def parse_dbg(path):
    recs = {}
    for ln in Path(path).read_text(encoding="ascii").splitlines():
        t, _, rest = ln.partition("\t")
        d = {}
        for m in re.finditer(r'(\w+)=("[^"]*"|[^,]*)', rest):
            v = m.group(2)
            d[m.group(1)] = v[1:-1] if v.startswith('"') else v
        recs.setdefault(t, []).append(d)
    return recs


# A beebasm -v listing in both shapes the two ports' beebasm builds print: every
# byte listed, and a long INCBIN cut to three bytes and "...". Then a SAVE, and a
# bank at &8000 that must be a section of its own.
LISTING = """﻿.start
     1100   A9 00      LDA #&00
     1102   20 10 11   JSR &1110
.table
     1105   10 11
     1107   60         RTS
.var
     0070
Macro POKE:
     1108   85 70      STA &70
End macro POKE
.sub
     1110   60         RTS
.blob
     1111   00 00 00 ... INCBIN "data/blob.bin"
.blob_end
     1211   EA         NOP
Saving file 'CODE'
.bank_start
     8000   A2 01      LDX #&01
     8002   60         RTS
Saving file 'BANK'
"""

SOURCE = """\\ the source the address-taken scan reads
.start   LDA #0 : JSR sub
.table   EQUW sub       ; sub's address in data: taken
.sub     RTS
.bank_start
    LDX #1 : RTS
"""


class ConvertTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "src").mkdir()
        (root / "src" / "main.asm").write_text(SOURCE)
        (root / "game.lst").write_text(LISTING, encoding="utf-8")
        self.out = root / "out"
        self.s = bd.convert(root / "game.lst", [root / "src"], self.out)
        self.dbg = parse_dbg(self.out / "game.dbg")

    def tearDown(self):
        self.tmp.cleanup()

    def test_sections(self):
        # the INCBIN runs to &1211, so the code is one section; the SAVE splits the bank off
        self.assertEqual(self.s["sections"], [(0x1100, 0x1212), (0x8000, 0x8003)])

    def test_instructions_and_data(self):
        self.assertEqual(self.s["instructions"], 8)
        self.assertEqual(self.s["statements"], 10)         # + the table and the INCBIN
        text = (self.out / "src" / "listing.s").read_text().splitlines()
        self.assertIn("    lda #&00", text)
        self.assertIn("    .byte $10,$11", text)
        self.assertIn("; Macro POKE:", text)

    def test_elided_incbin_spans_to_the_next_address(self):
        spans = [(int(s["seg"]), int(s["start"]), int(s["size"])) for s in self.dbg["span"]]
        self.assertIn((0, 0x11, 0x100), spans)             # &1111, for 256 bytes

    def test_labels_and_address_taken(self):
        syms = {s["name"]: s for s in self.dbg["sym"]}
        self.assertIn("ref", syms["sub"])                  # named in EQUW: taken
        self.assertNotIn("ref", syms["start"])             # never named in the source body
        self.assertNotIn("seg", syms["var"])               # an address with no bytes
        self.assertEqual(syms["bank_start"]["seg"], "1")

    def test_images(self):
        img = (self.out / "seg00_1100.bin").read_bytes()
        self.assertEqual(img[:8], bytes.fromhex("A900201011101160"))
        self.assertEqual(len(img), 0x112)


class ProjectsTest(unittest.TestCase):
    """The two ports' own listings, when they are on this machine: the
    sections the 2026-10-06 runs found, and the vendored model reading them."""

    def run_project(self, name, sections, instructions):
        root, lst, srcs = PROJECTS[name]
        if not (root / lst).exists():
            self.skipTest("%s not built here" % name)
        with tempfile.TemporaryDirectory() as tmp:
            s = bd.convert(root / lst, [root / d for d in srcs], Path(tmp))
            self.assertEqual(len(s["sections"]), sections)
            sys.path.insert(0, str(KIT / "template" / "tools" / "dataflow"))
            try:
                import model
                P = model.Program(tmp, tmp, game_dir="src")
            finally:
                sys.path.pop(0)
            self.assertEqual(len(P.insns), s["instructions"])
            self.assertEqual(P.bad, [])
            self.assertGreater(s["instructions"], instructions)

    def test_paradroid(self):
        self.run_project("Paradroid", 15, 20000)

    def test_edge_grinder(self):
        self.run_project("Edge Grinder", 10, 4000)


if __name__ == "__main__":
    unittest.main()
