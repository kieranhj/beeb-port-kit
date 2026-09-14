"""
listing.py - read Baron's symbol dump (`--symbols`) and its `-v` listing:
symbol addresses, and the opcode stream that says whether a change was
mechanical.

beeb-port-kit: new with the move to Baron (docs/toolchain-baron.md).

WHY IT EXISTS.
  * ADDRESSES. `docs/verification.md`'s standing rule is "addresses come from
    the build, every time" - main-RAM addresses move on every build, and a
    debugger breakpoint or an emulator memory read against a stale one is a
    measurement of nothing. Zero-page allocation makes this sharper still: a
    ZA_AUTO address is chosen by the assembler and moves when the code
    changes, so the assembler's own output is the ONLY source of truth for it.
  * MECHANICAL CHANGES. `docs/verification.md` procedure 13 proves a change
    meant to be mechanical left the code alone, by reducing two listings to
    one entry per emitted instruction and diffing. Both ports wrote that
    reducer inline each time and neither checked it in. It is checked in now.

TWO INPUTS, AND WHICH TO USE.
  * THE SYMBOL DUMP, `--symbols build/game.symbols.json`, is the one to use
    for addresses. It is what waitingforvsync/baron#5 asked for and it landed
    in 45e5cb8 (2026-09-13): a machine-readable file of every resolved symbol,
    which the listing never was. It carries what the listing could not - a
    computed constant's VALUE (`T1_I2` is `1272` in the dump; the listing used
    to echo `T1_I2 = (FIRE2_LINE - FIRE1_LINE) * SL - 2 + T1_TUNE2`
    unevaluated) - and it is stable, where the listing's layout is not. On the
    template it yields 309 top-level symbols against the listing's 48.
  * THE LISTING, `-v`, is still the input for `opcode_stream()`, which needs
    the emitted bytes. `symbols()` reads it too, and still should when all you
    have is a listing from a build you no longer have the dump for.

BOTH LISTING LAYOUTS PARSE. Baron changed the listing in 45e5cb8: a label now
prints WITH its address (`  1900  .start`), where it used to sit on its own
line and take the address of the next line that carried one, and the byte
field widened from 16 columns to 26. So `parse()` no longer keys off fixed
columns: it reads the address, then matches the byte field as a pattern and
takes what is left as the source text. Listings from either side of that
change read correctly.

That change also FIXED A WRONG ANSWER this file used to give. Under the old
layout a label at the END of a section - `end`, `infofile_end` - took the
address of the next line carrying one, which is the start of the NEXT section:
the template's `end` read as &4A00 (the panel) when it is &1DBE. Addresses
from a dump, or from a listing built with a Baron newer than 45e5cb8, do not
have that hazard. If you are reading an OLD listing, the last label of a
section is the one to distrust.

WHAT THE LISTING LOOKS LIKE (the current layout):

      1900  A2 FF                       ldx #&ff       an instruction
      1AD0  00 0F F0 FF                 EQUB &00, ...  data
      1903                              CRTC 8, R8_BLANK   a macro call
      4A00  FF 00 00 00 00 00 00 00...  INCBIN "..."   long data, bytes elided
      1900  .start                                     a label, with its address
    zxsrc = &00 [auto]                                 a ZA_AUTO allocation

WHAT THE DUMP LOOKS LIKE: `{"<source file>": {"<name>": <value>, ...}}`, one
object per source file, values already resolved (numbers, strings, booleans).
A name inside a `{ }` scope is qualified with the scope's own key, e.g.
`"@0:19724.zx_copy"`; `symbols()` reduces those to the leaf name, so a local
label is found the same way it is in a listing - as a name with several
addresses, which `lookup()` then refuses to guess between.

Verified against the template's own build, 2026-09-14 (py/tests/test_listing.py):
the dump agrees with the listing on all 48 symbols the listing has, bar the two
end-of-section labels the OLD listing got wrong.
"""

import json
import re
from pathlib import Path

ADDR_COL = 2
BYTES_COL = 8

