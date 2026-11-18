"""ay2sn.py - convert AY-3-8910 register states to SN76489 states, offline, per field.

Fork this into your project's tools/; keep this header.

From 1942-beeb's `tools/ay2sn.py` (Layer 8, decisions 46-54, 2026-09-10/11). There the
arcade's sound CPU was run headless from its ROM (beeb_port_kit/mame/z80sub.py) and its
two AYs' registers taken after every sound IRQ; this turned them into what the BBC's
SN76489 should hold at each 50 Hz field, so the 6502 player only replays register
values and converts nothing at run time. The rules are arkos-player-bbc's
lib/ay2sn.asm, re-derived with the clocks as parameters - which is the point of
having it here: a CPC or Spectrum source has AYs too, at other clocks.

  TONE    SN N = AY P x (SN_CLOCK / 32) / (AY_CLOCK / 16) = P x SN_CLOCK / (2 AY_CLOCK).
          1942's AYs are 1.5 MHz (`mame -listxml 1942`), not arkos's 1 or 2 MHz, so
          N = 4/3 P on a 4 MHz BBC SN.
  BASS    N > 1023 is below the SN's floor (122 Hz at 4 MHz). PERIODIC NOISE: noise
          control %011 (periodic, clocked by tone 2) with tone 2 = round(N / 15), so
          a bass voice takes tone 2 AND the noise channel, silencing tone 2 itself.
          When a drum wants the noise in the same field the drum wins and the bass
          drops an octave at a time into range instead (arkos's rule).
  VOLUME  AY 4-bit v -> 5-bit (v << 1) | (v & 1) -> 15 - ((n + 1) >> 1) attenuation
          (arkos make_tables.py). The AY's hardware envelope is not converted; 1942's
          sound ROM never set a volume register's bit 4 (sound_rip.py's inventory).
          A tune that does may play the envelope as a TIMBRE, not a fade, as
          phX's do (Factor6, Vortex Tracker II, 2026-11): R13 = 12, the repeating
          sawtooth, with the envelope period locked to the tone (tone 703, envelope
          22: 22 x 32 = 704), so it repeats at an audio rate and cannot be stepped
          per field. Flatten it before calling this: such a channel becomes a plain
          tone at full volume at its TONE's pitch, or at the envelope's own pitch
          (period x 16) when its tone is off (phX tools/music_convert.py).
  NOISE   AY 5-bit noise period -> the nearest of the SN's three fixed rates BY
          FREQUENCY; volume from the loudest noise-enabled channel.
  VOICES  up to three tones. One chip's three channels map straight across; two
          chips (1942's jingles) are six, and the three LOUDEST win each field,
          STICKY - a voice keeps its SN channel while it stays selected, so nothing
          hops slots between fields.
  TN      tn_noise=True: a channel with tone AND noise both on is the AY's noise
          gated by a low square - a growl, not a note - and the SN cannot AND the
          two. 1942 plays it as its noise alone (KC 2026-09-11: as a separate square
          the gun "needs work").

IRQS_PER_FIELD: 1942's sound IRQ is 4 per VIDEO frame (measured), so the sound is
frame-locked; taking 4 per 50 Hz field keeps it frame-locked on the BBC - the same
slowdown the game takes (59.6 Hz treated as 50, decision 10), pitch unchanged.
A fraction (4 x 59.637 / 50) gives real time instead.

Everything upstream of this is exact (the sound CPU, scored RAM for RAM against MAME,
0 wrong); THIS is the one step judged by ear, which is why render_ay/render_sn exist:
the same rip through both chips, for listening side by side. Decode the chip bytes
the player writes against these states; never count them (1942 BUGS.md #66: a count
of the writes passed three corrupted tunes).

    conv = Converter(ay_clock=1_500_000)
    states, stats = conv.convert(rows)           # rows: per IRQ, [regs_chip0, regs_chip1]
    write_wav("x_sn.wav", render_sn(states, conv))   # needs numpy

A field state is [N0, A0, N1, A1, N2, A2, noise_ctl, noise_att]: a tone period and an
attenuation per SN channel (15 = silent), the noise control byte (-1 = untouched) and
its attenuation.
"""

import math
import wave

SN_MAX = 1023
SILENT = 15


def sn_atten(v4):
    """AY 4-bit volume -> SN 4-bit attenuation (arkos make_tables.py)."""
    n = ((v4 & 15) << 1) | (v4 & 1)
    return 15 - ((min(n + 1, 31) >> 1) & 15)


