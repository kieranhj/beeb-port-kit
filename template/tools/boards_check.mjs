// boards_check.mjs - prove tools/boards.mjs still works in the jsbeeb this machine has.
//
// beeb-port-kit template, MIT, Kieran Connell 2026.
//
//     node tools/boards_check.mjs        prints one line per board, exits 1 on a failure
//
// boards.mjs reaches into jsbeeb's internals (cpu.writemem, cpu.romsel, cpu.model.swram,
// cpu.ramRomOs), so a jsbeeb update could break it without a word - and a broken board
// emulator would let a port's bank code "pass" on a board it has never run on. This runs
// a few instructions on a Model B for each board: page bank 4 for reading, select bank 5
// for writing through the board's own register, store &AA at &8000, select bank 4 for
// writing, store &55 at &8001. Then &AA must be in bank 5 and not bank 4, &55 in bank 4,
// and exactly one store counted as a mismatch (the first: written to 5 with 4 paged).

import { loadMachineSession } from "./jsbeeb_src.mjs";
import { boardEmu } from "./boards.mjs";

const MachineSession = await loadMachineSession();

// the store into the board's select register, for a bank n, as 6502 bytes
const SELECT = {
    watford: (n) => [0x8d, 0x30 + n, 0xff],                         // STA &FF3n (any value)
    solidisk: (n) => [0xa9, n, 0x8d, 0x60, 0xfe],                   // LDA #n : STA &FE60 (ORB)
};
const SETUP = {
    watford: [],
    solidisk: [0xa9, 0x0f, 0x8d, 0x62, 0xfe],                       // LDA #&0F : STA &FE62 (DDRB)
};

let failed = 0;
for (const kind of ["watford", "solidisk"]) {
    const s = new MachineSession("B-DFS1.2", { tube: false });
    await s.initialise();
    await s.boot(30);
    const cpu = s._machine.processor;
    boardEmu(cpu, kind);
    const code = [
        0x78,                                   // SEI
        ...SETUP[kind],
        0xa9, 0x04, 0x8d, 0x30, 0xfe,           // LDA #4 : STA &FE30 - bank 4 paged for reading
        ...SELECT[kind](5),                     // writes go to bank 5
        0xa9, 0xaa, 0x8d, 0x00, 0x80,           // LDA #&AA : STA &8000
        ...SELECT[kind](4),                     // writes go to bank 4
        0xa9, 0x55, 0x8d, 0x01, 0x80,           // LDA #&55 : STA &8001
    ];
    const at = 0x2000, end = at + code.length;
    s.writeMemory(at, [...code, 0x4c, end & 0xff, end >> 8]);       // JMP to itself
    cpu.pc = at;
    await s.runFor(4000);
    const bank = (n, a) => cpu.ramRomOs[cpu.romOffset + n * 16384 + (a - 0x8000)];
    const checks = [
        ["&AA in bank 5 at &8000", bank(5, 0x8000) === 0xaa],
        ["bank 4's &8000 untouched", bank(4, 0x8000) !== 0xaa],
        ["&55 in bank 4 at &8001", bank(4, 0x8001) === 0x55],
        ["one mismatched store", [...cpu.boardMismatch.values()].reduce((a, b) => a + b, 0) === 1],
    ];
    const bad = checks.filter(([, ok]) => !ok).map(([what]) => what);
    console.log(`${kind}: ${bad.length ? "FAIL - " + bad.join(", ") : "ok"}`);
    failed += bad.length;
}
process.exit(failed ? 1 : 0);
