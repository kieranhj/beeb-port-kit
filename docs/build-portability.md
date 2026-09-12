# Build portability: the rules (2026-09-11)

A port's build should work, and produce **the same disc**, on a machine its author has never
seen. These rules come from [paradroid-beeb issue #3](https://github.com/kieranhj/paradroid-beeb/issues/3),
where a contributor asked for a POSIX Makefile and then tested it on Linux and OpenBSD. Every
rule below is there because breaking it cost a round trip with a tester. The template follows
all of them (`template/Makefile`, `template/build.ps1`); `skills/beeb-portable-build` is the
test to run before asking anyone else to try a build.

## The make dialect

1. **The first line of the Makefile is `.POSIX:`.** POSIX runs every recipe line under
   `sh -e`. OpenBSD's make does; GNU make only does when `.POSIX:` is declared. Paradroid's
   pack loop did `pack_overlays.py ...; rc=$$?` to catch an exit code of 10 meaning "go round
   again". GNU make ran it fine, but on OpenBSD `sh -e` exited on the 10 before `rc=` ran:
   `*** Error 10`. With `.POSIX:`, GNU make fails in the same place, so the bug shows up on
   the development machine. Measured on GNU Make 4.4.1, 2026-09-11: with `.POSIX:`, `false;
   echo` stops at the `false`; without it the `echo` runs.
2. **Catch an expected non-zero exit as `cmd || rc=$$?`**, never as `cmd; rc=$$?`. An `||`
   list is exempt from `-e`.
3. **`.POSIX:` also changes the defaults**: `CC` becomes `c99` and `CFLAGS` `-O1` (GNU Make
   4.4.1). MSYS2 has no `c99`, so the template sets `CC = cc` and passes only `-O`, which
   every C compiler accepts.
4. **No GNU extensions**: no `$(wildcard)`, no `ifeq`, no `%` pattern rules, no `&:`, no
   `-include`, no `$(shell)`. `?=` and `-j` are in POSIX.1-2024. Choose between variants
   with a recursive `$(MAKE) VAR=value` (`make release`, `make master`), not a conditional.
5. **List every source explicitly.** A file the assembler includes but the Makefile does not
   list makes a build that goes stale without an error. This is worse than a build that
   fails, so it is deliberate that there is no wildcard.

## Dependencies that are not a plain DAG

6. **A rule that writes several files has one owner.** One output owns the recipe and the
   others depend on it with an empty recipe. Declaring all the outputs as targets of one rule
   makes it one rule per target, so under `-j4` Paradroid ran four copies of its briefing
   tool over the same files. GNU's `&:` fixes this but needs make 4.3 or later, and bmake
   has nothing equivalent.
7. **A flag that changes the output without touching a file** (`RELEASE`, `MASTER`) goes
   in a generated file that is **rewritten only when it changes**. The step that writes it
   runs before the build proper (`all:` runs the stamp, then `$(MAKE) $(SSD)`), so the
   second make sees the file's real mtime. A stamp rewritten on every build makes everything
   stale on every build: make counts a target whose recipe *ran* as updated.
8. **A vendored tool is built by the build**, and it is a prerequisite of *every* rule that
   uses it, including generator scripts that only run it indirectly. Paradroid missed that
   twice: a fresh clone ran the briefing generator before the compressor existed. An
   external tool (the assembler, Python) comes from `$PATH` with a `VAR ?=` override. A
   vendored tool's override must name an existing file, because it is a prerequisite.
9. **Generated data that is committed stays out of the default build.** Paradroid's exporters
   live behind `make data` in `mk/data.mk`. That way the tree builds without the source
   listing or Pillow, and an exporter change arrives as a diff someone can review.

## Names

10. **Host filenames are lowercase, extensions included**: b2 rejects a disc called `.SSD`
    with "unknown extension". Names *inside* the image (the DFS catalogue, the disc title,
    `*RUN Game`) keep their case. An intermediate named after a DFS file keeps that file's
    uppercase stem with a lowercase extension (`PARADAT.zx0`).
11. **No `.exe` and no absolute paths are written anywhere.** The platform supplies `.exe`
    (`shutil.which` and `gcc -o` add it, and MSYS2's make finds `bin/zx02.exe` when asked
    for `bin/zx02`). A path that only exists on the author's machine goes in a gitignored
    file (`template/local.ps1`), not in the build.
12. **Slashes as directory separators, and every filename in the case it has on disc.** A
    case-preserving filesystem forgives a wrong case in a filename and a case-sensitive one
    does not.

## The same disc everywhere

13. **The build is reproducible by default.** The template's build-stamp timestamp - in `INFO`,
    and in the release `!BOOT` stub that reprints it - is the source's time, not the clock's: `$SOURCE_DATE_EPOCH`, then the last commit's time (with
    `+` when the tree is dirty). Paradroid's `!BOOT` carried the wall clock, so when the
    OpenBSD tester reported a SHA256 nobody could say whether their build was wrong or just
    built later. The build prints the image's SHA256; publish it with the commit.
