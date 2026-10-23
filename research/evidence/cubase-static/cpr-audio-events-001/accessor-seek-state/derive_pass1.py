from pathlib import Path
import sys
H=Path(__file__).resolve().parent;R=H.parents[4]
sys.path.insert(0,str(R/"research/evidence/cubase-static/cpr-map-clock-001/attributes"))
import source_tools as s
s.derive([0x10036f89c,0x10036eff0,0x1003261a8,0x10030a1dc,0x10033a4f8,0x10033a054],H/"pass1")
