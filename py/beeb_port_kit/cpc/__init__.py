"""Amstrad CPC readers, for a port whose nearest relative is the CPC one."""
from . import dsk, cpcscr                  # noqa: F401
from .dsk import Dsk, amsdos_header, strip_amsdos   # noqa: F401
