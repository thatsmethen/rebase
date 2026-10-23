from pathlib import Path
import sys
H=Path(__file__).resolve().parent;R=H.parents[4]
sys.path.insert(0,str(R/"research/evidence/cubase-static/cpr-map-clock-001/attributes"))
import source_tools as s
s.derive([4298155792, 4298155796, 4298155816, 4298155832, 4298155848, 4298155936, 4298157708, 4298157752],H/"pass1")
