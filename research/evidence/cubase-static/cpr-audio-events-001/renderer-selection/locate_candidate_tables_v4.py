from pathlib import Path
import struct,hashlib,json
h=Path(__file__).resolve().parent;r=h.parents[4];p=r/'research/targets/derived/Cubase15-arm64';b=p.read_bytes();assert hashlib.sha256(b).hexdigest()=='dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb'
ss=[];at=32
for _ in range(struct.unpack_from('<I',b,16)[0]):
 c,n=struct.unpack_from('<II',b,at)
 if c==25:
  v=struct.unpack_from('<II16sQQQQIIII',b,at);ss.append((v[3],v[5],v[6]))
 at+=n
def offset(a):return next((o+a-v for v,o,n in ss if v<=a<v+n),None)
def va(off):return next((v+off-o for v,o,n in ss if o<=off<o+n),None)
def cstr(a):
 o=offset(a)
 if o is None:return None
 e=b.find(b'\0',o,o+512)
 if e<0:return None
 try:return b[o:e].decode('ascii')
 except:return None
rows=[]
for a in [0x100211a7c,0x1002129a4]:
 needle=struct.pack('<Q',a);start=0
 while True:
  pos=b.find(needle,start)
  if pos<0:break
  start=pos+1
  if pos%8:continue
  candidates=[]
  for back in range(pos-8,max(0,pos-2048),-8):
   ti=struct.unpack_from('<Q',b,back)[0];to=offset(ti)
   if to is None:continue
   name=cstr(struct.unpack_from('<Q',b,to+8)[0])
   if name and (name.startswith('N') or name[:1].isdigit()) and len(name)>8 and b[back-8:back]==b'\0'*8:
    candidates.append({'address_point':hex(va(back+8)),'slot':hex(pos-back-8),'typeinfo':hex(ti),'rtti_name':name});break
  rows.append({'target':hex(a),'cell':hex(va(pos)),'file_offset':pos,'hex':b[pos:pos+8].hex(),'candidate_primary_table':candidates})
(h/'candidate-tables-v4.json').write_text(json.dumps({'source':str(p),'sha256':hashlib.sha256(b).hexdigest(),'scope':'Pointer and primary RTTI candidates; receiver dispatch must be bound by original callers/constructors. No arbitrary-pointer semantics.','rows':rows},indent=2)+'\n')
for row in rows:print(row)
