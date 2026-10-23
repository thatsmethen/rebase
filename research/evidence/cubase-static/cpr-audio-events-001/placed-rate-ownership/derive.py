"""New immutable original-byte slices; no target execution."""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
sys.path.insert(0,str(ROOT/"research/evidence/cubase-static/cpr-map-clock-001/attributes"))
import source_tools as s
PASSES={4:[0x100211a7c,0x10036b0bc,0x10036b244,0x10036aea0,0x10036aee8,0x10036af30,0x10036ae90,0x10011376c,0x10036cd94],3:[0x101d3eb24,0x10036e34c,0x10036e858,0x10036af9c,0x10036e964,0x10036ed34],2:[0x1003704cc,0x1003704d4,0x1003704e0,0x1003704e8,0x1003704f4,0x1003704fc,0x100370504,0x10037050c,0x100370518,0x100370520,0x100370528,0x100370530,0x10036ef28,0x101d3e5b0],1:[0x10036ec30,0x1001139d0,0x10036fca0,0x10036fea0,0x10036afc8,0x10036e97c,0x100370538]}
if __name__=="__main__":
 n=int(sys.argv[1]); destination=HERE/f"pass{n}"
 if destination.exists(): raise SystemExit("Refusing to replace capture")
 print(s.derive(PASSES[n],destination))
