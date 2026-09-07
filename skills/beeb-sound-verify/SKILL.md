---
name: beeb-sound-verify
description: Capture the SN76489 writes the running BBC Micro port makes in the jsbeeb MCP and hand them to the project's verifier, which searches for them inside a reference stream rebuilt from the data the build actually includes. Use when the music files, the IRQ handler or the memory layout the tune lives in has changed, when a tune "sounds wrong", or when checking a mute or a music change.
---

# Sound capture against a reference stream

For a music player whose data is scattered, paged or converted, "it plays" is not the check. A
wrong address plays happily for thousands of frames before the stream runs off what it was
given, and the channels desynchronise into noise. Nothing but this catches a misplacement.

**Capture:** 10-20 fields of SN76489 writes, with cycle timestamps
**Pass:** the captured sequence matches the reference stream at **exactly one** frame
**Zero matches:** a placement, paging or IRQ bug. **Several:** the excerpt was too short to be diagnostic

## Steps

1. **Name the oracle before capturing.** The reference must be rebuilt *from the binaries the
   build `INCBIN`s and the map it assembles*, not from an intermediate file, so the placement
   itself is under test. Find the project's verifier in `tools/verify_*.py` and read its header
   (Edge Grinder: `tools/verify_vgi.py` lays the eleven register streams into a model of the
   Master's address space and decodes as the player would; `tools/akl/verify_akl.py` for the
   tracker build). If the project has no verifier, that is the first thing to build - a check
   of the player against its own output proves nothing (`docs/verification.md` procedure 15).

2. **Boot the build under test** (`beeb-smoke-test`) and run to the point where the tune in
   question is playing - the titles, the game, the finale. Note the field it started at if the
   verifier wants an offset.

3. **Capture, run, stop, save verbatim.** Ask for more entries than the fields produce: a
   busy tune writes ten or more bytes a field, and `stop_sound_capture` returns the *most
   recent* `max_entries`, so too few silently drops the start.

   ```
   start_sound_capture   session_id
   run_frames            session_id, count: 20
   stop_sound_capture    session_id, max_entries: 2000
   ```

   Each line is `<cycle>: 0x<byte> <decoded meaning>`. Paste the output unedited into a file in
   the scratchpad (`capture.txt`); the verifier parses the cycle and the byte and ignores the rest.

4. **Hand it to the verifier.**

   ```
   python tools/verify_vgi.py <scratchpad>/capture.txt
   ```

   Read the match count, not just the exit code. Edge Grinder's AKL check matched twelve fields
   at frame 427 and nowhere else in 17,446; that unique match is the pass.

5. **Run it after any change to the music files, the IRQ, or the memory layout the streams
   live in** - including a change that moved something *else* into the same bank. Both of Edge
   Grinder's tunes moved up a page in Layer 9i and both had to be re-exported and re-proved.

6. **The capture is also a diagnostic on its own.** Edge Grinder's mute crackled on jsbeeb and
   on b2; the capture showed `0xd9` (channel 2, attenuation 9) followed 246 cycles later by
   `0xdf` (attenuation 15), fifty times a second, and the fix followed from the timestamps. To
   verify a mute: capture ten muted fields and expect forty writes, all four channels at 15 and
   no tone writes; then `read_sound_state` the field after the un-mute press to see the volumes
   come back.

   ```
   read_sound_state   session_id
   ```

7. **Record** the frame the capture matched at, the build and flags, and the date, in the layer
   doc and the commit body ("capture matches at frame 427 and nowhere else").
