#!/usr/bin/env python3
"""
bench_depack.py - what ZX02 costs against ZX0, measured rather than quoted.

This is the harness behind the numbers in lib/zx02depack.6502 and py/zx02.py.
It assembles both depackers with Baron, compresses each file you name with
both compressors, steps both decodes through a 6502 simulator (py65), CHECKS
THE OUTPUT AGAINST THE SOURCE FILE BYTE FOR BYTE, and prints packed size and
cycles per output byte for each.

    pip install py65
    python lib/test/bench/bench_depack.py FILE [FILE ...]      # from the kit root

Needs, and says so if it cannot find them: baron, zx0.exe (Einar Saukas) and
zx02.exe (https://github.com/dmsc/zx02/releases). Paths below, or set BARON,
ZX0_EXE and ZX02_EXE.

WHAT IT SAID, 2026-09-07, over 43 data files from the two shipping ports -
sprites, tiles, chars, music, loading screens, panels, 242,481 bytes:

    depacker size   ZX0 257 bytes      ZX02 131 bytes
    cycles/byte     ZX0 115.4          ZX02  53.9        2.14x
    packed total    ZX0 90,793         ZX02 90,891       +0.11%

No file in that corpus was outside 2.04x..2.19x. The ratio loss is under 1%
per file except on data that is nearly all one repeated run, where ZX02's
8-bit gamma tells: a near-empty 2,560-byte panel went 67 -> 79 bytes.

The cycle counts are the decode ALONE, from the JSR to the RTS. They are not
comparable with a figure taken by timing a whole load in an emulator, which
is what the 40k-cycles-per-1K note in docs/hardware-facts.md is.
"""

import os
import subprocess
import sys
from pathlib import Path

try:
    from py65.devices.mpu6502 import MPU
except ImportError:
    raise SystemExit("bench_depack: needs py65 (pip install py65)")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent                  # the kit root
BUILD = HERE / "build"

BARON = Path(os.environ.get("BARON", r"C:\Users\khcon\OneDrive\BEEB\Bin\baron.exe"))
ZX0_EXE = Path(os.environ.get("ZX0_EXE", r"C:\Users\khcon\OneDrive\BEEB\Bin\zx0.exe"))
ZX02_EXE = Path(os.environ.get("ZX02_EXE", r"C:\Users\khcon\OneDrive\BEEB\Bin\zx02.exe"))

CODE = 0x2000                   # the harness, ~0x150 bytes
STREAM = 0x2400                 # the packed stream
OUT = 0x8000                    # the output; a 16K file fits under 0xC000
PROLOGUE = 23                   # the harness's own bytes, before the depacker


def assemble(harness, out_name):
    """Baron writes each named section into -p's directory, under the section's
    own filename - so the harnesses' sections are named ZX0 and ZX02."""
    r = subprocess.run([str(BARON), "-p", str(BUILD),
                        "-D", "STREAM=&%04X" % STREAM, "-D", "OUT=&%04X" % OUT,
                        str(harness)],
                       cwd=ROOT, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("bench_depack: baron failed\n" + r.stdout + r.stderr)
    return (BUILD / out_name).read_bytes()


def run(code, stream, expect):
    """Step the depacker over `stream`; return (cycles, output == expect).
    The harness RTSes with a bare stack, so the PC lands on 0x0000: that is
    the stop condition."""
    mpu = MPU()
    mem = mpu.memory
    mem[CODE:CODE + len(code)] = list(code)
    mem[STREAM:STREAM + len(stream)] = list(stream)
    mpu.pc = CODE
    mpu.sp = 0xFD
    mem[0x01FF] = mem[0x01FE] = 0xFF
    steps = 0
    while (mpu.pc & 0xFFFF) and steps < 40_000_000:
        mpu.step()
        steps += 1
    return mpu.processorCycles, bytes(mem[OUT:OUT + len(expect)]) == expect


def pack(exe, path, dst):
    if dst.exists():
        dst.unlink()
    subprocess.run([str(exe), "-f", str(path), str(dst)], check=True, capture_output=True)
    return dst.read_bytes()


def main(files):
    for tool in (BARON, ZX0_EXE, ZX02_EXE):
        if not tool.exists():
            raise SystemExit(f"bench_depack: {tool} not found (see this file's header)")
    BUILD.mkdir(parents=True, exist_ok=True)
    zx0_code = assemble(HERE / "harness_zx0.6502", "ZX0")
    zx02_code = assemble(HERE / "harness_zx02.6502", "ZX02")
    print("depacker size: zx0 %d bytes, zx02 %d bytes"
          % (len(zx0_code) - PROLOGUE, len(zx02_code) - PROLOGUE))
    print("%-26s%7s%7s%7s%10s%10s%9s" % ("file", "raw", "zx0 B", "zx02 B",
                                         "zx0 c/B", "zx02 c/B", "speedup"))
    t_raw = t0 = t2 = c0 = c2 = 0
    for f in files:
        f = Path(f)
        raw = f.read_bytes()
        s0 = pack(ZX0_EXE, f, BUILD / "t.zx0")
        s2 = pack(ZX02_EXE, f, BUILD / "t.zx02")
        cyc0, ok0 = run(zx0_code, s0, raw)
        cyc2, ok2 = run(zx02_code, s2, raw)
        if not (ok0 and ok2):
            raise SystemExit(f"bench_depack: {f.name} DECODED WRONG "
                             f"(zx0 ok={ok0}, zx02 ok={ok2})")
        t_raw += len(raw); t0 += len(s0); t2 += len(s2); c0 += cyc0; c2 += cyc2
        print("%-26s%7d%7d%7d%10.1f%10.1f%8.2fx"
              % (f.name[:25], len(raw), len(s0), len(s2),
                 cyc0 / len(raw), cyc2 / len(raw), cyc0 / cyc2))
    print("%-26s%7d%7d%7d%10.1f%10.1f%8.2fx"
          % ("TOTAL", t_raw, t0, t2, c0 / t_raw, c2 / t_raw, c0 / c2))
    print("packed size: zx02 is %+.2f%% of zx0" % (100.0 * (t2 - t0) / t0))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
