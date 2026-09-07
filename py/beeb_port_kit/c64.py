"""
c64.py - reading the Commodore 64 side of a port: the Pepto palette, hires
and multicolour byte decoding, 24x21 sprite blocks, 8x8 charsets, and the
byte tables in an assembler source or an IDA listing.

beeb-port-kit: from
  https://github.com/kieranhj/edge-beeb/blob/master/tools/bbc.py
      C64_RGB (Pepto), c64_pixels (multicolour), load_chars/tiles/map/sprites,
      parse_c64_table (ACME `!byte` under a label)
  https://github.com/kieranhj/edge-beeb/blob/master/tools/export_waves.py
      byte_values: the same, with `$xx + n` sums and decimal operands
  https://github.com/kieranhj/paradroid-beeb/blob/main/tools/export_bbc.py
      the hires decode (a set bit takes the cell's colour, a clear one the
      background)
  https://github.com/kieranhj/paradroid-beeb/blob/main/tools/rip_graphics.py
  https://github.com/kieranhj/paradroid-beeb/blob/main/tools/export_title.py
      parse_listing: an IDA `.BYTE` listing into a 64K memory image, with
      the running offset a continuation line needs
Proven: Edge's 256 characters, 211 tiles, 302-column map and 119 sprite
frames and Paradroid's charset, 16 decks and title screen all came through
these readers, and each port's reference renders (reference/*.png) are
byte-for-byte what the C64 shows. Fork this into your project's tools/;
keep this header.

Multicolour: a byte is four 2-bit pixels, each twice the width of a hires
pixel. Bit pair 00 is the background ($d021), 01 and 10 the shared colours
($d022/$d023 for characters, $d025/$d026 for sprites - NOTE the sprite order
differs: 01 is $d025, 11 is $d026 and 10 is the sprite's own colour), 11 the
per-cell colour (colour RAM's low 3 bits for characters). The decoders here
return the raw pair values; the caller applies its own game's register
values, because they are the game's, not the machine's.
"""

import re

# Pepto's palette, the one every C64 reference render in both ports uses.
C64_RGB = [
    (0x00, 0x00, 0x00), (0xFF, 0xFF, 0xFF), (0x68, 0x37, 0x2B), (0x70, 0xA4, 0xB2),
    (0x6F, 0x3D, 0x86), (0x58, 0x8D, 0x43), (0x35, 0x28, 0x79), (0xB8, 0xC7, 0x6F),
    (0x6F, 0x4F, 0x25), (0x43, 0x39, 0x00), (0x9A, 0x67, 0x59), (0x44, 0x44, 0x44),
    (0x6C, 0x6C, 0x6C), (0x9A, 0xD2, 0x84), (0x6C, 0x5E, 0xB5), (0x95, 0x95, 0x95),
]
C64_NAMES = ["black", "white", "red", "cyan", "purple", "green", "blue", "yellow",
             "orange", "brown", "light red", "dark grey", "mid grey",
             "light green", "light blue", "light grey"]

SPRITE_BYTES = 64          # 63 of bitmap plus a pad byte
SPRITE_ROWS = 21
SPRITE_WIDTH = 24          # hires pixels; 12 multicolour


def hires_pixels(byte):
    """Eight 1-bit pixels from one bitmap byte, left to right."""
    return [(byte >> (7 - i)) & 1 for i in range(8)]


def multicolour_pixels(byte):
    """Four bit-pair values (0-3) from one bitmap byte, left to right."""
    return [(byte >> (6 - 2 * i)) & 3 for i in range(4)]


c64_pixels = multicolour_pixels      # Edge's name


def decode_char(rows, multicolour=False):
    """An 8-byte character as 8 rows of 8 (hires) or 4 (multicolour) values."""
    f = multicolour_pixels if multicolour else hires_pixels
    return [f(b) for b in rows[:8]]


def decode_sprite(block, multicolour=False):
    """A 63/64-byte sprite as 21 rows of 24 (hires) or 12 (multicolour) values.
    Each row is three bytes, left to right."""
    f = multicolour_pixels if multicolour else hires_pixels
    rows = []
    for r in range(SPRITE_ROWS):
        row = []
        for b in block[r * 3:r * 3 + 3]:
            row += f(b)
        rows.append(row)
    return rows


def strip_load_address(data):
    """A PRG's two-byte load address removed; returns (address, data)."""
    return data[0] | (data[1] << 8), bytes(data[2:])


def read_charset(data, count=256):
    """`count` characters of 8 bytes each from a raw charset dump."""
    data = bytes(data)
    if len(data) < count * 8:
        raise ValueError(f"charset holds {len(data) // 8} characters, wanted {count}")
    return [data[i * 8:(i + 1) * 8] for i in range(count)]


def read_sprites(data, count=None):
    """`count` 63-byte sprite blocks from a raw 64-byte-per-sprite dump."""
    data = bytes(data)
    count = len(data) // SPRITE_BYTES if count is None else count
    if len(data) < count * SPRITE_BYTES:
        raise ValueError(f"sprite dump holds {len(data) // SPRITE_BYTES} frames, "
                         f"wanted {count}")
    return [data[i * SPRITE_BYTES:i * SPRITE_BYTES + 63] for i in range(count)]