class Converter:
    def __init__(self, ay_clock, sn_clock=4_000_000, irqs_per_field=4, field_hz=50,
                 sn_max=SN_MAX):
        self.ay_clock, self.sn_clock = ay_clock, sn_clock
        self.irqs_per_field, self.field_hz, self.sn_max = irqs_per_field, field_hz, sn_max
        self.sn_noise_hz = [sn_clock / (32.0 * 16 * (1 << r)) for r in range(3)]

    # --- the per-register rules ---------------------------------------------------
    def sn_period(self, ay_period):
        """SN tone period for an AY tone period (may exceed sn_max: see convert)."""
        return round(max(ay_period, 1) * self.sn_clock / (2.0 * self.ay_clock))

    def ay_hz(self, ay_period):
        return self.ay_clock / (16.0 * max(ay_period, 1))

    def sn_hz(self, n):
        return self.sn_clock / (32.0 * max(n, 1))

    def noise_rate(self, ay_noise_period):
        """The SN's fixed noise rate (0-2) nearest by frequency to the AY's."""
        f = self.ay_clock / (16.0 * max(ay_noise_period & 31, 1))
        return min(range(3), key=lambda r: abs(f - self.sn_noise_hz[r]))

    # --- rows -> fields -----------------------------------------------------------------
    def fields(self, rows, loop=None):
        """The state after the last IRQ of each field, and the field the loop
        restarts at. loop = (first_row, length) in IRQ rows, 0-based, or None.
        With an integral irqs_per_field and a loop that is a whole number of fields,
        any field inside the loop's first pass repeats exactly."""
        ipf = self.irqs_per_field
        lf = None
        if loop is not None:
            start, length = loop
            rows = rows[:start + length]
            lf = int(math.ceil(start / float(ipf)))
        if ipf == int(ipf):
            k = int(ipf)
            return rows[k - 1::k], lf
        n = int(len(rows) / ipf)
        return [rows[min(len(rows) - 1, int(round((i + 1) * ipf)) - 1)]
                for i in range(n)], lf

    @staticmethod
    def voices(row, chips, tn_noise=False):
        """Every audible tone: [(voice_id, ay_period, vol)], and the loudest
        noise-enabled channel's (vol, ay_noise_period)."""
        out, noise = [], (0, 0)
        for ci in chips:
            g = row[ci]
            for ch in range(3):
                vol = g[8 + ch] & 15
                tone_on = not (g[7] >> ch) & 1
                noise_on = not (g[7] >> (3 + ch)) & 1
                p = g[2 * ch] | ((g[2 * ch + 1] & 15) << 8)
                if vol and noise_on and vol > noise[0]:
                    noise = (vol, g[6] & 31)
                if vol and tone_on and not (tn_noise and noise_on):
                    out.append((ci * 3 + ch, max(p, 1), vol))
        return out, noise

    @staticmethod
    def chips_of(rows):
        """The chips any row gives an audible volume."""
        n = len(rows[0]) if rows else 0
        return [c for c in range(n)
                if any(any(r[c][8 + ch] & 15 for ch in range(3)) for r in rows)]

    def convert(self, rows, loop=None, chips=None, tn_noise=False, atten_add=0):
        """[field state], stats. atten_add makes every audible attenuation that many
        2 dB steps quieter - a per-sound trim for the ear."""
        frows, lf = self.fields(rows, loop)
        chips = self.chips_of(rows) if chips is None else chips
        slots = [None, None, None]
        out = []
        st = {"fields": len(frows), "loop": lf, "chips": chips, "periodic": 0,
              "octave": 0, "dropped": 0, "drum": 0}
        for row in frows:
            tv, (nvol, nper) = self.voices(row, chips, tn_noise)
            tv.sort(key=lambda v: -v[2])
            keep = tv[:3]
            st["dropped"] += len(tv) - len(keep)
            ids = {v[0] for v in keep}
            slots = [s if s in ids else None for s in slots]
            for v in keep:
                if v[0] not in slots:
                    slots[slots.index(None)] = v[0]
            byid = {v[0]: v for v in keep}
            state = [0, SILENT, 0, SILENT, 0, SILENT]
            noise_ctl, noise_att = None, SILENT
            if nvol:
                noise_ctl, noise_att = 4 | self.noise_rate(nper), sn_atten(nvol)
                st["drum"] += 1
            bass = None
            for s, vid in enumerate(slots):
                if vid is None:
                    continue
                _, p, vol = byid[vid]
                n = self.sn_period(p)
                if n > self.sn_max:
                    if noise_ctl is None and bass is None:
                        bass = (s, n, vol)
                        continue
                    while n > self.sn_max:
                        n >>= 1
                    st["octave"] += 1
                state[2 * s], state[2 * s + 1] = n, sn_atten(vol)
            if bass:
                s, n, vol = bass
                # the bass sounds on tone 2's clock: whatever held tone 2 moves to the
                # bass's own slot, and tone 2 itself is silenced
                if s != 2:
                    state[2 * s], state[2 * s + 1] = state[4], state[5]
                    slots[s], slots[2] = slots[2], slots[s]
                state[4], state[5] = max(1, min(self.sn_max, round(n / 15.0))), SILENT
                noise_ctl, noise_att = 3, sn_atten(vol)
                st["periodic"] += 1
            out.append(state + [noise_ctl if noise_ctl is not None else -1, noise_att])
        if atten_add:
            for f in out:
                for i in (1, 3, 5, 7):
                    if f[i] < SILENT:
                        f[i] = min(SILENT, f[i] + atten_add)
        return out, st


