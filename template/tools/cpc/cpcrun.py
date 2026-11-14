"""Minimal Amstrad CPC harness (forked from Isometrikum's for Square Roots).

Runs the unpacked demo (64K image at its entry &164B, from tools/depack.py) on
kosarev's z80 core, one 64 us scanline (256 T) at a time, and models only what the
demo touches:

  Gate Array  pens/border, mode, interrupt counter (52 HSYNCs, VSYNC resync, ack)
  RAM banking the 6128's &7Fxx configurations &C0-&C7 (Square Roots uses &C0 and &C4:
              bank 4 at &4000). The video always reads the base 64K (pages 0-3)
  CRTC 6845   R0-R13 counters per scanline: VCC/VLC/MA, R5 adjust, R7 VSYNC,
              R12/R13 latched at each CRTC frame start (so ruptures work)
  PPI 8255    port B bit 0 = VSYNC; port A/C drive the AY
  AY-3-8912   register file (logged)

Timing: by default every instruction is charged its CPC length in whole microseconds
(tools/cpctime.py, stepped one instruction at a time, much slower); RAW=1 counts raw Z80 T
at 4/us as Isometrikum's did, so busy code runs ~10-20% fast. Register writes take
effect at the end of the scanline they happen on.

Output (OUTDIR):
  frames.npy   uint8 [N, 312, 384] hardware colour 0..31 per mode-1 pixel, every EVERY-th frame
  ay.log       frame line T reg value   (every AY register write)
  out.log      frame line T port value  (every OUT)
  regs.log     frame: per-frame CRTC frame starts (line, R12/R13, R4, R5, R6, R1, R9)
Usage: python tools/cpcrun.py MEM.bin OUTDIR FRAMES [EVERY]   (RAW=1: raw Z80 T, no CPC timing)
"""
import os
import sys

import numpy as np
import z80

import cpctime

LINE = 256           # T-states per scanline
WIDTH = 768          # 48 chars x 16 mode-2 pixels
LINES = 312


def mode_lut():
    """byte -> pixel pen indices for modes 0,1,2 expanded to 8 mode-2-width pixels per byte"""
    lut = np.zeros((3, 256, 8), np.uint8)
    for b in range(256):
        bit = [(b >> (7 - i)) & 1 for i in range(8)]  # bit[0] = bit 7
        # mode 0: pixel0 = b7*1 + b3*2 + b5*4 + b1*8 ; pixel1 = b6*1 + b2*2 + b4*4 + b0*8
        p0 = bit[0] | bit[4] << 1 | bit[2] << 2 | bit[6] << 3
        p1 = bit[1] | bit[5] << 1 | bit[3] << 2 | bit[7] << 3
        lut[0, b] = [p0] * 4 + [p1] * 4
        # mode 1: pixel i = bit(7-i) + 2*bit(3-i)
        for i in range(4):
            p = bit[i] | bit[i + 4] << 1
            lut[1, b, 2 * i:2 * i + 2] = p
        lut[2, b] = bit
    return lut


