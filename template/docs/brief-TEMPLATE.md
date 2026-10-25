# Brief - <THE JOB, in a few words>

> **Status: PROPOSAL, <date> (<who asked>).** One of PROPOSAL (written, waiting on the owner),
> PLAN (agreed, not built), BUILT (<date>, branch, merge commit - see the last section) or
> SUPERSEDED (by <brief or decision>). **Update this line whenever the status changes**: it is
> the first thing anyone reads, and a brief whose status is stale sends the next session to build
> what is already built.
>
> Every figure below says **MEASURED** (read off a tool run - name the tool, the build and the
> emulator version), **COUNTED** (off the listing or the source, by hand) or **PROJECTED**
> (arithmetic on top of a count). Counted figures are suspect: 1942-beeb's were wrong by a fifth,
> and once by 2.5x; one costing said -13 cycles a blit where the build measured +7.
>
> *Read first: <the rules-file sections, the BUGS entries, the original's routines and the source
> files this touches>.*

Copy this file to `docs/brief-<name>.md` before the job starts, and commit it before any code - an
unattended job names its resume point here. A brief is for work a layer table does not fit: a
level set, a boss, the front end, a RAM hunt, a second engine. Delete these instructions and the
`<...>` placeholders as you fill it in; keep the section headings.

---

## 0. The proposal in one paragraph

What will be built, what it costs, what it needs from the owner. Someone who reads only this
paragraph can say yes or no.

## 1. What the original does - measured

The routine, the table, the behaviour, from the specification: the addresses read, the capture or
the recording it was scored against, and the score ("0 wrong over N frames, every excluded frame
named"). **A state the recording never reaches has not been measured**: say what drove it there.
What the port must reproduce, and what it may not.

## 2. The ledger - what it needs against what there is

| Region | Free now (MEASURED, from <build>) | This job wants | After |
|---|---|---|---|
| main RAM | | | |
| sideways bank N | | | |
| the tick (cycles) | | | |
| the disc (sectors, catalogue entries) | | | |

Read the free figures off the build (`docs/memory-map.md`, regenerated), never off a doc. If the
After column goes negative, the job opens with a lever (a RAM hunt), and this brief says which.

## 3. The options, costed

For each way of doing it: what it is, its bytes AND its cycles (MEASURED / COUNTED / PROJECTED),
what it risks, and what it changes for the player. **Always cost one option first: can hardware
the port already drives do this?** - the scroll, the CRTC, the background fill, the save-under
store - before a new engine. 1942 built the boss as a sprite with its own blitter (three days,
three store defects) and threw it away for the boss as background, composited into the ring and
moved by the scroll: the fight tick went from 180,824 cycles to 28,733.

### (a) <option>
### (b) <option>
### (c) <option> - the one I would build, and why

## 4. Where these figures could be wrong

Every COUNTED and PROJECTED number above, and what would move it. The first step of the build
measures the riskiest of them.

## 5. The decisions, for the owner

Each as a numbered question with the options, the recommendation and the reason - written so it
can be pasted into `docs/decisions.md` as a row (Status `OPEN`, or `PROPOSED` with the
recommendation). A taste call is answered from test discs side by side, each alternative one
switch away (an environment variable or `-D` whose default is the shipped value), not by argument.

| # | Question | Options | Recommended |
|---|---|---|---|

## 6. The steps

Each step ends in a commit with its measurement in the body, and the suite (or the oracles the
step touches) run after it. Name the oracle that proves each step, and if it is new, prove it
FAILS on the build before the step.

1. <step> - proved by <oracle>
2. <step> - proved by <oracle>

## 7. What was costed and put down

Every option refused, with the number that refused it - the valuable half. These become rows in
`docs/decisions.md`'s "Rejected, do not re-litigate" table.

## 8. What landed, <date>

Written when the job is done, and the status line at the top changed to BUILT. Per step: what was
built, the commit, the number that says it works (the oracle and its verdict), and what it COST
against section 2's ledger, MEASURED - beside the projection, so the next brief knows how far to
trust a projection. What is still open goes to `PLAN.md` (pointing here); the evidence goes to
`docs/done.md`.
