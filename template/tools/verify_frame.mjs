// verify_frame.mjs - a frame engine's contract, measured in jsbeeb.
//
// beeb-port-kit template, MIT, Kieran Connell 2026. From the phX port, 2026-11 (its
// tools/verify_frame.mjs: a demo whose every part enters its draw from one stable-raster IRQ),
// with phX's parts, rows and load windows moved out into an optional hooks module.
//
//   node tools/verify_frame.mjs DISC [FIELDS=300] [--entry=draw_entry] [--field=field_count]
//        [--settle=150 | --from-first] [--field-cycles=39936] [--jitter=0] [--nmi=&0D00]
//        [--disc=none|any] [--disc-late=480] [--hooks=FILE.mjs] [--model=B-DFS1.2|Master]
//
// At every execution of the ENTRY label (where a field's draw starts: the visible IRQ after a
// stable-raster slide, or the VSync handler) it records the CRTC's own counters (C4 row, C9
// scanline, C0 character, in the adjust or not), the CPU's cycle count, jsbeeb's frame count and
// the NMIs since the last entry. THE CONTRACT, every part of which must hold:
//   1. ONE BEAM POSITION: draw is entered at the same raster line every field (with --jitter=0
//      at the same character too; a handler entered through the MOS's IRQ path has a few
//      cycles of latency jitter: --jitter=N allows the character to spread N)
//   2. THE CADENCE: entries are FIELD-CYCLES apart (312 lines x 128 = 39,936), each quiet
//      field within +-jitter of t0 + i * FIELD-CYCLES - a lost or doubled field shows here
//   3. ONE VSYNC A FIELD: the System VIA's CA1 level from the 6845 rises once a field,
//      FIELD-CYCLES (+-8: jsbeeb clocks its video behind the CPU, MEASURED +-4) after the
//      last, on one line before draw entry
//   4. JSBEEB'S FRAME COUNT +1 A FIELD: video.frameCount moves only when C4 = R6, and the
//      web display decays its phosphor by it - a frame that never reaches R6 stands it still
//      and the browser's picture goes white (phX docs/layer-3-6845.md); exactly one a field
//   5. DISC FIELDS JUDGED APART: a 1770 byte is an NMI (at --nmi, the DFS's &0D00), which can
//      delay the visible IRQ past a stable-raster slide; a field with NMIs before its entry
//      enters late by 0..DISC-LATE cycles (every other field exactly on the cadence) and must
//      be a field where the design allows the disc: --disc=none (the default: there must be
//      none after the boot), --disc=any, or the hooks' discAllowed()
// Without hooks every field is one phase. FIELDS is how many entries to judge after the boot;
// PRESS_WHEN, RUN_UNTIL and JUNK (harness.mjs) apply. --from-first: boot with no settle and
// start at the first field the field counter moves (a sequence, judged from its first field).
//
// THE HOOKS (--hooks=FILE.mjs, every export optional) - a demo's sequence, a game's states:
//   setup(h, opt)              after open(), before the boot: read the build's symbols
//   tag(h)                     at each entry: an object merged into the sample ({part, row})
//   key(s)                     the sample's phase name: steady positions are judged per phase
//   steady(key)                how many steady positions that phase may have (default 1; phX's
//                              Balls cycled 4 CRTC frames a field: 4)
//   firstOk(prev, cur, pos)    a phase's first field must enter where the field before left
//                              (its frame is the last phase's); return true to exempt one
//                              (phX: a part whose last field made the plain frame)
//   discAllowed(s)             may this field have NMIs (phX: the card, black, its load windows)
//   report(samples)            extra figures for the JSON line
// template/examples/verify_frame_hooks.mjs is a worked example. A phase change with hooks also
// checks 1 per phase rather than once.
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { cli, num, open } from "./harness.mjs";

