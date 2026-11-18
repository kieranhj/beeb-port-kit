"""
music_convert.py - AY fields (tools/music_extract.py) to SN76489 fields, and WAVs of both; and
the report that finds where a tune's bass changes channel.

Fork this into your project's tools/; keep this header.

From the phX port (tools/music_convert.py, 2026-11), generalised for the kit: phX's clock,
envelope volume, tune boundaries and bass sections are now the config's (JSON, below; example
tools/music_config_example.json, made-up values). The conversion itself is the kit's
beeb_port_kit/ay2sn.py (imported, not copied: _kit() below), one row a field, with what an
AY tune may need first:

  ENVELOPE AS TIMBRE. A tune may use the AY's hardware envelope as a timbre, not a fade: phX's
  (Vortex Tracker II) wrote R13 = 12 once (the repeating /|/| sawtooth) and set a volume's bit 4
  with the envelope period locked to the tone (tone 703, envelope 22: 22 x 32 = 704), so it
  repeats at an audio rate and cannot be stepped per field. The SN has no envelope: such a
  channel is played at full volume ("env_vol") at its TONE's pitch, or at the envelope's own
  pitch (period x 16) when its tone is off. A tune that uses the envelope as a slow FADE wants
  it stepped per field instead - not done here (the --report line counts the envelope writes).
  BASS BY SECTION. Which channel is the bass can change within a tune (phX's tune 1 handed it
  from A to B part-way through). "bass_sections" is [[row, channel], ...]: from that row (in
  the music_extract rows) the channel (0-2 = A-C) is ay2sn's bass_voice - ALWAYS periodic
  noise, the drum taking the noise for at most its first "drum_max" fields while the bass
  rests (ay2sn.py's BASS_VOICE). channel null, or no sections at all, or --kit-bass: the kit's
  rule (any voice under the SN's floor to periodic noise, an octave up when a drum has it).
  Each section is converted from a fresh Converter (its voice slots reset).

  --report-bass: where the bass is. For every --window rows of each tune, the frames in which
  each channel is the LOWEST audible tone, and the frames each is under the SN's floor
  (N > 1023, 122 Hz at 4 MHz); adjacent windows with the same lowest channel are merged into
  a suggested "bass_sections" list. phX's: tune 1's channel A has 2,567 of its 2,639 tone
  fields under the floor until a hand-over to B, found this way and chosen by KC's ear. The
  report suggests; the ear decides (render both with --bass and listen).

    python tools/music_convert.py DIR [--config C.json] [--from F] [--seconds S] [--tag T]
                                  [--kit-bass] [--no-wav] [--report-bass [--window W]]

DIR holds ay_fields.npy (and tunes.json, if music_extract.py --music-time wrote one). Writes
DIR/sn_fields.npy (int16 [rows, 8]: N0 A0 N1 A1 N2 A2 noise_ctl noise_att, -1 = noise
untouched, ay2sn.py's state) for EVERY row (rows between tunes silent), DIR/convert.json (each
tune's sections and ay2sn's counts), and DIR/ay[_T].wav / sn[_T].wav for the window asked
(default the first 60 s from the first audible row; needs numpy, as everything here does).

THE CONFIG (every key optional):
  ay_clock        the AY's clock, Hz (default 1000000: a CPC; a Spectrum 128 is 1773400)
  sn_clock        the SN's (default 4000000: a BBC)
  field_hz        50
  env_vol         the volume an envelope channel plays at (default 15)
  tn_noise        ay2sn's tn_noise (default false)
  drum_max        ay2sn's drum_max (default 4)
  tunes           [{"tune": 1, "row": 0, "rows": N}, ...]; default DIR/tunes.json, else the
                  whole file as one tune
  bass_sections   [[row, channel or null], ...], rows ascending; the section in force at a
                  tune's first row is the last one at or before it
  pack            music_pack.py's (chunking): see there
"""
import argparse
import json
import os
import sys

import numpy as np


