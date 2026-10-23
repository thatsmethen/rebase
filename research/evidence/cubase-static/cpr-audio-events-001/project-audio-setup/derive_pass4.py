from pathlib import Path
import sys
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent; R=H.parents[4]
sys.path.insert(0,str(R/'research/evidence/cubase-static/cpr-map-clock-001/attributes'))
import source_tools as s
s.derive([0x10319b8b8,0x10319b860,0x10221e70c,0x10221e6c4],H/'pass4')
