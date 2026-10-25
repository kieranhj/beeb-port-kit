// passbench.mjs - a build's speed on the same game, whatever the build's speed.
//
// beeb-port-kit template, MIT, Kieran Connell 2026. From Stryker's Run's
// tools/passbench.mjs (2026-10-16 to 10-25), the measurement behind its grind's
// "no slower" and every layer's passes-a-second figure.
//
//   node tools/passbench.mjs CONFIG DISC [DISC2 ...] [--from P] [--passes N]
//        [--seed S] [--hold K,K@N] [--hang]
//
// A script that presses keys by frame plays a different game on a faster build, so
// the figure moves with the game as well as the code. Here the keys change by pass
// (passplay.mjs's generator, so seed S is pairlock.mjs's game S): builds that
// pairlock proves play the same game play identical passes here, and only the time
// differs. For passes FROM to FROM + N (default 200 to 1200, seed 1) it reports,
// per disc: passes a second and cycles a pass (2 MHz cycles: jsbeeb's own count),
// and with the config's `field` counter the fields each pass took. --hold plays
// those keys instead of the script ("K@N": down for 3 passes in every N).
//
// A build that stops making passes is reported with where it is - PC, ROMSEL,
// ACCCON, the stack, the last instructions by label in the bank each ran in, and
// the first BRK or unlabelled PC (harness.mjs hang()) - and exits 1. --hang adds
// that report after the last pass even when nothing stalled.
//   exit 0  every disc measured; 1 a disc stalled or measured nothing; 2 usage
import { holdKeys, loadConfig, scriptKeys, startPlay } from "./passplay.mjs";

const args = process.argv.slice(2);
const opt = (flag, d) => { const i = args.indexOf(flag); if (i < 0) return d; return args.splice(i, 2)[1]; };
const has = (flag) => { const i = args.indexOf(flag); if (i < 0) return false; args.splice(i, 1); return true; };
const FROM = parseInt(opt("--from", "200"), 10), N = parseInt(opt("--passes", "1000"), 10);
const SEED = parseInt(opt("--seed", "1"), 10);
const HOLD = opt("--hold", null)?.split(",");
const HANG = has("--hang");
const [cfgPath, ...discs] = args;
if (!discs.length) {
    console.error("usage: node tools/passbench.mjs CONFIG DISC [DISC2 ...] [--from P] [--passes N] [--seed S] [--hold K,K@N] [--hang]");
    process.exit(2);
}
let cfg;
try { cfg = await loadConfig(cfgPath); } catch (e) { console.error(`passbench: ${e.message}`); process.exit(2); }

const results = [];
let h, ok = true;
for (const disc of discs) {
    h = await startPlay(cfg, disc, { name: "passbench" });
    const play = h.play;
    h.watchBad();
    const keysAt = HOLD ? holdKeys(FROM + N + 2, HOLD) : scriptKeys(cfg, FROM + N + 2, SEED);
    let stalled = null;
    for (let p = 1; p <= FROM + N; p++) {
        if (!(await play.toPass(p))) { stalled = p; break; }
        play.setKeys(keysAt[p] || []);
    }
    const last = stalled ? stalled - 1 : FROM + N;
    const r = { disc, game: HOLD ? `holding ${HOLD.join("+")}` : `seed ${SEED}`, from: FROM, to: last };
    if (last > FROM) {
        const cyc = play.at[last].cycles - play.at[FROM].cycles, n = last - FROM;
        r.passesPerSecond = +(n / (cyc / 2e6)).toFixed(2);
        r.cyclesPerPass = Math.round(cyc / n);
        if (cfg.field) {
            const fields = {};
            for (let p = FROM; p < last; p++) { const d = (play.at[p + 1].field - play.at[p].field + 256) & 255; fields[d] = (fields[d] || 0) + 1; }
            r.fieldsPerPass = fields;
        }
    } else ok = false;
    if (stalled) { ok = false; r.stalledAt = stalled; r.hang = h.hang(); console.error(`passbench: ${disc} made no pass after ${last}`); }
    else if (HANG) { await h.s.runFrames(2); r.hang = h.hang(); }
    results.push(r);
    console.error(`passbench: ${disc}: ${r.passesPerSecond ?? "-"} passes/s, ${r.cyclesPerPass ?? "-"} cycles a pass` +
                  (r.fieldsPerPass ? `, fields a pass ${JSON.stringify(r.fieldsPerPass)}` : ""));
}
h.finish({ results }, ok, { samples: results.filter((r) => r.cyclesPerPass).length });
