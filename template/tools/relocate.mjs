// relocate.mjs - what lockstep.mjs and tracediff.mjs share: how two builds of one
// source, one moved by whole pages, map onto each other.
//
// beeb-port-kit template, MIT, Kieran Connell 2026. Stryker's Run's tracediff.mjs
// (2026-10-03 on) mapped a shifted PC back by a SHIFT argument and a hand-written
// list of segments (its game moved down, each bank's contents up, its copy-down
// stub not at all). Here the map is read off the two symbol dumps: a PC is named by
// the labels at or below it (bank-aware, through the config's `banks`), and two PCs
// are the same instruction when a label sits the same distance below each in its
// build. Every label is a segment, so a build that pads one bank at the start and
// another at the end, or leaves its stub where it was, needs no configuration - and
// a label that did not move maps to itself.
import { pagedIn, regionOf } from "./harness.mjs";

/** Each section's move, control minus shifted, from the labels the two dumps share
 *  by name: {section: [deltas]}. Exits 2 (through a.die) if any is not whole pages
 *  - the cycle-for-cycle premise - unless anyShift, or if nothing moved. */
export function pageShifts(a, b, { anyShift = false } = {}) {
    const bn = new Map(b.labels.map((l) => [l.raw, l]));
    const out = {};
    let moved = 0;
    for (const l of a.labels) {
        const o = bn.get(l.raw);
        if (!o) continue;
        const d = l.value - o.value, sec = l.sections[0] || "(none)";
        out[sec] ||= [];
        if (!out[sec].includes(d)) out[sec].push(d);
        if (d) moved++;
    }
    const bad = Object.entries(out).filter(([, ds]) => ds.some((d) => d % 256));
    if (bad.length && !anyShift)
        a.die(`labels moved by other than whole pages, so page crossings moved and the builds cannot run cycle for cycle: ` +
              bad.map(([s, ds]) => `${s} ${ds.join(",")}`).join("; "));
    if (!moved) a.die("no label moved between the two builds: not a shifted pair");
    return out;
}

/** Do the control's PC `cpc` and the shifted build's `pc` name the same
 *  instruction? Every SECTION the control has running over cpc (its org and size
 *  from the dump, paged in by the `banks` map) is asked: its nearest label at or
 *  below cpc - or its org, if none - and that label's distance between the builds
 *  is a move the PCs may differ by. All of them are asked, not only the nearest
 *  label's, because main RAM is overlaid: Stryker's Run's loading picture's code
 *  sits under the game it loads, so the nearest label to a game PC can be the
 *  picture's, which did not move, and "the nearest label" alone mapped a correct
 *  game PC into the picture and called it a divergence; and its compiled sprites
 *  run 500 bytes past their last label. A PC no section covers (the MOS, the DFS,
 *  the stack page) matches only itself. Returns (cpc, pc, romsel, acccon) => bool. */
export function pcMatcher(control, shifted, { master = true } = {}) {
    const sv = new Map(shifted.labels.map((l) => [l.raw, l.value]));
    const sorg = new Map(shifted.extents.map((e) => [e.name, e.org]));
    const secs = control.extents.filter((e) => sorg.has(e.name)).map((e) => ({ ...e, delta: e.org - sorg.get(e.name), labels: [] }));
    const byName = new Map(secs.map((e) => [e.name, e]));
    for (const l of control.labels) {
        const e = byName.get(l.sections[0]);
        if (e && sv.has(l.raw)) e.labels.push({ value: l.value, delta: l.value - sv.get(l.raw) });
    }
    for (const e of secs) e.labels.sort((a, b) => a.value - b.value);
    const cache = new Map();
    const deltas = (cpc, romsel, acccon) => {
        const key = cpc | ((romsel & 0x8f) << 16) | ((acccon & 0x08) << 24);
        let d = cache.get(key);
        if (d) return d;
        d = new Set();
        for (const e of secs) {
            if (cpc < e.org || cpc >= e.org + e.size) continue;
            if (!pagedIn(cpc, regionOf(e.sections, control.banks), romsel, acccon, master)) continue;
            const list = e.labels;
            let lo = 0, hi = list.length - 1, top = -1;
            while (lo <= hi) { const mid = (lo + hi) >> 1; if (list[mid].value <= cpc) { top = mid; lo = mid + 1; } else hi = mid - 1; }
            d.add(top >= 0 ? list[top].delta : e.delta);
        }
        if (!d.size) d.add(0);
        cache.set(key, d);
        return d;
    };
    return (cpc, pc, romsel = 0, acccon = 0) => deltas(cpc, romsel, acccon).has(cpc - pc);
}
