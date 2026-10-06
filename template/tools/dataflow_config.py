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
