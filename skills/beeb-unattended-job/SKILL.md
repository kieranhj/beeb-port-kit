---
name: beeb-unattended-job
description: Run a long job on a BBC Micro port while the owner is away (overnight, or a day's absence) - its own branch, the brief committed first with a resume point, decisions taken provisionally marked TAKEN and listed for review, real-hardware gates left shut, the suite run detached with its output outside the home folder, nothing merged or published, and a morning report with a branch ledger. Use when the user says to carry on without them, work overnight, "keep going while I'm out", or hands over a job to finish unsupervised.
---

# An unattended job

Unattended jobs work: 1942 built its front end, a RAM hunt and four enemy-behaviour decisions
overnight. They also failed in specific, repeated ways, and each rule below is one of them:

- decisions taken provisionally were reversed in the morning (1942's 125a);
- a real-hardware gate was bypassed: a branch merged before the owner's Master had seen it;
- the session limit cut a rewrite off half way - survivable only because the brief named the
  resume point;
- branches piled up until the owner lost track of which held what;
- suites died of memory, or of the 10-minute limit on a background command.

**Brief:** `docs/brief-<job>.md` (from `docs/brief-TEMPLATE.md`), committed before any code
**Report:** `docs/report-<job>-<date>.md`, for the owner, written last
**Output:** the session scratchpad or the system temp directory - never the repository, never the
user's home folder

## Steps

1. **Branch first**: `git switch -c <job>` off the commit the owner last saw. Note that commit in
   the brief. Never work on the default branch, never merge, never push unless the owner said to.

2. **Commit the brief before any code**, with its steps numbered and a **resume point**: "if this
   session ends, the next one starts at step N, reading X". Update the resume point in the brief
   as each step lands, in the same commit as the step.

3. **Decisions**: anything the original or the brief does not settle, take - but write it in
   `docs/decisions.md` with Status `TAKEN` (provisional, the agent's, for review), the options and
   why this one, and **build it behind a switch** where that is cheap, so the owner can try the
   other answer from a test disc. Never take a decision the owner has already answered differently;
   never re-litigate a rejected one.

4. **Hardware gates stay shut.** Anything the rules file says needs the owner's real machine (a
   disc access in play, a CRTC timing change, BREAK, a new mid-frame flip) is built and verified in
   the emulator and then stops at "ready for hardware". It is not merged, and the report says so in
   its first lines.

5. **One step, one commit, the measurement in the body**, and the oracles the step touches run
   before the commit.

6. **Run the suite detached**, so a background time limit or the session's own end does not kill
   it: launch it as a process that outlives the command (the project's suite runner with N at a
   time, e.g. `python tools/run_suite.py <OUT_DIR> 4`, started with `run_in_background` or a
   detached shell), with its output in the scratchpad or temp - absolute, outside the repo and
   the home folder - and pass/fail read from its exit codes. Lower N if the machine ran out of
   memory last time. Do not rebuild while it runs.

7. **No publishing.** A WIP or release disc goes out only when the owner asks (`beeb-publish-wip`).
   Leave the local disc built and say where it is.

8. **The report**, written for someone reading it first thing:
   - **where it ended**, in one paragraph, and how to try it (the disc path, the switch, the keys);
   - **what was built and what proves it** (each oracle's verdict, the suite's count);
   - **decisions TAKEN - please review**, each with its row number and the switch to try the other
     answer;
   - **gates waiting on hardware**;
   - **what is open**, and the resume point if the job is unfinished;
   - **a branch ledger**: every branch this job made or touched, its head commit, and whether it
     is merged, pushed, and published (it should say no, no, no).

9. **Write the session's memory note**: the branch, its state, the report's path.