_ADDR = re.compile(r"^  ([0-9A-F]{4})  ")
# The byte field, wherever the text column happens to sit: hex pairs, an
# optional "..." where Baron elided a long one, then TWO spaces or end of line.
# Two, so that source text which happens to open with hex-shaped letters (a
# macro call `FADE 1`) is not mistaken for emitted bytes.
_BYTES = re.compile(r"^([0-9A-F]{2}(?: [0-9A-F]{2})*(?:\.\.\.)?)(?:  |$)")
_LABEL = re.compile(r"^\.([A-Za-z_][A-Za-z_0-9.]*)\s*$")
_AUTO = re.compile(r"^([A-Za-z_][A-Za-z_0-9.]*) = &([0-9A-F]+) \[auto\]\s*$")
_MNEMONIC = re.compile(r"^[A-Za-z]{3}\b")
# The scope qualifiers Baron puts on a name in the dump: "@0:19724.", nested.
_SCOPE = re.compile(r"^(?:@\d+:\d+\.)+")


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
        rest = raw[BYTES_COL:]
        m2 = _BYTES.match(rest)
        field = m2.group(1) if m2 else ""      # a label line emits no bytes
        elided = field.endswith("...")
        data = bytes(int(b, 16) for b in field.replace(".", " ").split())
        text = rest[len(field):].strip()
        out.append(Line(int(m.group(1), 16), data, elided, text, n))
    return out


def is_dump(source):
    """True if `source` is Baron's `--symbols` JSON rather than a listing."""
    if isinstance(source, (str, Path)) and "\n" not in str(source):
        if str(source).lower().endswith(".json"):
            return True
    return _read(source).lstrip().startswith("{")


def values(source):
    """Every symbol in a `--symbols` dump as name -> [values], values as Baron
    resolved them: numbers, but also the strings and booleans a listing could
    never have shown. Names inside a `{ }` scope keep only their leaf name."""
    doc = json.loads(_read(source))
    found = {}

    def add(name, value):
        seen = found.setdefault(name, [])
        if value not in seen:                    # macro expansions repeat
            seen.append(value)

    for syms in doc.values():
        for key in sorted(syms):
            name = _SCOPE.sub("", key)
            add(name, syms[key])
            if "." in name:
                # A NAMED scope qualifies its labels - `rupt_timer.done`. Keep
                # the qualified name, which resolves exactly, AND the leaf, so
                # that asking for `done` still sees every `done` there is and
                # `lookup()` still refuses to pick one.
                add(name.rsplit(".", 1)[1], syms[key])
    return found


def symbols(source):
    """Every symbol as name -> [addresses], from a dump or from a listing.

    From a dump that is every resolved symbol with a numeric value - labels,
    constants and ZA_AUTO allocations alike. From a listing it is what the
    listing shows: labels and ZA_AUTO allocations.

    A name inside a `{ }` scope repeats - `loop` will have many addresses - so
    the value is a list and the caller decides; a top-level name has exactly
    one.
    """
    if is_dump(source):
        return {name: [v for v in vs if isinstance(v, int) and not isinstance(v, bool)]
                for name, vs in values(source).items()
                if any(isinstance(v, int) and not isinstance(v, bool) for v in vs)}
    found = {}
    pending = []
    for line in parse(source):
        auto = _AUTO.match(line.text) if line.addr is None else None
        if auto:
            found.setdefault(auto.group(1), []).append(int(auto.group(2), 16))
            continue
        m = _LABEL.match(line.text)
        if line.addr is None:
            if m:
                # A listing from before Baron 45e5cb8: the label takes the
                # address of the next line that carries one.
                pending.append(m.group(1))
            continue
        if m:
            found.setdefault(m.group(1), []).append(line.addr)
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

    A listing only: the dump has no bytes in it.
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


def _format(value):
    if isinstance(value, bool) or not isinstance(value, int):
        return repr(value)
    return "&%04X" % value


def _main(argv):
    if len(argv) < 2 or argv[0] not in ("symbols", "stream"):
        raise SystemExit(
            "usage: python -m beeb_port_kit.listing symbols DUMP|LISTING [NAME ...]\n"
            "       python -m beeb_port_kit.listing stream  LISTING\n"
            "\n"
            "symbols  every symbol and its value; NAME filters (substring).\n"
            "         Prefer build/game.symbols.json (baron --symbols): it has\n"
            "         computed constants too, which a listing does not.\n"
            "stream   one line per emitted instruction, addresses removed, for\n"
            "         diffing two builds of a change meant to be mechanical")
    what, path, rest = argv[0], argv[1], argv[2:]
    if what == "stream":
        print("\n".join(opcode_stream(path)))
        return
    syms = values(path) if is_dump(path) else symbols(path)
    for name in sorted(syms):
        if rest and not any(r.lower() in name.lower() for r in rest):
            continue
        print("%-24s %s" % (name, ", ".join(_format(v) for v in syms[name])))


if __name__ == "__main__":
    import sys
    _main(sys.argv[1:])
