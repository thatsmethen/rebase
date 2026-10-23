from pathlib import Path
import sys,json
H=Path(__file__).resolve().parent;ROOT=H.parents[4]
sys.path.insert(0,str(ROOT/'research/evidence/cubase-static/cpr-map-clock-001/attributes'))
import source_tools as s
s.derive([0x1003152b8,0x100315384,0x1037bce78,0x100314eb4,0x10031398c],H/'pass1')
