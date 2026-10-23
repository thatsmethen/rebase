from pathlib import Path
import sys
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent; R=H.parents[4]
sys.path.insert(0,str(R/'research/evidence/cubase-static/cpr-map-clock-001/attributes'))
import source_tools as s
s.derive([0x100965f54,0x101c25998,0x101c259d8,0x1031983e0,0x1031695b8,0x10171e9fc,0x10310a240],H/'pass2')
