from pathlib import Path
import sys
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent;R=H.parents[4]
sys.path.insert(0,str(R/'research/evidence/cubase-static/cpr-map-clock-001/attributes'))
import source_tools as s
s.derive([0x103101840,0x1031022a0,0x1007ddd64,0x10221d068],H/'pass1')
