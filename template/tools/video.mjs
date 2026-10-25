// video.mjs - boot a disc in headless jsbeeb, optionally press keys, and record N fields as a
// 50 fps video with its sound.
//
// beeb-port-kit template, MIT, Kieran Connell 2026. The command line over tools/capture.mjs, from
// Stryker's Run's tools/playvideo.mjs and tools/sidebyside.mjs (2026-10-25).
//
//   node tools/video.mjs DISC OUT.mp4 [--fields 500] [--from 0] [--keys SPEC] [--model M]
//        [--crop auto|mos|full|X,Y,W,H] [--scale 2] [--title T] [--no-caption] [--no-sound]
//        [--rate 50000] [--frames png|raw] [--ffmpeg PATH]
//
// Boots DISC (SHIFT+BREAK, harness.mjs's boot) on MODEL (jsbeeb's name; default Master if the
// build defines MASTER=1, else B-DFS1.2), runs --from fields unrecorded, then records --fields
// fields. --keys is a tools/keyscript.mjs schedule, fields counted from the end of the boot
// ("X" holds X throughout; "100:SPACE+5,300:RIGHT" presses SPACE for 5 fields at 100 and holds
// RIGHT from 300). The caption is the title and "field N". Writes OUT.mp4 (muxed), OUT.wav (the
// sound, mono) and prints one JSON line. With no ffmpeg anywhere (capture.mjs's findFfmpeg) the
// frames go to OUT-frames/ as PNGs (or --frames raw: OUT.rgba) and the WAV is still written.
// Exit 0: frames written and, with sound on, samples captured; 1: nothing captured; 2: could
// not run (usage, no disc, no symbols, ffmpeg failed).
//
// Measured 2026-10-25, jsbeeb 2.10.2: the template's build/game.ssd, 250 fields holding X,
// --crop 200,128,640,320 (its 20 displayed rows: cycle A's 4 and B's 16, vsync at absolute row
// 31) and Stryker's Run's build/strykers.ssd on a Master, --crop auto (see the commit).
//
// COMPARING AN ORIGINAL WHOSE RANDOMNESS COMES FROM A TIMER. A game that takes its random
// numbers from a VIA timer read (Stryker's Run read User VIA T2, &FE68/&FE69, at four sites)
// cannot replay a game in step with a port that replaced it with a PRNG: the timer follows time,
// and the two builds run at different speeds. Stryker's Run's sidebyside.mjs made them play one
// game WITHOUT WRITING THE ORIGINAL'S RAM: at each site the original's own LDA &FE6x still runs
// (same cycles, same read), and on the next instruction, before the AND that uses it, the
// emulator puts the port's PRNG's next byte in A. The PRNG is the port's routine transcribed
// into JS bit for bit, seeded where the port seeds it. Every site is checked to hold the bytes
// expected (LDA abs, then the AND) before the first pass, so a wrong build fails loudly:
//
//   const sites = new Map([[0x2383, 0x2386], ...]);     // LDA &FE68 at -> the instruction after
//   let pending = -1;
//   cpu.debugInstruction.add((pc) => {
//       if (sites.has(pc) && cpu.readmem(pc) === 0xad && cpu.readmem(pc + 2) === 0xfe) pending = sites.get(pc);
//       else if (pc === pending) { cpu.a = prng(); pending = -1; }
//       if (pc === seedAt) prng.seed();
//       return false;
//   });
//
// Then the bytes each build consumed are recorded in order and compared: a difference says
// where the two games parted. (In Stryker's Run the port's first generator lived at &92/&93,
// which the original also wrote as scratch; for builds from before that fix the original's writes
// there were mirrored into the JS generator - check that the PRNG's state is not a byte the
// original uses.) Other timer reads (raster positions) are left alone.
import { existsSync, unlinkSync } from "node:fs";

import { open } from "./harness.mjs";
import { parseKeys, applyKeys } from "./keyscript.mjs";
import { cropFor, startVideo, captureSound, writeWav, mux } from "./capture.mjs";

