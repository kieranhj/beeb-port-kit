---
name: beeb-doc-pass
description: A full pass over a BBC Micro port's documentation - put every fact in the one file it belongs in, check it against the code and the build, bring CLAUDE.md back inside its size budget, cut PLAN.md to what is left, move landed work's evidence to docs/done.md, give every decision its real status, regenerate the generated pages, and sweep for stale mentions. Documents only, on its own branch. Use when the user asks for a documentation pass, to tidy or update the docs, to make PLAN.md tight, to shrink CLAUDE.md, or to check the docs are consistent.
---

# Documentation pass

A port's documents drift one way: facts accumulate where they were first written, figures go
stale, `PLAN.md` turns into a history and the rules file into a diary. 1942's `CLAUDE.md` was
touched in 198 of 483 commits, grew 22K -> 167K - loaded in full every session - and needed nine
passes; its hand-kept pages (the memory map, the cell sheet, a chart, the decisions table's
Markdown) all went wrong at least once. This pass puts every fact in the ONE place it belongs,
checks it against the code and the build, and leaves `PLAN.md` as a short list of work. **It
changes documents only** - never code, data or tools, except to regenerate a generated file.

## 0. Before starting

- **Work on a branch** (`docs-pass-<date>`); do not start while another branch is about to merge
  documents - ask. Merge the default branch in first if this one is behind.
- **Build first**, so every figure is read off THIS build.
- Read the project's `CLAUDE.md` in full: its artefacts table, its generated files and its "never
  hand-edit" rules override anything here. Note its size (`wc -c CLAUDE.md`).

## 1. Where each kind of fact belongs

The project's own artefacts table wins; this is the default (`PORTING.md` §3):

| File | Holds | Does NOT hold |
|---|---|---|
| `CLAUDE.md` | standing rules, measured facts, traps, build and oracle commands - **inside its budget (~40K)** | history, what landed when, open work, figures that move on every edit, long oracle descriptions |
| `PLAN.md` | what is LEFT, in the owner's priority order, each item a few lines with a pointer to its brief | anything done, measurements, war stories |
| `docs/done.md` | what landed, per layer or brief, each with the number that says it landed; the rules file's history | plans |
| `docs/decisions.md` | the ONLY copy of every decision, numbered, short, with its Status | rationale essays (link the brief) |
| `BUGS.md` | numbered defects with evidence; fixed ones stay, marked FIXED with the commit | fixes' design notes (link them) |
| `docs/brief-*.md` | one job each: the plan, then a closing "what landed" | project-wide rules |
| an oracles doc (e.g. `docs/oracles.md`) | each oracle's long description, its runs, its known false failures | - |
| `README.md` | what the project is, how to build and run it, current state in a paragraph, where to look | detail that goes stale weekly |
| generated pages (`docs/memory-map.md`, per-asset sheets) | whatever the generator writes | hand edits - REGENERATE |

## 2. The pass, in order

1. **PLAN.md - make it tight.** Every item that is done moves OUT: its evidence (the numbers, the
   commit, the oracle's verdict) to `docs/done.md` under the right heading, its design detail to
   its brief. What stays is open work only: what is left, why it matters, the brief or bug, the
   decision it waits on. Keep the owner's order; if none is stated, say which you used. Aim for
   two minutes' reading.
2. **CLAUDE.md - current, and inside its budget.** Check every figure it quotes against the build;
   where a figure moves on every edit, replace it with where to read it. Where a section narrates
   how something came to be, keep the RULE and the trap and move the story to `docs/done.md` or the
   brief; move an oracle's long prose to the oracles doc, leaving the command line and its trap.
   Remove what the code no longer supports; fix what contradicts another file. **Do not delete a
   trap because it is old - traps are the point.** Report the size before and after.
3. **Generated files.** Run each generator (e.g. `python tools/memmap.py --write`) and read the
   result for sense: overlapping regions, "free" figures that contradict `CLAUDE.md`, entries for
   things that no longer exist. If the output is wrong the GENERATOR is wrong - fix it or report
   it; never hand-edit the output. Smoke-test a generated page's script before republishing it.
4. **decisions.md.** Every decision the code relies on has a row with its real Status (OPEN /
   PROPOSED / TAKEN / AGREED / SUPERSEDED by N / REJECTED); a merged branch's decisions are AGREED;
   superseded ones name their successor; essays move to the brief, leaving a line and a link. Then
   `python -m beeb_port_kit.check_decisions docs/decisions.md` (the kit's `py/`, or the project's
   fork) - a blank line between two rows silently ends the table.
5. **BUGS.md.** Each OPEN bug is still open (check the code or the oracle that shows it); each
   fixed one says FIXED with the commit.
6. **Briefs.** Each says at its top whether it is a PROPOSAL, PLAN, BUILT or SUPERSEDED, and a
   built one has its "what landed". A brief `PLAN.md` points at exists and is current.
7. **README.md.** A newcomer can build and run it from what is written: the build command, the
   tools, the disc it produces, how to play (keys, debug keys), the WIP link. Its "current state"
   matches `PLAN.md` and `done.md`.
8. **Consistency sweep.** Grep for what changed most recently (feature names, file names,
   constants, decision and bug numbers) across ALL docs and fix every stale mention. Check every
   relative link resolves, and every tool and oracle named exists.

## 3. Rules

- **Measure, do not recall.** A number you write comes from the build, a tool's output or a cited
  measurement - say which. If you cannot verify a claim, mark it UNVERIFIED rather than keep or
  delete it silently.
- **Move, do not delete.** Detail leaving `PLAN.md` or `CLAUDE.md` lands somewhere; nothing
  measured is thrown away. Removing a statement that is WRONG is fine - say so in the commit.
- **Keep the project's voice** - its headings, emphasis, and how it cites decisions and bugs.
- **No code changes.** A code defect the docs reveal goes into `BUGS.md` and the report.

## 4. Finish

Commit on the branch with a message listing, per file, what moved where and what was corrected and
why. Report: `CLAUDE.md`'s and `PLAN.md`'s sizes before and after, anything marked UNVERIFIED, any
defect found, anything that needs the owner's decision. Do not merge unless asked.
