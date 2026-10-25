---
name: beeb-close-layer
description: Close out a layer (or a brief) of a BBC Micro port - the layer doc with what was measured and rejected, a decisions.md row per deviation with its Status, PLAN.md cut and the evidence moved to docs/done.md, BUGS.md updated, the memory gauge read from the listing into memory-map.md with the date, every debug flag combination assembling, the smoke test passing, and a commit with the measurement in its body. Use when a layer is working in the emulator and the user says it is done, or before starting the next layer.
---

# Close a layer

A layer is done when it is visible in the emulator *and* its doc, decision rows and plan update
are written. What is sacred in both ports is finishing a layer, with its doc, before the next
starts; the rejected options in the doc are the valuable half, because they are what stops the
next session re-litigating them.

**Layer doc:** `docs/layer-N-<name>.md`
**Decisions:** `docs/decisions.md` - the only copy; one numbered, dated row per deviation, with a Status
**Landed:** `docs/done.md` - what landed, with the number that says so; the other half of `PLAN.md`
**Memory figures:** from `build/<NAME>.lst`, never from an earlier doc
**Commit body:** the measurement ("0 of 16,384, both banks", "6,155 cycles a sprite", "byte-identical")

## Steps

1. **Write the layer doc** with what was measured (the numbers, the method by procedure name,
   the emulator, the date) and what was tried and rejected, with why. "Do not re-litigate the
   blitter unrolls" saved Paradroid's RAM pass from repeating itself. A doc that records only
   the winning design will be argued with.

2. **A row in `docs/decisions.md` for every deviation from the original and every choice the
   hardware forced**, numbered on from the last row, dated, with its **Status** (`AGREED` once
   the owner has said yes; `TAKEN` if you took it while they were away), the reason in a line and
   a link to the layer doc section - the evidence lives there, not in the row. If the layer
   reversed an earlier decision by measurement, that is a *new* row saying so, and the old one's
   Status becomes `SUPERSEDED by N`. What was costed and refused goes in the "Rejected, do not
   re-litigate" table. Then `python -m beeb_port_kit.check_decisions docs/decisions.md`.

3. **Update `PLAN.md`**: tick the layer's row, move the detail that no longer drives the next
   decision into the layer doc, and rewrite "where we are" and "what is left". Cut it when it
   stops driving the next decision - Paradroid's went from 535 lines to 156. **The layer's
   evidence goes to `docs/done.md`** (what landed, the number, the commit), so a line can leave the
   plan without the evidence leaving with it.

4. **Update `BUGS.md`**: mark what the layer fixed (with the layer name; fixed entries stay for
   what they ruled out), add anything found and not fixed with its evidence. A path the layer
   made reachable for the first time (`wave_manager`'s skip path, Edge `BUGS.md` #10) is a
   candidate for a new entry, not a note.

5. **Read the memory gauge from the listing into `docs/memory-map.md`, with the date.** The
   `PRINT` lines the build emits are the figures; the pattern to search for is the project's
   (`CLAUDE.md` "Memory" or the top of `memory-map.md`):

   ```powershell
   .\build.ps1
   Select-String -Path build\<NAME>.lst -Pattern "CODE CEILING|HIGH WATERMARK|^FREE|HOLE|SLACK"
   ```

   Every free-space figure says the date it was measured. If a region's ceiling for *play*
   is lower than the image's (Edge Grinder's `SPR_SAVE` under `LOAD_STREAM`), say which the
   figure is against; a runtime table drifted over that line unnoticed once.

6. **Every flag combination still assembles.** The project's `-D` symbols are in `CLAUDE.md`
   "Build"; loop over all of them. A combination nobody has built since the layer began is a
   build that may not exist any more (`GFX_CPC=1` did not assemble without `MUSIC_AKL=1` for
   two layers of Edge Grinder).

   ```bash
   for R in 0 1; do for A in 0 1; do for C in 0 1; do
     printf "R=%s A=%s C=%s | " $R $A $C
     ../../Bin/baron.exe --check -v -D RELEASE=$R -D MUSIC_AKL=$A -D GFX_CPC=$C src/main.6502 \
       | grep -E "CODE CEILING|^FREE" | tr '\n' ' '; echo
   done; done; done
   ```

   `--check` assembles and validates while writing nothing, which is what this loop wants; the
   `PRINT` figures still come out. On Baron 0.4.0 or later add `--warn 2`, and expect the loop to be
   silent apart from the figures - a zero-page warning in one flag combination and not another
   is exactly what this sweep is for. (0.3.0 has no `--warn` and fails on it rather than
   ignoring it; `..\..\Bin\baron.exe` is still 0.3.0, so check what the project resolves. A
   project on the kit's `lib/` needs 0.4.1 or later anyway, for the `ASSERT` keyword.)
   A BeebASM project runs `beebasm -i src/main.asm -do /tmp/o.ssd -opt 2 -D ...` instead, where
   the `-do` exists only to stop loose `SAVE` files.

   Adapt the symbol names to the project's. Add any new `DEBUG_` flag to `DEBUG_ANY` and to
   the build stamp (the template's `BUILD_STAMP` macro, which fills `INFO` and the release
   boot alike); `RELEASE` asserts `DEBUG_ANY = 0`.

7. **The smoke test passes on the release build too** (`.\build.ps1 -Release`, then
   `beeb-smoke-test`). A DEV-only feature that the release build silently lacks is found here
   or by a playtester.

8. **Update the rules file** if the layer measured a new hardware fact (into "Confirmed
   hardware facts", with the readback), changed the build, or moved a region. A rules file that
   is wrong is fixed the same day. **Keep it inside its budget** (about 40K): the rule and the
   trap go in, the story of how they were found goes to `docs/done.md`, and a figure that moves
   on every edit is replaced by where to read it. 1942's grew to 167K one honest addition at a
   time; if it is over, run `beeb-doc-pass` before the next layer.

9. **Commit, one mechanism per commit, with the measurement in the body.** Doc-sync commits
   are separate and frequent. Confirm with the user before committing unless they already asked.

   ```
   Layer N: <what it does>

   <the measurement: "0 of 16,384 both banks at odd and even scroll phase",
    "50/100 scrolling", "byte-identical: Edge, BANK0", cycles before and after>
   ```

10. **Then, and only then, start the next layer** - reading its worked example in PORTING.md §4
    first, because it records what was tried and rejected there. **After the layer table**, work
    comes as briefs (`docs/brief-*.md` from `docs/brief-TEMPLATE.md`, PORTING.md §3.1): closing one
    is these same steps, plus its "what landed" section and its status line changed to BUILT.
