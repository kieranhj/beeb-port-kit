import json
import unittest
from pathlib import Path

from tests import paths                                    # noqa: F401  (sys.path)
from beeb_port_kit import listing

# Baron's listing as it has been since 45e5cb8 (2026-09-13): two spaces, four
# hex digits, two spaces, twenty-six columns of bytes, then the source text -
# and a label carries its OWN address rather than borrowing the next line's.
SAMPLE = """RELEASE = 0
SECTION Game, org = &1900, filename = "Game"
zxsrc = &00 [auto]
scroll = &00 [auto]
field_count = &0C [auto]
  1900  .start
  1900  A2 FF                       ldx #&ff
  1902  9A                          txs
  1903                              CRTC 8, R8_BLANK
  1903  A9 08                       lda #r
  1905  8D 00 FE                    sta CRTC_ADDR
  1908  .loop
  1908  A5 00                       lda scroll
  190A  D0 FC                       bne loop
  190C  .table
  190C  00 0F F0 FF                 EQUB &00, &0F, &F0, &FF
  4A00  .blob
  4A00  FF 00 00 00 00 00 00 00...  INCBIN "data/panel.bin"
  5400  .blob_end
  5400                              ASSERT blob_end - blob = 2560
ENDSECTION
"""

# The SAME listing as Baron wrote it BEFORE that commit: sixteen byte columns,
# and a label alone on its line. Old builds' listings still have to read.
OLD_SAMPLE = """RELEASE=0
SECTION Game, org = &1900, filename = "Game"
zxsrc = &00 [auto]
scroll = &00 [auto]
field_count = &0C [auto]
.start
  1900  A2 FF           ldx #&ff
  1902  9A              txs
  1903                  CRTC 8, R8_BLANK
  1903  A9 08           lda #r
  1905  8D 00 FE        sta CRTC_ADDR
.loop
  1908  A5 00           lda scroll
  190A  D0 FC           bne loop
.table
  190C  00 0F F0 FF     EQUB &00, &0F, &F0, &FF
.blob
  4A00  FF 00 00 00...  INCBIN "data/panel.bin"
.blob_end
  5400                  ASSERT blob_end - blob = 2560
ENDSECTION
"""

# A `--symbols` dump of the same thing: resolved values, scope-qualified names.
DUMP = json.dumps({
    "src/main.6502": {
        "start": 0x1900,
        "table": 0x190C,
        "blob": 0x4A00,
        "blob_end": 0x5400,
        "zxsrc": 0x00,
        "scroll": 0x00,
        "field_count": 0x0C,
        "PLAY_R7": 27,                  # a computed constant: no listing has this
        "BUILD_TIME": "13 Sep 2026 19:37:28+",
        "RELEASE": False,
        "@0:1234.loop": 0x1908,         # an anonymous `{ }` scope
        "rupt_timer.done": 0x1C24,      # a named scope
        "@6:6263.done": 0x1C48,
    }
})


class Parsing(unittest.TestCase):
    def test_line_kinds(self):
        lines = {ln.n: ln for ln in listing.parse(SAMPLE)}
        self.assertEqual(lines[7].addr, 0x1900)             # ldx #&ff
        self.assertEqual(lines[7].data, b"\xA2\xFF")
        self.assertTrue(lines[7].is_instruction)
        self.assertEqual(lines[9].addr, 0x1903)             # the macro call
        self.assertEqual(lines[9].data, b"")                # an address, no bytes
        self.assertFalse(lines[9].is_instruction)
        self.assertEqual(lines[16].data, b"\x00\x0F\xF0\xFF")   # EQUB
        self.assertFalse(lines[16].is_instruction)
        self.assertTrue(lines[18].elided)                   # INCBIN, bytes cut short
        self.assertEqual(lines[18].data, b"\xFF\x00\x00\x00\x00\x00\x00\x00")

    def test_a_label_line_has_its_address_and_no_bytes(self):
        line = [ln for ln in listing.parse(SAMPLE) if ln.text == ".start"][0]
        self.assertEqual(line.addr, 0x1900)
        self.assertEqual(line.data, b"")

    def test_source_text_that_looks_like_bytes_is_not_eaten(self):
        """The byte field ends at TWO spaces, so a macro call spelled in hex
        digits stays source text."""
        line = listing.parse("  1903                              FADE 1")[0]
        self.assertEqual(line.data, b"")
        self.assertEqual(line.text, "FADE 1")


