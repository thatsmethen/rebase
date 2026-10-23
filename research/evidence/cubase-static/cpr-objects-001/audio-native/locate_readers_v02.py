"""Read-only RTTI/vtable candidate lookup; no proprietary execution."""
from pathlib import Path
import struct, hashlib, json
here=Path(__file__).resolve().parent
root=here.parents[4]
p=root/'research/targets/derived/Cubase15-arm64'
b=p.read_bytes();sha=hashlib.sha256(b).hexdigest();assert sha=='dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb'
segs=[];pos=32
for _ in range(struct.unpack_from('<I',b,16)[0]):
 cmd,size=struct.unpack_from('<II',b,pos)
 if cmd==0x19:
  _,_,name,va,vs,off,fs,*_=struct.unpack_from('<II16sQQQQIIII',b,pos);segs.append((name.rstrip(b'\0').decode(),va,off,fs))
 pos+=size
def va(off):
 s,= [s for s in segs if s[2]<=off<s[2]+s[3]];return s[1]+off-s[2]
def matches(needle,aligned=False):
 start=0
 while True:
  q=b.find(needle,start)
  if q<0:return
  if not aligned or q%8==0:yield q
  start=q+1
rows=[]
for name in ['MEvent','MAudioEvent','PAudioClip','AudioCluster','AudioFile','MAudioPart','MAudioTrackEvent','PArrangement','FNPath']:
 token=f'N9Steinberg{len(name)}{name}E'.encode()+b'\0';row={'class':name,'rtti_token':token[:-1].decode(),'candidates':[]}
 for off in matches(token):
  for ptr in matches(struct.pack('<Q',va(off)),True):
   ti=va(ptr-8)
   for vp in matches(struct.pack('<Q',ti),True):
    if struct.unpack_from('<Q',b,vp-8)[0]!=0:continue
    vt=va(vp+8);reader=struct.unpack_from('<Q',b,vp+8+0x98)[0];writer=struct.unpack_from('<Q',b,vp+8+0xa0)[0]
    row['candidates'].append({'name_offset':off,'name_address':hex(va(off)),'typeinfo_address':hex(ti),'vtable_address':hex(vt),'reader_0x98':hex(reader),'writer_0xa0':hex(writer),'vtable_prefix_hex':b[vp-8:vp+8+0xb0].hex()})
 rows.append(row)
r={'source':str(p),'sha256':sha,'scope':'RTTI and primary-vtable candidates from original bytes. Slot semantics require native caller confirmation. No target execution.','classes':rows}
(here/'reader-candidates-v02.json').write_text(json.dumps(r,indent=2)+'\n')
for row in rows:print(row['class'],[(c['reader_0x98'],c['vtable_address']) for c in row['candidates']])
