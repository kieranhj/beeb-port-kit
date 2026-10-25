"""
dataflow_config.py - what beebgame's dataflow analyses need to know about this
game (tools/analyse.py passes it as --config). beebgame's
tools/dataflow/gamecfg.py documents every field; anything left out keeps its
default there. The template's values below; a port changes them as it grows.
"""

# The sources whose findings are reported: everything under src/.
GAME_DIR = 'src'

# The interrupt's entry (lib/irq.6502). The analysis treats it as able to run
# between any two instructions: every byte it reads is live everywhere, every
# byte it writes is never a known constant.
ISR_ROOTS = ('irq_handler',)

# Pointers the interrupt reads only its own data through (a sound or music
# player's stream pointer). Empty: the analysis then assumes they read nothing
# of the game's variables only for those listed, so leave a pointer out if
# unsure. The template's interrupt has none.
ISR_DATA_POINTERS = ()

# Zero-page pointers the game writes the SCREEN through: stores through them
# are taken never to hit a variable. The template's fill and depacker write
# through zxdst/fill_ptr into variables' memory as well, so none are listed.
SCREEN_POINTERS = ()

# Subroutines whose operands follow the JSR inline (none in the template), and
# the object model ranges.py can keep per-type facts with (none either).
INLINE_HELPERS = {}
OBJECTS = None

# patterns.py's const_var looks for variables in these segments. A Baron build
# has one segment per SECTION and its zero page in no segment, so this names
# none; const_load still finds bytes that are one known value.
VAR_SEGMENTS = ()

# ---- an interrupt that exits into the MOS (tools/isr_model.py) -------------
# OFF. Upstream takes an interrupt with any exit it cannot follow (a JMP to the
# MOS, a JMP (vector), a self-modified operand) or a store through a pointer to
# read and write ALL memory, and then no byte is a known value anywhere.
# lib/irq.6502 ends in RTI, so the template has no such exit. A port whose
# handler chains to the MOS (JMP (old IRQ1V), to keep its tick) or calls it
# (OSWORD through JMP (WORDV)) sets ISR_MODEL = True and names each such site:
# the MOS is then taken to return having touched only MOS_WORKSPACE. Any exit
# not named still means all memory (report.md's notes name it); a site named
# but no longer reached stops the run. tools/isr_model.py has the rest.
ISR_MODEL = False

# 'file:line' (as report.md's notes print it) -> why. A label-relative helper
# keeps them from going stale when code moves (Stryker's Run's _at):
#   def _at(path, label, code):
#       lines = open(path, encoding='utf-8').read().splitlines()
#       start = next(i for i, l in enumerate(lines) if l.split()[:1] == ['.' + label])
#       for i in range(start, len(lines)):
#           if code in lines[i].split(chr(92))[0]:
#               return '%s:%d' % (path, i + 1)
#       raise ValueError('%s: no %r after .%s' % (path, code, label))
#   ISR_MOS_EXITS = {_at('src/main.6502', 'irq_chain', 'JMP (old_irq1v)'): 'the MOS'}
ISR_MOS_EXITS = {}

# What the MOS's interrupt path may read and write, inclusive ranges. AN
# ASSUMPTION from the memory map, not measured; Stryker's Run's, which kept
# &F8/&F9 for itself (the MOS does not write them) and &0300-&03C7:
#   ((0x00E2, 0x00F7), (0x00FA, 0x00FF), (0x0200, 0x02FF), (0x03C8, 0x03FF),
#    (0x0800, 0x087F), (0x0A00, 0x0AFF), (0x0D00, 0x0DFF))
MOS_WORKSPACE = ()

# Stores through a pointer in the interrupt: 'file:line' -> (lo, hi), all it can hit.
ISR_POINTER_STORES = {}

# Per root (an ISR_ROOTS name): bytes its handler pushes on entry and pulls back
# before it leaves, so the interrupted code never sees them change (check by hand).
ISR_PRESERVES = {}
