"""
cpcvideo.py - the CPC's 6845 (as a type 0) and Gate Array at character resolution: the picture
machine under cpcboot.py. From the phX port, 2026-11 (its tools/cpcvideo.py; the code unchanged,
the hardware-colour table RGB added here so the other tools need not import cpcboot).

KNOWN DEFECTS (measured against WinAPE 2.0b2, type 0, on phX; see the kit's
docs/cpc-demo-porting.md section 14):
  1. Gate Array writes land half a microsecond early. A pen (or mode) write is applied on a
     whole-microsecond boundary (T_CHAR = 4); WinAPE applies it half a microsecond (4 mode-1
     pixels) later, so a colour boundary inside the picture is 4 px early here (phX BUGS 11:
     its sine scrollers, plasma, a chessboard pen swap). NOT fixed.
  2. The beam race: a CPU write into the line being displayed shows here a line earlier than in
     WinAPE (phX's Kefrens bars), because the Gate Array's fetch lead is not modelled. NOT fixed.
  3. Scanline order under per-line CRTC reprogramming (phX decision 63): on phX's outro (one-row
     frames, R4/R9/R12/R13 rewritten each line, the "RVI" technique) this model showed the line
     routine meant for scanline k as scanline (2, 0, 1)[k], and missed a new frame on a VLC 1 ->
     VLC 0 step (a dark line). WinAPE and the demo's source show scanline k. The fault is in this
     file's row/frame logic (line_counters / the Last Line decision), but it was NOT located or
     fixed: phX's outro converter built that part's expected pictures from the source's order
     instead. Every other phX RVI part matched WinAPE, so treat any part that rewrites R9/R4 every
     line as unverified until it has been checked against WinAPE.
  4. WinAPE shows the picture's top line black in every part; this model does not (a one-line
     difference in every capture comparison, not a fault of the demo).
  5. The type 0 rules below are from the ACCC CRTC compendium, checked against WinAPE only on the
     paths phX exercised. Types 1-4 are not modelled.

The CRTC is clocked at 1 MHz: one character (C0 step, 2 bytes fetched) per microsecond, 4 Z80
T-states. `catch_up(t)` advances everything to absolute T-state t; the CPU side calls it before
every CRTC, Gate Array or PPI access and between instructions, so a register or pen write lands
at its own character. Between boundaries (C0 = 0..2, R1, R2, HSYNC's end, R0) nothing but C0 and
the address moves, so the work is per segment, not per character.

TYPE 0 RULES MODELLED (from the ACCC CRTC compendium):
  - "Last Line" (C9 = R9 and C4 = R4) is decided over C0 = 0..1 and locked from C0 = 2;
  - at the end of a line (C0 = R0): Last Line -> R5 adjust lines if R5 > 0 (C4 once + 1), else a
    new frame (C4 = C9 = 0, VMA = R12/R13); else C9 = R9 -> C9 = 0, C4 + 1, VMA = VMA' ; else C9 + 1;
  - C9 counts only on a line whose C0 reached 1 (R0 = 0 freezes it);
  - VMA' = the address at C0 = R1 on a row's last line (C9 = R9);
  - DISPEN: C0 < R1, the row below R6 (vertical display off from C4 = R6), not R8 bits 4-5 = 3;
  - HSYNC from C0 = R2 for R3 & 15 characters (0: none); VSYNC when C4 = R7 is found at a line's
    start (tested every line, once per match), or at once when R7 is written equal to C4 after
    C0 = 2 (an effect with one-line frames, C4 always 0, triggers VSync by R7 = 0 then 1: phX's
    Clown); for R3 >> 4 lines (0: 16).
Gate Array: the interrupt counter counts HSYNCs' ends; 52 -> interrupt; 2 HSYNCs after VSYNC
starts it resets, interrupting if it was >= 32; an acknowledge clears bit 5. The picture is the
pens in force at each character, the border outside DISPEN, black during either sync.

THE PICTURE. A field is 312 lines of 64 characters, each character 16 mode-2 pixels: `field` is
uint8 [312, 1024] of hardware colours 0-31. Rows count by time from VSYNC's start (a standard
field is 19,968 us); a line's x = 0 is H_PORCH characters after the last HSYNC began, because a
monitor locks its lines to HSYNC, not to VSYNC (an effect may start VSYNC mid-line).
RGB[hw] is a hardware colour's (r, g, b) at levels 0/128/255; RGB[field[:, ::2]] is a field as
a 312 x 512 picture (what cpcboot.py saves).

Used as a library (cpcboot.py): Video(page_views), then write_crtc / write_ga_pen /
write_ga_mode / acknowledge / vsync_active from the port handlers and catch_up(t) between
instructions; on_field(n, field) is called at each VSYNC start.
"""
import numpy as np

