---
name: beeb-hwtest-disc
description: Build and run a hardware-test disc for the questions emulators cannot answer - one small probe program per question behind a MODE 7 menu, checked in jsbeeb first, then run by the owner on the real machine from a phone checklist, with the results recorded per machine and monitor. Use as soon as a port depends on a raster, CRTC, palette, shadow-RAM, disc or BREAK behaviour that no real-hardware measurement covers yet, and whenever a real machine and the emulator disagree.
---

# A hardware-test disc

Emulators passing is not enough: phX's real Master showed the MA13 addressing flipped, palette
writes landing early, a monitor that clamps black in the back porch, and a 1770 that ends READ
ADDRESS before the emulator does - none of which any emulator then modelled. A small disc of
probes, each answering one question, turns "it looks wrong on the real machine" into a fact
(`docs/hardware-facts.md` §1, §2, §6; phX `docs/hwtest.md`).

**One probe = one question**, a picture or readout the owner can judge by eye, and a jsbeeb run
of the same probe so the photo is compared with something.

## Steps

1. **Write the question first** in the project's `docs/hwtest.md`: what is unknown, what each
   outcome would look like on screen, what the port does in each case. A probe without a
   prediction cannot fail.

2. **Write the probe** as its own small program: draw ticks or coloured characters at known
   C0/lines so a photograph can be read to the character; vary the one thing under test across
   bands of the screen (odd/even C0, before/after a write, each candidate value). Keep keys for
   variants (`V`, `P`) and print the build's commit on screen.

3. **Menu and disc:** a MODE 7 menu that `*RUN`s each probe and comes back (BREAK or a key).
   The disc carries a checklist the owner can read on a phone: per probe, which key, what to
   look at, what each outcome means.

4. **Run it in jsbeeb first**, both the pinned version and jsbeeb main if the question touches
   what main changed (MA13, palette/R8 timing, the 1770):

   ```
   node tools/hwtest_check.mjs build/hwtest.ssd work/hwtest/t1.png 50 --menu-key=Digit3 --menu-text="HARDWARE TEST" --jitter=2 --model=Master
   ```

   It checks the frame contract, lists every CRTC/ULA/ACCCON write with its line and C0, and
   screenshots each variant (`--keys=KeyV,KeyP`). Every write the probe makes must land where
   the prediction says *in the emulator*; otherwise a real-machine difference means nothing.
   `tools/probe_6845.mjs` builds variants of a probe source and records one field each.

5. **Publish it** (`beeb-publish-wip`) and ask the owner to run it, naming the machine, the
   monitor and the medium (floppy, Gotek). Photographs, not descriptions, where a picture is
   the answer.

6. **Record the result per machine and monitor** in `docs/hwtest.md`: what was seen, the jsbeeb
   column beside it, the conclusion, and what the port now does. Two machines or monitors that
   disagree are both recorded (phX: a Sony and a CUB CRT). Move the fact into
   `docs/hardware-facts.md` once it is settled; leave it open there if it is not.

7. **Send emulator differences upstream** with the probe as the test case.

## Traps

- A `*RUN` from the boot arrives with interrupts disabled on a Master: a menu waiting in OSRDCH
  waits for ever until a `cli` (`docs/gotchas.md` class 6).
- Real RAM powers up as junk, not zeros: a probe that reads uninitialised memory passes in
  jsbeeb only (run the jsbeeb check with `JUNK=seed`).
- Results judged by eye are good to about a character or a pixel; say so when recording them.
