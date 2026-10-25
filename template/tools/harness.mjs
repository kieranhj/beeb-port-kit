// harness.mjs - the skeleton every headless oracle is built on.
//
// beeb-port-kit template, MIT, Kieran Connell 2026. Distilled from the 148-line
// suite of 1942 for the BBC Master (2026-09-07 to 10-23): verify_turner.mjs's
// need(), verify_sprite.mjs's coverage gate and asmConst(), verify_panel.mjs's
// write hook with the CRTC's counters beside it, measure_budget.mjs's breakpoint
// walker and profile_routines.mjs's paging-aware PC. ../../docs/verification.md
// "Headless harnesses" is the long form; ../../skills/beeb-oracle-harness the
// checklist. From Stryker's Run's tools/playscript.mjs and hang.mjs (2026-10-25):
// keyDownRaw by internal key number, callFrom, the bank map (open({banks}),
// gateOf, bank-aware symAt) with ungated sideways hooks refused, need("name+N"),
// an exact name preferred over scope leaves, and keepTrail/watchBad/hang;
// tools/harness_selftest.mjs proves each on the template's build. The pair
// harness (two builds, keys by pass) is passplay.mjs and pairlock.mjs.
//
// THE CONTRACT, which is the point of the file:
//
//   exit 0   the oracle ran, sampled something, covered every path it named, and
//            every sample agreed with the model
//   exit 1   it ran and something disagreed - OR it sampled nothing, OR a path it
//            needs was never taken. A check that ran over nothing is not a pass
//   exit 2   it could not judge: a usage error, a symbol not in the build, a disc
//            that never booted (the field counter never moved), a thrown hook
//
// One line of JSON on stdout, last, with the jsbeeb version in it; explanations on
// stderr. Never grep the output for "pass" - field names match it - read the exit
// code (1942 BUGS.md #9: verify_dynamic answered a well-formed object of ZEROS
// with exit 0 for weeks, and nobody noticed because nobody asked it to fail).
//
//   import { open } from "./harness.mjs";
//   const h = await open({ name: "verify_x", disc: "build/game.ssd" });
//   const FIELD = h.zp("field_count"), LOOP = h.need("main_loop");
//   await h.boot({ field: FIELD });
//   const cov = h.coverage();
//   h.onExec(LOOP, () => { cov.hit("pass"); });
//   ...
//   h.finish({ ...figures }, wrong === 0, { samples: n });
//
// ADDRESSES ARE NEVER ARGUMENTS HERE BY DEFAULT: they come out of the build's own
// symbol dump (build/<stem>.symbols.json beside the disc), because Baron moves zero
// page on every edit and an address written down is a measurement of nothing
// (1942: `scroll` read for `frame_count`, 13,696 frames where the answer was 50).
import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

import { loadMachineSession, keys, version } from "./jsbeeb_src.mjs";

const SCOPE = /^(?:@\d+:\d+\.)+/;
// The format-2 dump's kinds that are names. `params` are macro arguments (`r`, `v`
// in every CRTC macro call) and are left out: they are noise, not symbols.
const KINDS = ["labels", "assignments", "defines", "za_autos"];

/** Baron's --symbols dump as name -> [distinct values], scopes reduced as
 *  tools/listing.py reduces them: `@0:123.` prefixes dropped, a named scope's
 *  `main_loop.wait_take` kept AND its leaf `wait_take` added. Every value says
 *  whether it came by its EXACT name or as a scope's leaf: a top-level name wins
 *  over leaves of the same name (Stryker's Run's zero-page `lives` is an
 *  assignment, &95, and two routines in a bank have a local `.lives`; reading
 *  the leaves as rivals made `need("lives")` refuse a name the source means one
 *  way, 2026-10-25). Labels also carry their SECTION's name and its parents',
 *  so a PC in a sideways bank can be named from the bank that was paged.
 *  Exported for tools that read two dumps without booting (tracediff.mjs). */
