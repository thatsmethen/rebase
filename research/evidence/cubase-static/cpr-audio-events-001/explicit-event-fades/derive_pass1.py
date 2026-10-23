from pathlib import Path
import sys
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent;R=H.parents[4]
sys.path.insert(0,str(R/'research/evidence/cubase-static/cpr-map-clock-001/attributes'))
import source_tools as s
assert not (H/'pass1/derivation.json').exists()
s.derive([0x1000ea7b4,0x1000ea95c,0x1016e5830],H/'pass1')