def _kit():
    """beeb_port_kit: installed (pip install -e py/ in the kit), else $BEEB_PORT_KIT (the kit's
    root), else the kit checkout this file sits in (template/tools/ -> ../../py)."""
    try:
        import beeb_port_kit  # noqa: F401
        return
    except ImportError:
        pass
    here = os.path.dirname(os.path.abspath(__file__))
    for root in (os.environ.get('BEEB_PORT_KIT'), os.path.join(here, '..', '..')):
        if root and os.path.isdir(os.path.join(root, 'py', 'beeb_port_kit')):
            sys.path.insert(0, os.path.join(root, 'py'))
            return
    sys.exit('beeb_port_kit not found: pip install -e <kit>/py, or set BEEB_PORT_KIT')


_kit()
from beeb_port_kit import ay2sn  # noqa: E402

RATE = ay2sn.RATE
SILENT_STATE = [0, 15, 0, 15, 0, 15, -1, 15]


def load_config(path):
    c = json.load(open(path)) if path else {}
    c.setdefault('ay_clock', 1_000_000)
    c.setdefault('sn_clock', 4_000_000)
    c.setdefault('field_hz', 50)
    c.setdefault('env_vol', 15)
    c.setdefault('tn_noise', False)
    c.setdefault('drum_max', 4)
    c.setdefault('bass_sections', [])
    return c


def load_tunes(d, cfg, nrows):
    if cfg.get('tunes'):
        return cfg['tunes']
    tj = os.path.join(d, 'tunes.json')
    if os.path.exists(tj):
        return json.load(open(tj))
    return [{'tune': 1, 'row': 0, 'rows': nrows}]


def converter(cfg):
    return ay2sn.Converter(ay_clock=cfg['ay_clock'], sn_clock=cfg['sn_clock'],
                           irqs_per_field=1, field_hz=cfg['field_hz'])


def flatten_envelope(row, env_vol=15):
    """an AY row with each envelope channel made a plain tone at env_vol"""
    g = [int(x) for x in row]
    ep = g[11] | (g[12] << 8)
    for ch in range(3):
        if g[8 + ch] & 0x10:
            g[8 + ch] = env_vol
            if (g[7] >> ch) & 1 and ep:             # tone off: the envelope is the pitch
                p = min(4095, ep * 16)
                g[2 * ch], g[2 * ch + 1] = p & 255, p >> 8
                g[7] &= ~(1 << ch)
    return g


def env_level(shape, s):
    """the AY envelope's level (0-15) at step s since its R13 write (16 steps a cycle)"""
    k, i = s // 16, s % 16
    att, alt, hold, cont = bool(shape & 4), bool(shape & 2), bool(shape & 1), bool(shape & 8)
    first = i if att else 15 - i
    if not cont:
        later = np.zeros_like(s)
    elif hold:
        later = np.full_like(s, 15 if att != alt else 0)
    elif alt:
        later = np.where((k % 2 == 0) == att, i, 15 - i)
    else:
        later = first
    return np.where(k == 0, first, later)


