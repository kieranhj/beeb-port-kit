"""
cpcboot.py - a reference CPC 6128 that boots a demo from its own DSK, at CPC timing. From the
phX port, 2026-11 (its tools/phxrun.py, phX's reference): the boot command, the CRTC type's
read-back and the firmware state the loader finds are options here; phX's own report byte
became --report.

  Z80        kosarev's core, one instruction at a time at CPC timing (cpctime.py: PROVISIONAL,
             from memory), the Z80's own interrupt modes (IM 1 at boot; a loader may set IM 2,
             the vector read with &FF on the bus)
  memory     64K + 64K, the 6128's &7Fxx configurations &C0-&C7 (pages parked and loaded)
  video      cpcvideo.py: the 6845 as a type 0 at character resolution, the Gate Array
  FDC        fdc.py over disc.py: the uPD765A polled, the disc turning at 300 rpm
  PPI/AY     port B bit 0 = VSYNC, the keyboard released (every key up), the AY's registers

THE BOOT is RUN"NAME reduced to what a loader that takes over the machine uses: the AMSDOS file
NAME (--run) loaded at its header's load address (or --load), PC at its exec (or --exec), SP
(--sp, &BFF0), IM (--im, 1), the firmware's MODE 1 CRTC values in cpcvideo, and --poke bytes.
The default pokes are an EXAMPLE, what phX's loader needed: &0038 = EI:RET (an IM 1 handler
that does nothing), (&BE7D) -> &BE80 = 0 (AMSDOS's reserved area, its drive byte: drive A).
--no-default-pokes drops them. There is no firmware or BASIC ROM: a loader that calls the
firmware (&BBxx, &BCxx jumpblocks, KL, CAS, the disc ROM's RSXs) needs those stubbed by --poke
or this file extended. Anything the original's loader finds that this boot does not set up is
a difference to decide, not to assume away.

THE CRTC TYPE's read-back (--crtc-type), which a demo's type test reads: type 0 (the default):
R12-R17 read back on &BFxx, other registers 0, &BExx reads &FF (what phX's test took for type 0,
checked against WinAPE type 0 by the demo's choice of paths). Types 1 and 2 (UNVERIFIED, from
memory of the CPC CRTC compendium): R12/R13 read 0, R14-R17 read back; type 1's &BExx is a status
register (bit 5 set while the vertical border shows), type 2's reads &FF. Whatever the type,
the TIMING is cpcvideo's type 0: a demo with per-type paths must be run on its type 0 path.

    python cpcboot.py DSK OUTDIR FIELDS --run NAME [--every N] [--snap F,F,...] [--snap-every N]
                      [--trace page:addr,...] [--save-state F,..] [--load-state PKL]
                      [--crtc-type 0|1|2] [--poke ADDR=HEX ...] [--no-default-pokes]
                      [--load HEX --exec HEX] [--sp HEX] [--im N] [--report ADDR]
                      [--index-phase MS] [--rpm R] [--fdc-v1]

Writes OUTDIR/
  io.npy      every OUT, and every IN whose value differs from that port's last: field (u32),
              us since VSYNC (u32), kind (u8: 0 OUT, 1 IN), port (u16), value (u8). The beam
              position of every CRTC, Gate Array, PPI/AY and FDC access
  fdc.log     every FDC command and result: time (us) cmd|res|ovr bytes
  crtc.npy    every CRTC register write with the counters it found: field, us, reg, value,
              C0, C9, C4 (where in the line and the row it landed)
  cov.npy     every instruction start: (memory page in its slot << 16 | address, first field)
  fields.npy  each field's length in us (VSYNC to VSYNC): list every one not 19,968 and decide it
  fNNNNN.png  every N-th field as the monitor shows it (312 x 512, RGB at 0/128/255)
  snap_FFFFF.bin  all 128K (pages 0-7 in order) at the start of each field asked for
  state_FFFFF.pkl checkpoints (--save-state), to resume with --load-state: run a long demo in
              parallel chunks, each from a checkpoint
  trace.txt   with --trace: field us page pc af bc de hl sp ix iy at each traced start
  run.txt     the summary

Known defects: cpcvideo.py's (Gate Array writes half a microsecond early, the beam race a line
early, a scanline-order error under per-line R9/R4 reprogramming); cpctime.py's timings are
from memory; the interrupt acknowledge is cpctime.INT_NOPS (IM 1's) in either mode; fdc.py's
drive is a data-sheet model (phX's loads were 1-2.6 s off WinAPE's). Check the reference against
WinAPE (winape_shot.ps1, winape_match.py) before anything rests on it. Uses kosarev z80's
private attributes (_Z80State__int_mode, _StateBase__frame_tick): written against z80 1.x.
"""
import argparse
import os
import sys