def read_table(data, entry_size, count=None):
    """A flat table cut into `count` entries of `entry_size` bytes - a tile
    table (16 a tile), a column-major map (rows a column), and so on."""
    data = bytes(data)
    count = len(data) // entry_size if count is None else count
    if len(data) < count * entry_size:
        raise ValueError(f"table holds {len(data) // entry_size} entries, wanted {count}")
    return [list(data[i * entry_size:(i + 1) * entry_size]) for i in range(count)]


# --- assembler sources ----------------------------------------------------

def _read_text(path):
    with open(path, encoding="latin-1") as f:
        return f.read()


def _operand(term, consts):
    """One operand: `$xx`, decimal, a known constant, or `a + b` sums of them."""
    total = 0
    for part in term.split("+"):
        part = part.strip()
        if not part:
            continue
        if part.startswith("$"):
            total += int(part[1:], 16)
        elif part.startswith("0x"):
            total += int(part, 16)
        elif part.isdigit():
            total += int(part)
        elif part in consts:
            total += consts[part]
        else:
            raise ValueError(f"cannot read operand {term!r}")
    return total & 0xFF


def constants(text):
    """`name = $xx` assignments in an ACME/TASS source, name -> value."""
    return {name: int(value, 16)
            for name, value in re.findall(r"^(\w+)\s*=\s*\$([0-9a-fA-F]+)", text, re.M)}


_DIRECTIVES = (r"!byte", r"!by", r"\.byte", r"\.BYTE", r"dc\.b", r"db")
_BYTE_RE = re.compile(r"(?<![\w.])(?:" + "|".join(_DIRECTIVES) + r")\s+([^;]*)")


def parse_c64_table(source, label, count=None, consts=None):
    """The byte operands under `label` in an assembler source, until the
    next top-level label (one starting at column 0). ACME `!byte`, TASS
    `.byte`/`.BYTE`, and `dc.b`/`db` all count; comments after `;` do not.

    `source` is a path or the text itself. With `count`, exactly that many
    are returned and fewer is an error - the shape both ports relied on,
    because a table that comes up short is a label that moved.
    """
    text = source if "\n" in source else _read_text(source)
    consts = constants(text) if consts is None else consts
    lines = text.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if re.match(rf"^{re.escape(label)}\b", l))
    except StopIteration:
        raise ValueError(f"label {label!r} not found") from None
    out = []
    for i in range(start, len(lines)):
        line = lines[i]
        if i > start and re.match(r"^\w+", line):
            break                # a new top-level label, even one with !byte
                                 # on the same line
        m = _BYTE_RE.search(line)
        if not m:
            continue
        out += [_operand(t, consts) for t in m.group(1).split(",") if t.strip()]
        if count is not None and len(out) >= count:
            break
    if count is not None:
        if len(out) < count:
            raise ValueError(f"{label}: {len(out)} bytes, wanted {count}")
        return out[:count]
    return out


_MNEMONIC = re.compile(
    r"\b(LDA|STA|LDX|STX|LDY|STY|JSR|JMP|RTS|RTI|BEQ|BNE|BPL|BMI|BCS|BCC|BVS|BVC"
    r"|CLC|SEC|CLI|SEI|NOP|PHA|PLA|TAX|TAY|TXA|TYA|TSX|TXS|INX|INY|DEX|DEY|INC|DEC"
    r"|ADC|SBC|AND|ORA|EOR|CMP|CPX|CPY|ASL|LSR|ROL|ROR|BIT|PHP|PLP|BRK|SED|CLD|CLV)\b")


def parse_listing(source):
    """An IDA-style listing (`ADDR ... .BYTE v, v, ...` lines) as a 64K
    memory image plus a 64K 'filled' map.

    A .BYTE block carries its address on the FIRST line only and continues on
    the ones after it, so the running offset is not optional: without it every
    continuation line lands back on the block's own address and a 1,000-byte
    screen reads as one character repeated. Only an instruction line resets
    the base; IDA's comment and cross-reference lines inside a block do not.
    """
    text = source if "\n" in source else _read_text(source)
    mem = bytearray(65536)
    filled = bytearray(65536)
    current_base = None
    running_offset = 0
    for line in text.splitlines():
        m = re.match(r"^([0-9A-Fa-f]{4})\s", line)
        if not m:
            continue
        addr = int(m.group(1), 16)
        bm = re.search(r"\.BYTE\s+(.*)", line)
        if not bm:
            if _MNEMONIC.search(line):
                current_base = None
            continue
        vals = []
        for v in re.sub(r";.*", "", bm.group(1)).split(","):
            v = v.strip()
            if not v:
                continue
            try:
                vals.append(int(v[1:], 16) if v.startswith("$") else int(v))
            except ValueError:
                break
        if not vals:
            continue
        if current_base is None or addr != current_base:
            current_base = addr
            running_offset = 0
        base = current_base + running_offset
        for i, v in enumerate(vals):
            mem[(base + i) & 0xFFFF] = v & 0xFF
            filled[(base + i) & 0xFFFF] = 1
        running_offset += len(vals)
    return mem, filled
