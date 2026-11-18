#!/usr/bin/env python3
"""
fz_bench.py - lib/fzdepack.6502 against lib/zx02depack.6502, stepped through py65 on real data:
each output checked byte for byte against the file, and the cycles counted.

Fork this into your project's tools/; keep this header.

From the phX port (tools/fz_bench.py, 2026-11; py65's 65C02 there, the depacker was 65C02),
generalised: it writes its own harness and assembles it with Baron, so it needs no build of
yours, and it steps the NMOS 6502 by default (the kit's fzdepack.6502 is plain 6502).

    pip install py65
    python tools/fz_bench.py [--lib DIR] [--cmos] FILE...

--lib: the directory holding fzdepack.6502 and zx02depack.6502 (default src/lib, then the kit's
lib/ beside this template). --cmos steps py65's 65C02 instead. Baron from $BARON, ../bin, the
PATH; ZX02 by $ZX02_EXE / ../bin/zx02.exe, else the kit's beeb_port_kit/zx02.py (exact, slow).
The cycles are the decode alone, JSR to RTS.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fz  # noqa: E402

SRC, DST = 0x0800, 0x4000       # the stream, the output (a file up to 32K fits below &C000)
CODE = 0x0400

HARNESS = r"""
SECTION zeropage, org = &70, guard = &100
.zxsrc SKIP 2
.zxdst SKIP 2
.zxofs SKIP 1
.zxbit SKIP 1
.zxwrk SKIP 2
ENDSECTION
INCLUDE "zx02depack.6502"
INCLUDE "fzdepack.6502"
SECTION Bench, org = &0400, guard = &0800, filename = "BENCH"
.fz_unpack
    FZ_DEPACKER
    rts
.zx_unpack
    ZX02_DEPACKER
.bench_end
ENDSECTION
"""


def find_baron():
    for p in (os.environ.get('BARON'), os.path.join(HERE, '..', 'bin', 'baron.exe'),
              os.path.join(HERE, '..', 'bin', 'baron'), shutil.which('baron')):
        if p and os.path.isfile(p):
            return p
    sys.exit('fz_bench: Baron not found ($BARON, ../bin, PATH)')


def find_lib(arg):
    for d in ([arg] if arg else []) + [os.path.join(HERE, '..', 'src', 'lib'),
                                       os.path.join(HERE, '..', '..', 'lib')]:
        if d and os.path.isfile(os.path.join(d, 'fzdepack.6502')):
            return os.path.abspath(d)
    sys.exit('fz_bench: no fzdepack.6502 (--lib)')


def assemble(lib, work):
    for f in ('zx02depack.6502', 'fzdepack.6502'):      # (Baron includes by relative path)
        shutil.copy(os.path.join(lib, f), work)
    src = os.path.join(work, 'bench.6502')
    open(src, 'w').write(HARNESS)
    sym = os.path.join(work, 'bench.json')
    r = subprocess.run([find_baron(), '--warn', '2', '-p', work, '--symbols', sym, src],
                       capture_output=True, text=True, cwd=work)
    if r.returncode:
        sys.exit('fz_bench: baron failed\n' + r.stdout + r.stderr)
    import json
    syms = {}
    for a in json.load(open(sym))['assemblies']:
        for sec in a['sections']:
            for kind in ('labels', 'assignments'):
                for k, v in (sec.get(kind) or {}).items():
                    syms[k] = v['value']
    return open(os.path.join(work, 'BENCH'), 'rb').read(), syms


def zx02_pack(data):
    for exe in (os.environ.get('ZX02_EXE'), os.path.join(HERE, '..', 'bin', 'zx02.exe'),
                shutil.which('zx02')):
        if exe and os.path.isfile(exe):
            with tempfile.TemporaryDirectory() as d:
                i, o = os.path.join(d, 'i'), os.path.join(d, 'o')
                open(i, 'wb').write(data)
                subprocess.run([exe, '-f', i, o], check=True, capture_output=True)
                return open(o, 'rb').read()
    for root in (os.environ.get('BEEB_PORT_KIT'), os.path.join(HERE, '..', '..')):
        if root and os.path.isdir(os.path.join(root, 'py', 'beeb_port_kit')):
            sys.path.insert(0, os.path.join(root, 'py'))
    from beeb_port_kit import zx02
    return zx02.compress(data)


def run(code, entry, stream, outlen, cmos=False):
    """(output, cycles): the routine at entry from a JSR, to its RTS"""
    if cmos:
        from py65.devices.mpu65c02 import MPU
    else:
        from py65.devices.mpu6502 import MPU
    m = MPU()
    mem = m.memory
    mem[0:0x10000] = [0] * 0x10000
    mem[CODE:CODE + len(code)] = list(code)
    mem[SRC:SRC + len(stream)] = list(stream)
    mem[0x70], mem[0x71] = SRC & 0xFF, SRC >> 8
    mem[0x72], mem[0x73] = DST & 0xFF, DST >> 8
    stop = 0x0300
    mem[0x1FF], mem[0x1FE] = (stop - 1) >> 8, (stop - 1) & 0xFF
    m.sp = 0xFD
    m.pc = entry
    c0 = m.processorCycles
    while m.pc != stop:
        m.step()
    return bytes(mem[DST:DST + outlen]), m.processorCycles - c0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('files', nargs='+')
    ap.add_argument('--lib', default=None)
    ap.add_argument('--cmos', action='store_true')
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as work:
        code, syms = assemble(find_lib(a.lib), work)
    fz_size = syms['zx_unpack'] - syms['fz_unpack']
    zx_size = syms['bench_end'] - syms['zx_unpack']
    print(f'depacker: FZ {fz_size} bytes (with its RTS), ZX02 {zx_size}; '
          f'{"65C02" if a.cmos else "NMOS 6502"}')
    tot = [0] * 5
    for f in a.files:
        d = open(f, 'rb').read()
        z = fz.compress(d)
        assert SRC + len(z) + 8 <= DST and DST + len(d) <= 0xC000, f'{f}: too big for the bench'
        out, cyc = run(code, syms['fz_unpack'], z, len(d), a.cmos)
        assert out == d, f'{f}: the 6502 FZ output differs'
        zx = zx02_pack(d)
        out2, cyc2 = run(code, syms['zx_unpack'], zx, len(d), a.cmos)
        assert out2 == d, f'{f}: the 6502 ZX02 output differs'
        print(f'{os.path.basename(f)}: {len(d)} B; FZ {len(z)} B {cyc} cycles '
              f'({cyc / len(d):.1f}/B, fz.py est. {fz.est_cycles(z, len(d))}); '
              f'ZX02 {len(zx)} B {cyc2} cycles ({cyc2 / len(d):.1f}/B)')
        for i, x in enumerate((len(d), len(z), cyc, len(zx), cyc2)):
            tot[i] += x
    if len(a.files) > 1:
        print(f'TOTAL {tot[0]} B; FZ {tot[1]} B {tot[2] / tot[0]:.1f}/B; ZX02 {tot[3]} B '
              f'{tot[4] / tot[0]:.1f}/B')


if __name__ == '__main__':
    main()
