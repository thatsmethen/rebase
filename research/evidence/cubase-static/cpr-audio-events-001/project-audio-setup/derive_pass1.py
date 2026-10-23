from pathlib import Path
import sys
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent; R=H.parents[4]
sys.path.insert(0,str(R/'research/evidence/cubase-static/cpr-map-clock-001/attributes'))
import source_tools as s
s.derive([0x100966640,0x100966a54,0x100956f80],H/'pass1')