# --- rendering, for the ear (needs numpy) ---------------------------------------------
RATE = 44100
AY_LEVEL = [0, 0.0137, 0.0205, 0.0291, 0.0423, 0.0618, 0.0847, 0.1369, 0.1691,
            0.2647, 0.3527, 0.4499, 0.5704, 0.6873, 0.8482, 1.0]
SN_LEVEL = [10.0 ** (-0.1 * 2 * a) for a in range(15)] + [0.0]


def _np():
    try:
        import numpy
    except ImportError:
        raise ImportError("rendering needs numpy: pip install numpy")
    return numpy


def _square(np, freq, n, phase):
    t = phase + np.arange(n) * (freq / RATE)
    return np.where((t % 1.0) < 0.5, 1.0, -1.0), (phase + n * freq / RATE) % 1.0


def render_ay(rows, conv, chips=None):
    """What the AYs play for these rows, one field per irqs_per_field rows, so the
    tempo matches render_sn and only the timbre differs."""
    np = _np()
    chips = conv.chips_of(rows) if chips is None else chips
    per_irq = RATE / (conv.field_hz * conv.irqs_per_field)
    out, acc, phase, lfsr = [], 0.0, {}, {c: 1 for c in chips}
    for row in rows:
        acc += per_irq
        n = int(acc)
        acc -= n
        mix = np.zeros(n)
        for chip in chips:
            g = row[chip]
            nper = max(g[6] & 31, 1)
            steps = max(1, int(n * (conv.ay_clock / (16.0 * nper)) / RATE))
            bits = np.empty(steps)
            r = lfsr[chip]
            for i in range(steps):
                r = (r >> 1) | ((((r >> 0) ^ (r >> 3)) & 1) << 16)
                bits[i] = 1.0 if r & 1 else -1.0
            lfsr[chip] = r
            nwave = np.repeat(bits, -(-n // steps))[:n]
            for ch in range(3):
                vol = g[8 + ch] & 15
                if not vol:
                    continue
                tone_on = not (g[7] >> ch) & 1
                noise_on = not (g[7] >> (3 + ch)) & 1
                p = max(g[2 * ch] | ((g[2 * ch + 1] & 15) << 8), 1)
                w = np.ones(n)
                if tone_on:
                    sq, phase[(chip, ch)] = _square(np, conv.ay_hz(p), n,
                                                    phase.get((chip, ch), 0.0))
                    w = w * sq
                if noise_on:
                    w = w * nwave
                if tone_on or noise_on:
                    mix += AY_LEVEL[vol] * w
        out.append(mix)
    return np.concatenate(out) / 3.0 if out else np.zeros(0)


def render_sn(states, conv):
    """The SN76489 as a BBC has it: 15-bit LFSR, white noise taps on bits 0 and 1."""
    np = _np()
    per = RATE / conv.field_hz
    out, acc, phase, lfsr, last_ctl = [], 0.0, [0.0] * 3, 1 << 14, None
    for s in states:
        acc += per
        n = int(acc)
        acc -= n
        mix = np.zeros(n)
        for c in range(3):
            if s[2 * c + 1] < SILENT and s[2 * c]:
                sq, phase[c] = _square(np, conv.sn_hz(s[2 * c]), n, phase[c])
                mix += SN_LEVEL[s[2 * c + 1]] * sq
        ctl, att = s[6], s[7]
        if ctl >= 0 and att < SILENT:
            if ctl != last_ctl:
                lfsr = 1 << 14          # a write to the noise register resets it
            rate = ctl & 3
            clk = conv.sn_hz(max(s[4], 1)) if rate == 3 else conv.sn_noise_hz[rate]
            steps = max(1, int(n * clk / RATE))
            bits = np.empty(steps)
            for i in range(steps):
                fb = ((lfsr ^ (lfsr >> 1)) & 1) if ctl & 4 else (lfsr & 1)
                lfsr = (lfsr >> 1) | (fb << 14)
                bits[i] = 1.0 if lfsr & 1 else -1.0
            mix += SN_LEVEL[att] * np.repeat(bits, -(-n // steps))[:n]
        last_ctl = ctl
        out.append(mix)
    return np.concatenate(out) / 3.0 if out else np.zeros(0)


def write_wav(path, x):
    """Mono 16-bit WAV at RATE, normalised to 0.8 of full scale."""
    np = _np()
    x = x / max(1e-9, float(np.max(np.abs(x))) if len(x) else 1.0) * 0.8
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((x * 32767).astype("<i2").tobytes())
