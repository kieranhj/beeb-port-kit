// qdisc_test.mjs - does lib/qdisc.6502 read the disc byte for byte, and does
// lib/qdload.6502 find files by name? jsbeeb Master, headless.
//
//   node lib/test/qdisc_test.mjs          (from the kit's root; assembles
//                                          lib/test/qdisc_test.6502 itself)
//
// From the 1942 port's tools/verify_qdisc.mjs, with the named-file half added.
// It builds a DOUBLE-SIDED disc: the test SSD's tracks on side 0, a known pattern
// in every sector the SSD does not reach and in all of side 1 - the 1770 reads
// raw sectors, so nothing needs a catalogue entry to be read. The program breaks
//   qt_booted  after qd_boot: the file table must hold each file's (start sector,
//              sectors) exactly as the catalogue says - the first and the last
//              catalogue entries among them - and NOPE zero, with A = 1 missing;
//   qt_done    after each raw read: the bytes against the image, the sentinel
//              after the buffer (a SEEK's completion NMI came before every read:
//              an armed routine would store one junk byte exactly there), the
//              status's error bits, and the time;
//   qt_loaded  after each named load: the file's bytes, the sentinel after its
//              last page, qd_err = 0, and zxsrc on the buffer.
// It FAILS on any of those, or on a phase never reached. Exit code = verdict.
// Timing: the idle loop is 17 cycles a pass and the IRQ is masked, so the NMI's
// share of a read is elapsed - 17 x passes; cycles a byte is that over the bytes.
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const kit = join(here, "..", "..");
const { loadMachineSession } = await import(`file:///${join(kit, "template", "tools", "jsbeeb_src.mjs").split("\\").join("/")}`);
const baron = process.env.BARON || join(kit, "template", "bin", process.platform === "win32" ? "baron.exe" : "baron");
const out = join(here, "build");
mkdirSync(out, { recursive: true });
const ssdPath = join(out, "qdtest.ssd"), symPath = join(out, "qdtest.json");
execFileSync(baron, ["--warn", "2", "-o", ssdPath, "--title", "QDTEST", "--opt", "3",
    "--symbols", symPath, join(here, "qdisc_test.6502")], { stdio: "inherit" });

// ---- the symbols: every section's labels and assignments, flattened
const syms = {};
for (const a of JSON.parse(readFileSync(symPath, "utf8")).assemblies)
    for (const sec of a.sections)
        for (const kind of ["labels", "assignments"])
            for (const [k, v] of Object.entries(sec[kind] || {})) syms[k] = v.value;
const sym = (n) => { if (syms[n] === undefined) throw new Error(`no symbol ${n}`); return syms[n]; };

// ---- the disc: 80 tracks, 2 sides, 10 x 256, DSD order (track t side 0, side 1)
const TRACK = 2560;
const ssd = readFileSync(ssdPath);
const pattern = (side, track, i) => ((side * 131 + track * 37 + (i >> 8) * 11 + i * 7 + (i >> 5)) ^ (track << 1)) & 0xFF;
const image = [0, 1].map((side) => Array.from({ length: 80 }, (_, t) => {
    const b = Buffer.alloc(TRACK);
    for (let i = 0; i < TRACK; i++) b[i] = pattern(side, t, i);
    if (side === 0 && t * TRACK < ssd.length) ssd.copy(b, 0, t * TRACK, Math.min(ssd.length, (t + 1) * TRACK));
    return b;
}));
const dsd = Buffer.alloc(80 * 2 * TRACK);
for (let t = 0; t < 80; t++) for (let sd = 0; sd < 2; sd++) image[sd][t].copy(dsd, (2 * t + sd) * TRACK);
const dsdPath = join(out, "qdtest.dsd");
writeFileSync(dsdPath, dsd);

// the SSD's own catalogue, the oracle's copy
const cat = {};
const nfiles = ssd[0x105] >> 3;
for (let k = 0; k < nfiles; k++) {
    const o = 8 + 8 * k;
    const name = ssd.subarray(o, o + 7).toString("latin1").replace(/ +$/, "").replace(/[\x80-\xff]/g, (c) => String.fromCharCode(c.charCodeAt(0) & 0x7f));
    const len = ssd[0x100 + o + 4] | (ssd[0x100 + o + 5] << 8) | (((ssd[0x100 + o + 6] >> 4) & 3) << 16);
    const start = ssd[0x100 + o + 7] | ((ssd[0x100 + o + 6] & 3) << 8);
    cat[name] = { k, start, len, sectors: Math.ceil(len / 256), data: ssd.subarray(start * 256, start * 256 + len) };
}
const sectorBytes = (abs, n) => Buffer.concat(Array.from({ length: n }, (_, i) => {
    const s = abs + i, t = Math.floor(s / 10);
    return image[0][t].subarray((s % 10) * 256, (s % 10) * 256 + 256);
}));

// ---- the machine
const MachineSession = await loadMachineSession();
const s = new MachineSession("Master", { tube: false });
await s.initialise();
await s.boot(30);
s.loadDisc(dsdPath);
const cpu = s._machine.processor;
const mem = (a, n = 1) => Array.from(s.readMemory(a, n, { shadow: false }));
const QT_BUF = sym("QT_BUF"), SENT = sym("QT_SENTV");
const bps = {};
for (const n of ["qt_booted", "qt_sk", "qt_rd", "qt_done", "qt_loaded", "qt_end"]) bps[sym(n)] = n;
for (const a of Object.keys(bps)) s.addBreakpoint("execute", Number(a));
await s.autoboot();

const res = { jsbeeb: null, cfg: null, table: [], tableBad: 0, missing: null, reads: 0, badBytes: 0,
              badReads: [], sentinelMoved: 0, statusErrors: 0, run: null, loads: [] };
