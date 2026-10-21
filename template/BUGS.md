# Bugs

Open defects, with the evidence and what has been ruled out. Fixed entries stay for what they
ruled out. Index first, detail below.

| # | Status | Summary |
|---|---|---|
| 1 | FIXED | Every T1 fire alternated by ~24 cycles between frame-lock take and non-take fields: the take ran before the T1 restart in `rupt_vsync` |
| 2 | OPEN | `examples/vscroll/tools/verify_vscroll.mjs` throws on jsbeeb 2.3.1 and later: it passes numeric key codes, not `keys()` |

<!--
Format for an entry:

## N. One-line title

**Open YYYY-MM-DD.** Who saw it and where (emulator, model, hardware).

### What was measured
The numbers: cycle counts, addresses, bytes read back, screenshots referenced.

### Ruled out
What was tried and what it showed.

### Fixed (Layer X, YYYY-MM-DD)
The cause and the change, and the check that proved it.
-->

## 2. verify_vscroll.mjs throws on jsbeeb 2.x

**Open 2026-10-06, fixed 2026-10-21** (found in the 2026-10-06 documentation pass, a missed file
in the jsbeeb 2.0 fix). The example's harness, not the template's build.

### What was measured
2026-10-13, jsbeeb 2.3.2 (the `jsbeeb-mcp@4.0.0` cache): `node tools/verify_vscroll.mjs
build/vscroll.ssd 02 0D 10` stops at line 151, `s.keyDown(16)` (SHIFT+BREAK), in jsbeeb's
`requireKnownKeyCode`. Line 72's `KEY_DOWN = 40` and its `keyDown`/`keyUp` at 165 and 232 are the
same mistake. jsbeeb 2.x takes `KeyboardEvent.code` strings; up to 2.3.0 a number was silently
never pressed, from 2.3.1 it throws (`../docs/hardware-facts.md`, the jsbeeb 2.0 key note).

### Ruled out
The disc: `vscroll.ssd` is byte-identical across Baron 0.4.0, 0.5.3 (2026-10-11) and 0.6.0 (2026-10-21). The template's
own harnesses, `verify_dynamic.mjs` and `probe_shot.mjs`, already take keys from `keys()` in
`tools/jsbeeb_src.mjs` and run.

### Fixed (2026-10-21)
`keys()` has a `DOWN` (`ArrowDown` on 2.x, `40` on 1.x), and the harness takes SHIFT and DOWN from
it. Re-run on jsbeeb 2.10.2 (the `jsbeeb-mcp@4.3.0` cache): `pass: true`, and every figure in
`docs/vertical-scroll.md`'s table the same as jsbeeb 1.25.0's - field 39,936 cycles, 50 scanlines in
50 fields, strip 0 of 10,240, view 0 of 38,400, sliver 0 of 19,840, one lit run of 320x152,
`linesSeen` 0-7.

## 1. The fires alternated phase with the frame-lock take

**Open 2026-09-07, fixed the same day.** Found in jsbeeb while phasing the palette switch (decision 4).

### What was measured
The palette group that had to land in horizontal blanking landed 24 cycles apart in two boots
of the same build (entry 0's write visible at character 51 in one boot and 75 in another at the
same `T1_TUNE2`, read off the screenshot PNG by pixel scan), and the breakpoint pair
VSync-entry -> fire 1 read 9,391 and 9,367 on consecutive fields - the two numbers the original
Layer 0 recorded without asking why they differed.

### Cause
`rupt_vsync` ran the frame-lock take (six loads and stores, only when `frame_ready` and
`FRAME_LOCK` fields have passed) BEFORE restarting T1, so the restart - and every fire timed from
it - moved by the take's ~24 cycles on every second field. A single-write fire in blanking has
48 cycles of room and hides it; a 24-cycle group in the same 48 does not.

### Fixed (Layer 0, 2026-09-07)
The T1 restart is the first thing in `rupt_vsync` (decision 5). Consecutive fields now show the
switch at the same character on both parities (screenshot pairs one field apart, pixel-scanned),
and VSync-entry -> fire 1 reads 9,295 / 9,299.