import numpy as np
import z80

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cpctime   # noqa: E402
import cpcvideo  # noqa: E402
import disc      # noqa: E402
import fdc       # noqa: E402

RGB = cpcvideo.RGB                  # hardware colour -> (r, g, b); kept here for old importers

CONFIGS = {0: (0, 1, 2, 3), 1: (0, 1, 2, 7), 2: (4, 5, 6, 7), 3: (0, 3, 2, 7),
           4: (0, 4, 2, 3), 5: (0, 5, 2, 3), 6: (0, 6, 2, 3), 7: (0, 7, 2, 3)}
PAGE = 16384
DEFAULT_POKES = ['0038=FBC9', 'BE7D=80BE', 'BE80=00']   # EXAMPLE: phX's loader's needs


class CPC:
    def __init__(self, dsk, run=None, load=None, exe=None, sp=0xBFF0, im=1, pokes=(),
                 crtc_type=0):
        self.disc = disc.Disc(dsk)
        mem = bytearray(65536)
        pc = 0
        if run:
            hdr, data = self.disc.amsdos_file(run)
            ld = load if load is not None else (hdr or {}).get('load')
            pc = exe if exe is not None else (hdr or {}).get('exec')
            if ld is None or pc is None:
                raise SystemExit(f'{run} has no AMSDOS header: give --load and --exec')
            mem[ld:ld + len(data)] = data
        elif exe is not None:
            pc = exe
        for addr, b in pokes:
            mem[addr:addr + len(b)] = b
        m = self.m = z80.Z80Machine()
        m.set_memory_block(0, bytes(mem))
        m.pc, m.sp = pc, sp
        m._Z80State__int_mode = im
        m.set_output_callback(self.out)
        m.set_input_callback(self.inp)
        self.crtc_type = crtc_type
        self.memv = np.frombuffer(m.memory, np.uint8)
        self.t = 0                                  # absolute T-states at the instruction start
        self.pages = {p: bytearray(PAGE) for p in range(8)}
        self.slots = [0, 1, 2, 3]
        self.video = cpcvideo.Video(self.page_views)
        self.fdc = fdc.FDC(self.disc, self.now)
        self.ppi = [0, 0, 0]
        self.ay = [0] * 16
        self.ay_sel = 0
        self.crtc_sel = 0
        self.io = []
        self.cov = {}
        self.last_in = {}
        self.crtc_log = []
        self.trace_keys = set()             # page << 16 | pc: instruction starts to log
        self.trace = []

    # ------------------------------------------------------------- checkpoints
    VIDEO_SKIP = ('page_views', 'views', 'on_field')
    FDC_SKIP = ('disc', 'clock')
    SELF_KEEP = ('t', 'pages', 'slots', 'ppi', 'ay', 'ay_sel', 'crtc_sel', 'cov', 'last_in', 'pen')

    def save_state(self, path):
        """the whole machine between two instructions (CPU, 128K, video, FDC), for --load-state"""
        import pickle
        st = dict(cpu=bytes(self.m.get_state_view()),
                  me={k: getattr(self, k) for k in self.SELF_KEEP if hasattr(self, k)},
                  video={k: v for k, v in self.video.__dict__.items() if k not in self.VIDEO_SKIP},
                  fdc={k: v for k, v in self.fdc.__dict__.items() if k not in self.FDC_SKIP})
        with open(path, 'wb') as f:
            pickle.dump(st, f, protocol=pickle.HIGHEST_PROTOCOL)

    def load_state(self, path):
        import pickle
        with open(path, 'rb') as f:
            st = pickle.load(f)
        self.m.get_state_view()[:] = st['cpu']
        for k, v in st['me'].items():
            setattr(self, k, v)
        self.video.__dict__.update(st['video'])
        self.video.views = None
        self.fdc.__dict__.update(st['fdc'])

    # ------------------------------------------------------------- time
    def now(self):
        return self.t + self.m.frame_tick

    # ------------------------------------------------------------- memory
    def bank(self, cfg):
        new = CONFIGS[cfg]
        m = self.m
        for s in range(4):
            if new[s] != self.slots[s]:
                self.pages[self.slots[s]][:] = bytes(m.memory[s * PAGE:(s + 1) * PAGE])
        for s in range(4):
            if new[s] != self.slots[s]:
                m.set_memory_block(s * PAGE, bytes(self.pages[new[s]]))
        self.slots = list(new)
        self.video.views = None

    def page_views(self):
        out = []
        for p in range(4):
            if p in self.slots:
                s = self.slots.index(p)
                out.append(self.memv[s * PAGE:(s + 1) * PAGE])
            else:
                out.append(np.frombuffer(self.pages[p], np.uint8))
        return out

    def all_ram(self):
        return b''.join(bytes(self.m.memory[self.slots.index(p) * PAGE:(self.slots.index(p) + 1) * PAGE])
                        if p in self.slots else bytes(self.pages[p]) for p in range(8))

    def peek(self, addr):
        """a byte of the base 64K (pages 0-3), wherever it is banked"""
        p = addr >> 14
        if p in self.slots:
            return self.m.memory[self.slots.index(p) * PAGE + (addr & 0x3FFF)]
        return self.pages[p][addr & 0x3FFF]

    # ------------------------------------------------------------- ports
    def log(self, kind, port, v):
        t = self.now()
        self.video.catch_up(t)
        f, us = self.video.pos()
        self.io.append((f, us, kind, port, v))

    def out(self, port, v):
        t = self.now()
        hi = port >> 8
        if port & 0xC000 == 0x4000:                 # Gate Array (and RAM configuration)
            fn = v >> 6
            if fn == 0:
                self.pen = 16 if v & 0x10 else v & 15
            elif fn == 1:
                self.video.write_ga_pen(getattr(self, 'pen', 0), v, t)
            elif fn == 2:
                self.video.write_ga_mode(v, t)
            else:
                self.bank(v & 7)
        if port & 0x4000 == 0:                      # CRTC
            fn = hi & 3
            if fn == 0:
                self.crtc_sel = v & 31
            elif fn == 1:
                vd = self.video
                vd.catch_up(t)
                f, us = vd.pos()
                self.crtc_log.append((f, us, self.crtc_sel, v, vd.c0, vd.c9, vd.c4))
                vd.write_crtc(self.crtc_sel, v, t)
        if port & 0x0800 == 0:                      # PPI
            fn = hi & 3
            if fn == 0:
                self.ppi[0] = v
            elif fn == 2:
                self.ppi[2] = v
                if v >> 6 == 3:
                    self.ay_sel = self.ppi[0] & 15
                elif v >> 6 == 2:
                    self.ay[self.ay_sel] = self.ppi[0]
        if hi == 0xFB:
            self.fdc.write_data(v)
        elif hi == 0xFA:
            self.fdc.motor_write(v)
        self.log(0, port, v)

    def crtc_read(self, hi, t):
        sel, r = self.crtc_sel, self.video.r
        if hi == 0xBF:
            lo = 12 if self.crtc_type == 0 else 14
            return r[sel] if lo <= sel <= 17 else 0
        if self.crtc_type == 1:                     # status: bit 5 = vertical border (UNVERIFIED)
            self.video.catch_up(t)
            return 0x20 if not self.video.vdisp else 0x00
        return 0xFF

    def inp(self, port):
        t = self.now()
        hi = port >> 8
        v = 0xFF
        if hi == 0xFB:
            v = self.fdc.read_data() if port & 1 else self.fdc.msr()
        elif hi in (0xBE, 0xBF):
            v = self.crtc_read(hi, t)
        elif port & 0x0800 == 0 and hi & 3 == 1:    # PPI port B
            v = 0x1E | (1 if self.video.vsync_active(t) else 0)
        if self.last_in.get(port) != v:          # polling loops: log changes only
            self.last_in[port] = v
            self.log(1, port, v)
        return v

    # ------------------------------------------------------------- CPU
    def step(self):
        m = self.m
        mem = m.memory
        v = self.video
        v.catch_up(self.t)
        if v.int_pending and m.iff1 and not m.int_disabled:
            m._StateBase__frame_tick[:] = (0).to_bytes(4, 'little')
            m.on_handle_active_int()
            if m.frame_tick:
                v.acknowledge()
                self.t += 4 * cpctime.INT_NOPS
                return
        pc = m.pc
        page = self.slots[pc >> 14]
        key = page << 16 | pc
        if key not in self.cov:
            self.cov[key] = v.field_no
        if key in self.trace_keys:
            f, us = v.pos()
            self.trace.append((f, us, page, pc, m.af, m.bc, m.de, m.hl, m.sp, m.ix, m.iy))
        m._StateBase__frame_tick[:] = (0).to_bytes(4, 'little')
        m.ticks_to_stop = 1
        m.run()
        while m.pc == ((pc + 1) & 0xFFFF) and mem[pc] in (0xDD, 0xFD) and m.frame_tick == 4:
            m.ticks_to_stop = 1
            m.run()
        self.t += 4 * cpctime.nops(mem, pc, m.frame_tick)


