// probe_6845.mjs - build one variant of a probe source, run it, and record one field as the video
// saw it: the instrument for a 6845 question before a port depends on the answer.
//
// beeb-port-kit template, MIT, Kieran Connell 2026. From the phX port, 2026-11 (its step 3:
// one probe source, a TEST number and -D values per 6845 question, each recorded here before
// it was asked of a real Master).
//
//   node tools/probe_6845.mjs SRC.6502 TEST [NAME=VALUE ...] [--entry=draw_entry]
//        [--field=field_count] [--capture=30 | --capture-at=N] [--frames=200]
//        [--out=build/probes] [--model=Master]
//
// The probe source is the port's own (the kit ships none): one Baron source whose !BOOT runs it,
// with a `field_count` it increments a field and a `draw_entry` label at the start of the field's
// work, -D TEST=n choosing the experiment and the NAME=VALUEs its parameters. It is assembled
// with Baron ($BARON, else bin/baron(.exe), else the PATH) into OUT/p<tag>.ssd with its symbols
// beside it (--opt 2: !BOOT is *RUN), booted, and the --capture'th draw entry's field (or the
// one whose field_count is --capture-at, for a draw that starts at a given field) recorded:
//   every byte the video fetches (cpu.videoRead) with the monitor beam (video.bitmapY = the
//   raster line on the tube, horizCounter = C0), C9, C4, whether it is SHOWN (every display
//   enable on and not the teletext blank of a 2 MHz mode with the teletext bit - RTW's "TTX
//   trick") and logical 0's colour; every CPU write to the CRTC (&FE00-&FE01) or the ULA
//   (&FE20-&FE21) with the counters at it and the cycles since draw entry.
// Out: OUT/<tag>.json - per raster line: the characters shown (first and last C0), the first
// addresses, per scanline (C9) the same, logical 0's colour changes; the writes. A summary line
// on stdout. Exit 2 if the build fails or nothing was fetched.
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { cli, num, open } from "./harness.mjs";

const { pos, opt } = cli();
const [src, test, ...defs] = pos;
if (!test) { console.error("usage: node tools/probe_6845.mjs SRC.6502 TEST [NAME=VALUE ...] [--entry=LABEL] [--capture=N]"); process.exit(2); }
const OUT = opt.out || "build/probes";
const tag = [test, ...defs.map((d) => d.replace("=", ""))].join("-");
mkdirSync(OUT, { recursive: true });
const disc = join(OUT, `p${tag}.ssd`);

const baron = (() => {
    if (process.env.BARON) return process.env.BARON;
    const bin = resolve(dirname(fileURLToPath(import.meta.url)), "..", "bin");
    for (const f of ["baron.exe", "baron"]) if (existsSync(join(bin, f))) return join(bin, f);
    return "baron";
})();
const args = ["--warn", "1", "-o", disc, "--title", "PROBE", "--opt", "2", "-D", `TEST=${test}`,
    ...defs.flatMap((d) => ["-D", d]), "--symbols", disc.replace(/\.[sd]sd$/i, ".symbols.json"), src];
try {
    execFileSync(baron, args, { stdio: ["ignore", "ignore", "pipe"] });
} catch (e) {
    console.error(String(e.stderr || e));
    console.log(JSON.stringify({ probe: tag, error: "build failed", baron }));
    process.exit(2);
}

const h = await open({ name: `probe_6845 ${tag}`, disc, model: opt.model || "Master" });
const FIELD = h.zp(opt.field || "field_count");
const ENTRY = h.need(opt.entry || "draw_entry");
await h.boot({ field: FIELD });
const v = h.cpu.video;
const ALL = 63;                            // every display-enable bit (video.js)
let rec = false;
const fetches = [], writes = [];
const origRead = h.cpu.videoRead.bind(h.cpu);
h.cpu.videoRead = (a) => {
    if (rec) fetches.push([v.bitmapY, v.horizCounter, v.scanlineCounter, v.vertCounter, a,
        (v.dispEnabled & ALL) === ALL && !(v.teletextMode && !v.halfClock) ? 1 : 0, v.ulaPal[0]]);
    return origRead(a);
};
let entryT = 0;
h.onWrite(0xfe00, 0xfe21, (addr, val, c) => {
    if (rec && (addr <= 0xfe01 || addr === 0xfe20 || addr === 0xfe21)) writes.push([v.bitmapY, c.hc, c.sc, c.vc, addr, val, c.cycles - entryT]);
    return false;
});
let entries = 0, captured = false;
const entryBeams = [];                      // where the CRTC was at each draw entry (C0:C9:C4)
const CAP = num(opt.capture, 30);
h.onExec(ENTRY, () => {
    entries++;
    entryBeams.push(`${v.horizCounter}:${v.scanlineCounter}:${v.vertCounter}`);
    const start = opt["capture-at"] !== undefined ? h.byte(FIELD, "main") === num(opt["capture-at"]) && !rec && !captured : entries === CAP;
    if (start) { rec = true; captured = true; entryT = h.s.elapsedCycles; return false; }
    if (rec) { rec = false; return true; }
    return false;
}, h.gateOf(opt.entry || "draw_entry"));
await h.s.runFrames(num(opt.frames, 200));

// per raster line (bitmapY): displayed characters and what they were
const lines = new Map();
let seq = -1, prevY = null;
for (const [y, hc, sc, vc, a, en, pal] of fetches) {
    if (y !== prevY) { seq++; prevY = y; }          // in order: the raster may restart (a VSync)
    if (!lines.has(seq)) lines.set(seq, { seq, y, vc, n: 0, first: null, last: null, a0: null, sc: [], pal: [] });
    const L = lines.get(seq);
    if (en) {
        if (L.first === null) { L.first = hc; L.a0 = a; }
        L.last = hc;
        L.n++;
        if (!L.sc.includes(sc)) L.sc.push(sc);
        if (L.addrs === undefined) L.addrs = [];
        if (L.addrs.length < 3) L.addrs.push(a);
        if (L.bySc === undefined) L.bySc = {};      // per scanline: a burnt line's strays apart
        const b = L.bySc[sc] || (L.bySc[sc] = { n: 0, first: hc, last: hc, a0: a });
        b.n++;
        b.last = hc;
    }
    const last = L.pal[L.pal.length - 1];
    if (!last || last[1] !== pal) L.pal.push([hc, pal]);
}
const outFile = join(OUT, `${tag}.json`);
const result = { probe: tag, lines: [...lines.values()], writes };
writeFileSync(outFile, JSON.stringify(result));
const shown = result.lines.filter((L) => L.n);
console.log(JSON.stringify({ probe: tag, entries, captured, rasterLines: result.lines.length, displayedLines: shown.length,
    writes: writes.length, entryBeams: entryBeams.slice(0, 16).join(" "), file: outFile }));
if (!fetches.length) { console.error("probe_6845: nothing was fetched: the capture never started, or the display never came on"); process.exit(2); }
process.exit(0);
