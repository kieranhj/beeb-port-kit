// passplay.mjs - a game driven by its own loop: keys by PASS, not by frame or cycle.
//
// beeb-port-kit template, MIT, Kieran Connell 2026. From Stryker's Run's
// tools/passlock.mjs, passbench.mjs and playscript.mjs (2026-10-14 to 10-25), where
// the same keys-by-pass generator had been copied into five tools (passlock,
// passbench, hang, screendiff, sidebyside); this is the one copy, generalised.
//
// WHY BY PASS. A script that presses keys at frame N plays a different game on a
// faster build: the faster build is further into its loop when the key goes down,
// so the player turns at another column, a bullet hits or misses, and from then on
// the two builds are not comparable. Stryker's Run measured it: its layer 4 costing
// counted 31 late frames on one build and 41 on another on "the same" seed, and the
// difference was the input, not the code. Here a pass is one execution of the game
// loop's first instruction (the config's `loop` label), the machine is STOPPED there
// at the start of every pass, and the keys for pass N are set while it is stopped.
// Two builds whose game logic is the same then play the same game whatever their
// speed, and their game state can be compared at the start of every pass
// (pairlock.mjs) or their speed measured on the same game (passbench.mjs).
//
// THE CONFIG is a small JS module (or JSON, without the functions) naming
// everything game-specific; nothing here knows a game. examples/pairlock/ has the
// template's and Stryker's Run's. Its fields:
//
//   model        jsbeeb model ("Master", "B-DFS1.2"); default: "Master" if the build
//                defines MASTER=1, else "B-DFS1.2"
//   banks        section name -> sideways bank, "andy" or "hazel" (harness.mjs open())
//   loop         the label whose execution is a pass (gated by its bank, from banks)
//   field        optional: the zero-page field counter (passbench's fields a pass)
//   boot         { shiftFrames, settle } for harness.mjs boot()
//   start        { presses: [[frame, key, frames], ...], maxFrames } - the title, by
//                frame from the BREAK (no game loop is running yet) until pass 1
//   keys         action name -> internal key number, [column, row], or a symbol the
//                build defines as a key number; or keyOf(h, name) for keys read from
//                the game's own table once it has loaded
//   script       the generator: { hold: [min, max), gap: [min, max), groups: [...] }
//                (below); or keysAt(n, seed) returning an array of key lists
//   prng         optional { at, bytes, where } written into BOTH machines at pass 1:
//                a game seeded from a timer or the boot's length plays differently
//                on two builds unless it is pinned
//   onFirstPass  optional (h) => {}: anything else to even out at pass 1, in both
//   state        [{ name, at, len, where }] - the ranges compared every pass (at a
//                symbol, with +N, or &hex; len a number or (h) => number)
//   stateFn      optional (h) => ({ name: [bytes] }): state that needs reading logic
//   screen       optional { at, len, shown(h) -> "main" | "shadow", visible(h) ->
//                (i) => bool }: the shown screen, for pairlock --screen
//   stallFields  fields with no pass before a run is called stalled (1500)
//
// THE GENERATOR (burstKeys), Stryker's Run's exactly, so its seeds replay here: a
// burst of keys held for `hold` passes, then `gap` passes of none. Each group is an
// else-if chain: draw a number, take the first key if it is under that key's
// probability, else draw again for the next. The default groups are its: RIGHT 0.8
// else LEFT 0.5; SHIFT 0.5; DELETE 0.15; A 0.2 else Z 0.1 - names a config maps to
// keys. The random numbers are an LCG (1103515245, 12345; bits 16-31), so seed S is
// the same game in every tool that takes it.
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { open } from "./harness.mjs";

/** The LCG every keys-by-pass tool shares: rnd() in [0, 1). */
export function lcg(seed) {
    let s = seed >>> 0;
    return () => ((s = (Math.imul(s, 1103515245) + 12345) >>> 0) >>> 16) / 65536;
}

