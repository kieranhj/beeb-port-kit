---
name: beeb-start-port
description: Set up Layer 0 of a new C64-to-BBC Micro port from the beeb-port-kit - the docs skeleton with the four rules, the starter template, the jsbeeb MCP configuration, the proposal with its transfers table, and, where code already exists, the proof that splitting it changed nothing. Use when starting a new port, when a repo has code but no rules file or plan, or when the user asks to set up a project for Claude Code.
---

# Start a port: Layer 0

Layer 0 is the toolchain and the paperwork, and it is done when the same binary builds from
`src/`, the emulator is connected, and the seven artefacts exist. The purpose of the kit is to
make this an afternoon; the two ports it came from took an evening and two days respectively.

**Kit:** `C:\Users\khcon\OneDrive\BEEB\Repos\beeb-port-kit` (`PORTING.md` §2-4 is the source of this skill)
**The four rules** (PORTING.md §1), in these words, at the top of the rules file:
the original is the specification; deviations are agreed before they are built and written down after; no hardware abstraction layer, one layer at a time, visible in the emulator before the next; measure, do not recall
**MCP config:** `.mcp.json` = `{"mcpServers":{"jsbeeb":{"type":"stdio","command":"npx","args":["jsbeeb-mcp"]}}}`

## Steps

1. **Get the specification and prove which one it is** (PORTING.md §2.1). Source or a trusted
   disassembly of the *right version* - Paradroid spent two days finding it was not the Redux
   build. Any tool that rewrites the specification (an annotator, a table extractor) needs a
   round-trip check beside it: Paradroid's dropped 43 % of the data tables for three weeks.
   Keep reference screenshots of the original in the repo (gitignored if not yours).

2. **Choose the machine on day one** (§2.2). Model B with at least 16K of sideways RAM is the
   baseline, and the fewer banks the game needs the more people can run it on hardware; a
   Master is the choice when a measurement says the B cannot do it (Edge Grinder's 1-pixel
   scroll needed two 16K screens in a wrap region). The Electron is out of scope. RAM will be
   contended for the whole port, so `docs/memory-map.md` is kept current from Layer 0. Ask the
   owner; it is decision 1. Then go through the kit's `docs/target-portability.md` with the owner
   and record a row for each configuration the port will or won't run on: second processors,
   `*SHADOW`, sideways RAM not at 4-7, softloaded filing systems, no BASIC. "Not supported" is a
   fine answer; "not considered" is not.

3. **Copy the template and build it.** `template/` boots to a panel above a play area with a
   rupture, its own IRQ handler, direct keyboard and a compressed disc.

   ```powershell
   Copy-Item <kit>\template\* <project> -Recurse
   cd <project>; .\build.ps1
   ```

   or `make` anywhere with a POSIX make. Put this machine's tool paths in `local.ps1`
   (gitignored), never in the build. Then `beeb-smoke-test` on the target model. Do not start
   the game until the template boots. Keep the build portable from day one
   (`docs/build-portability.md`): rename `GAME`/`game` to the port's name in lowercase for
   host files, and before asking anyone else to build it, run `beeb-portable-build`.

4. **Write the docs skeleton** - the seven artefacts of PORTING.md §3, each with its rule in
   its header:
   - `CLAUDE.md`: the four rules at the top, then Target, Build, Source organisation, Confirmed
     hardware facts (empty; every entry must say what it was measured on and when), Memory.
     When a fact in it is wrong, fix it the same day.
   - `PLAN.md`: what is left and nothing else; the layer table from §4 with "done when" per row.
   - `docs/decisions.md`: one table, `# | Date | Decision | Where`; **the only copy**.
   - `BUGS.md`: numbered, with evidence; fixed entries are never deleted.
   - `docs/memory-map.md`: every region, what is in it, how much is free, with the date measured
     and "take live figures from the listing, never from this page" -
     `python tools/listing.py symbols build/<NAME>.symbols.json NAME` is the one-liner for that.
   - `docs/layer-0-toolchain.md`: this layer's notes, started now.
   - the build stamp - assembly time and every debug flag - as the disc file `INFO`, shown at
     boot and readable later with `*TYPE INFO` (the template does this; keep it).

5. **Configure the emulator as an MCP server.** Write `.mcp.json` at the project root with the
   JSON above, then `/mcp` to connect; the first connection of a session can time out - reconnect
   once. Confirm with `create_machine model: "<target>"` and a `screenshot` of the BASIC prompt.
   The model must be one of the server's enum (`B-DFS1.2`, `Master`, ...), so put the exact
   string in `CLAUDE.md` "Target".

6. **Write the proposal** (§2.3): what the last port taught, the memory map, the layer plan,
   and the numbered decisions for the owner. The part to copy is the **transfers table** - one
   row per practice from the previous port, "Transfers to this one?" with a reason:

   ```
   | Practice from the last port | Transfers to this one? |
   |---|---|
   | The original is the spec; decisions listed per layer | Yes, verbatim |
   | Circular-strip play buffer with hardware wrap | ... |
   | Tranche split and window scheduling | No: it exists only because that port was single-buffered |
   ```

   Also decide the scope of what is *not* the original's (§2.4) - sound effects it has not
   got, features of a later version - as decisions; the rule is "add nothing quietly".

7. **If there is existing code, split it into `src/` and prove the binary is unchanged.**
   Build the old tree first and keep the image, then split, then `beeb-identical-build` - per
   file if `!BOOT`'s timestamp makes the images differ. Edge Grinder's Layer 0 did this for a
   1,572-line file into six. The split is not done until the comparison is in the commit body.

8. **Record and close.** `docs/layer-0-toolchain.md` with what was measured (the emulator
   connected, the model, the identical-build result); decision rows for the machine and the
   scope; `PLAN.md`'s Layer 0 row ticked. Then `beeb-close-layer`.
