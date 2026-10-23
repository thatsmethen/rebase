from pathlib import Path
import struct,json,hashlib,bisect
H=Path(__file__).resolve().parent;R=H.parents[5]
d=json.loads((H/'raw-reference-candidates.json').read_text());data=Path(d['source']).read_bytes();assert hashlib.sha256(data).hexdigest()==d['source_sha256'];code=next(x for x in d['sections']if x['name']=='__text');fs=d['function_starts'];a=0x100000000;de=sh=0;starts=[]
for b in data[fs['offset']:fs['offset']+fs['bytes']]:
 de|=(b&127)<<sh
 if b&128:sh+=7
 elif de:a+=de;starts.append(a);de=sh=0
 else:break
targets={0x103806e44,0x103806fa4,0x103806748};hits=[]
for i,(w,)in enumerate(struct.iter_unpack('<I',data[code['offset']:code['offset']+code['size']])):
 if w&0x7c000000!=0x14000000:continue
 pc=code['address']+i*4;delta=w&0x3ffffff
 if delta&(1<<25):delta-=1<<26
 dest=pc+delta*4
 if dest not in targets:continue
 k=bisect.bisect_right(starts,pc)-1;hits.append({'at':hex(pc),'target':hex(dest),'word':hex(w),'start':hex(starts[k]),'next_start':hex(starts[k+1])})
out={'source_sha256':d['source_sha256'],'scope':'Aligned direct B/BL immediate candidates; native disassembly must confirm semantics.','targets':[hex(x)for x in sorted(targets)],'hits':hits};(H/'direct-call-candidates.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
