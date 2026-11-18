// verify_break.mjs - SHIFT+BREAK mid-run reboots the disc and plays like a cold boot.
//
// beeb-port-kit template, MIT, Kieran Connell 2026. From the phX port, 2026-11 (its step B7,
// KC's decision that a SHIFT+BREAK anywhere in the demo must restart it as from power-on), with
// its parts and music row made options.
//
//   node tools/verify_break.mjs DISC [B,B,...=300,900,2000] [--record=600] [--field=field_count]
//        [--key=SYM[:w|:sw]] [--track=SYM,SYM...] [--reach=60] [--late=SYM] [--stuck=N]
//        [--model=B-DFS1.2|Master]
//
// A cold boot's first RECORD fields are recorded; then for each break point B (fields after the
// boot) a FRESH machine runs to B, takes SHIFT+BREAK (a SOFT reset with SHIFT held - jsbeeb's
// autoboot, which waits for the MOS to ask the filing system to boot and the drive to start)
// and its first RECORD fields after it are recorded the same way. Each break must:
//   - reboot: the MOS asks for the boot and drive 0 starts (autoboot throws otherwise), and the
//     field counter (--field) moves after it
//   - play like the cold boot, from the first field its counter moves (before that the
//     values are whatever RAM held: zeros cold, the last run's after a BREAK). With --key (the run's clock: phX's music row, a signed word),
//     the --track symbols' values at each key value must agree with the cold boot's wherever
//     both reach it, and the warm run must reach as far as the cold one less --reach (its
//     boot can take longer: the head is wherever the break left it). Without --key, the set
//     of --track tuples seen must be the cold boot's set
//   - --late: a symbol that counts overruns must be 0 at the end; --stuck: no stretch of more
//     than N fields with the field counter still (default: reported, not judged)
// PRESS_WHEN (harness.mjs) is honoured after every BREAK too (beforeBreak/afterBreak): phX's
// disclaimer waited for SPACE on every boot. A plain BREAK is verify_break_plain.mjs.
import { cli, num, open, parseCond } from "./harness.mjs";

const { pos, opt } = cli();
const disc = pos[0];
if (!disc) { console.error("usage: node tools/verify_break.mjs DISC [B,B,...] [--key=SYM] [--track=SYM,...] ..."); process.exit(2); }
const points = (pos[1] || "300,900,2000").split(",").map(Number);
const M = num(opt.record, 600), REACH = num(opt.reach, 60);
const KEY = opt.key ? parseCond(`${opt.key}==0`) : null;      // its name and size; the op is unused
const TRACK = opt.track ? String(opt.track).split(",") : [];

let last;
const run = async (B) => {
    const h = last = await open({ name: "verify_break", disc });
    h.model = opt.model || (h.define("MASTER") ? "Master" : h.model);
    const FC = h.zp(opt.field || "field_count");
    const LATE = opt.late ? h.need(opt.late) : null;
    const tr = TRACK.map((n) => h.need(n));
    const kA = KEY ? h.need(KEY.sym) : null;
    const ram = (a) => (a >= 0x3000 && a < 0x8000 ? "main" : undefined);
    const keyNow = () => {
        if (kA === null) return null;
        const v = KEY.size === "b" ? h.byte(kA, ram(kA)) : h.word(kA, ram(kA));
        return KEY.size === "sw" && v >= 0x8000 ? v - 0x10000 : v;
    };
    await h.boot({ settle: 0, shiftFrames: 50 });
    let at = null, boot = null;
    if (B !== null) {
        await h.s.runFrames(B);
        at = { field: B, key: keyNow(), track: tr.map((a) => h.byte(a, ram(a))) };
        h.beforeBreak();
        try { boot = await h.s.autoboot({ hard: false }); await h.afterBreak(); }
        catch (e) { boot = { error: String(e).slice(0, 200) }; }
    }
    const rec = [];
    let fcLast = -1, stuck = 0, maxStuck = 0, moved = false;
    for (let f = 0; f < M; f++) {
        await h.s.runFrames(1);
        const fc = h.byte(FC, "main");
        if (fc === fcLast) { stuck++; maxStuck = Math.max(maxStuck, stuck); } else { if (fcLast >= 0) moved = true; stuck = 0; }
        fcLast = fc;
        if (moved) rec.push([keyNow(), tr.map((a) => h.byte(a, ram(a))).join(",")]);   // the engine's, not RAM's
    }
    if (!rec.length) rec.push([null, "never ran"]);
    return { at, boot, rec, moved, maxStuck, late: LATE === null ? null : h.byte(LATE, ram(LATE)) };
};

const byKey = (rec) => { const m = new Map(); for (const [k, t] of rec) if (!m.has(k)) m.set(k, t); return m; };
const lastKey = (rec) => rec[rec.length - 1][0];
const cold = await run(null);
if (!cold.moved) last.die("the cold boot's field counter never moved: wrong --field, or the disc did not boot");
const cm = byKey(cold.rec), cset = new Set(cold.rec.map(([, t]) => t));
const breaks = [];
let ok = true;
for (const B of points) {
    const w = await run(B);
    let diff = 0, first = null;
    if (KEY) {
        const wm = byKey(w.rec);
        for (const [k, t] of cm) if (wm.has(k) && wm.get(k) !== t) { diff++; first ??= { key: k, cold: t, warm: wm.get(k) }; }
    } else {
        const wset = new Set(w.rec.map(([, t]) => t));
        for (const t of new Set([...cset, ...wset])) if (cset.has(t) !== wset.has(t)) { diff++; first ??= { tuple: t, cold: cset.has(t), warm: wset.has(t) }; }
    }
    const reach = KEY ? lastKey(w.rec) >= lastKey(cold.rec) - REACH : true;
    const good = !w.boot?.error && w.moved && diff === 0 && reach && (w.late === null || w.late === 0) &&
        (opt.stuck === undefined || w.maxStuck <= num(opt.stuck));
    if (!good) ok = false;
    breaks.push({ field: B, at: w.at, boot: w.boot, lastKey: KEY ? lastKey(w.rec) : undefined, reach, diff, first,
                  late: w.late, maxStuck: w.maxStuck, ok: good });
}
last.finish({ key: opt.key || null, track: TRACK, record: M,
              cold: { lastKey: KEY ? lastKey(cold.rec) : undefined, states: cset.size, late: cold.late, maxStuck: cold.maxStuck },
              breaks }, ok, { samples: breaks.length });
