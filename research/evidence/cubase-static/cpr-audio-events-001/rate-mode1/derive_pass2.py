from pathlib import Path
import sys
H=Path(__file__).resolve().parent;R=H.parents[4]
sys.path.insert(0,str(R/"research/evidence/cubase-static/cpr-map-clock-001/attributes"))
import source_tools as s
s.derive([0x10030a664,0x10030a974],H/"pass2")
