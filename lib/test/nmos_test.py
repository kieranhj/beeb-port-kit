#!/usr/bin/env python3
"""
nmos_test.py - lib/nmos.6502's macros proved both ways: the bytes without NMOS,
the assembler's refusal with it, and what each NMOS form does when it runs.

    pip install py65
    python lib/test/nmos_test.py [TRIALS]          # from the kit root; default 400

Assembles lib/test/nmos_test.6502 three times with the kit's Baron
(template/bin, or BARON):

  1. NMOS=0: section NMACRO (every macro) must be byte-identical to NRAW (the
     65SC12 instruction each must be) - the Master build is unchanged.
  2. NMOS=1: NMACRO, every section `cmos = FALSE`, must assemble.
  3. NMOS=1 with one raw STZ (NMOS_NEG=1): Baron must REFUSE it, with "CMOS-
     only instruction" - the negative control, so (2) proves something.

Then each macro's two builds are run on py65: the NMOS=1 code on its NMOS 6502
(MPU), the NMOS=0 code on its 65C02 (MPU65C02, a superset of the 65SC12's
instructions used here), from the same random state, made to meet the
macro's condition (lib/nmos.6502's comment above it). After each, everything
is compared - A, X, Y, N V D I Z C, S, the label the code stopped at (a
branch's taken or fall-through path), zero page, the live stack and the
indexed operand's page - except what the macro's condition says is dead.
D is clear in every trial: the ADC/SBC forms assume it.

Exit code 0 if all of it holds. Measured 2026-10-25, Baron 0.6.0, py65 1.2.0:
34 macro sites, 112 bytes identical; NMOS build 151 bytes; the raw STZ refused;
34 x 400 trials, 0 differences (5.5 s). The control: with four conditions
weakened (INC_A_ADC's C, STZ_A's A, PHX_A's A and BVC_BIT6's V no longer
required or dead), 156 of 1,700 trials differ, so the run does compare.
"""

import json
import os
import random
import subprocess
import sys
from pathlib import Path

try:
    from py65.devices.mpu6502 import MPU as NMOS6502
    from py65.devices.mpu65c02 import MPU as CMOS65C02
except ImportError:
    raise SystemExit("nmos_test: needs py65 (pip install py65)")

HERE = Path(__file__).resolve().parent
KIT = HERE.parent.parent
SRC = HERE / "nmos_test.6502"
BUILD = HERE / "build" / "nmos"
EXE = "baron.exe" if os.name == "nt" else "baron"
BARON = Path(os.environ.get("BARON", KIT / "template" / "bin" / EXE))

N, V, D, I, Z, C = 0x80, 0x40, 0x08, 0x04, 0x02, 0x01
FLAG = {"N": N, "V": V, "Z": Z, "C": C}

# name -> (condition: {register or flag: value}, dead after)
# a condition value of "nz" means: N and Z as A's value sets them
CASES = {
    "stz_a": ({"A": 0}, ""), "stz_a_x": ({"A": 0}, ""), "stz_a_zx": ({"A": 0}, ""),
    "stz_x": ({"X": 0}, ""), "stz_y": ({"Y": 0}, ""),
    "stz_lda": ({}, "ANZ"), "stz_lda_x": ({}, "ANZ"), "stz_ldx": ({}, "XNZ"), "stz_ldy": ({}, "YNZ"),
    "stz_pha": ({"nz": 1}, ""), "stz_pha_x": ({"nz": 1}, ""),
    "bra_eq": ({"Z": 1}, ""), "bra_ne": ({"Z": 0}, ""), "bra_cs": ({"C": 1}, ""), "bra_cc": ({"C": 0}, ""),
    "bra_mi": ({"N": 1}, ""), "bra_pl": ({"N": 0}, ""), "bra_vs": ({"V": 1}, ""), "bra_vc": ({"V": 0}, ""),
    "bra_jmp": ({}, ""),
    "inc_a_adc": ({"C": 0}, "CV"), "dec_a_sbc": ({"C": 1}, "CV"),
    "inc_a_clc": ({}, "CV"), "dec_a_sec": ({}, "CV"),
    "inc_a_x": ({}, "X"), "inc_a_y": ({}, "Y"), "dec_a_x": ({}, "X"), "dec_a_y": ({}, "Y"),
    "phx_a": ({}, "ANZ"), "phy_a": ({}, "ANZ"), "plx_a": ({}, "A"), "ply_a": ({}, "A"),
    "bvc_bit6": ({}, "ANZV"), "bvs_bit6": ({}, "ANZV"),
}


def baron(out, *defs, expect_ok=True):
    out.mkdir(parents=True, exist_ok=True)
    syms = out / "symbols.json"
    cmd = [str(BARON), "--warn", "2", "-p", str(out), "--symbols", str(syms)]
    for d in defs:
        cmd += ["-D", d]
    r = subprocess.run(cmd + [str(SRC)], capture_output=True, text=True)
    if expect_ok and r.returncode:
        raise SystemExit("baron failed: %s\n%s" % (" ".join(defs), r.stderr))
    return r, syms


