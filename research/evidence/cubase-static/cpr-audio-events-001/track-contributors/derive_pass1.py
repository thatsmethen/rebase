from pathlib import Path
import sys
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent; R=H.parents[4]
sys.path.insert(0,str(R/'research/evidence/cubase-static/cpr-map-clock-001/attributes'))
import source_tools as s
s.derive([0x1001e4fa0,0x1000e9cf8,0x1002139f0,0x1000ea130,0x1002136ec,0x100213534,0x1001e4da0,0x1001e4884],H/'pass1')
