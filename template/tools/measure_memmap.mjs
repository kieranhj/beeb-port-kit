// measure_memmap.mjs - a memory map's claims, measured: what the video fetches, and what is where.
//
// beeb-port-kit template, MIT, Kieran Connell 2026. From the phX port, 2026-11 (its
// docs/memory-map.md was written from this tool's figures, not from the source's EQUs).
//
//   node tools/measure_memmap.mjs DISC --screen=RANGES [--bytes=FILE@ADDR[:WHERE],...]
//        [--latch] [--field=field_count] [--settle=20] [--model=B-DFS1.2|Master]
//
//   RANGES  FROM..TO,... (TO exclusive), each a symbol (with +N), &hex or 0xhex: the bytes the
//           screen is said to occupy. The template: --screen=PANEL_ADDR..PANEL_ADDR+&A00,&5800..&8000
//   WHERE   main, shadow, or a sideways bank number (default main)
//
// 1. THE BOOT: fields from SHIFT+BREAK until the field counter has moved three fields running.
// 2. THE SCREEN: every address the video fetches (cpu.videoRead) in one field while every display
//    enable is on must be EXACTLY the RANGES - no byte outside, none inside unread. jsbeeb also
//    fetches through the blanking: that span is reported beside it, not judged. Run after the
//    settle, on whatever the build displays then (a scrolling screen is measured where it is).
// 3. --latch: the same field under each of the four screen-size settings of the addressable
//    latch (C0/C1 = latch lines 4 and 5: 20K, 16K, 10K, 8K - what jsbeeb subtracts when MA
//    wraps past &8000), the build's own setting put back after. Reported: whether each set is
//    the same as the build's. A frame that never wraps reads the same under all four, and that
//    is a FACT to measure, not to assume (phX: its 20K screen at MA &300 never wrapped). It is
//    judged only with --latch=invariant (every setting the same set).
// 4. --bytes: each FILE's bytes (a host file - the build's own data) equal memory at ADDR.
// samples = the fields measured; exit 0 only if 2, 4 and (with =invariant) 3 hold.
import { readFileSync } from "node:fs";

import { cli, num, open } from "./harness.mjs";

const { pos, opt } = cli();
const disc = pos[0];
if (!disc || !opt.screen) { console.error("usage: node tools/measure_memmap.mjs DISC --screen=FROM..TO,... [--bytes=FILE@ADDR[:WHERE]] [--latch[=invariant]]"); process.exit(2); }
const h = await open({ name: "measure_memmap", disc });
h.model = opt.model || (h.define("MASTER") ? "Master" : h.model);
const FIELD = h.zp(opt.field || "field_count");
const ranges = String(opt.screen).split(",").map((r) => {
    const [a, b] = r.split("..");
    if (b === undefined) h.die(`--screen: ${r} is not FROM..TO`);
    return [h.addr(a), h.addr(b)];
});
const hex = (x) => "&" + x.toString(16).toUpperCase().padStart(4, "0");

// 1. the boot, field by field
await h.boot({ settle: 0 });
let bootFields = 0;
{
    const f0 = h.byte(FIELD, "main");
    let moved = 0;
    for (let i = 0; i < 3000 && moved < 3; i++) {
        const before = h.byte(FIELD, "main");
        await h.s.runFrames(1);
        bootFields++;
        if (h.byte(FIELD, "main") !== before) moved++;
        else moved = 0;
    }
    if (h.byte(FIELD, "main") === f0) h.die("the field counter never moved: the engine never started");
    bootFields -= 3;
}
await h.s.runFrames(num(opt.settle, 20));

const v = h.cpu.video;
let rec = null;
const orig = h.cpu.videoRead.bind(h.cpu);
h.cpu.videoRead = (a) => {
    if (rec) { rec.all.add(a); if ((v.dispEnabled & 63) === 63) { rec.addrs.add(a); rec.n++; } }
    return orig(a);
};
const field = async () => {
    rec = { addrs: new Set(), all: new Set(), n: 0 };
    await h.s.runFrames(1);
    const r = rec; rec = null;
    const a = [...r.addrs].sort((x, y) => x - y), all = [...r.all];
    return { n: r.n, set: a, key: a.join(","), allLo: Math.min(...all), allHi: Math.max(...all) };
};
const want = new Set();
for (const [a, b] of ranges) for (let x = a; x < b; x++) want.add(x);
const spans = (xs) => {          // a sorted list as FROM-TO runs, for a message
    const r = [];
    for (const x of xs) { const l = r[r.length - 1]; if (l && l[1] === x - 1) l[1] = x; else r.push([x, x]); }
    return r.slice(0, 12).map(([a, b]) => (a === b ? hex(a) : `${hex(a)}-${hex(b)}`)).join(",") + (r.length > 12 ? ` (+${r.length - 12} runs)` : "");
};
const judge = (r) => {
    const outside = r.set.filter((x) => !want.has(x));
    const got = new Set(r.set), unread = [...want].filter((x) => !got.has(x));
    return { fetches: r.n, distinct: r.set.length, outside: outside.length, unread: unread.length,
             outsideAt: outside.length ? spans(outside) : undefined, unreadAt: unread.length ? spans(unread) : undefined,
             withBlanking: [hex(r.allLo), hex(r.allHi)] };
};
const base = await field();
const screen = judge(base);
let ok = screen.outside === 0 && screen.unread === 0;
let samples = 1;

// 3. the latch
let latch = null;
if (opt.latch) {
    const via = h.cpu.sysvia;
    const orb = (line, val) => h.wr(0xfe40, [line | (val << 3)]);
    const now = [4, 5].map((line) => (via.IC32 >> line) & 1);   // the build's C0, C1 (jsbeeb keeps the latch in IC32)
    latch = [];
    for (const [c0, c1, name] of [[0, 0, "20K"], [0, 1, "16K"], [1, 0, "10K"], [1, 1, "8K"]]) {
        orb(4, c0); orb(5, c1);
        await h.s.runFrames(1);
        const r = await field();
        samples++;
        latch.push({ size: name, sameAsBuild: r.key === base.key, distinct: r.set.length });
    }
    orb(4, now[0]); orb(5, now[1]);
    if (opt.latch === "invariant" && !latch.every((l) => l.sameAsBuild)) ok = false;
}

// 4. bytes where they are said to be
const bytes = [];
for (const spec of opt.bytes ? String(opt.bytes).split(",") : []) {
    const m = /^(.+)@([^:]+)(?::(.+))?$/.exec(spec);
    if (!m) h.die(`--bytes: ${spec} is not FILE@ADDR[:WHERE]`);
    const data = readFileSync(m[1]), addr = h.addr(m[2]);
    const where = m[3] === undefined ? "main" : /^\d+$/.test(m[3]) ? +m[3] : m[3];
    const mem = h.rd(addr, data.length, addr >= 0x3000 ? where : undefined);
    let diff = 0, first = -1;
    for (let i = 0; i < data.length; i++) if (mem[i] !== data[i]) { diff++; if (first < 0) first = i; }
    bytes.push({ file: m[1], at: hex(addr), where, bytes: data.length, different: diff, ...(diff ? { firstAt: `+${first}` } : {}) });
    if (diff) ok = false;
}
h.finish({ bootFields, screen: { claimed: ranges.map(([a, b]) => `${hex(a)}-${hex(b - 1)}`), ...screen }, latch, bytes }, ok, { samples });