class Symbols(unittest.TestCase):
    def test_symbols_and_autos(self):
        syms = listing.symbols(SAMPLE)
        self.assertEqual(syms["start"], [0x1900])
        self.assertEqual(syms["loop"], [0x1908])
        self.assertEqual(syms["table"], [0x190C])
        self.assertEqual(syms["blob"], [0x4A00])
        self.assertEqual(syms["blob_end"], [0x5400])
        # ZA_AUTO allocations, including two variables sharing a byte
        self.assertEqual(syms["zxsrc"], [0x00])
        self.assertEqual(syms["scroll"], [0x00])
        self.assertEqual(syms["field_count"], [0x0C])

    def test_the_old_layout_still_reads(self):
        old = listing.symbols(OLD_SAMPLE)
        for name in ("start", "loop", "table", "blob", "zxsrc", "field_count"):
            self.assertEqual(old[name], listing.symbols(SAMPLE)[name], name)

    def test_the_old_layout_gets_a_section_end_label_wrong(self):
        """Documented in listing.py: under the old layout `blob_end` borrows
        the next line's address, and here there is none after it. The new
        layout prints the label's own address, which is why the dump - or a
        listing from a Baron newer than 45e5cb8 - is what to trust."""
        tail = 'SECTION Panel, org = &6000, filename = "PANEL"\n  6000  EA\n'
        new_layout = SAMPLE.replace("  5400                              ASSERT blob_end - blob = 2560\n", "") + tail
        old_layout = OLD_SAMPLE.replace("  5400                  ASSERT blob_end - blob = 2560\n", "") + tail
        self.assertEqual(listing.symbols(new_layout)["blob_end"], [0x5400])
        self.assertEqual(listing.symbols(old_layout)["blob_end"], [0x6000])   # wrong

    def test_lookup_refuses_an_ambiguous_local(self):
        doubled = SAMPLE + "\n  1F00  .loop\n  1F00  EA                          nop\n"
        self.assertEqual(listing.lookup(SAMPLE, "loop"), 0x1908)
        self.assertIsNone(listing.lookup(SAMPLE, "nosuch"))
        with self.assertRaises(ValueError):
            listing.lookup(doubled, "loop")


class Dump(unittest.TestCase):
    def test_it_is_recognised(self):
        self.assertTrue(listing.is_dump(DUMP))
        self.assertFalse(listing.is_dump(SAMPLE))

    def test_addresses_agree_with_the_listing(self):
        dump, lst = listing.symbols(DUMP), listing.symbols(SAMPLE)
        for name in ("start", "loop", "table", "blob", "blob_end",
                     "zxsrc", "scroll", "field_count"):
            self.assertEqual(dump[name], lst[name], name)

    def test_it_has_what_the_listing_cannot(self):
        """A computed constant's value - waitingforvsync/baron#5's point 2."""
        self.assertEqual(listing.symbols(DUMP)["PLAY_R7"], [27])
        self.assertNotIn("PLAY_R7", listing.symbols(SAMPLE))
        self.assertEqual(listing.values(DUMP)["BUILD_TIME"], ["13 Sep 2026 19:37:28+"])

    def test_non_numbers_are_not_addresses(self):
        """`values()` carries strings and booleans; `symbols()` does not, so a
        caller reading memory never gets handed one. A bool is not an address
        either, however much Python thinks False is 0."""
        syms = listing.symbols(DUMP)
        self.assertNotIn("BUILD_TIME", syms)
        self.assertNotIn("RELEASE", syms)

    def test_a_named_scope_resolves_exactly_and_the_leaf_stays_ambiguous(self):
        syms = listing.symbols(DUMP)
        self.assertEqual(syms["rupt_timer.done"], [0x1C24])
        self.assertEqual(sorted(syms["done"]), [0x1C24, 0x1C48])
        self.assertEqual(listing.lookup(DUMP, "rupt_timer.done"), 0x1C24)
        with self.assertRaises(ValueError):
            listing.lookup(DUMP, "done")


