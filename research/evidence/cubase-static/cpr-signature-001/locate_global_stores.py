"""Instruction-pattern leads for BSS attribute-id initializers; not semantic evidence."""
import struct,json,hashlib,bisect
from pathlib import Path
P=Path(__file__).resolve().parent;ROOT=P.parents[3]
source=ROOT/'research/targets/derived/Cubase15-arm64';data=source.read_bytes()
assert hashlib.sha256(data).hexdigest()=='dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb'
pos=32
for _ in range(struct.unpack_from('<I',data,16)[0]):
 c,n=struct.unpack_from('<II',data,pos)
 if c==0x19:
  v=struct.unpack_from('<II16sQQQQIIII',data,pos)
  for i in range(v[9]):
   s=struct.unpack_from('<16s16sQQIIIIIIII',data,pos+72+i*80)
   if s[0].rstrip(b'\0')==b'__text': textaddr,size,offset=s[2:5]
 if c==0x26:_,_,fo,fn=struct.unpack_from('<IIII',data,pos)
 pos+=n
starts=[];a=0x100000000;delta=shift=0
for v in data[fo:fo+fn]:
 delta|=(v&127)<<shift
 if v&128:shift+=7
 else:
  if not delta:break
  a+=delta;starts.append(a);delta=shift=0
wanted={0x105006320,0x105006324,0x10507ff34,0x10507ff38};pages={a&~0xfff for a in wanted}
words=struct.unpack_from('<'+'I'*(size//4),data,offset);rows=[]
for i,w in enumerate(words):
 if w&0x9f000000!=0x90000000:continue
 pc=textaddr+i*4; imm=((w>>29)&3)|(((w>>5)&0x7ffff)<<2)
 if imm&(1<<20):imm-=1<<21
 base=(pc&~0xfff)+(imm<<12)
 if base not in pages:continue
 reg=w&31;tracked={reg:base}
 for j in range(i+1,min(i+129,len(words))):
  ins=words[j];at=textaddr+4*j
  if ins&0xffc00000==0x91000000:
   rn=(ins>>5)&31;rd=ins&31
   if rn in tracked:tracked[rd]=tracked[rn]+((ins>>10)&0xfff)
  if ins&0xffc00000 in [0xb9000000,0xb9400000]:
   rn=(ins>>5)&31
   if rn in tracked:
    address=tracked[rn]+4*((ins>>10)&0xfff)
    if address in wanted:
     idx=bisect.bisect_right(starts,at)-1
     rows.append({'global':hex(address),'instruction':hex(at),'word':hex(ins),'operation':'str32'if ins&0xffc00000==0xb9000000 else'ldr32','value_register':ins&31,'adrp':hex(pc),'candidate_function':hex(starts[idx]),'next_function_start':hex(starts[idx+1]),'limit':'Pattern lead only: intervening register clobbers/control flow not modeled; inspect original function before using.'})
   # A 32-bit load overwrites its destination address register.
   if ins&0xffc00000==0xb9400000:tracked.pop(ins&31,None)
  if ins==0xd65f03c0:break
  if ins&0xfc000000==0x94000000:
   tracked={r:a for r,a in tracked.items() if 19<=r<=28}
rows=list({(r['global'],r['instruction']):r for r in rows}.values())
(P/'global-xref-leads.json').write_text(json.dumps({'source_sha256':hashlib.sha256(data).hexdigest(),'leads':rows},indent=2)+'\n')
print(json.dumps([r for r in rows if r['operation']=='str32'],indent=2))
