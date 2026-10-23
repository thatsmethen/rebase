"""Exclusive derivatives for the prepared/pitch output ownership study."""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
sys.path.insert(0,str(ROOT/"research/evidence/cubase-static/cpr-map-clock-001/attributes"))
import source_tools as s
if __name__=="__main__":
 n=int(sys.argv[1]);destination=HERE/f"pass{n}"
 if destination.exists():raise SystemExit("Refusing to replace capture")
 print(s.derive([int(a,16) for a in sys.argv[2:]],destination))
