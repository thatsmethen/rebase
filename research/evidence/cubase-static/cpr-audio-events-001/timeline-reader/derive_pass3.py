from pathlib import Path
import sys
H=Path(__file__).resolve().parent;R=H.parents[4]
sys.path.insert(0,str(R/"research/evidence/cubase-static/cpr-map-clock-001/attributes"))
import source_tools as s
s.derive([0x101c22c0c,0x101d9b3b4,0x101d9d450,0x101d9d790,0x101d9f068,0x101c3568c],H/"pass3")
