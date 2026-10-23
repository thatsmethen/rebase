"""Original-image bounded reference candidates; no execution or semantic promotion."""
from bisect import bisect_right
from hashlib import sha256
import json,struct
from pathlib import Path
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[4]
SRC=ROOT/'research/targets/derived/Cubase15-arm64'
EXPECTED='dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb'
before=SRC.stat();data=SRC.read_bytes();assert sha256(data).hexdigest()==EXPECTED
segments=[];sections=[];position=32
for _ in range(struct.unpack_from('<I',data,16)[0]):
 command,size=struct.unpack_from('<II',data,position)
 if command==0x19:
  v=struct.unpack_from('<II16sQQQQIIII',data,position)
  segments.append(dict(name=v[2].rstrip(b'\0').decode(),address=v[3],offset=v[5],size=v[6]))
  for n in range(v[-2]):
   s=struct.unpack_from('<16s16sQQIIIIIIII',data,position+72+80*n)
   sections.append(dict(name=s[0].rstrip(b'\0').decode(),segment=s[1].rstrip(b'\0').decode(),address=s[2],size=s[3],offset=s[4]))
 if command==0x26:_,_,fo,fs=struct.unpack_from('<IIII',data,position)
 position+=size
text=next(x for x in segments if x['name']=='__TEXT');code=next(x for x in sections if x['name']=='__text')
starts=[];address=text['address'];delta=shift=0
for b in data[fo:fo+fs]:
 delta|=(b&127)<<shift
 if b&128:shift+=7
 else:
  if delta==0:break
  address+=delta;starts.append(address);delta=shift=0
def enclosing(address):
 i=bisect_right(starts,address)-1
 assert i>=0 and i+1<len(starts)
 return dict(start=hex(starts[i]),next_start=hex(starts[i+1]),metadata_interval_bytes=starts[i+1]-starts[i])
targets={0x104670218:'MListNode primary vtable'}
call_targets={0x1000e9148,0x10171bcdc}
pages={a&~4095 for a in targets};hits=[];calls=[]
for i,(word,) in enumerate(struct.iter_unpack('<I',data[code['offset']:code['offset']+code['size']])):
 pc=code['address']+4*i
 if word&0x7c000000==0x14000000:
  imm=word&0x3ffffff
  if imm&0x2000000:imm-=0x4000000
  target=pc+4*imm
  if target in call_targets:calls.append(dict(at=hex(pc),word=f'{word:08x}',target=hex(target),branch='BL' if word>>31 else 'B',function=enclosing(pc)))
 if word&0x9f000000 not in (0x10000000,0x90000000):continue
 imm=((word>>5&0x7ffff)<<2)|(word>>29&3)
 if imm&(1<<20):imm-=1<<21
 if word&0x9f000000==0x10000000:
  if pc+imm in targets:hits.append(dict(kind='ADR',at=hex(pc),target=hex(pc+imm),label=targets[pc+imm],function=enclosing(pc)))
  continue
 page=(pc&~4095)+(imm<<12)
 if page not in pages:continue
 register=word&31
 for d in range(1,13):
  offset=code['offset']+4*i+4*d
  if offset+4>code['offset']+code['size']:break
  add=struct.unpack_from('<I',data,offset)[0]
  if add&0xff800000!=0x91000000 or add>>5&31!=register:continue
  value=page+((add>>10&4095)<<(12 if add&(1<<22) else 0))
  if value not in targets:continue
  hits.append(dict(kind='ADRP_ADD_candidate',at=hex(pc),add_at=hex(pc+d*4),target=hex(value),label=targets[value],source_register=register,result_register=add&31,intervening_instructions=d-1,status='adjacent pair' if d==1 else 'clobber/control-flow check required',function=enclosing(pc)))
after=SRC.stat();assert (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)
result=dict(source=str(SRC),sha256=EXPECTED,scope='Static __text ADR/ADRP+ADD and direct B/BL candidates only; no indirect completeness, receiver or PCM behavior claim. LC predecessor intervals are metadata, not proved function ends.',code=code,targets={hex(k):v for k,v in targets.items()},hits=hits,calls=calls)
with (OUT/'constructor-reference-candidates.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps(dict(hits=hits,calls=calls),indent=2))