export function readSymbols(path) {
    const doc = JSON.parse(readFileSync(path, "utf8"));
    const files = [], extents = [];
    if (Number.isInteger(doc.format)) {
        for (const asm of doc.assemblies) {
            const syms = {};
            const secs = asm.sections;
            const chain = (i) => {                  // the section and its parents, innermost first
                const out = [];
                for (let j = i, n = 0; j !== null && j !== undefined && secs[j] && n < 64; j = secs[j].parent, n++)
                    if (secs[j].name) out.push(secs[j].name);
                return out;
            };
            secs.forEach((sec, i) => {
                if (sec.name && Number.isInteger(sec.attributes?.org) && Number.isInteger(sec.size))
                    extents.push({ name: sec.name, org: sec.attributes.org, size: sec.size, sections: chain(i) });
                for (const kind of KINDS)
                    for (const [k, v] of Object.entries(sec[kind] || {}))
                        if (!(k in syms)) syms[k] = { value: v.value, kind, sections: chain(i) };
            });
            files.push({ sources: asm.sources, syms });
        }
    } else {                                    // Baron <= 0.4: {file: {name: value}}
        for (const [src, syms] of Object.entries(doc)) {
            const out = {};
            for (const [k, v] of Object.entries(syms)) out[k] = { value: v, kind: "?", sections: [] };
            files.push({ sources: [src], syms: out });
        }
    }
    const found = new Map();
    const labels = [];                          // {name, raw, value, sections}, by value: symAt, tracediff
    const add = (n, v, exact) => {
        if (!found.has(n)) found.set(n, []);
        const l = found.get(n);
        const had = l.find((x) => x.value === v.value);
        if (had) { had.exact ||= exact; return; }
        l.push({ ...v, exact });
    };
    for (const f of files)
        for (const [k, v] of Object.entries(f.syms)) {
            const name = k.replace(SCOPE, "");
            add(name, v, true);
            if (name.includes(".")) add(name.slice(name.lastIndexOf(".") + 1), v, false);
            if (v.kind === "labels" && typeof v.value === "number") labels.push({ name, raw: k, value: v.value, sections: v.sections });
        }
    labels.sort((a, b) => a.value - b.value);
    return { found, labels, extents, sources: files.flatMap((f) => f.sources) };
}

/** Which paging a label's section needs, from a `banks` map of section name ->
 *  a sideways bank number, "andy", "hazel" or "main" (the innermost section the
 *  map names wins). undefined: the map does not say. */
export function regionOf(sections, banks) {
    if (!banks) return undefined;
    for (const n of sections || []) if (n in banks) return banks[n];
    return undefined;
}

/** Is a label at `addr`, in a section of region `r`, the code paged in with this
 *  ROMSEL and ACCCON? Outside the switched windows, always; a label whose region
 *  the map does not give is taken (the map says nothing about it). */
export function pagedIn(addr, r, romsel, acccon, master = true) {
    if (r === undefined) return true;
    if (addr >= 0x8000 && addr < 0xc000) {
        const andyIn = master && addr < 0x9000 && (romsel & 0x80);
        if (r === "andy") return !!andyIn;
        if (typeof r === "number") return !andyIn && (romsel & 0x0f) === r;
        return false;
    }
    if (master && addr >= 0xc000 && addr < 0xe000) return r === "hazel" ? !!(acccon & 0x08) : true;
    return true;
}

/** The nearest label at or below `a` (within `reach` bytes) among `labels`
 *  (readSymbols' sorted list) that is paged in: [label, offset], or null. */
