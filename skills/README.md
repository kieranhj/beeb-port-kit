# Skills

The kit's procedures written as Claude Code skills: one directory per skill, one `SKILL.md`
each, no scripts (but `beeb-micro-grind`, which carries the two workflow scripts its agents run). Each is a numbered checklist with the exact commands or jsbeeb MCP calls, the
trap it guards against inline, and the per-project parameters looked up from the project's
`CLAUDE.md` or the assembler's own output rather than hardcoded (`tools/listing.py symbols`
reads them out of Baron's symbol dump, or its listing; zero-page addresses allocated by Baron
exist nowhere else). The long form of every one is in
[`docs/verification.md`](../docs/verification.md) (by procedure number) and
[`PORTING.md`](../PORTING.md) §2-4.

## Installing

Copy the directories you want into the project's `.claude/skills/`:

```powershell
Copy-Item <kit>\skills\beeb-* <project>\.claude\skills\ -Recurse
```

or into `~/.claude/skills/` to have them in every project. Claude Code picks them up on the
next session; invoke one by name (`/beeb-smoke-test`) or let the trigger sentence in its
description do it.

## The skills

| Skill | Source | Use when |
|---|---|---|
| `beeb-smoke-test` | procedure 1 | A build has just been made; does it boot? Build, boot the image the build ships (unpadded is fine) on the target model, 400 frames, one screenshot |
| `beeb-cycle-timing` | procedures 4, 5 | How long does a routine take? Breakpoint pair and `elapsed_cycles`; the zero-byte stub histogram as an option |
| `beeb-buffer-oracle` | procedure 3 | A scroll, tile writer or sprite change needs proving: diff the play buffer against an independent redraw, both dumps in one pass, both banks |
| `beeb-frame-drops` | procedure 6 | Is the game holding its rate? Count passes against fields over exactly 100 fields, per scenario |
| `beeb-measure-fact` | procedure 8 | About to depend on a register, a paging bit or a wrap size: probe it from BASIC or machine code and record the readback verbatim |
| `beeb-key-numbers` | procedure 9 | Adding or redefining a key: measure the matrix number with OSBYTE 121, SHIFT and CTRL through INKEY, proved on a known key |
| `beeb-sound-verify` | procedure 7 | The music files, IRQ or memory layout changed: capture SN76489 writes and hand them to the project's verifier |
| `beeb-bss-bugs` | procedure 10 | A bug is "first boot only" or "only on hardware": seed RAM with `&A5` and soft-reset into the game; also proves a region free |
| `beeb-cross-emulator` | procedure 11 | A bank switch, mid-frame CRTC change or displayed memory below `&3000` is about to be called done: what b-em and b2 must see, and how |
| `beeb-identical-build` | procedures 12, 13 | A change is meant to be mechanical: compare images or catalogue files byte for byte, or diff the listings reduced to opcode streams |
| `beeb-portable-build` | `docs/build-portability.md` | Before anyone else tries a build, or a tester reports a failure or a hash: fresh `make -j4`, a no-op rebuild, flag flips, a failing tool leaves no target, `make` and `build.ps1` compared byte for byte, the SHA256 to publish |
| `beeb-target-matrix` | `docs/target-portability.md` | Before a release, after a boot or loader change, or on "it doesn't work on my machine": every configuration the port claims that jsbeeb can emulate (DFS variants, Master, second processors, `*SHADOW`, `*CONFIGURE`, hidden or taken sideways RAM), one fresh machine each, before and after, checked to play; then what still needs b2, b-em, MAME or hardware |
| `beeb-dataflow` | `docs/dataflow.md` | Short of RAM or code space, or asking what a routine's register contract is, what a byte can hold, whether code is dead: beebgame's static analyses on the Baron build, each finding checked against the source and the two Baron traps, then changed a few at a time behind the gate |
| `beeb-oracle-harness` | `docs/verification.md` "Headless harnesses", procedures 16-19 | A check must run on every build, an MCP-by-hand check is to become a script, or a harness passes and nobody has seen it fail: `template/tools/harness.mjs`, addresses from the dump, the bank named on reads and writes, paging-gated hooks, a driven run, a coverage gate, a model that borrows nothing from the port, a negative control, exit 0/1/2 |
| `beeb-run-suite` | `docs/verification.md` "Headless harnesses" | After a build that will be committed, merged or published: `tools/verify_cmds.py` prints every oracle's line from the dump, `tools/run_suite.py` runs them N at a time into a scratch directory, the verdict is each exit code; suspect the tools when nearly everything fails |
| `beeb-arcade-capture` | `docs/arcade-porting.md` §3-4 | Porting from a ROM set with no source: the `-listxml` manifest, the live DIP switches, a human `.inp`, per-frame RAM records through the runner, the measured rotation, and captures driven where no recording goes (held state bytes, forced input, invincibility, an autopilot), with the ROM-checksum trap checked |
| `beeb-rom-model-probe` | `docs/arcade-porting.md` §5 | Porting a behaviour of a game with no source: read back from known data with watchpoints, transliterate the routine, score it frame by frame against a capture to 0 wrong with every exclusion named, refuse unread paths, and make the model the exporter's decode and the port's oracle |
| `beeb-start-port` | PORTING.md §2-4 | Starting a new port: the docs skeleton with the four rules, the template, `.mcp.json`, the proposal's transfers table, the identical-build proof for existing code |
| `beeb-close-layer` | PORTING.md §3-4 | A layer (or a brief) works in the emulator: the doc, the decision rows with their Status, the plan cut and its evidence moved to `done.md`, the bugs, the memory gauge with its date, the rules file inside its budget, every flag combination, the smoke test, the commit with the measurement |
| `beeb-ram-hunt` | PORTING.md §2.2, §5.6 | A feature does not fit or a region is near zero: regenerate the map, ledger free against wanted, list and cost every lever in bytes and cycles before building any, one lever a commit with the suite after each, a report with the rejected levers and their numbers |
| `beeb-unattended-job` | PORTING.md §12 | The owner is away (overnight): own branch, the brief committed first with a resume point, decisions marked `TAKEN`, hardware gates left shut, the suite detached outside the home folder, nothing merged or published, a morning report with a branch ledger |
| `beeb-release` | PORTING.md §10 | Cutting a release candidate or a release: features frozen at rc1, then the release build, the whole suite, the target matrix, real hardware, every bug closed or accepted, the disc's sector and catalogue budget, `INFO` naming the commit |
| `beeb-publish-wip` | PORTING.md §10 | Only when asked to publish: two discs from one commit (`-wip` debug, `-rc` release), the same names every time, a publishing-log commit, both emulator links. "Give me a build" means the local disc |
| `beeb-doc-pass` | PORTING.md §3, §3.3 | The docs have drifted: every fact into its one file, `CLAUDE.md` back inside its budget, `PLAN.md` cut to what is left, evidence to `done.md`, every decision's Status, generated pages regenerated, a stale-mention sweep. Documents only |
| `beeb-micro-grind` | beebgame's suggested farm (Eben Upton, `tools/dataflow/README.md`), as Stryker's Run grew it for cycles; `template/tools/grind.py`, `grind_config.py`, `pcprof.mjs` | Asked to grind or micro-optimise everything, once the gate is the port's suite: beebgame's annotations, 32-instruction windows weighted by measured cycles, an optimiser agent per window, two or three skeptics per candidate, then `grind.py run` applies the survivors a batch at a time through the gate, kept only if every check passes and no game is slower. Hundreds of agents a round; Stryker's Run kept 256 of 580 |

Every skill that touches the emulator names the MCP tools by the names in `jsbeeb-mcp`'s
`server.js` (`create_machine`, `boot_disc`, `run_frames`, `run_for_cycles`, `read_registers`,
`set_breakpoint`, `save_memory`, `start_sound_capture`, ...). If the server changes, the
skills are what to update.

MIT, Kieran Connell.
