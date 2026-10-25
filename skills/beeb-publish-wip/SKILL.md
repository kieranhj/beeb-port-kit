---
name: beeb-publish-wip
description: Publish a work-in-progress BBC Micro build to a stable URL and return emulator links to share - two discs from one commit, the debug build as <game>-wip.ssd and the release build as <game>-rc.ssd, each one's INFO naming the commit, under the same names every time, with a publishing-log commit in the site repo. Use only when the user asks to publish, share or update the WIP; "give me a build" means the local disc, not a publish.
---

# Publish a WIP build

**Local first.** "Give me a build", "let me try it" and "make a test disc" mean: build it and give
the path of the local disc. Publish only when the owner asks for the WIP to be updated or shared -
an experimental disc pushed to the shared folder is a link someone else will open (1942's owner,
2026-10-09: "you didn't need to push that as a WIP - I can test locally").

**Site repo, folder and names:** from the project's rules file or memory - e.g. a GitHub Pages repo
with a `content/wip/` folder shared by several projects. Ask once if neither says.
**Names:** `<game>-wip.ssd` (the debug build) and `<game>-rc.ssd` (the release build), lowercase,
the same names every time so shared links keep working

## Steps

1. **Build both discs from one commit**, the working tree clean (commit first if it is not):
   the default build (debug keys on) and the release build (`-Release` / `make release`). A WIP is
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

5. **Return both links**, each on its own line, saying which is which and the model they boot:

   ```
   https://bbc.xania.org/?disc=<site>/content/wip/<game>-wip.ssd&autoboot&model=<model>
   https://bbc.xania.org/?disc=<site>/content/wip/<game>-rc.ssd&autoboot&model=<model>
   ```

   `model=` is `B`, `BP` or `Master` (append `&coProcessor=true` for a second processor); use the
   machine the port targets. Pages hosting takes a minute or two to rebuild, so a link may 404
   briefly after the push.

6. **Record it**: the session's memory note gets the published commit and the site commit, so the
   next session knows what testers have.
