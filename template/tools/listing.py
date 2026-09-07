"""
listing.py - read Baron's `-v` listing: symbol addresses, and the opcode
stream that says whether a change was mechanical.

beeb-port-kit: new with the move to Baron (docs/toolchain-baron.md), and it
exists because two things the kit's procedures lean on lost their BeebASM
one-liners.

FORKED into beeb-port-kit/template 2026-09-07, unchanged - it has no
package-relative imports, so `python tools/listing.py symbols build/GAME.lst`
works from the project root.

WHY IT EXISTS.
  * ADDRESSES. `docs/verification.md`'s standing rule is "addresses come from
    the listing, every time" - main-RAM addresses move on every build, and a
    debugger breakpoint or an emulator memory read against a stale one is a
    measurement of nothing. Under BeebASM that was `-d` and a grep. Baron has
    no symbol dump (asked for upstream, waitingforvsync/baron#5), and its
    listing prints a label on its own line with the address on the NEXT line
    that carries one, so it wants a parser rather than a grep. Zero-page
    allocation makes this sharper still: a ZA_AUTO address is chosen by the
    assembler and moves when the code changes, so the listing is the ONLY
    source of truth for it.
  * MECHANICAL CHANGES. `docs/verification.md` procedure 13 proves a change
    meant to be mechanical left the code alone, by reducing two listings to
    one entry per emitted instruction and diffing. Both ports wrote that
    reducer inline each time and neither checked it in. It is checked in now.

WHAT IT PARSES. Baron's listing is fixed-column, which is what makes this
safe: two spaces, a four-digit hex address, two spaces, sixteen columns of
emitted bytes, then the source text.

      1900  A2 FF           ldx #&ff          an instruction
      1A85  00 0F F0 FF     EQUB &00, ...     data
      1903                  CRTC 8, R8_BLANK  a macro call: address, no bytes
      4A00  FF 00 00 00...  INCBIN "..."      long data, bytes elided by Baron
    .main_loop                                a label: column 0
    zxsrc = &00 [auto]                        a ZA_AUTO allocation: column 0

Verified against the template's own build, 2026-09-07: `symbols()` finds
`install_irq` at &1C04, `panel_start` at &4A00 and the seventeen `[auto]`
allocations the allocator reported (py/tests/test_listing.py).

THE STREAM'S POINT, AND ITS BLIND SPOT. Each entry is the opcode byte and its
operand LENGTH, never the operand's value, so code that has only moved
compares equal. Measured on the template, same day:

    a build against itself            0 differences
    one NOP inserted                  1 difference
    SCROLL_STEP changed 8 -> 4        0 differences

That last one is the point to understand: the stream proves the SHAPE of the
code is unchanged, not its constants - an operand's value is invisible to it,
because under a move every address-shaped operand changes legitimately. So
compare the images byte for byte FIRST; reach for the stream only when the
addresses were meant to move, and read a clean diff as "the same instructions
in the same order", not as "the same program".
"""

import re
from pathlib import Path

ADDR_COL = 2
BYTES_COL = 8
TEXT_COL = 24

_ADDR = re.compile(r"^  ([0-9A-F]{4})  ")
_LABEL = re.compile(r"^\.([A-Za-z_][A-Za-z_0-9.]*)\s*$")
_AUTO = re.compile(r"^([A-Za-z_][A-Za-z_0-9.]*) = &([0-9A-F]+) \[auto\]\s*$")
_MNEMONIC = re.compile(r"^[A-Za-z]{3}\b")


class Line:
    """One listing line: an address if it had one, the bytes it emitted, and
    the source text. `elided` marks a line whose bytes Baron abbreviated with
    "..." (a long INCBIN or EQUS), where `data` is a prefix, not the whole."""

    __slots__ = ("addr", "data", "elided", "text", "n")

    def __init__(self, addr, data, elided, text, n):
        self.addr = addr
        self.data = data
        self.elided = elided
        self.text = text
        self.n = n                      # 1-based line number in the listing

    @property
    def is_instruction(self):
        return bool(self.data) and bool(_MNEMONIC.match(self.text))

    def __repr__(self):
        a = "----" if self.addr is None else "%04X" % self.addr
        return "Line(%s %s %r)" % (a, self.data.hex(" ") if self.data else "", self.text[:32])


