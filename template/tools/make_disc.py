#!/usr/bin/env python3
"""
make_disc.py - post-process beebasm's SSD into the disc image that boots.

beebasm assembles and SAVEs every file uncompressed; this tool rewrites the
image so that the data file(s) ship ZX0-compressed, with the catalogue load
address moved to the staging address the loader in src/main.asm expects,
and lays the files out physically in BOOT ACCESS ORDER so the head never
seeks backwards during a load. It then pads a copy to 200K for emulators.

THE RAW IMAGE IS NOT BOOTABLE. load_stream / unpack_to run the depacker over
every file they load, so the loader only works on this tool's output: hand
build/GAME.SSD (or the padded copy) to an emulator, never build/GAME-RAW.SSD.

Modelled on edge-beeb's tools/make_disc.py, on top of the kit's dfs.py
(forked into this directory beside zx0.py). What is the PROJECT's, and stays
here rather than in dfs.py: the COMPRESSED table (which file stages where
and unpacks to where), STREAM_TOP (what each staging area may not reach) and
LAYOUT (the boot access order). All three must agree with src/main.asm.

The compressor is the reference zx0.exe (Einar Saukas) if one is found in
bin/ or the shared BEEB/Bin/, else the pure-Python zx0.compress (identical
output, seconds rather than milliseconds on a 16K bank). Either way the
stream is round-tripped through zx0.decompress before it is written.

Usage: python tools/make_disc.py RAW.SSD OUT.SSD [PADDED.SSD]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import dfs                                          # noqa: E402

# ---- the project's tables: must match src/main.asm ----------------------
LOADER_STAGE = 0x3000           # LOADER_STAGE in main.asm: the blanked screen
PANEL_ADDR = 0x4A00             # where PANEL unpacks to

# name -> (where the loader *LOADs the stream, where it unpacks to)
COMPRESSED = {
    "PANEL": (LOADER_STAGE, PANEL_ADDR),
}

# the address a stream staged at each staging address may not reach
STREAM_TOP = {LOADER_STAGE: PANEL_ADDR}

# boot access order: !BOOT, the code, then the data in the order it is loaded
LAYOUT = ["!BOOT", "Game", "PANEL"]

ROOT = Path(__file__).resolve().parent.parent
ZX0_CANDIDATES = [ROOT / "bin" / "zx0.exe",
                  Path(r"C:\Users\khcon\OneDrive\BEEB\Bin\zx0.exe"),
                  ROOT / ".." / ".." / "Bin" / "zx0.exe"]


def main():
    argv = sys.argv[1:]
    if len(argv) < 2:
        raise SystemExit(__doc__)
    raw_path, out_path = Path(argv[0]), Path(argv[1])
    padded_path = Path(argv[2]) if len(argv) > 2 else None

    zx0_exe = dfs.find_zx0_exe(ZX0_CANDIDATES)
    img = dfs.read_image(raw_path)
    missing = [n for n in LAYOUT if n not in img.files]
    if missing:
        raise SystemExit(f"{raw_path} lacks {missing} - the loader and the "
                         "disc would disagree")

    report = []
    for name, (stream, dest) in COMPRESSED.items():
        entry = img.files[name]
        raw = entry.data
        packed = dfs.compress(raw, zx0_exe, name)          # round-trip checked
        info = dfs.check_stream(name, stream, packed, dest, raw,
                                top=STREAM_TOP[stream])   # refuses an overlap
        entry.replace(packed, load=stream, exec=stream)
        report.append("  %-7s %6d -> %6d  stream %#06x -> %#06x, %d B of headroom"
                      % (name, len(raw), len(packed), stream, dest,
                         info["headroom"]))

    out = dfs.build_image(img.files, LAYOUT, img.title, img.cycle, img.opt)
    out_path.write_bytes(out)
    if padded_path:
        padded_path.write_bytes(dfs.pad(out))

    print("make_disc: ZX0 via %s" % (zx0_exe if zx0_exe else "tools/zx0.py (no zx0.exe found)"))
    print("\n".join(report))
    print("  image   %6d -> %6d%s" % (len(raw_path.read_bytes()), len(out),
                                    f", padded {dfs.DISC_200K}" if padded_path else ""))


if __name__ == "__main__":
    main()