const { pos: args, opt } = cli();
const disc = args[0];
if (!disc) { console.error("usage: node tools/verify_frame.mjs DISC [FIELDS] [--entry=LABEL] [--jitter=N] [--hooks=FILE.mjs] ..."); process.exit(2); }
const N = num(args[1], 300);
const FC = num(opt["field-cycles"], 39936), JIT = num(opt.jitter, 0), NMI = num(opt.nmi, 0x0d00);
const DISC_LATE = num(opt["disc-late"], 480);  // phX: the most a disc field's entry may be late (cycles), 416 measured
const VS_SLACK = 8 + JIT;
const hooks = opt.hooks ? await import(pathToFileURL(resolve(opt.hooks)).href) : {};
const h = await open({ name: "verify_frame", disc });
h.model = opt.model || (h.define("MASTER") ? "Master" : h.model);
const FIELD = h.zp(opt.field || "field_count");
const ENTRY = h.need(opt.entry || "draw_entry");
if (hooks.setup) await hooks.setup(h, opt);

if (opt["from-first"]) {
    await h.boot({ settle: 0 });
    const f0 = h.byte(FIELD, "main");
    for (let i = 0; i < 2000 && h.byte(FIELD, "main") === f0; i++) await h.s.runFrames(1);
    if (h.byte(FIELD, "main") === f0) h.die("the field counter never moved: the engine never started");
} else await h.boot({ field: FIELD, settle: num(opt.settle, 150) });

const cycles = () => h.cpu.currentCycles + h.cpu.cycleSeconds * 2000000;
const samples = [];
let lastVs = null, nmis = 0;
h.onExec(NMI, () => { nmis++; return false; }, { anyBank: true });
const vsTimes = [];
const via = h.cpu.video.sysvia;
const setVB = via.setVBlankInt.bind(via);
let vsLevel = false;
via.setVBlankInt = (level) => {
    if (level && !vsLevel) { const t = cycles(); vsTimes.push(t); lastVs = t; }
    vsLevel = !!level;
    return setVB(level);
};
h.onExec(ENTRY, () => {
    if (samples.length > N) return false;
    const s = { ...h.crtc(), t: cycles(), fc: h.cpu.video.frameCount, vs: lastVs, nmi: nmis };
    nmis = 0;
    if (hooks.tag) Object.assign(s, hooks.tag(h));
    samples.push(s);
    return false;
}, h.gateOf(opt.entry || "draw_entry"));
// N entries are N fields; a few more in case the boot left the engine mid-field
for (let i = 0; i < N + 50 && samples.length <= N; i++) await h.s.runFrames(1);
if (samples.length < 2) h.die(`${samples.length} entries at ${opt.entry || "draw_entry"} in ${N + 50} fields: is that the draw's entry?`, { where: h.where() });
samples.length = Math.min(samples.length, N + 1);

const tally = (xs) => { const o = {}; for (const x of xs) o[x] = (o[x] || 0) + 1; return o; };
const line = (s) => `${s.vc}:${s.sc}${s.adj ? "a" : ""}`;
const pos = (s) => (JIT ? line(s) : `${line(s)}:${s.hc}`);
const isDisc = (s) => s.nmi > 0;
const key = hooks.key || (() => "all");
const wrong = [];

// 2. the cadence
const t0 = samples[0].t;
const lateOf = samples.map((s, i) => s.t - (t0 + i * FC));
const offCadence = samples.filter((s, i) => !isDisc(s) && Math.abs(lateOf[i]) > JIT).length;
const discLate = samples.map((s, i) => [s, lateOf[i]]).filter(([s]) => isDisc(s)).map(([, l]) => l);
const discBadLate = discLate.filter((l) => l < -JIT || l > DISC_LATE + JIT).length;
const gaps = tally(samples.slice(1).map((s, i) => [s, samples[i]]).filter(([a, b]) => !isDisc(a) && !isDisc(b)).map(([a, b]) => a.t - b.t));
if (offCadence || discBadLate)
    wrong.push(`the cadence: ${offCadence} quiet fields off t0 + i x ${FC} by more than ${JIT}, ${discBadLate} disc fields beyond 0..${DISC_LATE}`);