# hardware colour 0-31 -> (r, g, b) at 0 / half / full: the Gate Array's 27 colours (0/1, 2/17,
# 3/9, 4/16, 5/8 are duplicates)
HW = [(1, 1, 1), (1, 1, 1), (0, 2, 1), (2, 2, 1), (0, 0, 1), (2, 0, 1), (0, 1, 1), (2, 1, 1),
      (2, 0, 1), (2, 2, 1), (2, 2, 0), (2, 2, 2), (2, 0, 0), (2, 0, 2), (2, 1, 0), (2, 1, 2),
      (0, 0, 1), (0, 2, 1), (0, 2, 0), (0, 2, 2), (0, 0, 0), (0, 0, 2), (0, 1, 0), (0, 1, 2),
      (1, 0, 1), (1, 2, 1), (1, 2, 0), (1, 2, 2), (1, 0, 0), (1, 0, 2), (1, 1, 0), (1, 1, 2)]
RGB = np.array([[(0, 128, 255)[c] for c in t] for t in HW], np.uint8)

T_CHAR = 4
LINE_CH = 64
FIELD_LINES = 312
BLACK = 0x14            # the hardware colour black (for sync)
H_PORCH = 14            # characters from HSYNC's start to the monitor's line start


def mode_lut():
    """byte -> 8 pen indices at mode-2 resolution, for modes 0, 1, 2"""
    lut = np.zeros((4, 256, 8), np.uint8)
    for b in range(256):
        bit = [(b >> (7 - i)) & 1 for i in range(8)]
        p0 = bit[0] | bit[4] << 1 | bit[2] << 2 | bit[6] << 3
        p1 = bit[1] | bit[5] << 1 | bit[3] << 2 | bit[7] << 3
        lut[0, b] = [p0] * 4 + [p1] * 4
        for i in range(4):
            lut[1, b, 2 * i:2 * i + 2] = bit[i] | bit[i + 4] << 1
        lut[2, b] = bit
        lut[3, b] = lut[0, b]
    return lut