class Stream(unittest.TestCase):
    def test_shape(self):
        s = listing.opcode_stream(SAMPLE)
        self.assertEqual(s[:5], ["A2/1", "9A/0", "A9/1", "8D/2", "A5/1"])
        self.assertIn("data:EQUB &00, &0F, &F0, &FF", s)
        self.assertEqual(len(s), 8)             # 6 instructions + 2 data lines

    def test_both_layouts_reduce_to_the_same_stream(self):
        """Which is what makes a listing from before 45e5cb8 comparable with
        one from after it: the same build reduces to the same stream."""
        self.assertEqual(listing.opcode_stream(SAMPLE),
                         listing.opcode_stream(OLD_SAMPLE))

    def test_moving_code_compares_equal(self):
        """The stream carries no addresses, so the same instructions assembled
        1,024 bytes higher are the same stream."""
        moved = "\n".join(
            ("  %04X%s" % (int(ln[2:6], 16) + 0x400, ln[6:])) if listing._ADDR.match(ln) else ln
            for ln in SAMPLE.split("\n"))
        self.assertEqual(listing.opcode_stream(SAMPLE), listing.opcode_stream(moved))

    def test_a_changed_instruction_shows(self):
        edited = SAMPLE.replace("  1902  9A                          txs",
                                "  1902  EA                          nop")
        a, b = listing.opcode_stream(SAMPLE), listing.opcode_stream(edited)
        self.assertEqual(len(a), len(b))
        self.assertEqual(sum(1 for x, y in zip(a, b) if x != y), 1)

    def test_operand_values_are_invisible(self):
        """The documented blind spot: compare images byte for byte first."""
        edited = SAMPLE.replace("  1900  A2 FF                       ldx #&ff",
                                "  1900  A2 04                       ldx #4")
        self.assertEqual(listing.opcode_stream(SAMPLE), listing.opcode_stream(edited))


TEMPLATE_BUILD = Path(__file__).resolve().parents[2] / "template" / "build"
TEMPLATE_LST = TEMPLATE_BUILD / "game.lst"
TEMPLATE_DUMP = TEMPLATE_BUILD / "game.symbols.json"


@unittest.skipUnless(TEMPLATE_LST.exists(), "template has not been built")
class AgainstTheTemplate(unittest.TestCase):
    """The real thing: the kit's own template build, whose addresses are known
    from its docs and from the allocator's own report."""

    def test_known_addresses(self):
        syms = listing.symbols(TEMPLATE_LST)
        self.assertEqual(syms["panel_start"], [0x4A00])     # docs/memory-map.md
        self.assertEqual(syms["panel_end"], [0x5400])
        self.assertEqual(listing.lookup(TEMPLATE_LST, "start"), 0x1900)
        # the zero-page allocator's own choices, which exist nowhere else
        self.assertEqual(len(syms["scroll"]), 1)
        self.assertLess(syms["scroll"][0], 0x90)
        self.assertLess(syms["field_count"][0], 0x90)

    def test_stream_is_self_consistent(self):
        s = listing.opcode_stream(TEMPLATE_LST)
        self.assertGreater(len(s), 100)
        self.assertEqual(s, listing.opcode_stream(TEMPLATE_LST))

    @unittest.skipUnless(TEMPLATE_DUMP.exists(), "no symbol dump in build/")
    def test_the_dump_agrees_with_the_listing(self):
        dump, lst = listing.symbols(TEMPLATE_DUMP), listing.symbols(TEMPLATE_LST)
        for name, addrs in lst.items():
            self.assertIn(name, dump, name)
            for addr in addrs:
                self.assertIn(addr, dump[name], name)

    @unittest.skipUnless(TEMPLATE_DUMP.exists(), "no symbol dump in build/")
    def test_the_dump_has_the_computed_constants(self):
        syms = listing.symbols(TEMPLATE_DUMP)
        self.assertGreater(len(syms), len(listing.symbols(TEMPLATE_LST)))
        self.assertIn("T1_I2", syms)                        # PRINTed by main.6502
        self.assertIn("PLAY_R7", syms)


if __name__ == "__main__":
    unittest.main()