def parse_poke(s):
    a, _, b = s.partition('=')
    return int(a, 16), bytes.fromhex(b)


def main():
    ap = argparse.ArgumentParser(description='A reference CPC 6128 that boots a DSK at CPC timing.',
                                 epilog='See the module docstring (python -c "import cpcboot; '
                                        'help(cpcboot)") for the outputs and the known defects.')
    ap.add_argument('dsk')
    ap.add_argument('outdir')
    ap.add_argument('fields', type=int, help='run until this field number (from reset)')
    ap.add_argument('--run', default='', help='the AMSDOS file to boot, as RUN"NAME (NAME or NAME.EXT)')
    ap.add_argument('--load', default='', help='hex: load address (default: the AMSDOS header\'s)')
    ap.add_argument('--exec', dest='exe', default='', help='hex: entry (default: the header\'s)')
    ap.add_argument('--sp', default='BFF0', help='hex: the stack pointer at entry')
    ap.add_argument('--im', type=int, default=1, choices=(0, 1, 2), help='interrupt mode at entry')
    ap.add_argument('--poke', action='append', default=[],
                    help='ADDR=HEXBYTES (hex), applied after the load; repeatable')
    ap.add_argument('--no-default-pokes', action='store_true',
                    help='drop the example pokes ' + ' '.join(DEFAULT_POKES))
    ap.add_argument('--crtc-type', type=int, default=0, choices=(0, 1, 2),
                    help='what the CRTC registers read back as (the timing is type 0 regardless)')
    ap.add_argument('--report', default='', help='hex address: report its byte at the end '
                                                 '(e.g. where a loader stores its CRTC test)')
    ap.add_argument('--every', type=int, default=50, help='save every N-th field as fNNNNN.png')
    ap.add_argument('--snap', default='', help='F,F,...: all 128K at the start of these fields')
    ap.add_argument('--snap-every', type=int, default=0)
    ap.add_argument('--trace', default='',
                    help='page:addr,... (hex): log every execution of these instruction starts '
                         'with the registers to trace.txt')
    ap.add_argument('--save-state', default='', help='F,F,...: checkpoint at the start of these fields')
    ap.add_argument('--load-state', default='', help='resume from a checkpoint (logs cover the resumed span; '
                                                      'cov, fdc.log and field lengths carry over)')
    ap.add_argument('--fdc-v1', action='store_true',
                    help='the first FDC model: overruns ignored, seeks instant, sector data at k*6250/n+62')
    ap.add_argument('--index-phase', type=float, default=0.0,
                    help='ms of the disc turn already gone at power-on (the real one is arbitrary)')
    ap.add_argument('--rpm', type=float, default=300.0, help='the drive speed (nominal 300)')
    a = ap.parse_args()
    if not a.run and not a.exe and not a.load_state:
        ap.error('give --run NAME (or --exec HEX with --poke, or --load-state)')
    os.makedirs(a.outdir, exist_ok=True)
    snaps = {int(x) for x in a.snap.split(',') if x}
    saves = {int(x) for x in a.save_state.split(',') if x}
    pokes = [parse_poke(p) for p in ([] if a.no_default_pokes else DEFAULT_POKES) + a.poke]
    c = CPC(open(a.dsk, 'rb').read(), run=a.run or None,
            load=int(a.load, 16) if a.load else None, exe=int(a.exe, 16) if a.exe else None,
            sp=int(a.sp, 16), im=a.im, pokes=pokes, crtc_type=a.crtc_type)
    if a.load_state:
        c.load_state(a.load_state)
    if a.index_phase:
        c.fdc.index_phase_t = int(a.index_phase * 1000 * fdc.T_US)
    c.fdc.turn_t = int(round(60e6 / a.rpm)) * fdc.T_US
    if a.fdc_v1:
        c.fdc.overrun_ends = c.fdc.seek_timed = c.fdc.ids_needed = False
    for item in a.trace.split(','):
        if item:
            p, ad = item.split(':')
            c.trace_keys.add(int(p, 16) << 16 | int(ad, 16))

    from PIL import Image

    def on_field(n, img):
        if a.every and n % a.every == 0:
            Image.fromarray(RGB[img[:, ::2]]).save(os.path.join(a.outdir, f'f{n:05d}.png'))
        if n + 1 in snaps or (a.snap_every and (n + 1) % a.snap_every == 0):
            open(os.path.join(a.outdir, f'snap_{n + 1:05d}.bin'), 'wb').write(c.all_ram())

    c.video.on_field = on_field
    io_dt = np.dtype([('field', 'u4'), ('us', 'u4'), ('kind', 'u1'), ('port', 'u2'), ('value', 'u1')])
    io_path = os.path.join(a.outdir, 'io.bin')
    io_f = open(io_path, 'wb')
    n_io = 0

    def flush():
        nonlocal n_io
        if c.io:
            io_f.write(np.array(c.io, dtype=io_dt).tobytes())
            n_io += len(c.io)
            c.io.clear()

    last_field = c.video.field_no
    while c.video.field_no < a.fields:
        c.step()
        if c.video.field_no != last_field:
            last_field = c.video.field_no
            if last_field in saves:
                c.save_state(os.path.join(a.outdir, f'state_{last_field:05d}.pkl'))
        if len(c.io) >= 500000:
            flush()
    flush()
    if c.trace_keys:
        with open(os.path.join(a.outdir, 'trace.txt'), 'w') as f:
            f.write('field us page pc af bc de hl sp ix iy\n')
            for r in c.trace:
                f.write(f'{r[0]} {r[1]} {r[2]} {r[3]:04X} ' + ' '.join(f'{x:04X}' for x in r[4:]) + '\n')
    io_f.close()
    np.save(os.path.join(a.outdir, 'io.npy'), np.fromfile(io_path, dtype=io_dt))
    os.remove(io_path)
    np.save(os.path.join(a.outdir, 'crtc.npy'), np.array(c.crtc_log, dtype=[
        ('field', 'u4'), ('us', 'u4'), ('reg', 'u1'), ('value', 'u1'), ('c0', 'u1'), ('c9', 'u1'), ('c4', 'u1')]))
    cov = np.array(sorted(c.cov.items()), dtype=np.uint32)
    np.save(os.path.join(a.outdir, 'cov.npy'), cov)
    with open(os.path.join(a.outdir, 'fdc.log'), 'w') as f:
        for t, kind, b in c.fdc.log:
            f.write(f'{t // 4} {kind} {b.hex(" ")}\n')
    summary = (f'{c.video.field_no} fields, {c.t // 4} us, pc &{c.m.pc:04X}, {n_io} port accesses, '
               f'{len(c.cov)} instruction starts, {len(c.fdc.log)} FDC events, {c.fdc.overruns} overruns')
    if a.report:
        ad = int(a.report, 16)
        summary += f', byte at &{ad:04X} = &{c.peek(ad):02X}'
    fl = np.array(c.video.field_lengths, np.uint32)
    np.save(os.path.join(a.outdir, 'fields.npy'), fl)
    vals, cnt = np.unique(fl, return_counts=True)
    top = sorted(zip(cnt.tolist(), vals.tolist()), reverse=True)[:6]
    summary += '\nfield lengths (us: count): ' + ', '.join(f'{v}: {n}' for n, v in top)
    open(os.path.join(a.outdir, 'run.txt'), 'w').write(summary + '\n')
    print(summary)


if __name__ == '__main__':
    main()
