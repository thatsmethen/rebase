from pathlib import Path
import sys
H=Path(__file__).resolve().parent;R=H.parents[4]
sys.path.insert(0,str(R/"research/evidence/cubase-static/cpr-map-clock-001/attributes"))
import source_tools as s
s.derive([0x10020f2e8,0x10020e354,0x10020e7c8],H/"pass1")
