// model_stub_test.mjs - py/beeb_port_kit/dfs.model_stub's !BOOT on real boots:
// a Master runs the game, a Model B gets the message and BASIC. jsbeeb, headless.
//
//   node lib/test/model_stub_test.mjs     (from the kit's root; PYTHON= to choose one)
//
// The "game" is 4K that belongs at &0E00 - over a Model B's DFS workspace, which
// is the whole point - whose first bytes store &A5 at &70 and spin. Two discs:
//   stub.ssd   !BOOT = model_stub(game, &0E00, &0E00), *OPT 4,2
//   plain.ssd  !BOOT = the game itself at &0E00, *OPT 4,2: the CONTROL - the
//              1942 port measured a B's DFS hanging inside a load there
// and each is SHIFT+BREAKed on jsbeeb's B (DFS 1.2, 8271), B1770 and Master:
//   stub on the Master       &70 = &A5, and the game's 4K at &0E00 intact
//   stub on a B              the message on screen, BASIC's prompt, &70 untouched,
//                            and a typed PRINT answered (the machine is alive)
//   plain on a B             recorded, not judged: what the stub is for
// Exit code = verdict on the first two.
import { execFileSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const kit = join(here, "..", "..");
const { loadMachineSession } = await import(`file:///${join(kit, "template", "tools", "jsbeeb_src.mjs").split("\\").join("/")}`);
const out = join(here, "build");
mkdirSync(out, { recursive: true });
const MSG = "This game needs a BBC Master";

// the game: LDA #&A5 : STA &70 : JMP * , then a 4K pattern
const py = `
import sys; sys.path.insert(0, ${JSON.stringify(join(kit, "py"))})
from beeb_port_kit import dfs
game = bytes([0xA9, 0xA5, 0x85, 0x70, 0x4C, 0x04, 0x0E]) + bytes((i * 7 + 3) & 255 for i in range(4096 - 7))
data, load, ex = dfs.model_stub(game, 0x0E00, 0x0E00, text=${JSON.stringify(MSG)})
for name, f in (("stub", dfs.Entry("!BOOT", data, load, ex)), ("plain", dfs.Entry("!BOOT", game, 0x0E00, 0x0E00))):
    files = {"!BOOT": f}
    dfs.to_host(files)
    open(${JSON.stringify(out)} + "/" + name + ".ssd", "wb").write(dfs.build_image(files, ["!BOOT"], b"STUB", opt=2))
`;
execFileSync(process.env.PYTHON || "python", ["-c", py], { stdio: "inherit" });

const MachineSession = await loadMachineSession();
async function trial(model, disc) {
    const s = new MachineSession(model, { tube: false });
    await s.initialise();
    await s.boot(30);
    s.loadDisc(join(out, disc));
    s.drainOutput();
    await s.autoboot();
    await s.runFrames(250);
    let text = s.drainOutput().screenText || "";
    const r = { model, disc, marker: s.readMemory(0x70, 1)[0], message: text.includes(MSG),
                pc: s._machine.processor.pc.toString(16) };
    const game = Array.from(s.readMemory(0x0E07, 32));
    r.gameIntact = game.every((b, i) => b === ((i * 7 + 3) & 255));
    if (model !== "Master") {
        await s.type("PRINT 6*7\r");
        await s.runFrames(100);
        text = s.drainOutput().screenText || "";
        r.basicAlive = /\b42\b/.test(text);
    }
    s.destroy?.();
    return r;
}
const res = { trials: [] };
for (const model of ["Master", "B-DFS1.2", "B1770"]) res.trials.push(await trial(model, "stub.ssd"));
for (const model of ["B-DFS1.2", "B1770"]) res.trials.push(await trial(model, "plain.ssd"));
for (const t of res.trials) {
    if (t.disc !== "stub.ssd") continue;
    t.ok = t.model === "Master" ? t.marker === 0xA5 && t.gameIntact && !t.message
                                : t.marker !== 0xA5 && t.message && t.basicAlive;
}
res.pass = res.trials.filter((t) => t.disc === "stub.ssd").every((t) => t.ok);
console.log(JSON.stringify(res, null, 1));
process.exit(res.pass ? 0 : 1);
