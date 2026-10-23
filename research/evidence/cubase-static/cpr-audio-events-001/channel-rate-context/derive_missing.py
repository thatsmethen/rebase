"""Reproduce only declared original-image function intervals; target never executed."""
from pathlib import Path
import sys
H=Path(__file__).resolve().parent;R=H.parents[4]
sys.path.insert(0,str(R/'research/evidence/cubase-static/cpr-map-clock-001/attributes'));import source_tools as s
P={1:[0x101d99584,0x101d3fc3c],2:[0x1005c078c,0x101d99584,0x101d437e0],3:[0x1005c0b18,0x101d9e048,0x101d9e4dc],4:[0x1005cabb0,0x101d9b5d8,0x101d9b5f0],5:[0x101c6a130],6:[0x101c69b00,0x100494728,0x100494734,0x1004916f0,0x100491728],7:[0x101c6d040,0x101c6d160],8:[0x1005c7d40],9:[0x1005c76e0,0x1005c7e88],10:[0x101c875d8,0x101d1fbfc,0x101d206dc],11:[0x1004924d8],12:[0x102fc7df0,0x102fc8340],13:[0x101ed701c,0x100da4e44,0x101ecacf4],14:[0x102fc82b4,0x102fc797c],15:[0x10171c594,0x10171c5c4,0x101ed6e48,0x101f46378]}
# Separate destination mandatory so historical evidence is never overwritten.
if __name__=='__main__':
 destination=Path(sys.argv[1]);destination.mkdir(exist_ok=False)
 for n,addresses in P.items():s.derive(addresses,destination/f'pass{n}')