const args = process.argv.slice(2);
const opt = (name, dflt) => { const i = args.indexOf(name); if (i < 0) return dflt; const v = args[i + 1]; args.splice(i, 2); return v; };
const flag = (name) => { const i = args.indexOf(name); if (i < 0) return false; args.splice(i, 1); return true; };
const FIELDS = parseInt(opt("--fields", "500"), 10), FROM = parseInt(opt("--from", "0"), 10);
const KEYS = opt("--keys", ""), MODEL = opt("--model", null), CROP = opt("--crop", "auto");
const SCALE = parseInt(opt("--scale", "1"), 10), TITLE = opt("--title", null), RATE = parseInt(opt("--rate", "50000"), 10);
const FRAMES = opt("--frames", null), FFMPEG = opt("--ffmpeg", null);
const NOCAP = flag("--no-caption"), NOSOUND = flag("--no-sound");
const [disc, out] = args;
if (!disc || !out || !(FIELDS > 0)) {
    console.error("usage: node tools/video.mjs DISC OUT.mp4 [--fields N] [--from F] [--keys SPEC] [--model M] [--crop auto|mos|full|X,Y,W,H] [--scale K] [--title T] [--no-caption] [--no-sound] [--rate HZ] [--frames png|raw] [--ffmpeg PATH]");
    process.exit(2);
}

const h = await open({ name: "video", disc });
h.model = MODEL || (h.define("MASTER") ? "Master" : "B-DFS1.2");
let sched;
try { sched = parseKeys(KEYS); } catch (e) { h.die(e.message); }
await h.boot();
const s = h.s;
let f = 0;
for (; f < FROM; f++) { applyKeys(s, sched, f); await s.runFrames(1); }

const base = out.replace(/\.mp4$/i, "");
const sound = NOSOUND ? null : captureSound(s, { rate: RATE });
const crop = cropFor(s, CROP);
const tmp = sound ? base + ".video.mp4" : out;
let video;
try {
    video = await startVideo(s, FRAMES ? out.replace(/\.mp4$/i, FRAMES === "raw" ? ".rgba" : "") : tmp,
        { crop, scale: SCALE, title: TITLE ?? disc.replace(/^.*[\\/]/, ""), caption: !NOCAP, ffmpeg: FFMPEG, format: FRAMES || "mp4" });
} catch (e) { h.die(`could not start the video: ${e.message}`); }
if (video.format !== "mp4" && !FRAMES) console.error("video: no ffmpeg found (--ffmpeg, $FFMPEG, PATH, imageio-ffmpeg): writing PNG frames");

const t0 = Date.now();
for (let n = 0; n < FIELDS; n++, f++) {
    applyKeys(s, sched, f);
    const r = await s.runFrames(1);
    if (!r.completed) h.die(`field ${f} did not complete`, { where: h.where() });
    await video.frame(`field ${f}`);
}
try { await video.finish(); } catch (e) { h.die(e.message); }

let wav = null, muxed = null;
if (sound) {
    wav = writeWav(base + ".wav", [sound.finish()], RATE);
    if (video.format === "mp4") {
        try { muxed = mux(video.ffmpeg, tmp, wav.path, out); } catch (e) { h.die(e.message); }
        if (existsSync(tmp)) unlinkSync(tmp);
    }
}
const ok = video.frames === FIELDS && (!sound || wav.samples > 0);
h.finish({ disc, from: FROM, fields: FIELDS, keys: KEYS || null, seconds: +((Date.now() - t0) / 1000).toFixed(1),
           crop: { x: crop.x, y: crop.y, w: crop.w, h: crop.h, spec: crop.spec, regs: crop.regs },
           video: { format: video.format, path: muxed || video.path, frames: video.frames, width: video.width, height: video.height, ffmpeg: video.ffmpeg },
           sound: wav ? { wav: wav.path, samples: wav.samples, rate: wav.rate, seconds: wav.seconds, peak: +wav.peak.toFixed(4) } : null },
         ok, { samples: video.frames });