export function labelAt(labels, a, { banks, romsel = 0, acccon = 0, master = true, reach = 512 } = {}) {
    let lo = 0, hi = labels.length - 1, top = -1;
    while (lo <= hi) { const mid = (lo + hi) >> 1; if (labels[mid].value <= a) { top = mid; lo = mid + 1; } else hi = mid - 1; }
    const ok = (l) => pagedIn(l.value, regionOf(l.sections, banks), romsel, acccon, master);
    for (let i = top; i >= 0 && a - labels[i].value < reach; i--) {
        if (!ok(labels[i])) continue;
        let best = labels[i];              // the longest (most qualified) name at that address
        for (let j = i - 1; j >= 0 && labels[j].value === best.value; j--)
            if (ok(labels[j]) && labels[j].name.length > best.name.length) best = labels[j];
        return [best, a - best.value];
    }
    return null;
}

const hex = (a, w = 4) => "&" + a.toString(16).toUpperCase().padStart(w, "0");

/** Open a harness: resolve the symbols NOW, so a missing name fails before a boot.
 *  `model` may be changed (h.model = ...) until boot() - e.g. from h.define("MASTER"). */
export async function open({ name, disc, symbols, model = "B-DFS1.2", tube = false, banks } = {}) {
    const h = { name: name || "harness", disc, model, banks, booted: false, s: null, cpu: null };
    const die = (msg, extra = {}) => {
        console.error(`${h.name}: ${msg}`);
        console.log(JSON.stringify({ harness: h.name, error: msg, ...extra, jsbeeb: version(), pass: false }));
        process.exit(2);
    };
    h.die = die;
    process.on("unhandledRejection", (e) => die(`threw: ${e?.stack || e}`, h.s ? { where: h.where() } : {}));
    process.on("uncaughtException", (e) => die(`threw: ${e?.stack || e}`, h.s ? { where: h.where() } : {}));

    if (!disc) die("no disc given");
    if (!existsSync(disc)) die(`no ${disc} - build first`);
    const symPath = symbols || disc.replace(/\.ssd$/i, ".symbols.json");
    if (!existsSync(symPath)) die(`no ${symPath}: the symbol dump is where every address comes from`);
    const { found, labels, extents, sources } = readSymbols(symPath);
    h.labels = labels;
    h.extents = extents;                      // each SECTION's org and size: where it runs
    const root = resolve(dirname(symPath), "..");  // the sources are relative to the build's cwd
    h.symbolsPath = symPath;

    // a name's candidates: by its exact name if it has one, else the leaves of the
    // scopes that end in it (readSymbols)
    const numeric = (n) => {
        const all = (found.get(n) || []).filter((v) => typeof v.value === "number");
        const exact = all.filter((v) => v.exact);
        return exact.length ? exact : all;
    };

    /** A symbol's value, or undefined. A local label with several addresses is
     *  undefined here and an error in need(), which says what they are. */
    h.sym = (n) => { const v = numeric(n); return v.length === 1 ? v[0].value : undefined; };
    /** A symbol's value or exit 2. Never a default: a default is a stale address.
     *  Labels, assignments (Baron dumps zero-page names as ASSIGNMENTS, so a
     *  labels-only reader gets undefined for them and compares nothing, silently:
     *  Stryker's Run's worldcheck did), -D defines and ZA_AUTO allocations are all
     *  read. `name+N`, `name-N` and `name+&NN` add an offset. */
    h.need = (n) => {
        const m = /^(.*?)(?:([+-])(&[0-9A-Fa-f]+|0x[0-9A-Fa-f]+|\d+))?$/.exec(n);
        const base = m[1];
        const off = m[3] === undefined ? 0 : (m[2] === "-" ? -1 : 1) *
            (/^(&|0x)/.test(m[3]) ? parseInt(m[3].replace(/^(&|0x)/, ""), 16) : +m[3]);
        const v = numeric(base);
        if (v.length > 1) die(`${base} has ${v.length} values (${v.map((x) => hex(x.value)).join(", ")}): qualify it, e.g. scope.${base}`);
        if (!v.length) die(`no ${base} in ${symPath}`);
        return v[0].value + off;
    };
    /** An address given as a symbol (with +N), &hex, 0xhex or a number. Config
     *  files name addresses by symbol; a literal is for what has none (the MOS's
     *  own locations) and is the caller's to justify. */
    h.addr = (t) => {
        if (typeof t === "number") return t;
        if (/^(&|0x)[0-9A-Fa-f]+$/.test(t)) return parseInt(t.replace(/^(&|0x)/, ""), 16);
        return h.need(t);
    };
    /** The sections a symbol was defined in, innermost first. */
    h.sectionsOf = (n) => { const v = numeric(n.replace(/[+-].*$/, "")); return v.length === 1 ? v[0].sections : undefined; };
    /** A ZERO-PAGE variable, refusing anything above &FF: a label of a similar name
     *  in the code is the confusion this exists to stop (1942: `frame` is a label at
     *  &2591, `frame_count` the variable at &12). */
    h.zp = (n) => {
        const a = h.need(n);
        if (a > 0xff) die(`${n} is ${hex(a)}, not zero page - wrong symbol?`);
        return a;
    };
    /** A defined symbol (-D NAME=v), or undefined. */
    h.define = (n) => numeric(n).find((v) => v.kind === "defines")?.value;
    /** An assembly-time constant. The dump's value (Baron evaluated it), checked
     *  against the source's literal where the source has one: if they DISAGREE the
     *  build is older than the source, and every figure from it is stale - exit 2. */
    h.asmConst = (n) => {
        const fromDump = h.sym(n);
        let fromSrc;
        const re = new RegExp(String.raw`^\s*${n}\s*=\s*(&[0-9A-Fa-f]+|\$[0-9A-Fa-f]+|\d+)\s*(?:[;\\]|$)`, "m");
        for (const s of sources) {
            if (s.startsWith("-")) continue;
            const f = join(root, s.replace(/\\/g, "/"));
            if (!existsSync(f)) continue;
            const m = readFileSync(f, "latin1").match(re);
            if (m) {
                const t = m[1];
                fromSrc = t[0] === "&" || t[0] === "$" ? parseInt(t.slice(1), 16) : parseInt(t, 10);
                break;
            }
        }
        if (fromDump !== undefined && fromSrc !== undefined && fromDump !== fromSrc)
            die(`${n} is ${fromSrc} in the source and ${fromDump} in ${symPath}: the build is stale - rebuild`);
        if (fromDump === undefined && fromSrc === undefined) die(`no constant ${n} in the dump or the source`);
        return fromDump ?? fromSrc;
    };
    /** The nearest label at or below `a`, for saying where a PC was. With `banks`
     *  given to open(), a label in &8000-&BFFF (or HAZEL) names a PC only while its
     *  bank is paged - the CPU's paging now, or `paging` {romsel, acccon} - so bank
     *  5's code is not named from bank 4's label at the same address. */
    h.symAt = (a, paging) => {
        const c = h.cpu;
        const at = labelAt(labels, a, { banks, romsel: paging?.romsel ?? c?.romsel ?? 0,
            acccon: paging?.acccon ?? c?.acccon ?? 0, master: c ? !!c.model.isMaster : true });
        return at ? (at[1] ? `${at[0].name}+${at[1]}` : at[0].name) : null;
    };
    /** The hook gate a symbol's code needs, from `banks`: {romsel: n} for a bank,
     *  {andy: true}, {hazel: true}, or {} for main RAM. exit 2 for an address in a
     *  sideways bank whose section the map does not place. */
    h.gateOf = (n) => {
        const a = h.need(n), r = regionOf(h.sectionsOf(n), banks);
        if (a >= 0x8000 && a < 0xc000) {
            if (r === "andy") return { andy: true };
            if (typeof r === "number") return { romsel: r };
            die(`${n} is ${hex(a)}, in a sideways bank, and open({banks}) does not say which: map its section (${(h.sectionsOf(n) || ["?"]).join(" < ")})`);
        }
        if (a >= 0xc000 && a < 0xe000 && r === "hazel") return { hazel: true };
        return {};
    };

    const MachineSession = await loadMachineSession();
    h.keys = keys();

    // ---- memory: the bank is NAMED in a switched window, reads and writes alike ----
    // &3000-&7FFF is main or shadow on a Master; &8000-&BFFF is a sideways bank (or
    // ANDY). jsbeeb's default follows the CPU's own paging, so an unnamed access goes
    // wherever the game had it at that instant: 1942's cheat write vanished on a boot
    // an odd number of fields longer, and two runs came back byte-identical
    // (verify_bossfly, 2026-09-19). `where` is "main", "shadow", a bank number,
    // {bank, shadow}, or "paged" - which says, in so many words, "whatever is in".
    const opts = (addr, n, where) => {
        const lo = addr, hi = addr + n - 1;
        const inScreen = lo <= 0x7fff && hi >= 0x3000, inBank = lo <= 0xbfff && hi >= 0x8000;
        if (!inScreen && !inBank) return {};
        if (where === undefined)
            throw new Error(`${hex(lo)}-${hex(hi)} is in a switched window: name the bank ` +
                `("main", "shadow", a bank number, {bank, shadow}, or "paged")`);
        if (where === "paged") return {};
        const master = h.cpu?.model?.isMaster;
        const o = typeof where === "object" ? { ...where }
            : typeof where === "number" ? { bank: where }
            : where === "main" ? { shadow: false } : where === "shadow" ? { shadow: true } : null;
        if (!o) throw new Error(`where = ${JSON.stringify(where)} is not a bank`);
        if (inScreen && o.shadow === undefined) throw new Error(`${hex(lo)} is in &3000-&7FFF: say "main" or "shadow"`);
        if (inBank && o.bank === undefined) throw new Error(`${hex(lo)} is in &8000-&BFFF: say which bank`);
        if (!master && o.shadow === false) delete o.shadow;          // a Model B has only main
        if (!master && o.shadow) throw new Error("only a Master has shadow RAM");
        return o;
    };
    h.rd = (addr, n = 1, where) => h.s.readMemory(addr, n, opts(addr, n, where));
    h.wr = (addr, bytes, where) => h.s.writeMemory(addr, bytes, opts(addr, bytes.length, where));
    h.byte = (addr, where) => h.rd(addr, 1, where)[0];
    h.word = (addr, where) => { const b = h.rd(addr, 2, where); return b[0] | (b[1] << 8); };

    /** Boot the disc with SHIFT+BREAK held, settle, and EXIT 2 if the field counter
     *  does not move: every way of getting the boot wrong - a key the emulator did
     *  not press, a disc that did not load, a wrong FIELD address - looks like "the
     *  program does nothing", and must not be judged as a result. `shiftFrames`
     *  (50) is how long SHIFT is held after the BREAK; `settle` the fields after.
     *  h.frames counts the fields run since the BREAK, for a start script by frame. */
    h.boot = async ({ field, settle = 150, fieldBytes = 1, shiftFrames = 50 } = {}) => {
        h.s = new MachineSession(h.model, { tube });
        await h.s.initialise();
        await h.s.boot(30);
        h.cpu = h.s._machine.processor;
        h.s.loadDisc(disc);
        h.s.keyDown(h.keys.SHIFT); h.s.reset(true); await h.s.runFrames(shiftFrames); h.s.keyUp(h.keys.SHIFT);
        await h.s.runFrames(settle);
        h.frames = shiftFrames + settle;
        if (field !== undefined) {
            const rdf = () => (fieldBytes === 2 ? h.word(field, "main") : h.byte(field, "main"));
            const f0 = rdf();
            await h.s.runFrames(10);
            if (rdf() === f0)
                die(`the field counter at ${hex(field, 2)} did not move in 10 fields: the disc did not boot, ` +
                    "or that is not the counter", { where: h.where() });
        }
        h.booted = true;
        return h.s;
    };

    // ---- hooks: on the instruction, gated on the paging ---------------------------
    // A sideways-bank address is that code only while that bank is paged, and on a
    // Master an address below &9000 is ALSO ANDY's when ROMSEL bit 7 is set: 1942's
    // stage_restart at &86D1 "fired" on every tick because the in-play text ran at
    // the same address in ANDY. So `romsel: n` means (ROMSEL & &8F) = n - bank n, ANDY
    // out - unless `andy: true`. `hazel` gates &C000-&DFFF on ACCCON's Y. `afterBoot`
    // (the default) keeps a hook dark until boot() returns, because the filing system
    // runs its own code at your overlay addresses while the disc loads.
    //   A hook on an address in &8000-&BFFF with no `romsel` (or `andy`), or on a
    // Master in &C000-&DFFF with no `hazel`, is REFUSED unless `anyBank: true` says
    // in so many words that any paging will do: Stryker's Run had 30-odd false
    // failures from a breakpoint taken in another bank's code at the same address
    // (its commits 1fd31bd, 76bff0b). `h.gateOf(name)` makes the gate from the
    // symbol's section, given open({banks}).
    const refuseUngated = (addr, g) => {
        if (g.anyBank) return;
        if (addr >= 0x8000 && addr < 0xc000 && g.romsel === undefined && !g.andy)
            throw new Error(`a hook at ${hex(addr)} is in the sideways window: give {romsel: bank} (or andy), ` +
                "h.gateOf(name), or {anyBank: true}");
        if (h.cpu?.model?.isMaster && addr >= 0xc000 && addr < 0xe000 && g.hazel === undefined)
            throw new Error(`a hook at ${hex(addr)} is HAZEL's or the MOS's on a Master: give {hazel: true|false} or {anyBank: true}`);
    };
    h.refuseUngated = refuseUngated;
    const gate = ({ romsel, andy = false, hazel, afterBoot = true }) => () => {
        if (afterBoot && !h.booted) return false;
        const c = h.cpu;
        if (romsel !== undefined) {
            if ((c.romsel & 0x0f) !== romsel) return false;
            if (c.model.isMaster && !!(c.romsel & 0x80) !== !!andy) return false;
        } else if (andy && !(c.romsel & 0x80)) return false;
        if (hazel !== undefined && !!(c.acccon & 0x08) !== !!hazel) return false;
        return true;
    };
    /** fn(pc) before the instruction at `addr` runs; return true to STOP the run. */
    h.onExec = (addr, fn, g = {}) => {
        refuseUngated(addr, g);
        const ok = gate(g);
        const hook = h.cpu.debugInstruction.add((pc) => pc === addr && ok() ? fn(pc) === true : false);
        return () => hook.remove();
    };
    /** The beam, as jsbeeb's CRTC has it: the instrument for every raster-phase claim
     *  (1942 verify_panel: a write's horizCounter in the line's blanking, every field). */
    h.crtc = () => {
        const v = h.cpu.video;
        return { hc: v.horizCounter, vc: v.vertCounter, sc: v.scanlineCounter, adj: !!v.inVertAdjust };
    };
    /** fn(addr, val, ctx) on every CPU write to lo..hi (ctx: pc - past the operand,
     *  the cycle count, ROMSEL, ACCCON, the CRTC counters). Return true to stop. */
    h.onWrite = (lo, hi, fn, g = {}) => {
        const ok = gate(g);
        const hook = h.cpu.debugWrite.add((addr, val) => {
            if (addr < lo || addr > hi || !ok()) return false;
            const c = h.cpu;
            return fn(addr, val, { pc: c.pc, cycles: h.s.elapsedCycles, romsel: c.romsel,
                                   acccon: c.acccon, ...h.crtc() }) === true;
        });
        return () => hook.remove();
    };

    /** Where the machine is, for any message that gives up: the PC symbolised, the
     *  paging, the stack's top and the MOS's last-error pointer (&FD) - a BRK into
     *  the MOS from a run-away jump reads as "it hung" without it (1942 BUGS.md #24, #29). */
    h.where = () => {
        const c = h.cpu;
        if (!c) return null;
        const stack = [];
        for (let i = 1; i <= 8; i++) stack.push(c.readmem(0x100 + ((c.s + i) & 0xff)));
        return { pc: hex(c.pc), at: h.symAt(c.pc), romsel: hex(c.romsel, 2),
                 acccon: c.model.isMaster ? hex(c.acccon, 2) : undefined,
                 s: hex(c.s, 2), stack: stack.map((b) => hex(b, 2)).join(" "),
                 errPtr: hex(c.readmem(0xfd) | (c.readmem(0xfe) << 8)) };
    };
    /** Run until `addr` executes (gated as onExec), within `budget` cycles. Returns
     *  the cycles it took, or null with h.gaveUp = where() - a harness that times out
     *  says WHERE, because "never reached" with no PC is a session lost. */
    h.runTo = async (addr, budget = 4_000_000, g = {}) => {
        refuseUngated(addr, g);
        const start = h.s.elapsedCycles;
        let hit = false;
        const off = h.onExec(addr, () => {
            if (h.s.elapsedCycles === start) return false;  // already sitting on it
            hit = true; return true;
        }, g);
        try {
            while (!hit && h.s.elapsedCycles - start < budget)
                await h.s.runFor(Math.min(1_000_000, budget - (h.s.elapsedCycles - start)));
        } finally { off(); }
        if (hit) return h.s.elapsedCycles - start;
        h.gaveUp = { want: hex(addr), wantAt: h.symAt(addr), budget, ...h.where() };
        return null;
    };

    // ---- keys by matrix position ---------------------------------------------------
    // keyDown/keyUp press a HOST key, through jsbeeb's keymap; a game that reads the
    // keyboard off the System VIA (keydown_int, OSBYTE &81 with a negative number)
    // wants a BBC key, and its source has the INTERNAL key number (OSBYTE 121's
    // numbering, measured: ../../skills/beeb-key-numbers). That number is the matrix
    // position, row * 16 + column, which keyDownRaw([column, row]) presses with no
    // keymap between. `k` is the internal number, [column, row], or a name the build
    // defines as a number (KEY_LEFT = 97): the build's own key, from its dump.
    const matrix = (k) => {
        if (Array.isArray(k)) return k;
        const n = typeof k === "number" ? k : h.need(k);
        if (!(n >= 0 && n < 0x80)) throw new Error(`key ${k} = ${n} is not an internal key number (0-127)`);
        return [n & 15, n >> 4];
    };
    h.matrix = matrix;
    h.keyDownRaw = (k) => h.s.keyDownRaw(matrix(k));
    h.keyUpRaw = (k) => h.s.keyUpRaw(matrix(k));

    /** Make the CPU, stopped at an instruction, call `target` as a JSR placed in
     *  front of that instruction would: the return address (the stopped PC - 1)
     *  pushed and PC set, with A, X, Y as given. RTS comes back to the instruction it
     *  was stopped at. Writes nothing but the stack: Stryker's Run's sound effect
     *  tools used to put a JSR stub in "free" RAM, which became a table (its
     *  decisions 32-34). From its tools/playscript.mjs, 2026-10-25. */
    h.callFrom = (target, { a, x, y } = {}) => {
        const c = h.cpu;
        const ret = (c.pc - 1) & 0xffff;
        c.writemem(0x100 + c.s, ret >> 8); c.s = (c.s - 1) & 0xff;
        c.writemem(0x100 + c.s, ret & 0xff); c.s = (c.s - 1) & 0xff;
        if (a !== undefined) c.a = a;
        if (x !== undefined) c.x = x;
        if (y !== undefined) c.y = y;
        c.pc = typeof target === "number" ? target : h.need(target);
    };

    /** The last `n` instructions' PCs with the paging, kept from now on: the trail
     *  hang() prints. One hook; call once. */
    h.keepTrail = (n = 64) => {
        if (h._trail) return;
        h._trail = [];
        h.cpu.debugInstruction.add((pc) => {
            h._trail.push([pc, h.cpu.romsel, h.cpu.acccon]);
            if (h._trail.length > n) h._trail.shift();
            return false;
        });
    };
    /** For a build that stopped making passes: where() and the trail, named by
     *  symAt with the paging each instruction ran under; and `firstBad` (from
     *  watchBad) - the first BRK, or the first PC below &C000 no label is near. */
    //   "No label near" is judged in main RAM, and in &8000-&BFFF only for a bank the
    // `banks` map names (the DFS and the other ROMs have no labels); `ignore` is a
    // list of [lo, hi] ranges that are someone else's code (the DFS's NMI page).
    h.watchBad = ({ ignore = [] } = {}) => {
        if (h._bad !== undefined) return;
        h._bad = null;
        h.keepTrail();
        const ours = new Set(Object.values(banks || {}).filter((v) => typeof v === "number"));
        h.cpu.debugInstruction.add((pc, op) => {
            if (h._bad) return false;
            const c = h.cpu;
            const judged = pc < 0x8000 ? true : pc < 0xc000 ? ours.has(c.romsel & 0x0f) && !(c.romsel & 0x80 && pc < 0x9000) : false;
            if (op === 0x00 || (judged && !ignore.some(([lo, hi]) => pc >= lo && pc <= hi) && h.symAt(pc) === null))
                h._bad = { pc: hex(pc), romsel: hex(c.romsel, 2), op: hex(op, 2),
                           trail: h._trail.slice(-40).map(([p, r, a]) => `${hex(p)} ${hex(r, 2)} ${h.symAt(p, { romsel: r, acccon: a }) ?? "?"}`) };
            return false;
        });
    };
    h.hang = () => ({ ...h.where(),
        trail: (h._trail || []).slice(-24).map(([p, r, a]) => `${hex(p)} ${hex(r, 2)} ${h.symAt(p, { romsel: r, acccon: a }) ?? "?"}`),
        ...(h._bad !== undefined ? { firstBad: h._bad } : {}) });

    /** A run's coverage: hit(name) as paths are taken, need(name, n) for what a pass
     *  requires. A check that never took a path cannot have caught its faults: 1942's
     *  sprite oracle passed for a month with no sprite drawn at a negative X - the one
     *  case that was broken (BUGS.md #84). */
    h.coverage = () => {
        const counts = {}, needs = [];
        return {
            counts,
            hit(n, k = 1) { counts[n] = (counts[n] || 0) + k; },
            need(n, min = 1, why = "") { needs.push({ n, min, why }); },
            gaps() {
                return needs.filter(({ n, min }) => (counts[n] || 0) < min)
                    .map(({ n, min, why }) => `${n}: ${counts[n] || 0} of ${min}${why ? " - " + why : ""}`);
            },
        };
    };

    /** Print the one JSON line and exit 0 or 1. `samples` is REQUIRED: how many
     *  things were judged. Zero fails ("this proved nothing"); so does any gap. */
    h.finish = (report, pass, { samples, cover } = {}) => {
        if (!Number.isFinite(samples)) die("finish() without `samples`: say how many things were judged");
        const gaps = cover ? cover.gaps() : [];
        const ok = !!pass && samples > 0 && gaps.length === 0;
        if (samples === 0) console.error(`${h.name}: NOTHING WAS SAMPLED - this proved nothing`);
        if (gaps.length) {
            console.error(`${h.name}: PATHS NEVER TAKEN, so this run does not clear them:`);
            for (const g of gaps) console.error("  " + g);
        }
        console.log(JSON.stringify({ harness: h.name, ...report, samples,
                                     ...(cover ? { coverage: cover.counts, neverExercised: gaps } : {}),
                                     ...(h.gaveUp ? { gaveUp: h.gaveUp } : {}),
                                     model: h.model, jsbeeb: version(), pass: ok }));
        process.exit(ok ? 0 : 1);
    };
    return h;
}
