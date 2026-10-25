// pairlock.mjs - two builds played the same game, pass by pass, their game state
// compared at the start of every pass: the A/B pair harness.
//
// beeb-port-kit template, MIT, Kieran Connell 2026. From Stryker's Run's
// tools/passlock.mjs (2026-10-14 to 10-25), its gate for every change to how the
// game DRAWS that must leave what it PLAYS alone: a renderer against its
// draw-everything oracle build, an optimised build against its control, a
// relocated build against its padded twin. Generalised: the game is a config
// (passplay.mjs says what it holds; examples/pairlock/ has two).
//
//   node tools/pairlock.mjs CONFIG CONTROL.ssd TEST.ssd [--passes N] [--seed S]
//        [--screen] [--poke P:ADDR=B,B[:WHERE]]... [--poke-both P:ADDR=...]...
//
// Both builds boot, play the config's start script to their first pass, and from
// there each is stopped at the start of every pass, the two compared, and given
// that pass's keys (passplay.mjs's generator from SEED, default 1; N passes,
// default 2000):
//   state   every range the config lists, and what its stateFn returns
//   screen  (--screen) the screen each build is SHOWING (shadow or main, by the
//           config's shown(), by default ACCCON's D bit on a Master), over the
//           bytes its visible() admits
// --poke writes bytes into the TEST machine at the start of pass P (hex bytes),
// --poke-both into both: a test's way to force a path, and the way to show the
// oracle FAILS - poke a byte the game reads and the first differing pass is named.
//
// THE VERDICT, harness.mjs's contract:
//   exit 0  N passes compared (or both builds stopped making passes at the same
//           pass, which ends the run: compared up to the one before), every one
//           identical, and the state moved (passesStateMoved: the passes whose
//           state differed from the pass before's). samples = the passes compared
//   exit 1  a pass differs - `firstDifference` names it, `what` the range, `bytes`
//           the first offsets (control vs test) - or only one build stopped
//           making passes, or no pass was compared, or the state never moved
//   exit 2  could not judge: a usage error, a name not in a dump, no game started
//
// Measure, do not assume, that the pair is deterministic: run a build against
// ITSELF first (exit 0), and a poked one (exit 1, at the pass you poked or after).
import { loadConfig, parsePoke, scriptKeys, startPlay } from "./passplay.mjs";

const args = process.argv.slice(2);
const take = (flag) => { const out = []; for (let i; (i = args.indexOf(flag)) >= 0; ) out.push(args.splice(i, 2)[1]); return out; };
const opt = (flag, d) => { const v = take(flag); return v.length ? v[v.length - 1] : d; };
const has = (flag) => { const i = args.indexOf(flag); if (i < 0) return false; args.splice(i, 1); return true; };
const PASSES = parseInt(opt("--passes", "2000"), 10), SEED = parseInt(opt("--seed", "1"), 10);
const SCREEN = has("--screen");
let pokes, pokesBoth;
try { pokes = take("--poke").map(parsePoke); pokesBoth = take("--poke-both").map(parsePoke); }
catch (e) { console.error(`pairlock: ${e.message}`); process.exit(2); }
const [cfgPath, discA, discB] = args;
if (!discB || args.length > 3) {
    console.error("usage: node tools/pairlock.mjs CONFIG CONTROL.ssd TEST.ssd [--passes N] [--seed S] [--screen] [--poke P:ADDR=B,B[:WHERE]]... [--poke-both ...]");
    process.exit(2);
}
let cfg;
try { cfg = await loadConfig(cfgPath); } catch (e) { console.error(`pairlock: ${e.message}`); process.exit(2); }
if (SCREEN && !cfg.screen) { console.error("pairlock: --screen, and the config has no `screen`"); process.exit(2); }

const A = await startPlay(cfg, discA, { name: "pairlock", pokes: pokesBoth });
const B = await startPlay(cfg, discB, { name: "pairlock", pokes: [...pokesBoth, ...pokes] });
const keysAt = scriptKeys(cfg, PASSES + 2, SEED);
const base = { control: discA, test: discB, config: cfgPath, seed: SEED, startFrames: [A.play.startFrame, B.play.startFrame] };
if (pokes.length || pokesBoth.length) base.pokes = { test: pokes.map((p) => `${p.pass}:${p.at}`), both: pokesBoth.map((p) => `${p.pass}:${p.at}`) };

let compared = 0, stalledAt = null, screenPasses = 0, moved = 0, last = null;
const fail = (why) => A.finish({ ...base, passesCompared: compared, ...why }, false, { samples: compared });
for (let p = 1; p <= PASSES; p++) {
    const okA = await A.play.toPass(p), okB = await B.play.toPass(p);
    if (!okA || !okB) {
        if (okA !== okB) fail({ firstDifference: p, what: okA ? "test made no pass" : "control made no pass", hang: (okA ? B : A).hang() });
        console.error(`pairlock: pass ${p}: both stopped making passes: compared to pass ${p - 1}`);
        stalledAt = p; break;
    }
    const sa = A.play.state(), sb = B.play.state();
    const now = JSON.stringify(sa);
    if (last !== null && now !== last) moved++;
    last = now;
    for (const k of Object.keys(sa)) {
        if (JSON.stringify(sa[k]) === JSON.stringify(sb[k])) continue;
        const bytes = [];
        sa[k].forEach((v, i) => { if (v !== sb[k]?.[i]) bytes.push(`+${i}: ${v.toString(16)} vs ${sb[k]?.[i]?.toString(16)}`); });
        fail({ firstDifference: p, what: k, bytes: bytes.slice(0, 12), differing: bytes.length });
    }
    if (SCREEN) {
        const a = A.play.shown(), b = B.play.shown();
        const vis = a.visible;
        let d = 0, first = -1;
        for (let i = 0; i < a.bytes.length; i++) if (a.bytes[i] !== b.bytes[i] && (!vis || vis(i))) { d++; if (first < 0) first = i; }
        screenPasses++;
        if (d) fail({ firstDifference: p, what: "screen", screenBytesDiffering: d, firstOffset: first,
                      shown: [a.where, b.where] });
    }
    const want = keysAt[p] || [];
    A.play.setKeys(want); B.play.setKeys(want);
    compared++;
    if (p % 500 === 0) console.error(`pairlock: pass ${p}: identical`);
}
// a game whose state never moved was not played: the keys reached nothing, or the
// config compares bytes nothing writes - a pass over nothing is not a pass
if (!moved) console.error("pairlock: THE STATE NEVER CHANGED from one pass to the next - nothing was played");
A.finish({ ...base, passes: stalledAt ? stalledAt - 1 : PASSES, passesCompared: compared, passesStateMoved: moved, stalledAt,
           identical: true, ...(SCREEN ? { screenPassesIdentical: screenPasses } : {}) },
         moved > 0, { samples: compared });