const readCycles = [], seekCycles = [], nmiPerByte = [];
let tSeek = 0, tRead = 0, reached = new Set();
for (let guard = 0; guard < 4000 && !reached.has("qt_end"); guard++) {
    s.resetBreakpointHits();
    await s.runFor(40_000_000);
    const hit = s.hitBreakpoint();
    if (!hit) { res.error = `no breakpoint in 40M cycles at pc ${cpu.pc.toString(16)}`; break; }
    const what = bps[cpu.pc], now = s.elapsedCycles;
    if (!what) continue;
    reached.add(what);
    if (what === "qt_sk") { tSeek = now; continue; }
    if (what === "qt_rd") { tRead = now; seekCycles.push(now - tSeek); continue; }
    if (what === "qt_booted") {
        res.cfg = { ctl: mem(sym("qd_cfg_ctl"))[0].toString(16), rate: mem(sym("qd_cfg_rate"))[0],
                    seekOp: mem(sym("qd_seek_op") + 1)[0].toString(16), ctl1: mem(sym("qd_ctl1") + 1)[0].toString(16) };
        res.missing = mem(sym("qt_miss"))[0];
        const nch = sym("QD_NCH"), stride = nch + 3, base = sym("qd_cat");
        const n = (sym("qd_cat_end") - base) / stride;
        for (let j = 0; j < n; j++) {
            const e = mem(base + j * stride, stride);
            const name = String.fromCharCode(...e.slice(0, nch)).trim();
            const got = { name, start: e[nch] | (e[nch + 1] << 8), sectors: e[nch + 2] };
            const want = cat[name] ? { start: cat[name].start, sectors: cat[name].sectors } : { start: 0, sectors: 0 };
            got.ok = got.start === want.start && got.sectors === want.sectors;
            got.catIndex = cat[name] ? cat[name].k : null;
            if (!got.ok) { res.tableBad++; got.want = want; }
            res.table.push(got);
        }
        continue;
    }
    if (what === "qt_done") {
        const [track, side, first, pages] = mem(sym("qt_track"), 4);
        const idle = mem(sym("qt_idle"), 3).reduce((v, b, i) => v + (b << (8 * i)), 0);
        const phase = mem(sym("qt_phase"))[0], status = mem(sym("qt_ok"))[0];
        const got = Buffer.from(mem(QT_BUF, pages * 256));
        const want = image[side][track].subarray(first * 256, (first + pages) * 256);
        let bad = 0;
        for (let i = 0; i < got.length; i++) if (got[i] !== want[i]) bad++;
        const sent = mem(QT_BUF + pages * 256)[0];
        res.reads++;
        if (bad) { res.badBytes += bad; res.badReads.push({ side, track, first, pages, bad }); }
        if (sent !== SENT) res.sentinelMoved++;
        if (status & 0x1C) res.statusErrors++;
        const elapsed = now - tRead;
        readCycles.push(elapsed);
        nmiPerByte.push((elapsed - 17 * idle) / (pages * 256));
        if (phase === 1) res.run = { side, track, first, pages, bad, sentinel: sent === SENT, cycles: elapsed };
        continue;
    }
    if (what === "qt_loaded") {
        const lid = mem(sym("qt_lid"))[0];
        const kind = mem(sym("loads_kind") + lid)[0], spage = mem(sym("loads_pages") + lid)[0];
        const nameAt = mem(sym("loads_lo") + lid)[0] | (mem(sym("loads_hi") + lid)[0] << 8);
        const name = String.fromCharCode(...mem(nameAt, 8)).split("\r")[0];
        const f = cat[name];
        let want;
        if (kind === 0) want = f.data;                     // the file (its last sector's tail is the disc's)
        else want = sectorBytes(f.start + mem(sym("qd_poff"))[0], mem(sym("qd_plen"))[0]);
        const got = Buffer.from(mem(QT_BUF, want.length));
        let bad = 0;
        for (let i = 0; i < want.length; i++) if (got[i] !== want[i]) bad++;
        const zx = mem(sym("zxsrc"), 2);
        const r = { name, kind: kind ? "part" : "stream", bytes: want.length, catIndex: f.k, bad,
                    qd_err: mem(sym("qd_err"))[0] };
        if (spage) r.sentinel = mem(QT_BUF + spage * 256)[0] === SENT;
        if (kind === 0) r.zxsrc = zx[0] === 0 && zx[1] === (QT_BUF >> 8);
        r.ok = bad === 0 && r.qd_err === 0 && r.sentinel !== false && r.zxsrc !== false;
        res.loads.push(r);
    }
}
const stat = (a) => a.length ? { min: Math.min(...a), median: a.slice().sort((x, y) => x - y)[a.length >> 1],
                                 max: Math.max(...a) } : null;
res.wholeTrackReadCycles = stat(readCycles.slice(0, -1));
res.seekOneTrackCycles = stat(seekCycles.slice(1, 159));
res.nmiCyclesPerByte = stat(nmiPerByte.map((v) => Math.round(v * 10) / 10));
res.reached = [...reached];
const firstEntry = nfiles - 1, lastEntry = 0;
res.pass = !res.error && reached.has("qt_end") && res.missing === 1 && res.tableBad === 0 &&
    res.table.some((e) => e.catIndex === firstEntry) && res.table.some((e) => e.catIndex === lastEntry) &&
    res.reads === 160 + 1 && res.badBytes === 0 && res.sentinelMoved === 0 && res.statusErrors === 0 &&
    !!res.run && res.run.bad === 0 && res.loads.length === sym("NLOADS") && res.loads.every((l) => l.ok);
res.badReads = res.badReads.slice(0, 5);
console.log(JSON.stringify(res, null, 1));
process.exit(res.pass ? 0 : 1);
