import unittest
from pathlib import Path

from tests import paths                                    # noqa: F401  (sys.path)
from beeb_port_kit import listing

# A listing in Baron's exact layout: two spaces, four hex digits, two spaces,
# sixteen columns of bytes, then the source text.
SAMPLE = """RELEASE=0
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
        self.assertEqual(lines[18].data, b"\xFF\x00\x00\x00")

    def test_symbols_and_autos(self):
        syms = listing.symbols(SAMPLE)
        self.assertEqual(syms["start"], [0x1900])
        self.assertEqual(syms["loop"], [0x1908])
        self.assertEqual(syms["table"], [0x190C])
        self.assertEqual(syms["blob"], [0x4A00])
        # a label before a line with an address but no bytes still resolves
        self.assertEqual(syms["blob_end"], [0x5400])
        # ZA_AUTO allocations, including two variables sharing a byte
        self.assertEqual(syms["zxsrc"], [0x00])
        self.assertEqual(syms["scroll"], [0x00])
        self.assertEqual(syms["field_count"], [0x0C])

    def test_lookup_refuses_an_ambiguous_local(self):
        doubled = SAMPLE + "\n.loop\n  1F00  EA              nop\n"
        self.assertEqual(listing.lookup(SAMPLE, "loop"), 0x1908)
        self.assertIsNone(listing.lookup(SAMPLE, "nosuch"))
        with self.assertRaises(ValueError):
            listing.lookup(doubled, "loop")


class Stream(unittest.TestCase):
    def test_shape(self):
        s = listing.opcode_stream(SAMPLE)
        self.assertEqual(s[:5], ["A2/1", "9A/0", "A9/1", "8D/2", "A5/1"])
        self.assertIn("data:EQUB &00, &0F, &F0, &FF", s)
        self.assertEqual(len(s), 8)             # 6 instructions + 2 data lines

    def test_moving_code_compares_equal(self):
        """The stream carries no addresses, so the same instructions assembled
        1,024 bytes higher are the same stream."""
        moved = "\n".join(
            ("  %04X%s" % (int(ln[2:6], 16) + 0x400, ln[6:])) if listing._ADDR.match(ln) else ln
            for ln in SAMPLE.split("\n"))
        self.assertEqual(listing.opcode_stream(SAMPLE), listing.opcode_stream(moved))

    def test_a_changed_instruction_shows(self):
        edited = SAMPLE.replace("  1902  9A              txs",
                                "  1902  EA              nop")
        a, b = listing.opcode_stream(SAMPLE), listing.opcode_stream(edited)
        self.assertEqual(len(a), len(b))
        self.assertEqual(sum(1 for x, y in zip(a, b) if x != y), 1)

    def test_operand_values_are_invisible(self):
        """The documented blind spot: compare images byte for byte first."""
        edited = SAMPLE.replace("  1900  A2 FF           ldx #&ff",
                                "  1900  A2 04           ldx #4")
        self.assertEqual(listing.opcode_stream(SAMPLE), listing.opcode_stream(edited))


TEMPLATE_LST = Path(__file__).resolve().parents[2] / "template" / "build" / "game.lst"


@unittest.skipUnless(TEMPLATE_LST.exists(), "template has not been built")
class AgainstTheTemplate(unittest.TestCase):
    """The real thing: the kit's own template listing, whose addresses are
    known from its docs and from the allocator's own report."""

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


if __name__ == "__main__":
    unittest.main()