def _read(source):
    if isinstance(source, (str, Path)) and "\n" not in str(source):
        p = Path(source)
        if p.exists():
            return p.read_text(encoding="utf-8", errors="replace")
    return source if isinstance(source, str) else str(source)


def parse(source):
    """The listing as a list of Line. `source` is a path or the text."""
    out = []
    for n, raw in enumerate(_read(source).split("\n"), 1):
        m = _ADDR.match(raw)
        if not m:
            out.append(Line(None, b"", False, raw.rstrip(), n))
            continue
        field = raw[BYTES_COL:TEXT_COL]
        elided = "..." in field
        data = bytes(int(b, 16) for b in field.replace(".", " ").split())
        out.append(Line(int(m.group(1), 16), data, elided, raw[TEXT_COL:].rstrip(), n))
    return out


def symbols(source):
    """Every label and ZA_AUTO allocation as name -> [addresses].

    A label takes the address of the next line that carries one, which is how
    Baron lays the listing out. Local labels inside `{ }` scopes repeat -
    `loop` will have many addresses - so the value is a list and the caller
    decides; a top-level name has exactly one.
    """
    lines = parse(source)
    found = {}
    pending = []
    for line in lines:
        auto = _AUTO.match(line.text) if line.addr is None else None
        if auto:
            found.setdefault(auto.group(1), []).append(int(auto.group(2), 16))
            continue
        if line.addr is None:
            m = _LABEL.match(line.text)
            if m:
                pending.append(m.group(1))
            continue
        for name in pending:
            found.setdefault(name, []).append(line.addr)
        pending = []
    return found


def lookup(source, name):
    """The one address of `name`, or None. Raises on an ambiguous local."""
    hits = symbols(source).get(name, [])
    if len(hits) > 1:
        raise ValueError("%s is a local label with %d addresses: %s"
                         % (name, len(hits), ", ".join("&%04X" % a for a in hits)))
    return hits[0] if hits else None


def opcode_stream(source):
    """One entry per emitted instruction or datum, with no addresses in it.

    An instruction becomes `"A9/1"` - its opcode byte and operand length - so
    the same code assembled somewhere else compares EQUAL, while a changed
    instruction does not. A data line becomes `"data:<text>"`, the directive
    as written, because a long one's bytes are elided in the listing anyway.
    """
    stream = []
    for line in parse(source):
        if not line.data:
            continue
        if line.is_instruction:
            stream.append("%02X/%d" % (line.data[0], len(line.data) - 1))
        else:
            stream.append("data:" + " ".join(line.text.split()))
    return stream


def _main(argv):
    if len(argv) < 2 or argv[0] not in ("symbols", "stream"):
        raise SystemExit(
            "usage: python -m beeb_port_kit.listing symbols LISTING [NAME ...]\n"
            "       python -m beeb_port_kit.listing stream  LISTING\n"
            "\n"
            "symbols  every label and ZA_AUTO address; NAME filters (substring)\n"
            "stream   one line per emitted instruction, addresses removed, for\n"
            "         diffing two builds of a change meant to be mechanical")
    what, path, rest = argv[0], argv[1], argv[2:]
    if what == "stream":
        print("\n".join(opcode_stream(path)))
        return
    syms = symbols(path)
    for name in sorted(syms):
        if rest and not any(r.lower() in name.lower() for r in rest):
            continue
        addrs = syms[name]
        print("%-24s %s" % (name, ", ".join("&%04X" % a for a in addrs)))


if __name__ == "__main__":
    import sys
    _main(sys.argv[1:])
