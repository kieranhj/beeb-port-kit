# Bugs

Open defects, with the evidence and what has been ruled out. Fixed entries stay for what they
ruled out. Index first, detail below.

| # | Status | Summary |
|---|---|---|
| 1 | FIXED | Every T1 fire alternated by ~24 cycles between frame-lock take and non-take fields: the take ran before the T1 restart in `rupt_vsync` |

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
