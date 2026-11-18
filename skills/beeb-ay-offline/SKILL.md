---
name: beeb-ay-offline
description: Convert an AY-3-8910/8912 tune to the BBC's SN76489 offline, one record per field - extract the AY registers from the reference run, measure how the tune uses the chip (envelope, noise, which channel is the bass in each section), convert with periodic-noise bass and the envelope as a timbre, render AY and SN WAVs for the owner's ear, and pack the stream into tunes and bank-sized chunks. Use for a CPC or Spectrum original's music when the player must cost a fixed few hundred cycles a field (a raster demo, a cycle-counted game), or when a run-time ay2sn sounds wrong.
---

# AY to SN, offline

A raster demo cannot spare a software-bass interrupt or a run-time converter: the SN gets a
pre-made record each field, a count byte and the bytes to send (`docs/cpc-demo-porting.md` §19).
What decides whether it sounds right is measured, per section of the tune, not assumed per tune:
phX's tune 1 handed the bass from channel A to channel B halfway through, and treating A as the
bass throughout turned a deliberate glitch into a flat noise and the bass line into one note
(decision 65).

**Pass:** the owner's ear on the AY and SN WAVs side by side, then the player's bytes in jsbeeb
identical to the stream, tick for tick (`beeb-sound-verify`).

## Steps

1. **Extract** the AY registers per field (or per music frame) from the reference run's log:

   ```
   python tools/music_extract.py work/ref/ay.log work/music --music-time
   ```

   `--format` reads the kit's `cpcrun.py`/`cpcref_units.py` AY logs or raw PPI OUTs.
   `--music-time` gives one row per music frame - the demo's own clock when the original plays
   0 or 2 frames a field during loads - finds the tunes and writes `tunes.json`.

2. **Measure the chip use** before converting: envelope shapes and whether the envelope period
   is locked to a tone (a timbre, not an envelope), noise periods, and the bass:

   ```
   python tools/music_convert.py work/music --report-bass --window 80
   ```

   It prints, per window, the lowest channel and the channels under the SN's floor (~122 Hz,
   N = 1023), and suggests `bass_sections`. Read the suggestion; where two channels tie
   (unisons), keep the earlier choice the owner has heard.

3. **Configure** from `tools/music_config_example.json`: the tunes' rows and the
   `bass_sections` (`[row, channel]` list). Periodic noise for the bass (clocked by tone 2 at
   N / 15) is the default for raster demos; close bass periods collapse under N / 15, so listen
   for it.

4. **Convert and render** for listening:

   ```
   python tools/music_convert.py work/music --config music.json --from 4100 --seconds 28 --tag cube
   ```

   `ay_cube.wav` (the AY with its envelope) against `sn_cube.wav`. Give the owner short windows
   around anything that changes, and alternatives when the SN cannot do what the AY does (phX:
   the AY's tone AND noise has no SN equivalent; a white-noise-clocked-by-tone-2 variant was
   offered and the plain one chosen). The owner decides; record the decision.

5. **Pack** each tune from a fresh chip, and the sequence in bank-sized chunks:

   ```
   python tools/music_pack.py work/music --tunes
   python tools/music_pack.py work/music --seq build/data --config music.json
   ```

   `--tunes` prints sizes raw and ZX02-packed at several offset limits (`-m`: what a streaming
   decoder's ring must hold); `--seq` writes the chunks, `music_seq.6502` and `sn_rows.json`, and
   decodes every chunk back against the SN states. Run `--tunes` before `--seq` when the
   conversion changed: `--seq` checks against the tunes' files.

6. **Verify the player** against `sn_rows.json` tick for tick in jsbeeb, across chunk changes,
   rests and the restart (`beeb-sound-verify`), and the field budget (the tick's worst cycles).

## Traps

- The AY's clock: a CPC's AY is 1 MHz (N = 2P on a 4 MHz SN); a Spectrum's 1.7734 MHz.
- Commit the conversion, then build: a disc stamped with the previous commit says the old music.
- A drum takes the noise channel from the periodic bass; the converter gives the drum the first
  `drum_max` fields of a noise run and the bass rests meanwhile - check the rests by ear.