export const DEFAULT_SCRIPT = {
    hold: [10, 80], gap: [0, 10],
    groups: [[["RIGHT", 0.8], ["LEFT", 0.5]], [["SHIFT", 0.5]], [["DELETE", 0.15]], [["A", 0.2], ["Z", 0.1]]],
};

/** keysAt[p] for p in 0..n-1: the keys held through pass p. A prefix of a longer
 *  run's array is the shorter run's: n only truncates. */
export function burstKeys(n, seed = 1, spec = DEFAULT_SCRIPT) {
    const rnd = lcg(seed);
    const { hold = [10, 80], gap = [0, 10], groups = [] } = spec;
    const keysAt = [];
    for (let p = 0; p < n; ) {
        const len = hold[0] + Math.floor(rnd() * (hold[1] - hold[0])), keys = [];
        for (const chain of groups)
            for (const [k, prob] of chain) if (rnd() < prob) { keys.push(k); break; }
        for (let i = 0; i < len && p < n; i++) keysAt[p++] = keys;
        const g = gap[0] + Math.floor(rnd() * (gap[1] - gap[0]));
        for (let i = 0; i < g && p < n; i++) keysAt[p++] = [];
    }
    return keysAt;
}

/** "K" held throughout, "K@N" down for the first 3 passes of every N (a jump
 *  wants pressing, not holding): Stryker's Run's passbench --hold. */
export function holdKeys(n, list) {
    return Array.from({ length: n }, (_, p) => list.filter((k) => {
        const [, every] = k.split("@"); return !every || p % +every < 3;
    }).map((k) => k.split("@")[0]));
}

/** A config file: a JS module's default export, or JSON. */
export async function loadConfig(path) {
    if (!path || !existsSync(path)) throw new Error(`no config ${path}`);
    if (/\.json$/i.test(path)) return JSON.parse(readFileSync(path, "utf8"));
    const mod = await import(pathToFileURL(resolve(path)).href);
    return mod.default ?? mod;
}

/** Boot `disc` and play the config's start script to the first pass, stopped there.
 *  Returns the harness `h` with h.play: { passes, toPass(n), setKeys(list), state(),
 *  shown() }. `name` is the harness name; `pokes` are [{pass, at, bytes, where}]. */
