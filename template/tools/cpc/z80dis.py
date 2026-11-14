"""Disassemble a 64K memory image via sna2skool: python tools/z80dis.py MEM.bin START END"""
import sys
from skoolkit import sna2skool
mem, s, e = sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3], 16)
sna2skool.main(['-H', '-o', '0', '-s', str(s), '-e', str(e), mem])
