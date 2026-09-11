---
name: beeb-smoke-test
description: Build the current BBC Micro port, boot the shipping disc image in the jsbeeb MCP on the project's target model, run a few hundred frames and look at one screenshot. Use when a build has just been made, before any other check, or when the user asks whether the build still boots.
---

# Boot-and-look smoke test

The first thing after every build and the only check that trusts a screenshot: for "did it
boot", a screenshot is enough. Everything past that point is verified against the buffer
(`beeb-buffer-oracle`), never the picture.

**Image to boot:** the post-processed SSD the project ships (`build/game.ssd` in the kit template; `build/<NAME>-200K.SSD` in the two ports, which pad because they publish that file)
**Never boot:** the assembler's own output (`*-RAW.SSD`, `*-raw.ssd`) - the loader expects the compressed layout the disc tool writes
**Frames to run:** ~400 (about 8 s of emulated time; enough to clear the loader and reach the title)

## Steps

1. **Build, and check the exit code.** Baron is silent on success and puts every error of a run
   on stderr as `file:line:col:`, so the exit code is the whole story. (A BeebASM project is the
   awkward one: it writes *progress* to stderr, so do not redirect that stream or
   `$ErrorActionPreference = 'Stop'` throws on a successful build.) The build command and
   the shipping image's name come from the project's `CLAUDE.md` ("Build" section), not from
   memory: `.\build.ps1` in both ports and the template, `make` on any POSIX system.

   ```powershell
   .\build.ps1
   if ($LASTEXITCODE -ne 0) { "build failed" }
   ```

2. **Pick the post-processed image, not the raw one.** The raw image is not bootable: the loader
   expects compressed streams and rewritten catalogue addresses. **Padding is irrelevant to
   booting** - jsbeeb stopped complaining in 1.9.0, jsbeeb-mcp 3.0.0 guarantees it by
   dependency, and the kit booted a 2,304-byte image on `B-DFS1.2` and `Master` to check
   (2026-09-07). Boot whatever the project ships; pad only what you publish, so that a released
   size differing from last time is itself a signal.

3. **Create a machine of the model the game is built for**, from `CLAUDE.md`'s "Target"
   table. A Master-only game (shadow RAM, ANDY, HAZEL, ROM paging) boots wrongly on a B and the
   symptom looks like a game bug. The MCP's `model` is an enum: `Master`, `B-DFS1.2`,
   `B-DFS0.9`, `B1770`, `B1770A`, `MasterADFS`, `MasterANFS`. `B-DFS2.26` is not one of them.

   ```
   create_machine   model: "Master"                 # or "B-DFS1.2" for a Model B game
   ```

   If the first MCP connection of a session times out, reconnect (`/mcp`) and try again.

4. **Boot and run.** `boot_disc` is load, SHIFT down, reset, SHIFT up in one call. The path
   must be absolute.

   ```
   boot_disc    session_id, image_path: "<abs project path>/build/<the shipping image>"
   run_frames   session_id, count: 400
   screenshot   session_id
   ```

5. **Look at the screenshot once.** Title page or loading screen up, in the right mode, panel
   where it belongs: pass. Report what is on screen in one line. If the picture is noise but
   there is reason to think the buffer is right, suspect the MCP capture path before the game
   (it misrendered Paradroid's three-cycle rupture while the real jsbeeb page was fine); pass
   `active_only: false` for the whole 1024 x 625 field.

6. **The stale-session trap.** After many boots and keypresses in one session, `boot_disc`
   stops autobooting and the screen shows `Searching` / `File not found` - the tape filing
   system, meaning SHIFT was not seen at BREAK. The disc image is fine. **Do not go hunting
   through the catalogue**: `destroy_machine` and make a fresh one. First check that no key
   from an earlier test is still held (`key_up` it), because a held key at BREAK gives the same
   symptom for a real reason - and a held key survives `restore_state` as well (the keyboard is
   not in the snapshot; measured 2026-09-07), so a snapshot workflow can carry one along without
   ever pressing it again.

7. **Report**: the image booted, the model, what the screenshot shows, and the session id so
   the next skill can reuse the machine.
