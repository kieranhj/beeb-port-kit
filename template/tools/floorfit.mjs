// floorfit.mjs - a cost model that survives the ticks that are not about the thing
// being costed: FIT THE FLOOR, READ THE SLOPE.
//
// beeb-port-kit template, MIT, Kieran Connell 2026. From 1942's
// tools/measure_budget.mjs (2026-09-15), which answered "how many objects fit a
// 25 Hz tick" - 7,257 fixed cycles + 5,218 a blit, so 13 objects in 79,872 cycles.
//
// Per-tick work swings by orders of magnitude for reasons unrelated to what you are
// costing: 1942's stage seam was a 663,371-cycle tick, a death's ring refill
// ~660,000, the caption's text tens of thousands. A least-squares fit over every tick
// regressed to a NEGATIVE cost a blit. The MINIMUM work at each x is the clean tick -
// the fixed work plus that many items - so fit a line through the minima, taking only
// x values with enough samples (>= 5) that the minimum is a floor and not one tick.
//
// Read `slope` (cycles an item), not the peak: the peak is whichever tick was busiest
// in that run, and it moves between two builds that cost the same. 1942's decision 103
// moved the peak 978 cycles and the slope 7. And measure the before and after as a
// PAIR - same day, same jsbeeb, same run length - or the difference is the emulator's
// (jsbeeb 2.3.0 against 1.25.0 changed three of nine harnesses' figures).
//
//   import { floorFit } from "./floorfit.mjs";
//   const f = floorFit(rows, { x: "blits", y: "work", budget: 79872 });
//   // f.fixed, f.slope, f.fit (items that fit the budget), f.table, f.points
//
//   node tools/floorfit.mjs ROWS.json [X Y [BUDGET]]    rows: [{x:.., y:..}, ...]
//   node tools/floorfit.mjs --selftest                   the mean fit failing beside it
//
// The labels matter as much as the numbers: a figure from this is MEASURED; one added
// up off the listing is COUNTED, and 1942's counted figures were wrong by a fifth, once
// by 2.5x, and once in sign (decision 103: -13 a blit counted, +7 measured).
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

/** Least squares through the minimum `y` at each `x` with >= minSamples rows. */
export function floorFit(rows, { x = "x", y = "y", minSamples = 5, budget } = {}) {
    const by = new Map();
    for (const r of rows) {
        const k = r[x], v = r[y];
        if (!Number.isFinite(k) || !Number.isFinite(v)) continue;
        if (!by.has(k)) by.set(k, []);
        by.get(k).push(v);
    }
    const points = [...by].filter(([, v]) => v.length >= minSamples).sort((a, b) => a[0] - b[0])
        .map(([k, v]) => ({ x: k, floor: Math.min(...v), samples: v.length }));
    const n = points.length;
    if (n < 2) {
        return { error: `${n} x value(s) with >= ${minSamples} samples: a line needs two - run longer, ` +
                        "or drive the load through more values", points };
    }
    const sx = points.reduce((a, p) => a + p.x, 0), sy = points.reduce((a, p) => a + p.floor, 0);
    const sxx = points.reduce((a, p) => a + p.x * p.x, 0), sxy = points.reduce((a, p) => a + p.x * p.floor, 0);
    const slope = (n * sxy - sx * sy) / (n * sxx - sx * sx);
    const fixed = (sy - slope * sx) / n;
    const resid = Math.max(...points.map((p) => Math.abs(p.floor - (fixed + slope * p.x))));
    const ys = rows.map((r) => r[y]).filter(Number.isFinite).sort((a, b) => a - b);
    return {
        fixed: Math.round(fixed), slope: Math.round(slope), maxResidual: Math.round(resid),
        fit: budget && slope > 0 ? Math.floor((budget - fixed) / slope) : undefined,
        over: budget ? ys.filter((v) => v > budget).length : undefined,
        rows: ys.length, peak: ys[ys.length - 1],
        points,
        table: points.map((p) => `${p.x}: ${p.floor} (${p.samples} samples)`),
    };
}

/** The mean fit, for showing why not. */
export function meanFit(rows, { x = "x", y = "y" } = {}) {
    const r = rows.filter((o) => Number.isFinite(o[x]) && Number.isFinite(o[y]));
    const n = r.length, sx = r.reduce((a, o) => a + o[x], 0), sy = r.reduce((a, o) => a + o[y], 0);
    const sxx = r.reduce((a, o) => a + o[x] * o[x], 0), sxy = r.reduce((a, o) => a + o[x] * o[y], 0);
    const slope = (n * sxy - sx * sy) / (n * sxx - sx * sx);
    return { fixed: Math.round((sy - slope * sx) / n), slope: Math.round(slope) };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
    const [a, xk = "x", yk = "y", budget] = process.argv.slice(2);
    if (!a) {
        console.error("usage: node tools/floorfit.mjs ROWS.json [X Y [BUDGET]] | --selftest");
        process.exit(2);
    }
    if (a === "--selftest") {
        // 1942's shape: 7,257 + 5,218 a blit, a little jitter, and the heavy ticks -
        // the seams and refills - landing on the LOW blit counts, where they did.
        const rows = [];
        let seed = 1;
        const rnd = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff;
        for (let i = 0; i < 1200; i++) {
            const blits = 2 + Math.floor(rnd() * 12);
            let work = 7257 + 5218 * blits + Math.floor(rnd() * 3000);
            if (blits <= 4 && rnd() < 0.08) work += 600000;       // a seam or a refill
            rows.push({ x: blits, y: work });
        }
        const f = floorFit(rows, { budget: 79872 }), m = meanFit(rows);
        const ok = Math.abs(f.slope - 5218) < 300 && Math.abs(f.fixed - 7257) < 1500 && m.slope < f.slope / 2;
        console.log(JSON.stringify({ floor: { fixed: f.fixed, slope: f.slope, fit: f.fit },
                                     mean: m, truth: { fixed: 7257, slope: 5218 }, pass: ok }));
        process.exit(ok ? 0 : 1);
    }
    const rows = JSON.parse(readFileSync(a, "utf8"));
    const f = floorFit(rows, { x: xk, y: yk, budget: budget ? Number(budget) : undefined });
    console.log(JSON.stringify(f, null, 1));
    process.exit(f.error ? 1 : 0);
}
