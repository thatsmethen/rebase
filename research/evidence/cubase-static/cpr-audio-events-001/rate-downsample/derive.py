from pathlib import Path
import sys,json
H=Path(__file__).resolve().parent;ROOT=H.parents[4]
sys.path.insert(0,str(ROOT/'research/evidence/cubase-static/cpr-map-clock-001/attributes'))
import source_tools as s
s.derive([0x1003108f0,0x100310b84,0x10031179c],H/'pass1')