14. **There is one compressor, not whichever one is found.** The template used to run
    `zx02.exe` if it was installed and the Python port if not. On one file in 29 the two
    differed by a trailing byte, so the disc depended on what was installed. The reference
    source is now vendored and built (`template/tools/zx02src/VENDORED.md`). The Python port
    remains the round-trip oracle.
15. **A failed step leaves no target behind.** `.DELETE_ON_ERROR` is GNU-only, so a recipe
    removes its own output on failure (`baron ... || { rm -f $(RAW); exit 1; }`), and tools
    write to a temporary file and rename it into place. Otherwise a half-written image looks
    up to date on the next run, and nobody can tell whether a tester's hash came from a
    clean build.
16. **Two build scripts must produce the same image**, byte for byte, not "the same apart
    from the timestamp". Check with `python tools/dfs.py compare a.ssd b.ssd`: it prints both
    SHA256s, then says either "identical images" or which file differs. On the template,
    `make` and `build.ps1` with the same `SOURCE_DATE_EPOCH` give `26cf9e27...` (2026-09-11).

17. **Line endings are fixed by `.gitattributes`, not by each clone's settings.** Git on
    Windows (`core.autocrlf=true`, the installer's default) checks text out with CRLF.
    Without the attributes, a clone of the kit on this machine got the template's `Makefile`
    with 157 CRs and the vendored `zx02.c` with 245 (2026-09-11).
    `template/.gitattributes` pins `Makefile`, `*.mk`, `*.sh` and `tools/zx02src/**` to LF
    and marks the images and data as binary. Measured here, MSYS2's GNU Make 4.4.1 builds a
    CRLF Makefile without complaint, and to the same image. The rule is for everything
    that isn't MSYS2: a Windows checkout built from WSL or a Linux VM, another make, a shell
    script (`$'\r': command not found`), and vendored source whose bytes should match
    upstream's. None of those were tested here.

## Windows (MSYS2) problems, recorded so nobody has to find them again

- MSYS2 clears `TMP`/`TEMP` in some shells, and gcc then tries to write to `C:\Windows\` and
  fails. Pass `TMP=` explicitly (Paradroid, 2026-09).
- `rm -f bin/zx0` deletes `bin/zx0.exe` as well. Only run it on a file the build made.
- PowerShell launched from MSYS2's `sh` could not run the Microsoft Store Python alias. Run
  PowerShell builds from a Windows shell.
- A login shell (`bash -l`) drops the Windows PATH unless `MSYS2_PATH_TYPE=inherit` is set,
  and then `python` and `baron` go missing.

## Not yet tested

The template's Makefile has only been run on GNU Make 4.4.1 (MSYS2). Paradroid's has been run
on Linux and OpenBSD and failed on OpenBSD, which is why rule 1 exists. A run under bmake, or
on a Mac, is the next thing worth doing.
