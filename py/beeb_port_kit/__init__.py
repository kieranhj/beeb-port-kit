"""beeb_port_kit - the Python tool code that was identical, or nearly, between
two C64 -> BBC Micro ports (Paradroid, Edge Grinder), packaged so a third
port can fork it.

The consumption model is copy-and-hack: take the module you need into your
project's tools/, keep its header, and change what your game needs. It is a
package as well so the tests can import it.

    zx02     Daniel Serpell's ZX02 compressor and decompressor, in Python -
             what NEW ports use: half the depacker, twice the speed
    zx0      Einar Saukas's ZX0, the same in Python - what the two shipping
             discs use, kept so their tools stay byte-identical
    dfs      DFS .ssd images: catalogue, layout, padding, the stream checks
    modes    BBC MODE 0/1/2/4/5 pixel packing, colours, dither, render
    c64      Pepto palette, hires/multicolour decode, sprites, charsets, tables
    art      PNG sheets of cells <-> logical colours, palette PNG, guide layer
    cpc      Amstrad .dsk and screen readers, for a CPC port's artwork

Pillow is the only dependency, and only art, cpc.cpcscr and modes.render()
need it. Nothing here imports either port's code; only the tests do, by path.
"""

from . import zx0, zx02, dfs, modes, c64, art, cpc      # noqa: F401
from .dfs import DiscError, Entry, Image                 # noqa: F401
from .art import Sheet, ArtError                         # noqa: F401
from .cpc import Dsk                                     # noqa: F401

__version__ = "0.1.0"
__all__ = ["zx0", "zx02", "dfs", "modes", "c64", "art", "cpc",
           "DiscError", "Entry", "Image", "Sheet", "ArtError", "Dsk"]
