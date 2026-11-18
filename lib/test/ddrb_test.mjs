// ddrb_test.mjs - the System VIA's DDRB and the Master's CMOS chip. jsbeeb, headless, from BASIC.
//
//   node lib/test/ddrb_test.mjs          (from the kit's root)
//
// A Master's CMOS chip hangs on PB6 and PB7 of the System VIA, which MOS 3.20 sets as outputs
// once, at reset: DDRB &CF. A game that writes &0F there (as the template's setup_display did,
// to make the latch's PB0-3 outputs, which they already are) and later gives the machine back to
// the MOS for a load has the filing system read its CMOS settings as &FF: FDRIVE 7, 30 ms a step
// on a 1770. This reads CMOS byte 11 (FDRIVE in bits 0-2) by OSBYTE 161 three times on a Master:
//   as the MOS left DDRB        must be the real byte, not &FF          (the control)
//   after ?&FE42 = &0F          must be &FF                             (the trap)
//   after ?&FE42 = &CF again    must be the first reading               (the fix)
// and reads DDRB as each MOS leaves it: &CF on a Master, &0F on a Model B (B-DFS1.2 and B1770),
// so leaving it alone serves both.
// Exit code = verdict.
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const kit = join(here, "..", "..");
const { loadMachineSession } = await import(`file:///${join(kit, "template", "tools", "jsbeeb_src.mjs").split("\\").join("/")}`);
const MachineSession = await loadMachineSession();
const hex = (v) => "&" + v.toString(16).toUpperCase().padStart(2, "0");

async function machine(model) {
    const s = new MachineSession(model, { tube: false });
    await s.initialise();
    await s.runUntilPrompt(30);
    return s;
}
// a BASIC line typed, and the last number it printed (hex)
async function ask(s, line) {
    await s.runFor(100_000);
    await s.type(line);
    const out = (await s.runUntilPrompt(30)).screenText.split("\n").map((l) => l.trim()).filter((l) => /^[0-9A-F]+$/.test(l));
    return parseInt(out.at(-1), 16);
}
const CMOS11 = "A%=161:X%=11:PRINT ~(USR&FFF4 AND &FF0000) DIV &10000";

const result = { ddrb: {}, cmos11: {}, wrong: [] };
for (const model of ["Master", "B-DFS1.2", "B1770"]) {
    const s = await machine(model);
    result.ddrb[model] = hex(await ask(s, "PRINT ~?&FE42"));
}
if (result.ddrb.Master !== "&CF") result.wrong.push(`Master's DDRB ${result.ddrb.Master}, want &CF`);
for (const m of ["B-DFS1.2", "B1770"]) if (result.ddrb[m] !== "&0F") result.wrong.push(`${m}'s DDRB ${result.ddrb[m]}, want &0F`);

const s = await machine("Master");
const asLeft = await ask(s, CMOS11);
const withOF = await ask(s, `?&FE42=&0F:${CMOS11}`);
const putBack = await ask(s, `?&FE42=&CF:${CMOS11}`);
result.cmos11 = { asLeft: hex(asLeft), withDDRB0F: hex(withOF), putBack: hex(putBack) };
if (asLeft === 0xff) result.wrong.push("CMOS byte 11 read &FF with DDRB as the MOS left it: no control");
if (withOF !== 0xff) result.wrong.push(`CMOS byte 11 read ${hex(withOF)} with DDRB &0F, want &FF`);
if (putBack !== asLeft) result.wrong.push(`CMOS byte 11 read ${hex(putBack)} with DDRB &CF again, want ${hex(asLeft)}`);

result.pass = result.wrong.length === 0;
console.log(JSON.stringify(result));
process.exit(result.pass ? 0 : 1);
