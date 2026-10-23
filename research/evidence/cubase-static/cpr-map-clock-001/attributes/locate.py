import re,struct,json
from pathlib import Path
from source_tools import *
HERE=Path(__file__).resolve().parent
names=[]
for m in re.finditer(rb'[^\x00]{0,110}(?:ScoreEventAttributeContainer|NoteData)[^\x00]{0,10}\x00',data):
 b=m.group()[:-1]
 if not b.startswith(b'N9Steinberg') and b not in [b'NoteData',b'ScoreEventAttributeContainer']:continue
 a=address(m.start());row=dict(text=b.decode(),address=hex(a),file_offset=m.start(),references=[])
 for p in re.finditer(re.escape(struct.pack('<Q',a)),data):
  o=p.start()
  if o%8:continue
  ti=address(o)-8;tables=[]
  for q in re.finditer(re.escape(struct.pack('<Q',ti)),data):
   j=q.start()
   if j%8==0 and data[j-8:j]==bytes(8):
    vt=address(j+8);tables.append(dict(address=hex(vt),prefix=region(vt-16,16),slots={hex(k):hex(struct.unpack_from('<Q',data,j+8+k)[0])for k in range(0,0x120,8)}))
  row['references'].append(dict(address=hex(address(o)),typeinfo_candidate=hex(ti),vtables=tables))
 names.append(row)
# Address-materialization candidates only; each retained instruction must be
# interpreted in its original function before being promoted to a factory link.
targets={int(x['address'],16)for x in names}
for x in names:
 for ref in x['references']:
  for table in ref['vtables']:targets.add(int(table['address'],16))
text=next(s for s in sections if s['name']=='__text');xrefs=[]
for i,(w,) in enumerate(struct.iter_unpack('<I',data[text['offset']:text['offset']+text['size']])):
 if w&0x9f000000!=0x90000000:continue
 pc=text['address']+i*4;imm=((w>>29)&3)|(((w>>5)&0x7ffff)<<2)
 if imm&(1<<20):imm-=1<<21
 page=(pc&~4095)+(imm<<12);reg=w&31
 if page not in {a&~4095 for a in targets}:continue
 for k in range(1,9):
  nextw=struct.unpack_from('<I',data,text['offset']+(i+k)*4)[0]
  if nextw&0xffc00000==0x91000000 and (nextw>>5)&31==reg:
   a=page+((nextw>>10)&4095)
   if a in targets:xrefs.append(dict(target=hex(a),adrp=region(pc,4),add=region(pc+k*4,4),function=hex(containing(pc))))
(HERE/'class-and-vtable-locator.json').write_text(json.dumps(dict(source=str(SOURCE),source_sha256=PIN,names=names,address_materializations=xrefs,limit='Exact original pointer/instruction candidates; factory and reader semantics require native function correlation.'),indent=2)+'\n')
print(json.dumps(dict(names=names,address_materializations=[dict(target=x['target'],address=x['adrp']['address'],function=x['function'])for x in xrefs]),indent=2))