export async function startPlay(cfg, disc, { name = "passplay", pokes = [] } = {}) {
    const h = await open({ name, disc, banks: cfg.banks });
    if (!cfg.loop) h.die("the config names no `loop` label");
    h.model = cfg.model || (h.define("MASTER") ? "Master" : "B-DFS1.2");
    const LOOP = h.need(cfg.loop);
    const loopGate = cfg.loopGate || h.gateOf(cfg.loop);
    const field = cfg.field ? h.zp(cfg.field) : undefined;
    const resolvedPokes = pokes.map((p) => ({ ...p, addr: h.addr(p.at) }));
    const prng = cfg.prng ? { addr: h.addr(cfg.prng.at), bytes: cfg.prng.bytes, where: cfg.prng.where } : null;
    const stateSpec = (cfg.state || []).map((e) => ({ name: e.name || String(e.at), at: h.addr(e.at), len: e.len, where: e.where }));

    await h.boot({ settle: 0, ...(cfg.boot || {}) });
    const play = { passes: 0, target: 1, lastStop: -1, at: [], held: [], startFrame: null };
    h.play = play;
    h.onExec(LOOP, () => {
        const c = h.s.elapsedCycles;
        if (c === play.lastStop) return false;       // resuming from the stop: counted already
        play.passes++;
        play.at[play.passes] = { cycles: c, field: field === undefined ? undefined : h.byte(field) };
        if (play.passes === 1) {
            if (prng) h.wr(prng.addr, prng.bytes, prng.where);
            if (cfg.onFirstPass) cfg.onFirstPass(h);
        }
        for (const p of resolvedPokes) if (p.pass === play.passes) h.wr(p.addr, p.bytes, p.where);
        if (play.onPass) play.onPass(play.passes, c);
        if (play.passes >= play.target) { play.lastStop = c; return true; }
        return false;
    }, loopGate);

    // the title, by frame: presses until the first pass
    const presses = cfg.start?.presses || [];
    const maxFrames = cfg.start?.maxFrames ?? 6000;
    const ev = new Map();
    const at = (f, e) => { if (!ev.has(f)) ev.set(f, []); ev.get(f).push(e); };
    for (const [f, k, n = 40] of presses) { at(f, ["down", k]); at(f + n, ["up", k]); }
    for (let f = h.frames + 1; f <= maxFrames && play.passes < 1; f++) {
        for (const [what, k] of ev.get(f) || []) (what === "down" ? h.keyDownRaw : h.keyUpRaw)(keyOf(h, cfg, k));
        await h.s.runFrames(1);
        h.frames = f;
    }
    if (play.passes < 1) h.die(`${disc}: no pass of ${cfg.loop} in ${maxFrames} frames - the start script did not start a game`, { where: h.where() });
    play.startFrame = h.frames;
    h.s.releaseAllKeys();

    const chunk = 400000;                            // cycles: 10 fields
    const stallChunks = Math.ceil(((cfg.stallFields ?? 1500) * 39936) / chunk);
    /** Run to the start of pass n, stopped there; false if no pass came for
     *  stallFields fields (the game has left its loop: a hang, or a screen waiting
     *  for a key the script never presses). */
    play.toPass = async (n) => {
        play.target = n;
        for (let i = 0; play.passes < n; i++) { if (i === stallChunks) return false; await h.s.runFor(chunk); }
        return true;
    };
    /** Hold exactly `keys` (action names) from now on. */
    play.setKeys = (keys) => {
        for (const k of play.held) if (!keys.includes(k)) h.keyUpRaw(keyOf(h, cfg, k));
        for (const k of keys) if (!play.held.includes(k)) h.keyDownRaw(keyOf(h, cfg, k));
        play.held = keys;
    };
    play.state = () => {
        const out = {};
        for (const e of stateSpec) {
            const len = lenOf(h, e.len);
            out[e.name] = [...h.rd(e.at, len, e.where)];
        }
        if (cfg.stateFn) Object.assign(out, cfg.stateFn(h));
        return out;
    };
    play.shown = () => {
        const sc = cfg.screen;
        const where = sc.shown ? sc.shown(h) : (h.cpu.model.isMaster && (h.cpu.acccon & 1) ? "shadow" : "main");
        return { where, bytes: h.rd(h.addr(sc.at), lenOf(h, sc.len), where), visible: sc.visible ? sc.visible(h) : null };
    };
    return h;
}

/** A length: a number, a symbol (an assembly-time constant), or (h) => number. */
function lenOf(h, len) {
    return typeof len === "function" ? len(h) : typeof len === "string" ? h.addr(len) : len;
}

/** The matrix key for an action name: cfg.keyOf(h, name), else cfg.keys[name]. */
export function keyOf(h, cfg, name) {
    if (cfg.keyOf) { const k = cfg.keyOf(h, name); if (k !== undefined) return k; }
    const k = cfg.keys?.[name];
    if (k === undefined) h.die(`the config has no key for ${name}`);
    return k;
}

/** The keys for passes 0..n-1 from the config's script and the seed. */
export function scriptKeys(cfg, n, seed) {
    if (cfg.keysAt) return cfg.keysAt(n, seed);
    return burstKeys(n, seed, cfg.script || DEFAULT_SCRIPT);
}

/** "P:ADDR=B,B[:WHERE]" -> {pass, at, bytes, where}: a poke at the start of pass P
 *  (hex bytes; ADDR a symbol with +N or &hex; WHERE main, shadow, a bank or paged). */
export function parsePoke(t) {
    const m = /^(\d+):([^=]+)=([0-9A-Fa-f,]+)(?::(\w+))?$/.exec(t);
    if (!m) throw new Error(`poke ${t}: want PASS:ADDR=HEX,HEX[:WHERE]`);
    const w = m[4];
    return { pass: +m[1], at: m[2], bytes: m[3].split(",").map((b) => parseInt(b, 16)),
             where: w === undefined ? undefined : /^\d+$/.test(w) ? +w : w };
}
