#!/usr/bin/env python3
"""beebjit_shot.py -- boot a disc in beebjit, a screenshot after a settle and after each key.

beeb-port-kit template, MIT, Kieran Connell 2026. From the phX port, 2026-11.

    python tools/beebjit_shot.py DISC OUT.png [--seconds 12] [--model master|b] [KEY ...]

beebjit is the SECOND OPINION beside jsbeeb, and for a 2 MHz mode with the teletext bit it is
the one that models the MA13 addressing quirk ("MA6 is xor'ed with the 1MHz clock", its video.c,
measured from LinearTTX.ssd on a real Master), which jsbeeb's pin did not (phX docs/hwtest.md
"J"). A picture that differs between the two is a question for the real machine, not an answer.

Needs the beebjit-mcp driver (its Python package `beebjit_mcp`: importable, or its src/ directory
in $BEEBJIT_MCP_SRC) and a headless beebjit with the debugger's savescreen and loaddisc commands
(the beebjit-mcp fork's build: $BEEBJIT). Neither is vendored by the kit.

KEY: a key as beebjit's keydown takes it - a letter (v, p) or a number; after each one is held
for a fifth of a second and released, OUT-kN.png. Exit 2 if the driver or beebjit cannot be found.
"""
import argparse
import os
import sys
from pathlib import Path

CYC = 2_000_000          # the BBC's 2 MHz: beebjit counts 6502 cycles


def save(bbc, path):
    from PIL import Image
    bgra, w, h = bbc.captureScreen()
    Image.frombytes("RGBA", (w, h), bgra, "raw", "BGRA").convert("RGB").save(path)
    print("wrote", path)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("\n\n", 1)[1])
    ap.add_argument("disc", help="the disc image (.ssd/.dsd)")
    ap.add_argument("out", help="the screenshot after the settle (.png); OUT-kN.png after key N")
    ap.add_argument("keys", nargs="*", help="keys to press in turn after the settle")
    ap.add_argument("--seconds", type=float, default=12, help="seconds of emulated time after the boot (default 12)")
    ap.add_argument("--model", default="master", help="beebjit-mcp's model: master (default), b, mos35, compact")
    ap.add_argument("--beebjit", default=os.environ.get("BEEBJIT"), help="the headless beebjit (default $BEEBJIT)")
    a = ap.parse_args()

    src = os.environ.get("BEEBJIT_MCP_SRC")
    if src:
        sys.path.insert(0, src)
    try:
        from beebjit_mcp import BeebjitDriver
    except ImportError as e:
        sys.exit(f"beebjit_shot: cannot import beebjit_mcp ({e}): pip install it, or set BEEBJIT_MCP_SRC to its src/")
    if not a.beebjit or not Path(a.beebjit).exists():
        print(f"beebjit_shot: no beebjit at {a.beebjit!r}: set BEEBJIT or --beebjit", file=sys.stderr)
        sys.exit(2)

    keys = [ord(k.lower()) if len(k) == 1 and k.isalpha() else int(k) for k in a.keys]
    bbc = BeebjitDriver(Path(a.beebjit), model=a.model)
    bbc.start()
    try:
        bbc.coldBootWithAutoboot(0, Path(a.disc).resolve())
        bbc.runCycles(int(a.seconds * CYC), timeout=120)
        save(bbc, a.out)
        for i, k in enumerate(keys, 1):
            bbc.keyDown(k)
            bbc.runCycles(CYC // 5)
            bbc.keyUp(k)
            bbc.runCycles(CYC // 2)
            save(bbc, a.out.replace(".png", f"-k{i}.png"))
    finally:
        bbc.close()


if __name__ == "__main__":
    main()
