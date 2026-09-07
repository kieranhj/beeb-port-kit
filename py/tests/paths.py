"""Where the two ports and the reference compressor live on this machine.
The tests that need them skip when they are absent."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

EDGE_TOOLS = Path(os.environ.get(
    "EDGE_BEEB", r"C:\Users\khcon\OneDrive\BEEB\Repos\edge-beeb")) / "tools"
PARADROID_TOOLS = Path(os.environ.get(
    "PARADROID_BEEB", r"C:\Users\khcon\OneDrive\Projects\Paradroid")) / "tools"
ZX0_EXE = Path(os.environ.get("ZX0_EXE", r"C:\Users\khcon\OneDrive\BEEB\Bin\zx0.exe"))
ZX02_EXE = Path(os.environ.get("ZX02_EXE", r"C:\Users\khcon\OneDrive\BEEB\Bin\zx02.exe"))