def render_ay_env(fields, ay_clock=1_000_000, field_hz=50):
    """the AY as it plays: tones, noise, and the hardware envelope (every R13 shape; it
    restarts where R13's value changes between rows - the rows do not record the writes)"""
    out, phase, lfsr, acc = [], [0.0, 0.0, 0.0], 1, 0.0
    level = np.array(ay2sn.AY_LEVEL)
    per = RATE / float(field_hz)
    estep, shape = 0.0, None
    for row in fields:
        g = [int(x) for x in row]
        acc += per
        n = int(acc)
        acc -= n
        t = np.arange(n)
        if g[13] != shape:
            shape, estep = g[13], 0.0
        ep = max(1, g[11] | (g[12] << 8))
        rate = ay_clock / (16.0 * ep)                 # envelope steps a second
        s = (estep + t * rate / RATE).astype(np.int64)
        estep += n * rate / RATE
        elev = level[env_level(shape & 15, s)]
        nper = max(g[6] & 31, 1)
        steps = max(1, int(n * (ay_clock / (16.0 * nper)) / RATE))
        bits = np.empty(steps)
        for i in range(steps):
            lfsr = (lfsr >> 1) | ((((lfsr >> 0) ^ (lfsr >> 3)) & 1) << 16)
            bits[i] = 1.0 if lfsr & 1 else -1.0
        nwave = np.repeat(bits, -(-n // steps))[:n]
        mix = np.zeros(n)
        for ch in range(3):
            v = g[8 + ch]
            tone_on = not (g[7] >> ch) & 1
            noise_on = not (g[7] >> (3 + ch)) & 1
            if not (tone_on or noise_on):
                if v & 0x10:
                    mix += elev - elev.mean()       # the envelope alone: a buzz
                continue
            amp = elev if v & 0x10 else level[v & 15]
            w = np.ones(n)
            if tone_on:
                p = max(g[2 * ch] | ((g[2 * ch + 1] & 15) << 8), 1)
                f = ay_clock / (16.0 * p)
                tt = phase[ch] + t * f / RATE
                w = np.where((tt % 1.0) < 0.5, 1.0, -1.0)
                phase[ch] = (phase[ch] + n * f / RATE) % 1.0
            if noise_on:
                w = w * nwave
            mix += amp * w
        out.append(mix)
    return np.concatenate(out) / 3.0 if out else np.zeros(0)


# --- the bass report ------------------------------------------------------------------------
def tone_periods(g):
    """[(channel, ay_period)] of the audible tones of a (flattened) row"""
    out = []
    for ch in range(3):
        if (g[8 + ch] & 15) and not (g[7] >> ch) & 1:
            out.append((ch, max(1, g[2 * ch] | ((g[2 * ch + 1] & 15) << 8))))
    return out


def bass_windows(rows, conv, window):
    """per window: (first row, lowest-tone frames per channel, under-floor frames per channel)"""
    out = []
    for w0 in range(0, len(rows), window):
        low, under = [0, 0, 0], [0, 0, 0]
        for g in rows[w0:w0 + window]:
            tp = tone_periods(g)
            if not tp:
                continue
            low[max(tp, key=lambda x: x[1])[0]] += 1
            for ch, p in tp:
                if conv.sn_period(p) > conv.sn_max:
                    under[ch] += 1
        out.append((w0, low, under))
    return out


def report_bass(rows, tunes, conv, window):
    suggest = []
    for t in tunes:
        t0, t1 = t['row'], t['row'] + t['rows']
        wins = bass_windows(rows[t0:t1], conv, window)
        print(f"tune {t['tune']} rows {t0}-{t1 - 1}: lowest tone A/B/C, under the floor A/B/C,"
              f" per {window} rows")
        secs = []
        for w0, low, under in wins:
            if not any(low):
                continue
            ch = int(np.argmax(low))
            print(f'  {t0 + w0:7}  lowest {low}  under {under}  -> {"ABC"[ch]}')
            if not secs or secs[-1][1] != ch:
                secs.append([t0 + w0, ch, [0, 0, 0]])
            secs[-1][2] = [a + b for a, b in zip(secs[-1][2], low)]
        for i, (r, ch, low) in enumerate(secs):
            end = secs[i + 1][0] if i + 1 < len(secs) else t1
            print(f'  section rows {r}-{end - 1}: bass {"ABC"[ch]} (lowest-tone frames A/B/C '
                  f'{low})')
            suggest.append([r, ch])
    print('suggested "bass_sections":', json.dumps(suggest))
    return suggest


# --- the conversion -------------------------------------------------------------------------
def sections_of(tune, cfg, forced=None, kit_bass=False):
    """[(first row, bass_voice or None)] covering the tune"""
    t0, t1 = tune['row'], tune['row'] + tune['rows']
    if kit_bass:
        return [(t0, None)]
    if forced is not None:
        return [(t0, forced)]
    secs = sorted((int(r), c) for r, c in cfg['bass_sections'])
    at = [c for r, c in secs if r <= t0]
    out = [(t0, at[-1] if at else None)]
    out += [(r, c) for r, c in secs if t0 < r < t1]
    return out


def convert_all(rows, tunes, cfg, forced=None, kit_bass=False, log=print):
    """sn states for every row (silent outside the tunes) and what each tune did"""
    states = [list(SILENT_STATE) for _ in rows]
    info = []
    for k, t in enumerate(tunes):
        t1 = t['row'] + t['rows']
        f = forced[k] if forced else None
        secs = sections_of(t, cfg, f, kit_bass) + [(t1, None)]
        done = []
        for (s0, bass), (s1, _) in zip(secs, secs[1:]):
            s, st = converter(cfg).convert([[r] for r in rows[s0:s1]], chips=[0],
                                           tn_noise=cfg['tn_noise'], bass_voice=bass,
                                           drum_max=cfg['drum_max'])
            states[s0:s1] = s
            st = {k2: v for k2, v in st.items() if k2 not in ('loop', 'chips')}
            done.append({'row': s0, 'rows': s1 - s0, 'bass': bass, 'stats': st})
            log(f"tune {t['tune']} rows {s0}-{s1 - 1}: bass "
                f"{'kit rule' if bass is None else 'ABC'[bass]}; {st}")
        info.append({'tune': t['tune'], 'sections': done})
    return states, info


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('dir')
    ap.add_argument('--config', default=None)
    ap.add_argument('--from', dest='f0', type=int, default=None)
    ap.add_argument('--seconds', type=float, default=60.0, help='0: to the end')
    ap.add_argument('--tag', default='', help='the WAVs are ay_TAG.wav, sn_TAG.wav')
    ap.add_argument('--bass', default=None, help='per tune, e.g. 0,1,1: one bass channel for '
                    'each whole tune, overriding bass_sections (for listening)')
    ap.add_argument('--kit-bass', action='store_true')
    ap.add_argument('--no-wav', action='store_true')
    ap.add_argument('--report-bass', action='store_true')
    ap.add_argument('--window', type=int, default=250)
    a = ap.parse_args()
    cfg = load_config(a.config)
    fields = np.load(os.path.join(a.dir, 'ay_fields.npy'))
    rows = [flatten_envelope(r, cfg['env_vol']) for r in fields]
    tunes = load_tunes(a.dir, cfg, len(rows))
    conv = converter(cfg)
    if a.report_bass:
        report_bass(rows, tunes, conv, a.window)
        return
    forced = [int(x) for x in a.bass.split(',')] if a.bass else None
    states, info = convert_all(rows, tunes, cfg, forced, a.kit_bass)
    np.save(os.path.join(a.dir, 'sn_fields.npy'), np.array(states, np.int16).reshape(-1, 8))
    json.dump({'tunes': info}, open(os.path.join(a.dir, 'convert.json'), 'w'), indent=1)
    if a.no_wav:
        return
    audible = ((fields[:, 8:11] & 0x1F) != 0).any(1)
    f0 = a.f0 if a.f0 is not None else int(np.argmax(audible))
    f1 = len(fields) if a.seconds <= 0 else min(len(fields), f0 + int(a.seconds * cfg['field_hz']))
    print(f'rendering rows {f0}-{f1 - 1} ({(f1 - f0) / cfg["field_hz"]:.1f} s)')
    tag = '_' + a.tag if a.tag else ''
    ayw, snw = os.path.join(a.dir, f'ay{tag}.wav'), os.path.join(a.dir, f'sn{tag}.wav')
    ay2sn.write_wav(ayw, render_ay_env(fields[f0:f1], cfg['ay_clock'], cfg['field_hz']))
    ay2sn.write_wav(snw, ay2sn.render_sn(states[f0:f1], conv))
    print('wrote', ayw, snw)


if __name__ == '__main__':
    main()
