---
name: beeb-identical-build
description: Prove that a change meant to be mechanical left the BBC Micro port's binary untouched - by comparing disc images and catalogue files byte for byte - or, where addresses legitimately moved, that no instruction was added, removed or reordered, by diffing the two beebasm listings reduced to opcode streams. Use when splitting a source file, reordering includes, changing the build script, widening a table, relocating data, or any change whose commit message wants to say "byte-identical".
---

# Byte-identical build and listing-stream diff

Two checks for a change that should not alter behaviour. The first is for a change that should
not alter the disc *at all*; the second is for a change that legitimately moves addresses and
must be proved to have done nothing else. Both are faster than the oracle and, for this class of
change, stronger.

**Baseline:** build the OLD tree first and keep its image and listing somewhere the new build will not overwrite
**Always differs:** `!BOOT`, which stamps the assembly time - so compare per file, not per image, when it does
**Listing:** `build/<NAME>.lst`, from beebasm `-v`

## Steps

1. **Build the old tree into a baseline and keep it.** Before touching the source, or from a
   `git stash` / `git worktree` of `HEAD`. Copy `build/` aside; the next build overwrites it.

   ```powershell
   .\build.ps1
   Copy-Item build build-old -Recurse
   ```

2. **Make the change and build again**, with the same flags. The `-D` symbols the project
   passes (`RELEASE`, `MUSIC_AKL`, `GFX_CPC`, ...) are in `CLAUDE.md` "Build"; a different flag
   set is a different binary and the comparison means nothing.

3. **Compare the images.** Identical is the pass and the end.

   ```bash
   cmp build-old/<NAME>.SSD build/<NAME>.SSD
   ```

4. **If they differ only where they should, compare per file.** Edge Grinder's `!BOOT` carries
   the assembly time and a DEV stamp, so its disc always differs there. Extract the files that
   must not have changed (`Edge`, `BANK0`, the data banks) from both catalogues and compare
   those. Neither port ships the extractor; it is a few lines over the DFS catalogue (sectors 0
   and 1: names at `&0008`, load/exec/length/start sector at `&0108`, eight bytes a file) - the
   kit's `py/beeb_port_kit/dfs.py` reads one. Say in the commit which files were compared.

5. **When addresses legitimately moved - a width change, a data removal, a relocation - diff
   the listing streams instead.** Reduce each listing to one entry per emitted instruction,
   `(mnemonic, addressing class)`, operands dropped, absolute and zero-page collapsed together.
   It is a dozen lines of regex over the listing's opcode column; write it inline in the
   scratchpad, as both ports did.

   ```bash
   python reduce.py build-old/<NAME>.lst > old.txt
   python reduce.py build/<NAME>.lst     > new.txt
   diff old.txt new.txt && wc -l old.txt
   ```

   Identical streams (7,753 instructions in Paradroid's blitter pass; 22,954 in its RAM pass)
   prove no instruction was added, removed or reordered, so every difference in the image is a
   width change or data. Then the smoke test only has to confirm the new addresses do not collide.

6. **Know what it cannot validate.** A change that *intentionally* alters instructions -
   Paradroid's SCANSTEP tail folding - fails the stream diff by design; that is the oracle's job
   (`beeb-buffer-oracle`). Do not weaken the reducer to make such a change pass.

7. **Apply the same check to generated data.** "Every existing output is byte for byte
   untouched" caught a 28-byte move in every sprite bank when two tables were emitted in the
   other order (Edge decision 63). `git diff --stat src/data/` after running an exporter is the
   cheap form; an unexpected file in it is the finding.

8. **Put the result in the commit body**: "byte-identical" with the files compared, or
   "listing stream identical, N instructions" with the count.
