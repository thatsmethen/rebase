"""Bounded original ADRP/use candidates; register clobbers remain to review."""
import bisect,hashlib,json,struct,sys
from pathlib import Path
P=Path(__file__).resolve().parent
sys.path.insert(0,str(P.parent/'attributes'))
import source_tools as s
T=0x104feeee0
rows=[]
section=next(x for x in s.sections if x['name']=='__text')
words=struct.unpack('<'+'I'*(section['size']//4),s.data[section['offset']:section['offset']+section['size']])
for i,w in enumerate(words):
 if w&0x9f000000!=0x90000000:continue
 pc=section['address']+4*i;rd=w&31
 imm=((w>>29)&3)|(((w>>5)&0x7ffff)<<2)
 if imm&(1<<20):imm-=1<<21
 page=(pc&~4095)+(imm<<12)
 if page!=T&~4095:continue
 for j in range(i+1,min(i+13,len(words))):
  v=words[j];kind=None;target=None
  if (v>>5)&31!=rd:continue
  if v&0xffc00000==0x91000000:target=page+((v>>10)&4095);kind='ADD immediate'
  elif v&0xffc00000 in (0xf9400000,0xf9000000):target=page+((v>>10)&4095)*8;kind='LDR64'if v&0xffc00000==0xf9400000 else'STR64'
  elif v&0xffc00000 in (0xb9400000,0xb9000000):target=page+((v>>10)&4095)*4;kind='LDR32'if v&0xffc00000==0xb9400000 else'STR32'
  if target!=T:continue
  k=bisect.bisect_right(s.starts,pc)-1
  rows.append(dict(adrp=hex(pc),use=hex(section['address']+4*j),kind=kind,target=hex(T),function=hex(s.starts[k]),next_function=hex(s.starts[k+1]),distance=j-i,adrp_word=hex(w),use_word=hex(v)))
sec=[x for x in s.sections if x['address']<=T<x['address']+x['size']]
result=dict(source=str(s.SOURCE.relative_to(s.ROOT)),source_sha256=s.PIN,target=hex(T),section=sec,candidates=rows,
 limits=['Pattern candidates only; intervening clobbers and full original disassembly must be checked.','No runtime value is inferred from zero-fill or a nullable global.'])
(P/'global-xrefs.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
