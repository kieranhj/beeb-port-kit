// capture.mjs - a headless jsbeeb's picture and sound, to a video: each field's displayed frame
// cropped from the emulator's framebuffer, an optional caption band over it, piped to ffmpeg as
// raw RGBA (H.264, yuv420p, 50 fps); the SN76489 as jsbeeb renders it, filtered down to a sample
// rate and written as a WAV; the two muxed.
//
// beeb-port-kit template, MIT, Kieran Connell 2026. From Stryker's Run's tools/sidebyside.mjs and
// tools/playvideo.mjs (2026-10-21 to 10-25), which made its side-by-side video of the 1986 original
// and the optimised build playing one game (3,000 fields, both machines' sound left and right) and
// its whole-world videos. tools/video.mjs is the command line over this module.
//
//   import { findFfmpeg, cropFor, startVideo, captureSound, writeWav, mux } from "./capture.mjs";
//   const sound = captureSound(h.s);                       // from now on
//   const video = await startVideo(h.s, "out.video.mp4", { crop: cropFor(h.s, "auto"), title: "Game" });
//   for (let f = 0; f < 500; f++) { await h.s.runFrames(1); await video.frame(`field ${f}`); }
//   await video.finish();
//   writeWav("out.wav", [sound.finish()], sound.rate);
//   mux(video.ffmpeg, "out.video.mp4", "out.wav", "out.mp4");
//
// THE PICTURE. jsbeeb paints each field into a 1024 x 625 RGBA framebuffer and snapshots it at
// the paint (`_completeFb8`, what its screenshot() reads): the frame the CRTC showed, main or
// shadow, whatever the CPU had paged. A 2 MHz character is 8 pixels wide there and a 1 MHz one
// 16; each scanline is two framebuffer rows. runFrames(1) stops on the paint, so call frame()
// after each. The crop:
//   "auto"     from the CRTC's registers when startVideo is called: x = (R0 + 1 - R2 -
//              (R3 & 15) / 2) * charPx - 8, width R1 * charPx; y = (total lines - R7 * (R9 + 1))
//              * 2, height R6 * (R9 + 1) * 2. Fitted on jsbeeb 2.10.2, 2026-10-25: MODEs 0, 1, 2, 4
//              and 5 with the MOS's registers on a Model B and a Master all gave the measured
//              non-black box of a CLG'd screen, (200, 64) 640 x 512. ONE CRTC FRAME A FIELD ONLY:
//              a rupture (the template's own two cycles) reprograms R4, R6 and R7 mid-field, so
//              the registers at any instant describe one cycle; give the box instead
//   "mos"      the MOS's MODE 0-2 and 4-5 picture, (200, 64) 640 x 512
//   "full"     jsbeeb's active area, as its screenshotActive() crops it (borders off), 896 x 600
//   "X,Y,W,H"  a box in framebuffer pixels
//   Measure a box before trusting it: frame() with outDir/"png" writes PNGs to look at.
//
// THE SOUND. jsbeeb's SN76489 renders at 500 kHz (4 MHz / 8) into a buffer it hands to a
// callback when full; captureSound() takes that callback over (`_onBuffer`) and box-filters the
// samples down to `rate` (default 50 kHz, a whole factor of 10: Stryker's Run's choice). Only
// what is generated after the call is kept. writeWav() normalises the peak to 0.9 over all
// channels together (one channel: mono; two: left and right, e.g. two machines).
//
// FFMPEG. findFfmpeg(): the explicit path, else $FFMPEG, else ffmpeg on the PATH, else Python's
// imageio-ffmpeg (`pip install imageio-ffmpeg`; its binary is a full ffmpeg with libx264), else
// null - and then startVideo writes the frames instead: format "png" (one PNG a field, in a
// directory named after the output) or "raw" (the RGBA concatenated, with a .json saying the
// size), so a run without ffmpeg still yields something to check or encode later.
import { mkdirSync, writeFileSync, openSync, writeSync, closeSync } from "node:fs";
import { spawn, spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import { join } from "node:path";

import { resolveJsbeebSrc } from "./jsbeeb_src.mjs";

const FB_W = 1024, FB_H = 625;

/** An ffmpeg binary's path, or null: explicit, $FFMPEG, the PATH, imageio-ffmpeg. */
export function findFfmpeg(explicit) {
    if (explicit) return explicit;
    if (process.env.FFMPEG) return process.env.FFMPEG;
    const w = spawnSync(process.platform === "win32" ? "where" : "which", ["ffmpeg"], { encoding: "utf8" });
    if (w.status === 0 && w.stdout.trim()) return w.stdout.trim().split(/\r?\n/)[0];
    for (const py of ["python", "python3"]) {
        const r = spawnSync(py, ["-c", "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"], { encoding: "utf8" });
        if (r.status === 0 && r.stdout.trim()) return r.stdout.trim();
    }
    return null;
}

/** The crop box for `spec` ("auto", "mos", "full", "X,Y,W,H"), clipped to the framebuffer. */
export function cropFor(s, spec = "auto") {
    let box;
    if (spec === "mos") box = { x: 200, y: 64, w: 640, h: 512 };
    else if (spec === "full") {
        const v = s._video;
        box = { x: v.leftBorder, y: v.topBorder, w: FB_W - v.leftBorder - v.rightBorder, h: FB_H - v.topBorder - v.bottomBorder };
    } else if (spec === "auto") {
        const v = s._video, r = v.regs, ppc = v.pixelsPerChar;
        const rows = r[4] + 1, lines = rows * (r[9] + 1) + r[5];
        box = { x: (r[0] + 1 - r[2] - ((r[3] & 15) >> 1)) * ppc - 8, w: r[1] * ppc,
                y: (lines - r[7] * (r[9] + 1)) * 2, h: r[6] * (r[9] + 1) * 2, regs: [...r.slice(0, 10)] };
    } else {
        const p = String(spec).split(",").map(Number);
        if (p.length !== 4 || p.some((n) => !Number.isInteger(n) || n < 0))
            throw new Error(`crop ${spec}: not auto, mos, full or X,Y,W,H`);
        box = { x: p[0], y: p[1], w: p[2], h: p[3] };
    }
    const x = Math.max(0, Math.min(FB_W - 2, box.x)), y = Math.max(0, Math.min(FB_H - 2, box.y));
    const w = Math.max(2, Math.min(FB_W - x, box.w)) & ~1, h = Math.max(2, Math.min(FB_H - y, box.h)) & ~1;
    return { ...box, x, y, w, h, spec };
}

function sharpLib() {
    return createRequire(`${resolveJsbeebSrc().src}/machine-session.js`)("sharp");   // jsbeeb's own dependency
}

const esc = (t) => String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

/**
 * Start a video of `s` (a MachineSession) at `out`. opts: crop (from cropFor), scale (nearest
 * neighbour, default 1), title (a bold first caption line; with no title and no frame() line
 * there is no band), fps (50), crf (18), ffmpeg (a path, or found), format ("mp4", or "png"/"raw"
 * to write the frames instead; with no ffmpeg found it falls back to "png").
 * Returns { frame(line) - append the field painted last, finish() - close, frames, format, ffmpeg }.
 */
export async function startVideo(s, out, opts = {}) {
    const crop = opts.crop || cropFor(s, "auto");
    const scale = opts.scale || 1, fps = opts.fps || 50, title = opts.title || "";
    const band = opts.caption === false ? 0 : (opts.band ?? 44);
    const ffmpeg = opts.format && opts.format !== "mp4" ? null : findFfmpeg(opts.ffmpeg);
    const format = ffmpeg ? "mp4" : (opts.format && opts.format !== "mp4" ? opts.format : "png");
    const W = crop.w, H = band + crop.h;
    const frame = Buffer.alloc(W * H * 4);
    const BG = [24, 24, 24];
    for (let i = 0; i < W * H; i++) { frame[i * 4] = BG[0]; frame[i * 4 + 1] = BG[1]; frame[i * 4 + 2] = BG[2]; frame[i * 4 + 3] = 255; }
    const sharp = band || format === "png" ? sharpLib() : null;
    const captions = new Map();
    const caption = async (line) => {
        const key = title + "|" + line;
        let c = captions.get(key);
        if (c) return c;
        const two = title && line;
        const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${band}">
<rect width="100%" height="100%" fill="rgb(${BG.join(",")})"/>
${title ? `<text x="${W / 2}" y="${two ? 19 : 28}" font-family="Arial, Helvetica, sans-serif" font-size="17" font-weight="bold" fill="#ffffff" text-anchor="middle">${esc(title)}</text>` : ""}
${line ? `<text x="${W / 2}" y="${two ? 38 : 28}" font-family="Consolas, 'Courier New', monospace" font-size="14" fill="#c8c8c8" text-anchor="middle" xml:space="preserve">${esc(line)}</text>` : ""}
</svg>`;
        c = await sharp(Buffer.from(svg)).flatten({ background: { r: BG[0], g: BG[1], b: BG[2] } }).ensureAlpha().raw().toBuffer();
        if (captions.size > 4000) captions.clear();
        captions.set(key, c);
        return c;
    };

    const v = { frames: 0, format, ffmpeg, crop, width: W * scale, height: H * scale, path: out };
    let ff = null, done = false, rawFd = null, pngDir = null;
    const failed = [];
    if (format === "mp4") {
        const vf = scale > 1 ? ["-vf", `scale=iw*${scale}:ih*${scale}:flags=neighbor`] : [];
        ff = spawn(ffmpeg, ["-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", `${W}x${H}`, "-r", String(fps),
            "-i", "-", ...vf, "-c:v", "libx264", "-preset", "medium", "-crf", String(opts.crf ?? 18), "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", out], { stdio: ["pipe", "inherit", "inherit"] });
        ff.on("close", (code) => { if (!done) failed.push(`ffmpeg exited (${code}) before the last frame`); });
        ff.stdin.on("error", (e) => failed.push(`ffmpeg: ${e.message}`));
    } else if (format === "raw") {
        rawFd = openSync(out, "w");
        writeFileSync(out + ".json", JSON.stringify({ width: W, height: H, pix_fmt: "rgba", fps,
            ffmpeg: `ffmpeg -f rawvideo -pix_fmt rgba -s ${W}x${H} -r ${fps} -i ${out} -pix_fmt yuv420p out.mp4` }));
    } else {
        pngDir = out.replace(/\.[^./\\]+$/, "") + "-frames";
        mkdirSync(pngDir, { recursive: true });
        v.path = pngDir;
    }
    const write = (buf) => new Promise((res) => { if (ff.stdin.write(buf)) res(); else ff.stdin.once("drain", res); });

    v.frame = async (line = "") => {
        if (failed.length) throw new Error(failed[0]);
        if (band) (await caption(line)).copy(frame, 0, 0, W * band * 4);
        const fb = s._completeFb8;
        for (let y = 0; y < crop.h; y++) {
            const src = ((crop.y + y) * FB_W + crop.x) * 4;
            frame.set(fb.subarray(src, src + W * 4), (band + y) * W * 4);
            for (let x = 0; x < W; x++) frame[((band + y) * W + x) * 4 + 3] = 255;
        }
        if (ff) await write(Buffer.from(frame));
        else if (rawFd !== null) writeSync(rawFd, frame);
        else {
            let img = sharp(Buffer.from(frame), { raw: { width: W, height: H, channels: 4 } });
            if (scale > 1) img = img.resize(W * scale, H * scale, { kernel: "nearest" });
            await img.png().toFile(join(pngDir, `${String(v.frames).padStart(6, "0")}.png`));
        }
        v.frames++;
    };
    v.finish = async () => {
        done = true;
        if (ff) {
            ff.stdin.end();
            const code = await new Promise((res) => (ff.exitCode !== null ? res(ff.exitCode) : ff.on("close", res)));
            if (code !== 0) throw new Error(`ffmpeg exited ${code}`);
        }
        if (rawFd !== null) closeSync(rawFd);
        if (failed.length) throw new Error(failed[0]);
        return v;
    };
    return v;
}

/**
 * Tap `s`'s SN76489 from now on. Returns { rate, finish() -> Float32Array of the samples so far }.
 * jsbeeb's chip renders at 500 kHz; each output sample is the mean of the input samples in its
 * 1/rate of a second (a box filter: 50 kHz, the default, takes exactly 10).
 */
export function captureSound(s, { rate = 50000 } = {}) {
    const chip = s._soundChip;
    if (!chip || typeof chip.catchUp !== "function" || !chip.buffer)
        throw new Error("this session has no SN76489 to tap (an Atom?)");
    const step = chip.soundchipFreq / rate;          // input samples per output sample
    const out = { rate, data: new Float32Array(rate * 10), n: 0 };
    let acc = 0, k = 0, edge = step, pos = 0;        // pos: input samples consumed
    const push = (x) => {
        acc += x; k++; pos++;
        if (pos < edge) return;
        if (out.n === out.data.length) { const d = new Float32Array(out.data.length * 2); d.set(out.data); out.data = d; }
        out.data[out.n++] = acc / k; acc = 0; k = 0; edge += step;
    };
    chip.catchUp();
    let skip = chip.position;                        // what the buffer holds now is from before now
    chip._onBuffer = (buf) => { for (let i = skip; i < buf.length; i++) push(buf[i]); skip = 0; };
    out.finish = () => {
        chip.catchUp();
        for (let i = skip; i < chip.position; i++) push(chip.buffer[i]);
        skip = chip.position;
        return out.data.subarray(0, out.n);
    };
    return out;
}

/** A 16-bit PCM WAV of one channel (mono) or more (interleaved), the peak over all scaled to 0.9. */
export function writeWav(path, channels, rate) {
    const n = Math.min(...channels.map((c) => c.length)), ch = channels.length;
    let peak = 0;
    for (const c of channels) for (let i = 0; i < n; i++) peak = Math.max(peak, Math.abs(c[i]));
    const gain = peak > 0 ? 0.9 / peak : 0;
    const bytes = n * ch * 2, buf = Buffer.alloc(44 + bytes);
    buf.write("RIFF", 0); buf.writeUInt32LE(36 + bytes, 4); buf.write("WAVE", 8);
    buf.write("fmt ", 12); buf.writeUInt32LE(16, 16); buf.writeUInt16LE(1, 20); buf.writeUInt16LE(ch, 22);
    buf.writeUInt32LE(rate, 24); buf.writeUInt32LE(rate * ch * 2, 28); buf.writeUInt16LE(ch * 2, 32); buf.writeUInt16LE(16, 34);
    buf.write("data", 36); buf.writeUInt32LE(bytes, 40);
    const q = (x) => Math.max(-32768, Math.min(32767, Math.round(x * gain * 32767)));
    for (let i = 0; i < n; i++) for (let c = 0; c < ch; c++) buf.writeInt16LE(q(channels[c][i]), 44 + (i * ch + c) * 2);
    writeFileSync(path, buf);
    return { path, samples: n, channels: ch, rate, seconds: +(n / rate).toFixed(3), peak };
}

/** Video and WAV into one file (the video stream copied, the sound AAC). Throws on failure. */
export function mux(ffmpeg, video, wav, out, { shortest = true } = {}) {
    const r = spawnSync(ffmpeg, ["-y", "-loglevel", "error", "-i", video, "-i", wav, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        ...(shortest ? ["-shortest"] : []), "-movflags", "+faststart", out], { stdio: "inherit" });
    if (r.status !== 0) throw new Error(`ffmpeg mux failed (${r.status})`);
    return out;
}
