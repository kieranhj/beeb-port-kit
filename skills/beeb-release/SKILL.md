---
name: beeb-release
description: Take a BBC Micro port from release candidate to release - freeze features at rc1, then for each candidate the release build, the whole oracle suite on it, the target matrix, the second emulator, real hardware, every BUGS.md row closed or accepted, the disc's sector and catalogue budget, INFO naming the commit, the padded disc and its hash, and the release post. Use when the user says to cut a release candidate, make a release, call a version 1.0, or asks whether a build is ready to ship.
---

# Release

**Freeze features at rc1.** After the first release candidate, only fixes go in; a feature
restarts the count at a new rc1. 1942 went from rc1 to v1.0 in nine days and five candidates
because three features landed inside the window - one of them a whole enemy engine between rc4 and
rc5 - and each one re-opened every check below. If the owner wants a feature after rc1, say what it
costs in candidates and let them choose.

**Build:** the project's release switch (`.\build.ps1 -Release` / `make release`): `RELEASE=1`,
every `DEBUG_` flag off, `DEBUG_ANY = 0` asserted
**Suite:** the project's oracle runner on the build the suite expects (it may be a separate
play-boot build of the same code - the rules file says)
**Matrix:** `beeb-target-matrix`; second emulator `beeb-cross-emulator`

## Each candidate

1. **Tag the commit as a candidate** (`rcN`) in the commit message, and build the release disc
   from it. Check `*TYPE INFO` on the disc names that commit, the build time and no debug flags -
   a release disc that cannot say which commit it is cannot be reproduced.

2. **Run the whole suite**, not the newest oracle, and record the count ("147 of 148, the one
   known-failing run named"). A known false failure is named with its signature; an unexplained
   one blocks the candidate. If everything fails at once, suspect the tools before the port.

3. **The release build plays**: `beeb-smoke-test` on it, then a play-through on the release disc
   itself - the release differs in kind (no debug keys, perhaps a title the debug build does not
   have), so a debug-build play-through does not cover it. **Baron's `NOT` is bitwise**: check the
   release really has no debug keys (`IF NOT(RELEASE)` was true for `RELEASE = 1` in 1942).

4. **The target matrix** for every configuration the decisions say the port runs on, and the
   refusal on the ones it does not (a model check in `!BOOT` should print a message, not hang).

5. **Second emulator and real hardware.** b2 or beebjit, and the owner's machine, from the release
   disc: boot, play through at least one seam, BREAK, and anything the rules file gates on
   hardware. This is the owner's step; the candidate waits for it.

6. **`BUGS.md`**: every open row is FIXED (with the commit) or explicitly ACCEPTED for this release
   by the owner, with the reason. No row is silently open.

7. **The disc's budgets**: sectors used against the disc size, and DFS catalogue entries against
   31 - the catalogue bound before the sectors did in 1942. Pad the SSD to 200K; record its size
   and SHA256 (`beeb-portable-build` says how), so a published file that differs is noticed.

8. **Docs**: `PLAN.md` says what is left after this release; `docs/done.md` carries the
   candidate's evidence; the README states the version, the machine it needs and how to play.

## The release

9. When a candidate passes every step with no change since it was built, **rename it**, not
   rebuild it: the version line goes into the stamp in a commit of its own, and the disc built from
   that commit is checked against step 1 once more.
10. **Publish** only when the owner says (`beeb-publish-wip`, or the project's release route), with
    the release post: what it is, the machine it needs, the keys, and credits.
11. **After the release**, the freeze lifts; new features start on a branch, and the next release
    starts its own rc1.
