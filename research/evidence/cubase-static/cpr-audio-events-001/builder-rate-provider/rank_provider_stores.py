from pathlib import Path
import sys,struct,json
H=Path(__file__).resolve().parent;R=H.parents[4]
sys.path.insert(0,str(R/'research/evidence/cubase-static/cpr-map-clock-001/attributes'));import source_tools as s
rows=json.loads((H/'provider-store-candidates.json').read_text())['rows'];fs=sorted({int(x['containing'],16)for x in rows});out=[]
for a in fs:
 end=s.starts[s.starts.index(a)+1];calls=[]
 for i,(w,)in enumerate(struct.iter_unpack('<I',bytes.fromhex(s.region(a,end-a)['bytes_hex']))):
  if w&0x7c000000!=0x14000000:continue
  imm=w&0x3ffffff
  if imm&0x2000000:imm-=0x4000000
  t=a+4*i+4*imm
  if 0x10171b000<=t<=0x101727000:calls.append(dict(at=hex(a+4*i),target=hex(t)))
 if calls:out.append(dict(entry=hex(a),length=end-a,calls=calls))
(H/'root-related-store-candidates.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
