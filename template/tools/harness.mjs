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
// From the phX port, 2026-11: JUNK=seed (every RAM filled from a PRNG, then a
// SOFT BREAK - a real machine's RAM is not jsbeeb's zeros), runUntil (run on
// until a symbol reaches a value: phX's SEQ_ROW, generalised as RUN_UNTIL),
// pressWhen (press a key once a symbol is set: phX's disclaimer skip,
// generalised as PRESS_WHEN), afterBreak (both of them again after a harness's
// own BREAK) and cli() for the tools' `--name=value` options.
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

/** A tool's command line: positionals, and `--name=value` / `--flag` (true) options.
 *  Only the `=` form takes a value, so a positional can never be eaten by a flag. */
export function cli(argv = process.argv.slice(2)) {
    const pos = [], opt = {};
    for (const a of argv) {
        const m = /^--([^=]+)(?:=(.*))?$/s.exec(a);
        if (m) opt[m[1]] = m[2] === undefined ? true : m[2];
        else pos.push(a);
    }
    return { pos, opt };
}

/** A number from the command line or the environment: decimal, &hex or 0xhex. */
export function num(t, dflt) {
    if (t === undefined || t === true || t === "") return dflt;
    if (typeof t === "number") return t;
    const s = String(t);
    const v = /^(&|0x|\$)/i.test(s) ? parseInt(s.replace(/^(&|0x|\$)/i, ""), 16) : Number(s);
    if (!Number.isFinite(v)) throw new Error(`${s} is not a number`);
    return v;
}

/** The xorshift32 the JUNK fill draws from: the same seed, the same bytes, on every
 *  machine and jsbeeb version (it touches nothing of the emulator's). */
export function junkBytes(seed) {
    let x = (seed >>> 0) || 1;
    return () => { x ^= x << 13; x >>>= 0; x ^= x >>> 17; x ^= x << 5; x >>>= 0; return x & 255; };
}

/** Fill a jsbeeb machine's RAM from junkBytes(seed). `only` names the regions:
 *    zp      &0000-&008F (the user's zero page; the MOS's &90-&FF is left)
 *    main    &0E00-&7FFF (from a DFS machine's PAGE; the MOS's and the DFS's pages left)
 *    swr     every sideways RAM bank the model has (a B's 0-7, a Master's 4-7)
 *    andy    a Master's ANDY (&8000-&8FFF, 4K)
 *    hazel   a Master's HAZEL from &C000 + hz0 to &C000 + hz1 (default &C300-&DBFF: the
 *            MOS's and the DFS's own HAZEL workspace below and above is left alone:
 *            phX's defaults)
 *    shadow  a Master's LYNNE (&3000-&7FFF shadow, 20K)
 *  A Model B has no andy/hazel/shadow: they are skipped there. Exported so a harness
 *  that builds its own machine can do the same. Returns the regions filled. */
export function junkFill(cpu, seed, { only = ["zp", "main", "andy", "hazel", "shadow", "swr"], hz0 = 0x300, hz1 = 0x1c00 } = {}) {
    const rnd = junkBytes(seed), m = cpu.ramRomOs, done = [];
    const fill = (name, a, b) => { for (let i = a; i < b; i++) m[i] = rnd(); done.push(name); };
    const master = !!cpu.model.isMaster;
    // jsbeeb's map (6502.js romSelect): 0-&7FFF main, &8000 ANDY, &9000 HAZEL, &B000 LYNNE,
    // then romOffset + bank * 16K for the sideways banks
    if (only.includes("zp")) fill("zp", 0x0000, 0x0090);
    if (only.includes("main")) fill("main", 0x0e00, 0x8000);
    if (master && only.includes("andy")) fill("andy", 0x8000, 0x9000);
    if (master && only.includes("hazel")) fill("hazel", 0x9000 + hz0, 0x9000 + hz1);
    if (master && only.includes("shadow")) fill("shadow", 0xb000, 0x10000);
    if (only.includes("swr"))
        for (let b = 0; b < 16; b++)
            if (cpu.model.swram?.[b]) fill(`swr${b}`, cpu.romOffset + b * 16384, cpu.romOffset + (b + 1) * 16384);
    return done;
}

/** "name>=value" (also >, <=, <, ==, !=), the name with :w (a word) or :sw (a signed
 *  word): RUN_UNTIL's and runUntil's condition, parsed. */