def labels(syms):
    out = {}
    for a in json.loads(syms.read_text())["assemblies"]:
        for s in a["sections"]:
            for k, v in (s.get("labels") or {}).items():
                if isinstance(v.get("value"), int):
                    out[k] = v["value"]
    return out


def run(cls, image, org, lab, name, st):
    m = cls()
    mem = bytearray(st["mem"])
    mem[org:org + len(image)] = image
    m.memory = mem
    m.a, m.x, m.y, m.sp, m.p = st["A"], st["X"], st["Y"], st["S"], st["P"]
    m.pc = lab["t_" + name]
    for _ in range(32):
        if m.memory[m.pc] == 0x00:              # the BRK after each path
            break
        m.step()
    else:
        raise SystemExit("%s: never reached a BRK" % name)
    where = {lab["t_%s_end" % name]: "fall-through", lab.get("t_%s_t" % name): "taken"}.get(m.pc, hex(m.pc))
    return m, where


def compare(name, cond, dead, a, aw, b, bw):
    diffs = []
    for r in "AXY":
        if r not in dead and getattr(a, r.lower()) != getattr(b, r.lower()):
            diffs.append("%s %02X/%02X" % (r, getattr(a, r.lower()), getattr(b, r.lower())))
    mask = N | V | D | I | Z | C
    for f in dead:
        mask &= ~FLAG.get(f, 0)
    if (a.p ^ b.p) & mask:
        diffs.append("P %02X/%02X" % (a.p, b.p))
    if a.sp != b.sp:
        diffs.append("S %02X/%02X" % (a.sp, b.sp))
    if aw != bw:
        diffs.append("path %s/%s" % (aw, bw))
    live = list(range(0x100)) + list(range(0x100 + a.sp + 1, 0x200)) + list(range(0x1200, 0x1400))
    for adr in live:
        if a.memory[adr] != b.memory[adr]:
            diffs.append("&%04X %02X/%02X" % (adr, a.memory[adr], b.memory[adr]))
            break
    return diffs


def state(rng, cond):
    st = {"A": rng.randrange(256), "X": rng.randrange(256), "Y": rng.randrange(256),
          "S": rng.randrange(0x40, 0x100), "P": rng.randrange(256) & ~D | 0x30,
          "mem": bytearray(0x10000)}
    for lo, hi in ((0, 0x200), (0x1200, 0x1400)):    # all the code may touch
        st["mem"][lo:hi] = rng.randbytes(hi - lo)
    for k, v in cond.items():
        if k in "AXY":
            st[k] = v
        elif k in FLAG:
            st["P"] = st["P"] | FLAG[k] if v else st["P"] & ~FLAG[k]
    if "nz" in cond:                            # N and Z as A sets them (LDA, PLA, TXA...)
        st["P"] &= ~(N | Z)
        st["P"] |= (st["A"] & N) | (Z if st["A"] == 0 else 0)
    return st


def main():
    trials = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    if not BARON.exists():
        raise SystemExit("nmos_test: no Baron at %s (set BARON)" % BARON)
    fails = 0

    _, s0 = baron(BUILD / "cmos", "NMOS=0", "NMOS_NEG=0")
    m0 = (BUILD / "cmos" / "NMACRO").read_bytes()
    raw = (BUILD / "cmos" / "NRAW").read_bytes()
    same = m0 == raw
    print("NMOS=0: NMACRO %d bytes, NRAW %d bytes: %s" % (len(m0), len(raw), "identical" if same else "DIFFER"))
    fails += not same

    _, s1 = baron(BUILD / "nmos", "NMOS=1", "NMOS_NEG=0")
    m1 = (BUILD / "nmos" / "NMACRO").read_bytes()
    print("NMOS=1: NMACRO %d bytes, assembled with cmos = FALSE" % len(m1))

    r, _ = baron(BUILD / "neg", "NMOS=1", "NMOS_NEG=1", expect_ok=False)
    refused = r.returncode != 0 and "CMOS-only" in r.stderr
    print("NMOS=1 with a raw STZ: %s" % ("refused (%s)" % r.stderr.strip().splitlines()[0] if refused else "NOT REFUSED"))
    fails += not refused

    l0, l1 = labels(s0), labels(s1)
    found = sorted(k[2:] for k in l0 if k.startswith("t_") and not k.endswith(("_end", "_t")) and k != "t_last")
    missing = set(found) ^ set(CASES)
    if missing:
        raise SystemExit("nmos_test: the cases and the source disagree: %s" % sorted(missing))
    rng = random.Random(1)
    bad = 0
    for name in found:
        cond, dead = CASES[name]
        for _ in range(trials):
            st = state(rng, cond)
            a, aw = run(CMOS65C02, m0, 0x2000, l0, name, st)
            b, bw = run(NMOS6502, m1, 0x2000, l1, name, st)
            d = compare(name, cond, dead, a, aw, b, bw)
            if d:
                bad += 1
                if bad <= 10:
                    print("  %s: %s" % (name, ", ".join(d)))
    print("run: %d macros x %d trials, %d differ" % (len(found), trials, bad))
    fails += bad
    print("PASS" if not fails else "FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