class Video:
    def __init__(self, page_views):
        self.page_views = page_views        # () -> 4 uint8 arrays, the base pages 0-3 (zero-copy)
        self.views = None                   # cached; the owner sets None when banking changes
        self.r = [63, 40, 46, 0x8E, 38, 0, 25, 30, 0, 7, 0, 0, 0x30, 0, 0, 0, 0, 0]
        self.ct = 0                         # absolute character time
        self.c0 = self.c4 = self.c9 = 0
        self.c5 = 0
        self.adjust = False
        self.last_line = False
        self.c0_reached_1 = False
        self.vma = self.vma_row = 0x3000
        self.vma_next = 0x3000
        self.vdisp = True
        self.hsync_left = 0
        self.vsync_left = 0
        self.vsync_hs = 0
        self.vs_done = False                # VSync already given for this C4 = R7 match
        # Gate Array
        self.pens = [0x14] * 17
        self.mode = 1
        self.next_mode = 1
        self.icount = 0
        self.int_pending = False
        # monitor
        self.field_no = 0
        self.field_start = 0                # character time VSYNC last started
        self.h_anchor = 0                   # character time HSYNC last started
        self.field = np.zeros((FIELD_LINES, LINE_CH * 16), np.uint8)
        self.lut = mode_lut()
        self.on_field = None                # callback(field_no, image) at each VSYNC start
        self.field_lengths = []             # us from each VSYNC start to the next

    # --------------------------------------------------------------- positions
    def pos(self, ct=None):
        """(field, microseconds since VSYNC started) of a character time"""
        ct = self.ct if ct is None else ct
        return self.field_no, ct - self.field_start

    # --------------------------------------------------------------- the CPU side
    def write_crtc(self, reg, v, t):
        self.catch_up(t)
        if reg < 18:
            self.r[reg] = v
        if reg == 7 and v == self.c4 and self.c0 >= 2 and not self.vsync_left and not self.vs_done:
            self.vs_done = True
            self.start_vsync()

    def write_ga_pen(self, pen, colour, t):
        self.catch_up(t)
        self.pens[pen] = colour & 31

    def write_ga_mode(self, v, t):
        self.catch_up(t)
        self.next_mode = v & 3              # the GA takes a new mode at the next HSYNC
        if v & 0x10:
            self.icount = 0
            self.int_pending = False

    def acknowledge(self):
        self.int_pending = False
        self.icount &= 0x1F

    def vsync_active(self, t):
        self.catch_up(t)
        return self.vsync_left > 0

    # --------------------------------------------------------------- the clock
    def catch_up(self, t):
        target = t // T_CHAR
        while self.ct < target:
            nb = self.next_boundary()
            n = min(nb - self.c0, target - self.ct)
            if n <= 0:
                self.char_step()
                continue
            self.span(n)

    def next_boundary(self):
        """the next C0 (> the current) at which something but C0 and VMA changes"""
        r = self.r
        c0 = self.c0
        cands = [r[0] + 1 if r[0] >= c0 else c0 + 1]
        for b in (1, 2, r[1], r[2]):
            if b > c0:
                cands.append(b)
        if self.hsync_left:
            cands.append(c0 + self.hsync_left)
        return min(cands)

    def span(self, n):
        """n characters with no boundary inside: draw them, move C0 and VMA"""
        self.draw(n)
        if self.hsync_left:
            self.hsync_left -= n
            if self.hsync_left == 0:
                self.hsync_end()
        self.c0 += n
        self.vma = (self.vma + n) & 0x3FFF
        self.ct += n
        self.at_c0()

    def char_step(self):
        self.span(1)

    def at_c0(self):
        """the state changes due at the C0 just reached (end-of-line wrap included)"""
        r = self.r
        c0 = self.c0
        if c0 == 1:
            self.c0_reached_1 = True
        if c0 == 2 and not self.adjust:
            self.last_line = self.c9 == r[9] and self.c4 == r[4]
        if c0 == r[1] and self.c9 == r[9]:
            self.vma_next = self.vma
        if c0 == r[2] and r[3] & 15:
            self.hsync_left = r[3] & 15
            self.h_anchor = self.ct           # the monitor's line locks to HSYNC
        if c0 > r[0]:                       # the line ends
            self.new_line()

    def hsync_end(self):
        self.mode = self.next_mode
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
        if self.vsync_left:
            self.vsync_left -= 1

    def new_line(self):
        self.line_counters()
        self.vsync_test()

    def vsync_test(self):
        """type 0: C4 = R7 is tested at every line's start; one VSync per match"""
        if self.c4 == self.r[7]:
            if not self.vs_done and not self.vsync_left:
                self.vs_done = True
                self.start_vsync()
        else:
            self.vs_done = False

    def line_counters(self):
        r = self.r
        self.c0 = 0
        reached = self.c0_reached_1
        self.c0_reached_1 = False
        if self.adjust:
            self.c5 += 1
            if self.c5 >= r[5]:
                self.new_frame()
            return
        if self.last_line:
            self.last_line = False
            if r[5]:
                self.adjust = True
                self.c5 = 0
                self.c4 = (self.c4 + 1) & 127
                self.c9 = 0
                return
            self.new_frame()
            return
        if not reached:
            self.vma = self.vma_row
            return
        if self.c9 == r[9]:
            self.c9 = 0
            self.c4 = (self.c4 + 1) & 127
            self.vma_row = self.vma = self.vma_next
            if self.c4 == r[6]:
                self.vdisp = False
        else:
            self.c9 = (self.c9 + 1) & 31
            self.vma = self.vma_row

    def new_frame(self):
        r = self.r
        self.adjust = False
        self.c4 = self.c9 = 0
        self.vma_row = self.vma = self.vma_next = (r[12] << 8 | r[13]) & 0x3FFF
        self.vdisp = r[6] > 0

    def start_vsync(self):
        if self.vsync_left:
            return
        self.vsync_left = (self.r[3] >> 4) or 16
        self.vsync_hs = 2
        if self.on_field:
            self.on_field(self.field_no, self.field)
        self.field = np.zeros_like(self.field)
        self.field_lengths.append(self.ct - self.field_start)
        self.field_no += 1
        self.field_start = self.ct

    # --------------------------------------------------------------- the picture
    def draw(self, n):
        # the picture's x follows HSYNC (a monitor locks to it), its rows VSYNC: x = 0 is
        # H_PORCH characters after HSYNC began (C0 = 0 for the firmware's R2 = 46 + 4)
        base = self.field_start + (self.h_anchor + H_PORCH - self.field_start) % LINE_CH
        rel = self.ct - base
        if rel < 0:
            return
        line, x = divmod(rel, LINE_CH)
        if line >= FIELD_LINES:
            return
        n = min(n, LINE_CH - x)
        if n <= 0:
            return
        row = self.field[line]
        if self.hsync_left or self.vsync_left:
            row[x * 16:(x + n) * 16] = BLACK
            return
        r = self.r
        disp = self.vdisp and not self.adjust and (r[8] & 0x30) != 0x30
        if not disp:
            row[x * 16:(x + n) * 16] = self.pens[16]
            return
        k = min(n, max(0, r[1] - self.c0))
        if k:
            if self.views is None:
                self.views = self.page_views()
            ma = (self.vma + np.arange(k)) & 0x3FFF
            off = ((self.c9 & 7) << 11) | ((ma & 0x3FF) << 1)      # within the 16K page
            page = ma >> 12
            b = np.empty(2 * k, np.uint8)
            if (page == page[0]).all():
                v = self.views[page[0]]
                b[0::2] = v[off]
                b[1::2] = v[off + 1]
            else:
                for p in set(page.tolist()):
                    sel = page == p
                    v = self.views[p]
                    b[0::2][sel] = v[off[sel]]
                    b[1::2][sel] = v[off[sel] + 1]
            pens = np.array(self.pens[:16], np.uint8)
            row[x * 16:(x + k) * 16] = pens[self.lut[self.mode][b]].reshape(-1)
        if n > k:
            row[(x + k) * 16:(x + n) * 16] = self.pens[16]


if __name__ == '__main__':
    print(__doc__)
