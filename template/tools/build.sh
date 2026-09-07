#!/bin/sh
# The same build as build.ps1, from bash (Git Bash on Windows, or a Unix
# host with a beebasm on the path): PowerShell turns beebasm's progress on
# stderr into a terminating error under some profiles, and this does not.
# Same names and disc titles as build.ps1. Flags come from the environment:
#   RELEASE=1 MASTER=1 sh tools/build.sh
# Run from the project root: beebasm resolves INCLUDE/INCBIN from the cwd.
set -e
R=${RELEASE:-0}; M=${MASTER:-0}
BEEB=${BEEBASM:-/c/Users/khcon/OneDrive/BEEB/Bin/beebasm.exe}
[ -x bin/beebasm.exe ] && BEEB=bin/beebasm.exe
STEM=GAME; TITLE=GAME
[ "$M" = 1 ] && { STEM=$STEM-MASTER; TITLE=${TITLE}M; }
mkdir -p build
"$BEEB" -i src/main.asm -do build/$STEM-RAW.SSD -opt 3 -title "$TITLE" \
    -D RELEASE=$R -D MASTER=$M -v > build/$STEM.lst
python tools/make_disc.py build/$STEM-RAW.SSD build/$STEM.SSD build/$STEM-200K.SSD
