// jsbeeb_src.mjs - find the jsbeeb the MCP is using, and say which one it is.
//
// beeb-port-kit template, MIT, Kieran Connell 2026.
//
// The headless harnesses (probe_shot.mjs, verify_dynamic.mjs) drive the same
// MachineSession class the jsbeeb MCP server uses, so they have to import it from
// wherever `npx jsbeeb-mcp` cached the package. That path used to be hardcoded:
//
//   C:/Users/.../npm-cache/_npx/e76f2a7d329553db/node_modules/jsbeeb/src
//
// which named one user, one machine, and an npx cache hash that changes whenever the
// spec does. Worse, it was silent: updating jsbeeb-mcp from 3.3.0 to 3.4.0 swapped
// jsbeeb 1.24.1 for 1.25.0 underneath that exact path, and the harnesses would have
// carried on measuring against a different emulator without a word (2026-09-07).
//
// So: resolve it, and PRINT THE VERSION on stderr, because a harness that cannot say
// which emulator it measured with is not an instrument.
//
// JSBEEB_SRC still overrides everything, for a checkout or an odd install.

import { existsSync, readdirSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

function versionAt(dir) {
    const pkg = join(dir, "package.json");
    if (!existsSync(join(dir, "src", "machine-session.js")) || !existsSync(pkg)) return null;
    try {
        return JSON.parse(readFileSync(pkg, "utf8")).version || "0.0.0";
    } catch {
        return null;
    }
}

const cmp = (a, b) => {
    const pa = a.split(".").map(Number), pb = b.split(".").map(Number);
    for (let i = 0; i < 3; i++) if ((pa[i] || 0) !== (pb[i] || 0)) return (pa[i] || 0) - (pb[i] || 0);
    return 0;
};

/** Absolute path to jsbeeb's src/, plus the version found there. */
export function resolveJsbeebSrc() {
    const override = process.env.JSBEEB_SRC;
    if (override) {
        const dir = join(override, "..");
        return { src: override.split("\\").join("/"), version: versionAt(dir) || "unknown (JSBEEB_SRC)" };
    }

    const roots = [
        join(process.cwd(), "node_modules"),
        process.env.LOCALAPPDATA ? join(process.env.LOCALAPPDATA, "npm-cache", "_npx") : null,
        join(homedir(), ".npm", "_npx"),
    ].filter(Boolean);

    const found = [];
    for (const root of roots) {
        if (!existsSync(root)) continue;
        // either <root>/jsbeeb, or <root>/<npx-hash>/node_modules/jsbeeb
        for (const dir of [join(root, "jsbeeb"),
                           ...readdirSync(root, { withFileTypes: true })
                               .filter((e) => e.isDirectory())
                               .map((e) => join(root, e.name, "node_modules", "jsbeeb"))]) {
            const v = versionAt(dir);
            if (v) found.push({ dir, version: v });
        }
    }
    if (!found.length) {
        throw new Error(
            "cannot find jsbeeb. Run `npx jsbeeb-mcp` once so npm caches it, " +
            "or set JSBEEB_SRC to a jsbeeb checkout's src/ directory.");
    }
    found.sort((a, b) => cmp(b.version, a.version));
    const best = found[0];
    return { src: join(best.dir, "src").split("\\").join("/"), version: best.version };
}

/** Import MachineSession, announcing the jsbeeb it came from. */
export async function loadMachineSession() {
    const { src, version } = resolveJsbeebSrc();
    console.error(`[jsbeeb ${version}] ${src}`);
    const { MachineSession } = await import(`file:///${src}/machine-session.js`);
    return MachineSession;
}
