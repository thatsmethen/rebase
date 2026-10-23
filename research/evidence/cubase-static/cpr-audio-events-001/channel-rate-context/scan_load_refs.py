"""Encoded ADRP/unsigned-LDR target candidates; intervening clobbers require review."""
import sys,struct,json
from pathlib import Path
H=Path(__file__).resolve().parent; R=H.parents[4]
sys.path.insert(0,str(R/'research/evidence/cubase-static/cpr-map-clock-001/attributes'));import source_tools as s
T={0x10395d5b0,0x104f864f2};rows=[]
c=next(x for x in s.sections if x['name']=='__text');b=s.data[c['offset']:c['offset']+c['size']]
for i,(w,) in enumerate(struct.iter_unpack('<I',b)):
 if w&0x9f000000!=0x90000000:continue
 pc=c['address']+i*4;imm=((w>>5&0x7ffff)<<2)|(w>>29&3)
 if imm&(1<<20):imm-=1<<21
 page=(pc&~4095)+(imm<<12)
 if page not in {t&~4095 for t in T}:continue
 reg=w&31
 for d in range(1,13):
  if i*4+d*4>=len(b):break
  v=struct.unpack_from('<I',b,i*4+d*4)[0]
  if v>>5&31!=reg:continue
  scale={0x3dc00000:16,0xfd400000:8,0xf9400000:8,0xbd400000:4,0xb9400000:4}.get(v&0xffc00000)
  if scale is None:continue
  a=page+(v>>10&4095)*scale
  if a in T:rows.append(dict(adrp=hex(pc),load=hex(pc+4*d),target=hex(a),caller=hex(s.containing(pc)),distance=d,register=reg))
(H/'engine-key-load-candidates.json').write_text(json.dumps(dict(source_sha256=s.PIN,candidates=rows,limitation='Encoded address candidates only, no dataflow claim'),indent=2)+'\n')
print(json.dumps(rows,indent=2))
