---
name: beeb-winape-check
description: Check a home-made CPC reference against WinAPE (CRTC type 0) automatically - capture the original running in WinAPE at known times, match every capture to the reference field it shows, classify what differs - then review each part's BBC code against the original's source where it exists. Use at Layer 1 of a CPC port, as soon as the reference makes pictures, and again before calling any part done; not at release.
---

# The third reference: WinAPE, then the source

A home-made CPC reference is an oracle too. phX's showed every outro row's scanlines in the
wrong order, and the BBC port copied it faithfully: every harness passed, because each one
compares the BBC against the reference (decision 63). A logo row short and the Gate Array's
writes half a microsecond early were found the same way, and only this way. A third party's
emulator is the cheapest independent check there is; the original's source is the next.

**Pass:** every matched capture identical to its reference field, or its difference explained
(a known reference defect, the loads' timing) and written down.
**Do it early:** phX ran it after every part was built (`docs/cpc-demo-porting.md` §14).

## Steps

1. **Set WinAPE up for verification**, once: a CPC 6128, CRTC type 0 (or the type the demo's
   own test picks), no Plus, no PAL filter or stretch, 100% speed, set in WinAPE's dialog and
   kept in a separate copy of WinAPE.ini (see `template/tools/cpc/winape_shot.ps1`'s help:
   `Get-Help .\tools\cpc\winape_shot.ps1 -Full`). Check one capture by eye before trusting a run:
   an install with its own settings captures a scaled picture.

2. **Capture.** Wall-clock captures from the moment WinAPE starts the disc (`/A` autoruns it):

   ```powershell
   .\tools\cpc\winape_shot.ps1 -Disc original.dsk -Out work\winape\run1 -Every 0.5 -Until 330 -Exe $env:WINAPE
   ```

   Captures land as PNGs named by milliseconds. A run that stops early (WinAPE closed, the
   machine slept) is rerun, not patched.

3. **Make the reference's fields as pictures** (the project's picture machine, e.g.
   `tools/cpc/cpcvideo.py` driven by `tools/cpc/cpcboot.py`'s logs), one PNG per field.

4. **Match.** Copy `tools/cpc/example_winape_parts.json` and fill in the project's parts (field
   ranges), the capture box and scale, thresholds, and the field-0 time `t0`:

   ```
   python tools/cpc/winape_match.py work/winape/run1 work/ref/frames work/winape/match --config winape_parts.json
   ```

   It writes `match.csv` (each capture's best field and its difference), one frame per part and
   a difference sheet. A part whose reference is known to be wrong (decision 63's outro) can take
   another picture source from a field on (`--override FILE:FIELD`).

5. **Classify every residue** in a project doc (phX: `docs/winape-check.md` "The result"): pixel
   identical; a raster line or a byte column (OUT timing in the reference); a load's lag (the
   drive model); a real reference error - each of the last goes in BUGS.md with its fields.

6. **Review against the source**, when it exists (keep it out of git if its licence says so):
   each part's BBC code read beside the original's, for what no picture check sees - durations,
   rows, fades between parts, palette ladders, off-by-ones, the original's own bugs (phX's Balls
   carry bug: copy it, and say so). Findings go in BUGS.md; deviations still need the owner.

7. **Re-run after any change to the reference machine** - its fixes change every expected picture
   downstream.

## Traps

- The reference passing its own checks proves nothing about the CPC (`docs/gotchas.md` class 1).
- WinAPE's top line is black in every part; the reference's is not. Crop it, don't "fix" it.
- Field timing: the original's loads run off its drive; expect captures to drift by seconds
  around loads and match within a window (`--window`).
