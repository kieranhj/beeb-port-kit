# Done

**What has landed, per layer or per brief, with the number that says it landed.** `PLAN.md` is
what is left; this is the other half of it, so that a line can leave the plan without the evidence
leaving with it. When a `PLAN.md` item is finished, its evidence - the measurement, the oracle's
verdict, the commit - comes here, and the plan loses the line.

It is also where the rules file's history goes. `CLAUDE.md` keeps the RULE and the trap; the story
of how the rule was learned, the figures it carried on a given day and the designs it replaced
come here, so the file loaded every session stays small (`CLAUDE.md`'s budget line).

The deep detail is in `docs/layer-*.md` and `docs/brief-*.md`; every deviation is in
`docs/decisions.md` and every defect in `BUGS.md`. **This file is a log, not a source of truth** -
where it disagrees with those, they win. Newest first within a heading. Every figure says what
measured it and when (MEASURED off a tool run, COUNTED off the listing, PROJECTED from a count).

---

## Layer 0 - the toolchain

**2026-09-07.** The template builds with Baron and boots in jsbeeb: a panel over a scrolling strip
at 25 Hz, all eight MODE 1 colours on screen (decision 4). The frame lock held 100 fields to
exactly 50 passes (`docs/layer-0-toolchain.md`); `verify_dynamic` is the check.

---

<!-- One heading per layer and per brief, in the order they landed:

## Layer N - <name>  /  ## <brief title> (`docs/brief-<name>.md`)

**<date>, <commit>.** What landed, in a sentence. The number that says so ("0 of 14,336 at every
tick", "13 objects fit a 25 Hz tick", "main RAM 3 -> 179 bytes"), the oracle or tool that gave it,
and the emulator version if it is a cycle figure. What it cost. A pointer to the doc with the rest.
-->
