"""Reproduce original-byte derivatives in a new, unsealed capture directory."""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
sys.path.insert(0,str(ROOT/"research/evidence/cubase-static/cpr-map-clock-001/attributes"))
import source_tools as s
PASSES={
    1: [0x1016e6744, 0x1016e1ce4, 0x1016e300c, 0x101c22dc0, 0x1002115a0, 0x10020ee24],
    2: [0x1016e1bd0, 0x1016e1894, 0x1016ea7fc],
    3: [0x1016e222c, 0x10174b610, 0x1017014e4],
    4: [0x1016e20b8, 0x103104c40, 0x10174b638],
    5: [0x1001fc8b0, 0x1016e4d98, 0x1016e2194, 0x101c247f4, 0x1016e70ec, 0x10174a698, 0x10174b56c, 0x101700d6c, 0x10171759c, 0x101700d64, 0x1001f5430],
    6: [0x101744d58, 0x1016e3990, 0x1016e3794],
    7: [0x101744688, 0x1016e39c8],
    8: [0x1017427e0, 0x101747fe4],
    9: [0x101742a98],
    10: [0x101725d9c],
}
if __name__=="__main__":
    n=int(sys.argv[1]); destination=HERE/f"pass{n}"
    if destination.exists(): raise SystemExit("Refusing to replace an existing capture")
    print(s.derive(PASSES[n],destination))
