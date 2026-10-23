"""Candidate-only encoded field accesses; not receiver proof."""
from pathlib import Path
import sys,struct,json
H=Path(__file__).resolve().parent;R=H.parents[4]
sys.path.insert(0,str(R/'research/evidence/cubase-static/cpr-map-clock-001/attributes'));import source_tools as s
rows=[]
for a in range(0x101710000,0x101730000,4):
 w=int.from_bytes(bytes.fromhex(s.region(a,4)['bytes_hex']),'little');kind=None
 if w&0xffc00000 in [0xf9000000,0xf9400000] and (w>>10&0xfff)*8==0x128:kind='loadstore+128'
 if w&0xffc00000 in [0xa9000000,0xa9400000] and (w>>15&0x7f)*8 in[0x120,0x128]:kind='pair+120or128'
 if w&0xffc00000==0x91000000 and (w>>10&0xfff)==0x128:kind='address+128'
 if kind:rows.append(dict(address=hex(a),word=hex(w),kind=kind,containing=hex(s.containing(a))))
(H/'provider-field-candidates.json').write_text(json.dumps(dict(source_sha256=s.PIN,range=['0x101710000','0x101730000'],rows=rows,limitations='Encoded candidates only. Register receiver and paired second offset need local def-use.'),indent=2)+'\n')
print(json.dumps(rows,indent=2))
