"""Reproduce only this study's exact raw intervals in a new study directory.

Original bytes are immutable; these metadata intervals are not proved bodies.
Run this before analyze_pass.mjs. Do not rerun against a sealed study.
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT / "research/evidence/cubase-static/cpr-map-clock-001/attributes"))
import source_tools as s

PASSES = {
    1: [0x101D3E5A0],
    2: [0x101FF6070, 0x101FF825C, 0x101FFE6BC,
        0x101A17CD4, 0x101A17D08, 0x101A17D1C],
    3: [0x1001F9090, 0x1001F95F8, 0x101D3E5A8],
    4: [0x101D42E70, 0x1001FD4F4],
    5: [0x1016E3794, 0x10020EE24, 0x1016E6744,
        0x1016E300C, 0x1016E3990, 0x1016E39C8],
    6: [0x10020E354],
    7: [0x10020E7C8, 0x10171C5A0, 0x101C225D0, 0x1007DDD24],
}

if __name__ == "__main__":
    selected = int(sys.argv[1])
    destination = HERE / f"pass{selected}"
    if destination.exists():
        raise SystemExit("Refusing to replace an existing capture directory.")
    print(s.derive(PASSES[selected], destination))
