import bisect,hashlib,json,struct
from pathlib import Path
here=Path(__file__).resolve().parent;root=here.parents[4];p=root/'research/targets/derived/Cubase15-arm64';b=p.read_bytes();expected='dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb';assert hashlib.sha256(b).hexdigest()==expected
pos=32;segments=[]
for _ in range(struct.unpack_from('<I',b,16)[0]):
 cmd,size=struct.unpack_from('<II',b,pos)
 if cmd==0x19:
  x=struct.unpack_from('<II16sQQQQIIII',b,pos);segments.append((x[2].rstrip(b'\0').decode(),x[3],x[5],x[6]))
 if cmd==0x26:_,_,fo,fs=struct.unpack_from('<IIII',b,pos)
 pos+=size
text=next(s for s in segments if s[0]=='__TEXT');starts=[];address=text[1];delta=shift=0
for byte in b[fo:fo+fs]:
 delta|=(byte&127)<<shift
 if byte&128:shift+=7
 else:
  if delta==0:break
  address+=delta;starts.append(address);delta=shift=0
targets={0x1003015d4,0x100301604,0x1002fc89c,0x1002fca24}
rows=[]
for i,(w,) in enumerate(struct.iter_unpack('<I',b[text[2]:text[2]+text[3]-(text[3]%4)])):
 if w&0x7c000000 !=0x14000000:continue
 address=text[1]+4*i;imm=w&0x3ffffff
 if imm&0x2000000:imm-=0x4000000
 target=address+4*imm
 if target not in targets:continue
 k=bisect.bisect_right(starts,address)-1
 if k<0 or k+1>=len(starts):continue
 rows.append({'address':hex(address),'word':f'{w:08x}','target':hex(target),'containing_lc_start':hex(starts[k]),'next_lc_start':hex(starts[k+1]),'interval_bytes':starts[k+1]-starts[k],'branch':'BL' if w>>31 else 'B'})
(here/'predicate-caller-candidates.json').write_text(json.dumps({'source':str(p),'sha256':expected,'scope':'Candidate direct ARM64 B/BL words in file-backed TEXT; caller boundaries from LC_FUNCTION_STARTS. Instructions and semantics must be checked in native disassembly. No indirect call completeness.','calls':rows},indent=2)+'\n')
for t in sorted(targets):
 print(hex(t),[(r['containing_lc_start'],r['interval_bytes'],r['address']) for r in rows if r['target']==hex(t)])
