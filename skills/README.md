# Skills

The kit's procedures written as Claude Code skills: one directory per skill, one `SKILL.md`
each, no scripts. Each is a numbered checklist with the exact commands or jsbeeb MCP calls, the
trap it guards against inline, and the per-project parameters looked up from the project's
`CLAUDE.md` or beebasm listing rather than hardcoded. The long form of every one is in
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
| `beeb-smoke-test` | procedure 1 | A build has just been made; does it boot? Build, pad, boot on the target model, 400 frames, one screenshot |
| `beeb-cycle-timing` | procedures 4, 5 | How long does a routine take? Breakpoint pair and `elapsed_cycles`; the zero-byte stub histogram as an option |
| `beeb-buffer-oracle` | procedure 3 | A scroll, tile writer or sprite change needs proving: diff the play buffer against an independent redraw, both dumps in one pass, both banks |
| `beeb-frame-drops` | procedure 6 | Is the game holding its rate? Count passes against fields over exactly 100 fields, per scenario |
| `beeb-measure-fact` | procedure 8 | About to depend on a register, a paging bit or a wrap size: probe it from BASIC or machine code and record the readback verbatim |
| `beeb-key-numbers` | procedure 9 | Adding or redefining a key: measure the matrix number with OSBYTE 121, SHIFT and CTRL through INKEY, proved on a known key |
| `beeb-sound-verify` | procedure 7 | The music files, IRQ or memory layout changed: capture SN76489 writes and hand them to the project's verifier |
| `beeb-bss-bugs` | procedure 10 | A bug is "first boot only" or "only on hardware": seed RAM with `&A5` and soft-reset into the game; also proves a region free |
| `beeb-cross-emulator` | procedure 11 | A bank switch, mid-frame CRTC change or displayed memory below `&3000` is about to be called done: what b-em and b2 must see, and how |
| `beeb-identical-build` | procedures 12, 13 | A change is meant to be mechanical: compare images or catalogue files byte for byte, or diff the listings reduced to opcode streams |
| `beeb-start-port` | PORTING.md §2-4 | Starting a new port: the docs skeleton with the four rules, the template, `.mcp.json`, the proposal's transfers table, the identical-build proof for existing code |
| `beeb-close-layer` | PORTING.md §3-4 | A layer works in the emulator: the doc, the decision rows, the plan, the bugs, the memory gauge with its date, every flag combination, the smoke test, the commit with the measurement |

Every skill that touches the emulator names the MCP tools by the names in `jsbeeb-mcp`'s
`server.js` (`create_machine`, `boot_disc`, `run_frames`, `run_for_cycles`, `read_registers`,
`set_breakpoint`, `save_memory`, `start_sound_capture`, ...). If the server changes, the
skills are what to update.

MIT, Kieran Connell.
