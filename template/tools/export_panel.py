#!/usr/bin/env python3
"""
export_panel.py - the template's one data file: src/data/panel.bin

A 4-row MODE 1 status panel, 2,560 bytes (4 rows x 640), as a generated
pattern of coloured bars. It stands in for the port's panel image so the
loader, the ZX0 stream, the catalogue rewrite and the rupture's cycle A all
have something real to carry; the port replaces this with its exporter for
the original's artwork (beeb-port-kit PORTING.md, Layer 1).

The pattern is chosen to be checkable by eye and by bytes: vertical bars of
the four MODE 1 logical colours, five CRTC units (20 px) wide, shifted one
bar per character row so the four rows differ, and a line of logical 3 along
the top scanline of row 0 and the second-to-last scanline of row 3 so the
panel's edges are visible. Under the panel's own palette (decision 4:
black, red, yellow, white) the bars are those four and the edges white; the
play strip below it is in the other four (blue, magenta, cyan, green).

THE LAST SCANLINE OF ROW 3 IS ALL LOGICAL 0 AND MUST STAY SO. It is the
line the rupture's palette switch straddles: the switch is sixteen ULA
writes (96 cycles) against 48 cycles of horizontal blanking, so twelve of
them land in this line's DISPLAYED part. Those twelve are logicals 1-3,
which a line of logical 0 never looks up; the four for logical 0 land in
its blanking. Any other colour on this line would show the switch as a
glitch at the beam (src/rupture.asm, docs/layer-0-toolchain.md). It reads
as black, the panel's colour 0.

MODE 1 byte layout (beeb-port-kit docs/hardware-facts.md, measured): four
pixels a byte, the pixel's colour bit 1 in the high nibble and bit 0 in the
low nibble, pixel 0 in bits 7 and 3. A byte of four pixels of colour c is
therefore &00, &0F, &F0 or &FF for c = 0..3. A character cell is 8 bytes:
its eight scanlines, one byte each; cells are 8 bytes apart along a row
and rows are 640 bytes apart.

Usage: python tools/export_panel.py            (writes src/data/panel.bin)
       python tools/export_panel.py --check    (reports, writes nothing)
"""

import sys
from pathlib import Path

ROWS = 4
UNITS = 80                       # CRTC units across; R1 = 80
UNIT_BYTES = 8
ROW_BYTES = UNITS * UNIT_BYTES   # 640
PANEL_BYTES = ROWS * ROW_BYTES   # 2,560
BAR_UNITS = 5                    # 20 px a bar

SOLID = (0x00, 0x0F, 0xF0, 0xFF)  # four pixels of logical 0, 1, 2, 3


def panel():
    out = bytearray(PANEL_BYTES)
    for row in range(ROWS):
        for unit in range(UNITS):
            colour = (unit // BAR_UNITS + row) & 3
            base = row * ROW_BYTES + unit * UNIT_BYTES
            for scan in range(8):
                out[base + scan] = SOLID[colour]
            if row == 0:
                out[base + 0] = SOLID[3]          # top edge, white
            if row == ROWS - 1:
                out[base + 6] = SOLID[3]          # bottom edge, white
                out[base + 7] = SOLID[0]          # the straddle line: ALL logical 0
    return bytes(out)


def main():
    data = panel()
    assert len(data) == PANEL_BYTES
    last = (ROWS - 1) * ROW_BYTES
    assert all(data[last + u * UNIT_BYTES + 7] == 0 for u in range(UNITS)),         "the panel's last scanline must be all logical 0 (the palette straddle line)"
    dest = Path(__file__).resolve().parent.parent / "src" / "data" / "panel.bin"
    if "--check" in sys.argv[1:]:
        print(f"panel: {len(data)} bytes, {ROWS} rows x {ROW_BYTES}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    print(f"wrote {dest} ({len(data)} bytes)")


if __name__ == "__main__":
    main()
