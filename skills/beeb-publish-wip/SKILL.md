---
name: beeb-publish-wip
description: Publish a work-in-progress BBC Micro build to a stable URL and return emulator links to share - two discs from one commit (committed before building), the debug build as <game>-wip.ssd and the release build as <game>-rc.ssd (.dsd if double-sided), each one's INFO naming the commit, under the same names every time, the served file's hash checked against the build, links carrying ?v=<commit>, with a publishing-log commit in the site repo. Use only when the user asks to publish, share or update the WIP; "give me a build" means the local disc, not a publish.
---

# Publish a WIP build

**Local first.** "Give me a build", "let me try it" and "make a test disc" mean: build it and give
the path of the local disc. Publish only when the owner asks for the WIP to be updated or shared -
an experimental disc pushed to the shared folder is a link someone else will open (1942's owner,
2026-10-09: "you didn't need to push that as a WIP - I can test locally").

**Site repo, folder and names:** from the project's rules file or memory - e.g. a GitHub Pages repo
with a `content/wip/` folder shared by several projects. Ask once if neither says.
**Names:** `<game>-wip.ssd` (the debug build) and `<game>-rc.ssd` (the release build), lowercase,
the same names every time so shared links keep working; `.dsd` for a double-sided disc (phX:
`phx-wip.dsd`) - bbc.xania.org's `disc=` takes either
**Version:** every link carries the commit, `?v=<commit>`, URL-encoded inside `disc=`

## Steps

1. **Commit first, then build both discs from that commit**, the working tree clean. The stamp
   is the last commit's - `tools/build_stamp.py` writes `BUILD_COMMIT` (the short hash, `+` if
   the tree is dirty) and `INFO` prints it - so a disc built before the commit names the commit
   before it, and a `+` in `INFO` means the disc is no commit at all. Then the default build
   (debug keys on) and the release build (`-Release` / `make release`). A WIP is
   two discs because the release differs in kind - no debug keys, possibly a title or tune the
   debug build lacks - and playtesters need to try the thing that will ship beside the thing
   that is easy to test. Check each disc's `INFO` (`*TYPE INFO`, or read it off the image) names
   that commit and the right flags.

2. **Work out what changed** since the last publish, from the project's history:

   ```powershell
   git -C <site repo> log -1 --format=%cI -- content/wip/<game>-wip.ssd   # when last published
   git -C <project> log --oneline --since=<that date>                      # what landed since
   ```

3. **Confirm with the owner before committing and pushing**, unless the request itself said to.

4. **Copy, commit, push**: both files, one commit, a message for a publishing log - the project and
   the headline change ("1942 WIP: class 1 flies its own engine; rc5"), not "update ssd".

   ```powershell
   Copy-Item <debug disc>   "<site repo>\content\wip\<game>-wip.ssd" -Force
   Copy-Item <release disc> "<site repo>\content\wip\<game>-rc.ssd"  -Force
   git -C <site repo> add content/wip/<game>-wip.ssd content/wip/<game>-rc.ssd
   git -C <site repo> commit -m "<message>"
   git -C <site repo> push
   ```

5. **Check the served file before handing out the link.** GitHub Pages rebuilds in a minute or
   two and then serves with a cache of about 600 s, so for up to ten minutes the URL may give the
   **previous disc**, not a 404 - a tester then reports on a build you did not mean. Compare the
   served file's hash with the local one, and wait until they agree:

   ```powershell
   (Get-FileHash <debug disc>).Hash
   curl.exe -s "<site>/content/wip/<game>-wip.ssd?v=<commit>" -o $env:TEMP\served.ssd; (Get-FileHash $env:TEMP\served.ssd).Hash
   ```

6. **Return both links**, each on its own line, saying which is which and the model they boot,
   with the commit in each. The `?v=` belongs to the disc's URL, so inside `disc=` it is encoded
   (`?` -> `%3F`, `=` -> `%3D`):

   ```
   https://bbc.xania.org/?disc=<site>/content/wip/<game>-wip.ssd%3Fv%3D<commit>&autoboot&model=<model>
   https://bbc.xania.org/?disc=<site>/content/wip/<game>-rc.ssd%3Fv%3D<commit>&autoboot&model=<model>
   ```

   e.g. `...?disc=https://bitshifters.github.io/content/wip/phx-wip.dsd%3Fv%3D899629c&autoboot&model=Master`.
   A bare link cannot say which build a tester ran, and a cached old disc looks the same (KC,
   phX, 2026-11-17: "make sure WIP links have a version identifier"). `model=` is `B`, `BP` or
   `Master` (append `&coProcessor=true` for a second processor); use the machine the port
   targets.

7. **Record it**: the session's memory note gets the published commit and the site commit, so the
   next session knows what testers have; put the project commit in the site commit's message too.
