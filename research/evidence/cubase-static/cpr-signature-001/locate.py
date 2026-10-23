"""Locate selected native RTTI/vtable evidence without executing target code."""
import hashlib,json,re,struct
from pathlib import Path
P=Path(__file__).resolve().parent;ROOT=P.parents[3]
SOURCE=ROOT/'research/targets/derived/Cubase15-arm64';data=SOURCE.read_bytes()
EXPECTED='dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb'
assert hashlib.sha256(data).hexdigest()==EXPECTED
segments=[];pos=32
for _ in range(struct.unpack_from('<I',data,16)[0]):
 c,n=struct.unpack_from('<II',data,pos)
 if c==0x19:
  v=struct.unpack_from('<II16sQQQQIIII',data,pos);segments.append(dict(name=v[2].rstrip(b'\0').decode(),address=v[3],offset=v[5],size=v[6]))
 pos+=n
def addr(o):
 s,=[s for s in segments if s['offset']<=o<s['offset']+s['size']];return s['address']+o-s['offset']
def offs(a,n=1):
 s,=[s for s in segments if s['address']<=a and a+n<=s['address']+s['size']];return s['offset']+a-s['address']
def refs(a):
 pattern=struct.pack('<Q',a);i=0;v=[]
 while (i:=data.find(pattern,i))!=-1:
  if i%8==0:v.append(i)
  i+=1
 return v
candidates=[]
for m in re.finditer(rb'N9Steinberg\d+[A-Za-z0-9_]*Signature[A-Za-z0-9_]*E\x00',data):
 sa=addr(m.start());row=dict(name=m.group()[:-1].decode(),name_address=hex(sa),name_file_offset=m.start(),typeinfo=[])
 for o in refs(sa):
  ti=addr(o-8);tables=[]
  for p in refs(ti):
   if p>=8 and data[p-8:p]==b'\0'*8:
    vt=addr(p+8)
    slots={hex(s):hex(struct.unpack_from('<Q',data,p+8+s)[0])for s in [0,8,0x10,0x20,0x30,0x98,0xa0]}
    tables.append(dict(address=hex(vt),source_file_offset=p+8,slots=slots))
  if tables:row['typeinfo'].append(dict(address=hex(ti),name_pointer_file_offset=o,primary_tables=tables))
 candidates.append(row)
(P/'locator.json').write_text(json.dumps({'source':str(SOURCE),'source_sha256':EXPECTED,'candidates':candidates,'limits':['RTTI/zero-prefix pointer locator only; selected virtual-slot semantics require original instructions and constructor/caller correlation.']},indent=2)+'\n')
print(json.dumps(candidates,indent=2))
