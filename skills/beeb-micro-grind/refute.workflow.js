export const meta = {
  name: 'beeb-micro-grind-refute',
  description: 'The skeptics of an interrupted grind round: one agent per missing (candidate, lens), the candidate read from the round opt-<window>.json on disk',
  whenToUse: 'Resuming evaluate.workflow.js after it died between the optimisers and the skeptics (or in another session): args = the output of `python tools/grind.py todo build/grind/rN`, {round, items}, plus cpu and listing as evaluate.workflow.js takes them',
  phases: [
    { title: 'Refute', detail: 'a skeptic per missing lens, writing build/grind/r<round>/skeptic-<window>-<i>-<lens>.json as evaluate.workflow.js does' },
  ],
}

// beeb-port-kit, MIT, Kieran Connell 2026. From Stryker's Run's .claude/skills/beeb-micro-grind.
// The skeptics of evaluate.workflow.js, with the candidate read from disk (a workflow script has no
// file access, and 200 candidates are too big for args): VERDICT and LENSES are copied from it word
// for word, so `python tools/grind.py add build/grind/rN` sees no difference.
const ROUND = args.round
const DIR = `build/grind/r${ROUND}`
const CPU = args.cpu || 'the CPU the project CLAUDE.md "Target" names'
const LISTING = args.listing || 'the build listing (CLAUDE.md "Build" names it)'
const SKILL = '.claude/skills/beeb-micro-grind/SKILL.md'

const VERDICT = {
  type: 'object',
  properties: {
    refuted: { type: 'boolean' },
    reason: { type: 'string' },
    cycles_per_execution_recounted: { type: 'number' },
    bytes_recounted: { type: 'integer' },
    file_written: { type: 'string' },
  },
  required: ['refuted', 'reason', 'file_written'],
}

const LENSES = [
  ['semantics', 'Every path. Find each entry into the changed lines (labels, fall-through from above, branches and JMP/JSR from anywhere, address tables, label+N operand references, RTS-to-pushed-address tricks) and each exit. For each, compare old and new on every register, flag (N, Z, C, V, D) and memory byte that is live afterwards - the annotation\'s in:/out: lists say what is live, but check them against the code that follows. Interrupts: can the interrupt handler (tools/dataflow_config.py ISR_ROOTS, and what it calls) run in between and see or change something differently? Stack depth and contents at every exit.'],
  ['machine', `${CPU}. Is every opcode and addressing mode real on that CPU (an NMOS 6502 has none of the 65C02 additions; a 65C12 has no BBR/BBS/RMB/SMB/WAI/STP; 65C02 timings differ: decimal-mode ADC/SBC +1, RMW abs,X)? Recount the cycles of old and new for every path with page crossings (+1 on indexed and (zp),Y reads that cross a page; on a 65C02 writes always cost the full amount) and taken branches (+1, +1 more across a page), and the bytes. If the byte count changes, everything after it in the region moves: check in ${LISTING} whether a hot branch or indexed table read after it starts or stops crossing a page, and count that. Branch ranges. Self-modifying code: an operand that some other code writes (labels like name = * + 1, stores to label+1/+2 anywhere in the sources) must stay where those writes put their bytes, with the same meaning. Code read as data. The assembler's syntax and the CPU setting of the section.`],
  ['project', 'This project\'s rules (CLAUDE.md, and the skill\'s "The rules"). Does it touch a PROTECTED line (tools/grind_config.py PROTECT, PROTECT_BYTES), a generated source (GENERATED), data or a table, raster-timed code, or memory whose meaning other code relies on (zero page shared by several names; scratch another routine expects intact)? Does it run with a sideways bank paged (ROMSEL), with ANDY in, or with ACCCON\'s X bit set (then &3000-&7FFF reads shadow RAM), and does the new code still read and write the RAM the old did? Does it fit the free space of its region (the region\'s ASSERT, the project\'s room table)? Does the game still play exactly as before - same state, same screen, same sound - on paths the gate\'s checks (tools/grind_config.py CHECKS) never reach: the front end, game over, the end of the game, define keys, a death?'],
]
const refutePrompt = (it, lens, path) => `You are a skeptic in the beeb-micro-grind skill (read ${SKILL}, "What a skeptic does", and the project's CLAUDE.md). Your lens: ${lens[0]}. ${lens[1]}

The candidate is number ${it.i} (counting from 0) of the "candidates" array in ${DIR}/opt-${it.window}.json: read that file and take that element. Its "old" and "new" are the exact lines of ${it.file} (around line ${it.line}) it replaces and what replaces them, "claim" the cycles and bytes it says it saves, "equivalence" its argument that nothing else changes, "relies_on" what the argument assumes. The window file is build/grind/w/${it.window}.txt (the annotated lines; if it is gone, annotate again: tools/analyse.py annotate, then tools/grind.py windows --all). The other candidates in that file are alternatives to it or independent of it; judge only this one.

Try to REFUTE it: find a path, a state or a count where it is wrong. Read the source yourself; do not trust the argument or the annotations without checking them. If you are not sure it is right, it is refuted. Write {"refuted": ..., "reason": "...", "cycles_per_execution_recounted": n, "bytes_recounted": n} to ${path}, then return the same object with file_written set.`

// items may be compact, [window, i, file, line, 'smp'] (the lenses' initials), to keep args small
const LENS_OF = { s: 'semantics', m: 'machine', p: 'project' }
const ITEMS = args.items.map(x => Array.isArray(x)
  ? { window: x[0], i: x[1], file: x[2], line: x[3], lenses: [...x[4]].map(c => LENS_OF[c]) } : x)
const jobs = []
for (const it of ITEMS) for (const name of it.lenses) jobs.push([it, LENSES.find(l => l[0] === name)])
log(`round ${ROUND}: ${ITEMS.length} candidates, ${jobs.length} skeptics to run`)

const votes = await pipeline(
  jobs,
  ([it, lens]) => agent(refutePrompt(it, lens, `${DIR}/skeptic-${it.window}-${it.i}-${lens[0]}.json`),
    { label: `refute ${lens[0]} ${it.file}:${it.line}`, phase: 'Refute', schema: VERDICT }),
)
const done = votes.filter(Boolean)
log(`${done.length} of ${jobs.length} skeptics answered (${done.filter(v => v.refuted).length} refuted); the rest: run grind.py todo again`)
return { round: ROUND, asked: jobs.length, answered: done.length }