export function parseCond(t) {
    const m = /^([A-Za-z_][\w.]*(?:[+-](?:&[0-9A-Fa-f]+|0x[0-9A-Fa-f]+|\d+))?)(?::(w|sw|b))?\s*(>=|<=|==|!=|>|<|=)\s*(-?(?:&[0-9A-Fa-f]+|0x[0-9A-Fa-f]+|\d+))$/.exec(t.trim());
    if (!m) throw new Error(`${t} is not NAME[:w|:sw]>=VALUE (or >, <=, <, ==, !=)`);
    const neg = m[4].startsWith("-");
    const v = num(neg ? m[4].slice(1) : m[4]);
    return { sym: m[1], size: m[2] || "b", op: m[3] === "=" ? "==" : m[3], value: neg ? -v : v };
}

/** PRESS_WHEN's "KEY@COND": KEY a keys() name (SPACE) or an internal key number
 *  (98, &62); COND a parseCond condition, or a bare symbol meaning "!= 0" - and then
 *  the symbol is CLEARED before the BREAK, because a soft BREAK keeps RAM and a value
 *  left from the last run would press at once. A trailing ? makes it optional: a build
 *  without the symbol boots without the press. No @COND: press at once. */
export function parsePress(t) {
    let s = t.trim(), optional = false;
    if (s.endsWith("?")) { optional = true; s = s.slice(0, -1); }
    const [k, c] = s.split("@");
    const key = /^(\d+|&[0-9A-Fa-f]+|0x[0-9A-Fa-f]+)$/.test(k) ? num(k) : k;
    if (!c) return { key, cond: null, clear: false, optional };
    const bare = /^[A-Za-z_][\w.]*$/.test(c);
    return { key, cond: bare ? { sym: c, size: "b", op: "!=", value: 0 } : parseCond(c), clear: bare, optional };
}

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
    const symPath = symbols || disc.replace(/\.[sd]sd$/i, ".symbols.json");  // .ssd or .dsd
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
    //   Three options, each also an environment variable so ANY harness takes them
    // without a change (an option given to boot() wins over the variable):
    //   junk / JUNK=seed     every RAM filled from junkFill(seed) after the power-on, then
    //                        a SOFT BREAK, which keeps it - a real machine after a power-on
    //                        or another program, not jsbeeb's zeros. JUNK_ONLY=zp,main,...
    //                        narrows the regions, JUNK_HZ0/JUNK_HZ1 HAZEL's span (junkFill).
    //                        The same seed is the same bytes: a failure is reproducible.
    //                        phX's rule: nothing may read RAM it did not write - a real
    //                        Master's RAM after a run (KC's SHIFT+BREAK) is not zeros
    //   pressWhen / PRESS_WHEN=KEY@COND   press KEY (a keys() name, or an internal key
    //                        number) once COND holds (pressWhen() below), e.g. a
    //                        disclaimer's SPACE@dc_secs
    //   runUntil / RUN_UNTIL=COND          after the settle, run on until COND holds
    //                        (runUntil() below), e.g. RUN_UNTIL=row:sw>=2990 - an oracle
    //                        for something late in a sequence, without its own start code
    //   prepare(h)           called with the machine made and the disc in, BEFORE the
    //                        BREAK: hooks that must see the boot itself (the DFS's loads:
    //                        examples/verify_disc) go on here, with { afterBoot: false }
    h.boot = async ({ field, settle = 150, fieldBytes = 1, shiftFrames = 50,
                      junk = process.env.JUNK, pressWhen = process.env.PRESS_WHEN,
                      runUntil = process.env.RUN_UNTIL, prepare } = {}) => {
        h.s = new MachineSession(h.model, { tube });
        await h.s.initialise();
        await h.s.boot(30);
        h.cpu = h.s._machine.processor;
        h.s.loadDisc(disc);
        h.junked = null;
        if (junk !== undefined && junk !== "") {
            const seed = num(junk, 1);
            h.junked = { seed, regions: junkFill(h.cpu, seed, {
                only: (process.env.JUNK_ONLY || "zp,main,andy,hazel,shadow,swr").split(","),
                hz0: num(process.env.JUNK_HZ0, 0x300), hz1: num(process.env.JUNK_HZ1, 0x1c00) }) };
            console.error(`${h.name}: JUNK=${seed}: ${h.junked.regions.join(" ")} filled, then a soft BREAK`);
        }
        h._press = pressWhen ? (typeof pressWhen === "string" ? parsePress(pressWhen) : pressWhen) : null;
        if (h._press) h._press.addr = h._press.cond ? h.sym(h._press.cond.sym) : undefined;
        if (h._press?.cond && h._press.addr === undefined && !h._press.optional)
            die(`pressWhen: no ${h._press.cond?.sym} in ${symPath} (add ? to make it optional)`);
        if (h._press?.clear && h._press.addr !== undefined) h.wr(h._press.addr, [0], ramOf(h._press.addr));
        if (prepare) await prepare(h);
        h.s.keyDown(h.keys.SHIFT); h.s.reset(h.junked === null); await h.s.runFrames(shiftFrames); h.s.keyUp(h.keys.SHIFT);
        h.frames = shiftFrames + (await h.pressWhen());
        await h.s.runFrames(settle);
        h.frames += settle;
        if (field !== undefined) {
            const rdf = () => (fieldBytes === 2 ? h.word(field, "main") : h.byte(field, "main"));
            const f0 = rdf();
            await h.s.runFrames(10);
            if (rdf() === f0)
                die(`the field counter at ${hex(field, 2)} did not move in 10 fields: the disc did not boot, ` +
                    "or that is not the counter", { where: h.where() });
        }
        h.booted = true;
        if (runUntil) h.frames += await h.runUntil(runUntil);
        return h.s;
    };

    // a symbol's RAM for h.rd/h.wr: main in &3000-&7FFF, nothing to name below; a
    // condition on a sideways address is refused (which bank would it mean?)
    const ramOf = (a) => {
        if (a >= 0x8000 && a < 0xc000) die(`${hex(a)} is in the sideways window: a condition reads RAM below &8000`);
        return a >= 0x3000 && a < 0x8000 ? "main" : undefined;
    };
    const readCond = (c) => {
        const a = h.need(c.sym);
        const v = c.size === "b" ? h.byte(a, ramOf(a)) : h.word(a, ramOf(a));
        return c.size === "sw" && v >= 0x8000 ? v - 0x10000 : v;
    };
    const holds = (c, v) => ({ ">=": v >= c.value, ">": v > c.value, "<=": v <= c.value, "<": v < c.value,
                               "==": v === c.value, "!=": v !== c.value })[c.op];
    /** Run on, a field (`step`) at a time, until `cond` holds - a parseCond string
     *  ("row:sw>=2990") or {sym, size, op, value} - within `budget` fields; exit 2 if
     *  it never does (a clock that never got there is not a result). Returns the
     *  fields run. phX's SEQ_ROW (its music row), generalised. */
    h.runUntil = async (cond, { budget = 40000, step = 1 } = {}) => {
        const c = typeof cond === "string" ? parseCond(cond) : cond;
        let n = 0;
        while (!holds(c, readCond(c))) {
            if (n >= budget) die(`runUntil ${c.sym} ${c.op} ${c.value}: not in ${budget} fields (it is ${readCond(c)})`, { where: h.where() });
            await h.s.runFrames(step); n += step;
        }
        return n;
    };
    /** Press the boot's pressWhen key once its condition holds (holding it `hold`
     *  fields), within `budget` fields. 0 if there is none, or it is optional and the
     *  build lacks its symbol. Returns the fields run. phX's skipDisclaimer: its !BOOT's
     *  countdown (DC_SECS set) waited for SPACE. */
    h.pressWhen = async (spec = h._press) => {
        if (!spec || (spec.cond && h.sym(spec.cond.sym) === undefined)) return 0;
        const { key, cond, hold = 3, budget = 600 } = spec;
        let n = 0;
        if (cond) while (!holds(cond, readCond(cond))) {
            if (++n > budget) die(`pressWhen ${key}: ${cond.sym} ${cond.op} ${cond.value} never held in ${budget} fields`);
            await h.s.runFrames(1);
        }
        if (typeof key === "number") { h.keyDownRaw(key); await h.s.runFrames(hold); h.keyUpRaw(key); }
        else {
            const k = h.keys[key] ?? key;
            h.s.keyDown(k); await h.s.runFrames(hold); h.s.keyUp(k);
        }
        return n + hold;
    };
    /** After a harness's own BREAK (h.s.autoboot, h.s.reset): the boot's pressWhen
     *  again (call beforeBreak() before the BREAK). Returns the fields run. */
    h.afterBreak = async () => h.pressWhen();
    /** Before a harness's own BREAK: clear the pressWhen symbol as boot() does. */
    h.beforeBreak = () => {
        if (h._press?.clear && h._press.addr !== undefined) h.wr(h._press.addr, [0], ramOf(h._press.addr));
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