class CPC:
    def __init__(self, mem, entry=None):
        entry = int(os.environ.get('ENTRY', '164B'), 16) if entry is None else entry  # kit: ENTRY=hex
        m = self.m = z80.Z80Machine()
        m.set_memory_block(0, mem)
        m.pc, m.sp = entry, 0xBFF0
        m.set_output_callback(self.out)
        m.set_input_callback(self.inp)
        self.pens = [0x14] * 17
        self.pen = 0
        self.mode = 1
        self.crtc = [0] * 18
        self.crtc_sel = 0
        self.ppi = [0, 0, 0]
        self.ay = [0] * 16
        self.ay_sel = 0
        # CRTC state
        self.vcc = self.vlc = 0
        self.ma = self.ma_row = 0
        self.adjust = -1         # >=0 while in R5 vertical adjust
        self.vsync = 0           # lines of VSYNC left
        # GA int state
        self.icount = 0
        self.int_pending = False
        self.vsync_hs = 0
        # monitor
        self.frame = 0
        self.mline = 0           # monitor line since last VSYNC
        self.tline = 0           # T at start of the current scanline (frame_tick)
        self.fb = np.zeros((LINES, WIDTH), np.uint8)
        self.frames = []
        self.out_log = []
        self.ay_log = []
        self.reg_log = []
        self.lut = mode_lut()
        # RAM banking: pages[p] holds physical 16K page p while it is not mapped
        self.pages = {p: bytearray(16384) for p in range(8)}
        self.ram_cfg = 0
        self.slots = [0, 1, 2, 3]

    # ------------------------------------------------------------- ports
    def stamp(self):
        return self.frame, self.mline, self.m.frame_tick - self.tline

    def out(self, port, v):
        self.out_log.append((*self.stamp(), port, v))
        if port & 0xC000 == 0x4000:          # Gate Array
            f = v >> 6
            if f == 0:
                self.pen = 16 if v & 0x10 else v & 15
            elif f == 1:
                self.pens[self.pen] = v & 31
            elif f == 3:
                self.bank(v & 7)
            elif f == 2:
                self.mode = v & 3
                if v & 0x10:
                    self.icount = 0
                    self.int_pending = False
        if port & 0x4000 == 0:               # CRTC
            fn = (port >> 8) & 3
            if fn == 0:
                self.crtc_sel = v & 31
            elif fn == 1 and self.crtc_sel < 18:
                self.crtc[self.crtc_sel] = v
        if port & 0x0800 == 0:               # PPI
            fn = (port >> 8) & 3
            if fn == 0:
                self.ppi[0] = v
            elif fn == 2:
                self.ppi[2] = v
                if v >> 6 == 3:
                    self.ay_sel = self.ppi[0] & 15
                elif v >> 6 == 2:
                    self.ay[self.ay_sel] = self.ppi[0]
                    self.ay_log.append((*self.stamp(), self.ay_sel, self.ppi[0]))

    CONFIGS = {0: (0, 1, 2, 3), 1: (0, 1, 2, 7), 2: (4, 5, 6, 7), 3: (0, 3, 2, 7),
               4: (0, 4, 2, 3), 5: (0, 5, 2, 3), 6: (0, 6, 2, 3), 7: (0, 7, 2, 3)}

    def bank(self, cfg):
        """switch the Z80's view; every slot whose page changes is parked and the new one
        loaded. A page mapped twice (config 3) is not modelled"""
        new = self.CONFIGS[cfg]
        m = self.m
        for s in range(4):
            if new[s] != self.slots[s]:
                self.pages[self.slots[s]][:] = bytes(m.memory[s * 16384:(s + 1) * 16384])
        for s in range(4):
            if new[s] != self.slots[s]:
                m.set_memory_block(s * 16384, bytes(self.pages[new[s]]))
        self.slots = list(new)
        self.ram_cfg = cfg

    def page(self, p):
        """physical 16K page p, wherever it is"""
        if p in self.slots:
            s = self.slots.index(p)
            return bytes(self.m.memory[s * 16384:(s + 1) * 16384])
        return bytes(self.pages[p])

    def inp(self, port):
        if port & 0x0800 == 0 and (port >> 8) & 3 == 1:
            return 0x1E | (1 if self.vsync else 0)
        return 0xFF

    # ------------------------------------------------------------- CPU
    def take_int(self):
        m = self.m
        self.int_pending = False
        self.icount &= 0x1F
        m.iff1 = m.iff2 = 0
        m.halted = False
        m.sp = (m.sp - 2) & 0xFFFF
        m.set_memory_block(m.sp, bytes([m.pc & 255, m.pc >> 8]))
        m.pc = 0x38

    timed = False       # True: every instruction charged its CPC length (tools/cpctime.py)

    def set_tick(self, v):
        self.m._StateBase__frame_tick[:] = v.to_bytes(4, 'little')

    def step(self):
        """one instruction at CPC timing; returns its pc"""
        m = self.m
        mem = m.memory
        pc, t0 = m.pc, m.frame_tick
        m.ticks_to_stop = 1
        m.run()
        while m.pc == ((pc + 1) & 0xFFFF) and mem[pc] in (0xDD, 0xFD) and m.frame_tick - t0 == 4:
            m.ticks_to_stop = 1         # kosarev stops after a lone DD/FD prefix
            m.run()
        self.set_tick(t0 + 4 * cpctime.nops(mem, pc, m.frame_tick - t0))
        return pc

    def run_line(self):
        if self.timed:
            return self.run_line_timed()
        m = self.m
        end = self.tline + LINE
        while m.frame_tick < end:
            if self.int_pending and m.iff1:
                self.take_int()
            m.ticks_to_stop = min(end - m.frame_tick, 64)
            m.run()
        # rebase kosarev's frame_tick (it wraps near 100k)
        over = m.frame_tick - end
        m._StateBase__frame_tick[:] = over.to_bytes(4, 'little')
        self.tline = 0

    def run_line_timed(self):
        m = self.m
        end = self.tline + LINE
        while m.frame_tick < end:
            if self.int_pending and m.iff1:
                self.take_int()
                self.set_tick(m.frame_tick + 4 * cpctime.INT_NOPS)
                continue
            self.step()
        self.set_tick(m.frame_tick - end)
        self.tline = 0

    # ------------------------------------------------------------- video
    def draw_line(self):
        r = self.crtc
        if self.frame % self.every or self.mline >= LINES or self.adjust >= 0 or self.vcc >= r[6]:
            return
        mem = self.m.memory if self.slots == [0, 1, 2, 3] else self.base()
        nch = min(r[1], WIDTH // 16)
        row = self.fb[self.mline]
        pal = np.array(self.pens[:16], np.uint8)
        lut = self.lut[min(self.mode, 2)]
        for c in range(nch):
            ma = (self.ma_row + c) & 0x3FFF
            addr = ((ma & 0x3000) << 2) | ((self.vlc & 7) << 11) | ((ma & 0x3FF) << 1)
            for k in range(2):
                row[c * 16 + k * 8:c * 16 + k * 8 + 8] = pal[lut[mem[addr + k]]]

    def base(self):
        return b''.join(self.page(p) for p in range(4))

    def end_line(self):
        r = self.crtc
        self.draw_line()
        # GA interrupt counter on HSYNC
        self.icount += 1
        if self.icount == 52:
            self.icount = 0
            self.int_pending = True
        if self.vsync_hs:
            self.vsync_hs -= 1
            if self.vsync_hs == 0:
                if self.icount >= 32:
                    self.int_pending = True
                self.icount = 0
        if self.vsync:
            self.vsync -= 1
        # CRTC vertical counters
        new_frame = False
        if self.adjust >= 0:
            self.adjust -= 1
            if self.adjust < 0:
                new_frame = True
        elif self.vlc == r[9]:
            self.vlc = 0
            self.ma_row += r[1]
            if self.vcc == r[4]:
                if r[5]:
                    self.adjust = r[5] - 1
                else:
                    new_frame = True
            else:
                self.vcc = (self.vcc + 1) & 127
                if self.vcc == r[7]:
                    self.start_vsync()
        else:
            self.vlc = (self.vlc + 1) & 31
        if new_frame:
            self.vcc = self.vlc = 0
            self.ma_row = (r[12] << 8 | r[13]) & 0x3FFF
            self.reg_log.append((self.frame, self.mline, r[12], r[13], r[4], r[5], r[6], r[1], r[9], r[7]))
            if r[7] == 0:
                self.start_vsync()
        self.mline += 1

    def start_vsync(self):
        if self.vsync:
            return
        self.vsync = 16
        self.vsync_hs = 2
        if self.frame % self.every == 0:
            self.frames.append(self.fb[:, ::2].copy())
        self.fb[:] = self.pens[16]
        self.frame += 1
        self.mline = 0


def main(memfile, outdir, frames, every=1):
    os.makedirs(outdir, exist_ok=True)
    c = CPC(open(memfile, 'rb').read())
    c.timed = os.environ.get('RAW') != '1'
    c.every = every
    c.tline = c.m.frame_tick
    guard = 0
    while c.frame < frames and guard < frames * 400:
        c.run_line()
        c.end_line()
        guard += 1
    np.save(os.path.join(outdir, 'frames.npy'), np.array(c.frames, np.uint8))
    with open(os.path.join(outdir, 'out.log'), 'w') as f:
        for fr, ln, t, p, v in c.out_log:
            f.write(f'{fr} {ln} {t} {p:04X} {v:02X}\n')
    with open(os.path.join(outdir, 'ay.log'), 'w') as f:
        for fr, ln, t, r, v in c.ay_log:
            f.write(f'{fr} {ln} {t} {r} {v}\n')
    with open(os.path.join(outdir, 'regs.log'), 'w') as f:
        for row in c.reg_log:
            f.write(' '.join(str(x) for x in row) + '\n')
    open(os.path.join(outdir, 'final.bin'), 'wb').write(bytes(c.m.memory))
    print(f'{len(c.frames)} frames, {len(c.out_log)} OUTs, {len(c.ay_log)} AY writes, {guard} lines')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]) if len(sys.argv) > 4 else 1)
