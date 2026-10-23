"""Exclusive original-image function slices; no target execution."""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
sys.path.insert(0,str(ROOT/"research/evidence/cubase-static/cpr-map-clock-001/attributes"))
import source_tools as s
PASSES={1:[0x100211a7c,0x10021225c,0x1002126dc,0x1002c2040,0x1002eeea8,0x100112ca8,0x100110c18],2:[0x10035a0f4,0x10035a744,0x10035a0d4,0x10035a0e4,0x1002b603c,0x1002c2198,0x1002c2c58,0x1002c2aa8,0x1002c2748,0x1002c3d7c,0x1001113f8,0x100112df8],3:[0x1002b5e20,0x10035a2b8,0x1002c3968,0x1002ee09c,0x1002ee24c,0x1002ee258,0x1002ef7a8],4:[0x1002b6664,0x1002b6504,0x1002c4700,0x1002c4790,0x1002c47b8,0x1002c4534,0x1002c3730,0x1002d8c20,0x1002ee24c,0x1002c2748,0x10035a640],5:[0x1002ed698,0x1002d8cd0],6:[0x1002ef6b4],7:[0x1002ef378],8:[0x1002d89fc,0x1002ef4d8,0x1002d9034,0x1002d90cc,0x1002d9114,0x1002d8d5c],9:[0x1002d91a4,0x1002d9620,0x1002d96e8,0x1002d96f0,0x1002d976c,0x1002d9830],10:[0x1002ede48]}
if __name__=="__main__":
 n=int(sys.argv[1]); destination=HERE/f"pass{n}"
 if destination.exists(): raise SystemExit("Refusing to replace capture")
 print(s.derive(PASSES[n],destination))
