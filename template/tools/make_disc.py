#!/usr/bin/env python3
"""
make_disc.py - post-process the assembler's SSD into the disc image that boots.

The assembler SAVEs every file uncompressed; this tool rewrites the image so
that the data file(s) ship ZX02-compressed, with the catalogue load address
moved to the staging address the loader in src/main.6502 expects, and lays
the files out physically in BOOT ACCESS ORDER so the head never seeks
backwards during a load.

THE RAW IMAGE IS NOT BOOTABLE. load_stream / unpack_to run the depacker over
every file they load, so the loader only works on this tool's output: hand
build/game.ssd to an emulator, never build/game-raw.ssd.

PADDED is optional and the build scripts do not ask for it. Emulators do not
need a full-size image - jsbeeb stopped complaining in 1.9.0, and the kit
booted this template's 2,304-byte image on both models to check (2026-09-07,
../../docs/hardware-facts.md). Pad when you PUBLISH, so that a released size
differing from the last release is a signal.

Modelled on edge-beeb's tools/make_disc.py, on top of the kit's dfs.py
(forked into this directory beside zx02.py). What is the PROJECT's, and stays
here rather than in dfs.py: the COMPRESSED table (which file stages where
and unpacks to where), STREAM_TOP (what each staging area may not reach) and
LAYOUT (the boot access order). All three must agree with src/main.6502.

ONE COMPRESSOR, NOT WHICHEVER IS FOUND. ZX02 (Daniel Serpell's 6502-tuned
fork of ZX0 - half the depacker and twice the speed for +0.11% on the packed
size; tools/zx02.py has the measurements), built from the source vendored in
tools/zx02src/. It is found as --zx02, then $ZX02, then bin/zx02 (make builds
it there), then zx02 on the PATH - and if none exists the build STOPS. It
used to fall back to the Python port, which ends one byte shorter than the
reference on some inputs, so the image depended on what was installed
(tools/zx02src/VENDORED.md). tools/zx02.py is still the oracle: every stream
is round-tripped through zx02.decompress before it is written, so a
compressor or flag change fails the build rather than the boot.

The output is written through a temporary file, and its SHA256 printed: that
is the number to compare with another machine's build of the same commit.

Usage: python tools/make_disc.py [--zx02 PATH] RAW.ssd OUT.ssd [PADDED.ssd]
"""

import hashlib
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import dfs                                          # noqa: E402

# ---- the project's tables: must match src/main.6502 ---------------------
LOADER_STAGE = 0x3000           # LOADER_STAGE in main.6502: the blanked screen
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


def find_zx02(requested):
    """The compressor to run. shutil.which adds `.exe` on Windows, so no
    name here carries one."""
    for name in (requested, os.environ.get("ZX02")):
        if name:
            found = shutil.which(name)
            if not found:
                raise SystemExit(f"make_disc: no compressor at {name!r}")
            return Path(found)
    found = shutil.which(str(ROOT / "bin" / "zx02")) or shutil.which("zx02")
    if not found:
        raise SystemExit(
            "make_disc: no zx02 compressor. `make` builds bin/zx02 from "
            "tools/zx02src/; build.ps1 does the same when a C compiler is on "
            "the PATH; or set ZX02 to one built from the same source.")
    return Path(found)


def write_atomic(path, data):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def main():
    argv = sys.argv[1:]
    requested = None
    if argv[:1] == ["--zx02"] and len(argv) > 1:
        requested, argv = argv[1], argv[2:]
    if len(argv) < 2:
        raise SystemExit(__doc__)
    raw_path, out_path = Path(argv[0]), Path(argv[1])
    padded_path = Path(argv[2]) if len(argv) > 2 else None

    zx02_exe = find_zx02(requested)
    img = dfs.read_image(raw_path)
    missing = [n for n in LAYOUT if n not in img.files]
    if missing:
        raise SystemExit(f"{raw_path} lacks {missing} - the loader and the "
                         "disc would disagree")

    report = []
    for name, (stream, dest) in COMPRESSED.items():
        entry = img.files[name]
        raw = entry.data
        packed = dfs.compress(raw, zx02_exe, name)         # round-trip checked
        info = dfs.check_stream(name, stream, packed, dest, raw,
                                top=STREAM_TOP[stream])   # refuses an overlap
        entry.replace(packed, load=stream, exec=stream)
        report.append("  %-7s %6d -> %6d  stream %#06x -> %#06x, %d B of headroom"
                      % (name, len(raw), len(packed), stream, dest,
                         info["headroom"]))

    # Every file loads and runs in the HOST, second processor or not
    # (dfs.to_host says why; the loader's own OSFILE block does the same).
    dfs.to_host(img.files)
    out = dfs.build_image(img.files, LAYOUT, img.title, img.cycle, img.opt)
    write_atomic(out_path, out)
    if padded_path:
        write_atomic(padded_path, dfs.pad(out))

    print("make_disc: ZX02 via %s" % zx02_exe)
    print("\n".join(report))
    print("  image   %6d -> %6d%s" % (len(raw_path.read_bytes()), len(out),
                                    f", padded {dfs.DISC_200K}" if padded_path else ""))
    print("  sha256  %s  %s" % (hashlib.sha256(out).hexdigest(), out_path.name))


if __name__ == "__main__":
    main()
