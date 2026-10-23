"""Original aligned AArch64 direct B/BL references; indirect calls excluded."""
import json,struct,sys
from pathlib import Path
P=Path(__file__).resolve().parent
sys.path.insert(0,str(P.parent.parent/'cpr-map-clock-001'/'attributes'))
import source_tools as s
T=int(sys.argv[1],16);code=next(x for x in s.sections if x['name']=='__text');rows=[]
for i,(w,)in enumerate(struct.iter_unpack('<I',s.data[code['offset']:code['offset']+code['size']])):
 if w&0x7c000000!=0x14000000:continue
 im=w&0x3ffffff;im=im-(1<<26)if im&(1<<25)else im;pc=code['address']+i*4
 if pc+im*4==T:rows.append(dict(pc=hex(pc),function=hex(s.containing(pc)),word=hex(w),file_offset=code['offset']+i*4,kind='BL'if w&0x80000000 else'B'))
out=dict(source=str(s.SOURCE.relative_to(s.ROOT)),source_sha256=s.PIN,target=hex(T),matches=rows,limits=['Aligned encoded direct references only; not complete dynamic callers.','LC_FUNCTION_STARTS predecessor is an enclosing candidate, not exact body proof.'])
(P/f'calls-{T:x}.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
