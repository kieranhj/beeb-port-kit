#!/usr/bin/env python3
"""
make_disc_example.py - the shape of a project's make_disc.py on top of
beeb_port_kit.dfs: beebasm's SSD in, the shipping SSD out, with the data
files ZX02-compressed and the catalogue rewritten to where the loader stages
each stream.

Both ports' make_disc.py are this with longer tables. What is the PROJECT's,
and stays here rather than in dfs.py:

  * COMPRESSED: which files ship packed, where main.asm's loader *LOADs
    each stream, and where it unpacks to. All three numbers must match the
    loader; the stream address is what the catalogue's load address becomes.
  * STREAM_TOP: the address each staging area may not reach.
  * LAYOUT: boot ACCESS order, so the head never seeks backwards. beebasm's
    own order is SAVE-statement order.
  * the list of files the loader reads, whose absence is an error.

Usage: python make_disc_example.py RAW.SSD OUT.SSD [PADDED.SSD]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from beeb_port_kit import dfs  # noqa: E402

# Both must match src/main.asm.
DEPK_STREAM = 0x3000            # streams stage in the screen, before the mode change
UNPACK_BANK = 0x8000            # and unpack into a sideways RAM bank

COMPRESSED = {                  # name: (stream address, unpack destination)
    "BANK0": (DEPK_STREAM, UNPACK_BANK),
    "BANK1": (DEPK_STREAM, UNPACK_BANK),
}
STREAM_TOP = {DEPK_STREAM: 0x8000}
LAYOUT = ["!BOOT", "GAME", "BANK0", "BANK1"]

ZX02_CANDIDATES = [Path(__file__).parent / "bin" / "zx02.exe",
                   Path(r"C:\Users\khcon\OneDrive\BEEB\Bin\zx02.exe")]


def main(argv):
    if len(argv) < 2:
        raise SystemExit(__doc__)
    raw_path, out_path = Path(argv[0]), Path(argv[1])
    padded_path = Path(argv[2]) if len(argv) > 2 else None

    exe = dfs.find_exe(ZX02_CANDIDATES)             # None -> zx02.py, slower
    img = dfs.read_image(raw_path)
    missing = [n for n in LAYOUT if n not in img.files]
    if missing:
        raise SystemExit(f"{raw_path} lacks {missing} - the loader and the disc "
                         "would disagree")

    report = []
    for name, (stream, dest) in COMPRESSED.items():
        entry = img.files[name]
        raw = entry.data
        packed = dfs.compress(raw, exe, name)
        info = dfs.check_stream(name, stream, packed, dest, raw,
                                top=STREAM_TOP[stream])
        entry.replace(packed, load=stream, exec=stream)
        report.append("  %-7s %6d -> %6d  stream %#06x, %d B of headroom"
                      % (name, len(raw), len(packed), stream, info["headroom"]))

    out = dfs.build_image(img.files, LAYOUT, img.title, img.cycle, img.opt)
    out_path.write_bytes(out)
    if padded_path:
        padded_path.write_bytes(dfs.pad(out))
    print("make_disc: ZX02")
    print("\n".join(report))
    print("  image   %6d -> %6d" % (raw_path.stat().st_size, len(out)))


if __name__ == "__main__":
    main(sys.argv[1:])