// 4. jsbeeb's frame count
const fcSteps = tally(samples.slice(1).map((s, i) => s.fc - samples[i].fc));
if (!(Object.keys(fcSteps).length === 1 && fcSteps[1] > 0)) wrong.push(`jsbeeb's frame count does not step by one a field: ${JSON.stringify(fcSteps)}`);

// 3. VSync: once a field, a field apart, on one line before draw entry (quiet fields)
const t1 = samples[samples.length - 1].t;
const vsRun = vsTimes.filter((t) => t > t0 && t <= t1);
const vsGapsRaw = vsRun.slice(1).map((t, i) => t - vsRun[i]);
const vsLead = tally(samples.filter((s) => !isDisc(s) && s.vs !== null && s.vs > t0).map((s) => Math.round((s.t - s.vs) / 128)));
if (!(vsGapsRaw.every((g) => Math.abs(g - FC) <= VS_SLACK) && Object.keys(vsLead).length === 1 && vsRun.length === samples.length - 1))
    wrong.push(`VSync is not once a field at one place (gaps ${JSON.stringify(tally(vsGapsRaw))}, lines before draw ${JSON.stringify(vsLead)}, ${vsRun.length} in ${samples.length - 1} fields)`);

// 1. positions, per phase; a phase's first field where the last one left
const per = {};
let firstBad = null, nFirstBad = 0;
for (let i = 0; i < samples.length; i++) {
    const s = samples[i], k = key(s);
    const first = i > 0 && key(samples[i - 1]) !== k;
    const p = (per[k] ||= { steady: {}, first: {}, hc: {}, disc: 0, fields: 0 });
    p.fields++;
    if (isDisc(s)) { p.disc++; continue; }
    p[first ? "first" : "steady"][pos(s)] = (p[first ? "first" : "steady"][pos(s)] || 0) + 1;
    p.hc[s.hc] = (p.hc[s.hc] || 0) + 1;
    const prev = samples[i - 1];
    if (first && !isDisc(prev) && pos(s) !== pos(prev) && !(hooks.firstOk && hooks.firstOk(prev, s, pos(s)))) {
        nFirstBad++;
        firstBad ??= { i, phase: k, before: pos(prev), now: pos(s) };
    }
}
for (const [k, p] of Object.entries(per)) {
    const allowed = hooks.steady ? hooks.steady(k) : 1;
    if (Object.keys(p.steady).length > allowed) wrong.push(`${k}: draw entered at ${Object.keys(p.steady).length} steady positions (${allowed} allowed)`);
    const hcs = Object.keys(p.hc).map(Number);
    if (hcs.length && Math.max(...hcs) - Math.min(...hcs) > JIT) wrong.push(`${k}: the entry character spreads ${Math.min(...hcs)}..${Math.max(...hcs)}, more than --jitter=${JIT}`);
}
if (nFirstBad) wrong.push(`${nFirstBad} phases' first fields not at the position the field before left`);

// 5. the disc only where allowed
const discOk = hooks.discAllowed || (opt.disc === "any" ? () => true : () => false);
const discOut = samples.filter((s) => isDisc(s) && !discOk(s));
if (discOut.length) wrong.push(`${discOut.length} fields with NMIs where the disc is not allowed (first: ${JSON.stringify(discOut[0])})`);

for (const w of wrong) console.error(`verify_frame: ${w}`);
h.finish({ entry: opt.entry || "draw_entry", fieldCycles: gaps, jitter: JIT, frameCountSteps: fcSteps,
           vsyncGaps: tally(vsGapsRaw), vsyncLinesBeforeDraw: vsLead, byPhase: per,
           discFields: discLate.length ? { count: discLate.length, entryLateCycles: { min: Math.min(...discLate), max: Math.max(...discLate) } } : 0,
           firstBad, wrong, ...(hooks.report ? hooks.report(samples) : {}) },
         wrong.length === 0, { samples: samples.length });
