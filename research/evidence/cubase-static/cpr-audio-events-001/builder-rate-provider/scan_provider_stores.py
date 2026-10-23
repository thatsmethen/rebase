from pathlib import Path
import sys,struct,json
H=Path(__file__).resolve().parent;R=H.parents[4]
sys.path.insert(0,str(R/'research/evidence/cubase-static/cpr-map-clock-001/attributes'));import source_tools as s
c=next(x for x in s.sections if x['name']=='__text');rows=[]
for i,(w,)in enumerate(struct.iter_unpack('<I',s.data[c['offset']:c['offset']+c['size']])):
 a=c['address']+i*4;kind=None
 if w&0xffc00000==0xf9000000 and (w>>10&0xfff)*8==0x128:kind='strx+128'
 if w&0xffc00000==0xa9000000 and (w>>15&0x7f)*8 in[0x120,0x128]:kind='stpx+120or128'
 if kind and w>>5&31!=31:rows.append(dict(address=hex(a),word=f'{w:08x}',kind=kind,containing=hex(s.containing(a)),receiver_register=w>>5&31))
(H/'provider-store-candidates.json').write_text(json.dumps(dict(source_sha256=s.PIN,scope='Encoded __text stores only; receiver ownership not assumed, vector/indirect stores not enumerated.',rows=rows),indent=2)+'\n')
print(len(rows));print(json.dumps(rows,indent=2))
