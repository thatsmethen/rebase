"""Read-only encoded ADRP/ADD candidates, not complete dataflow or xrefs."""
from pathlib import Path
import json,struct,sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[4]
sys.path.insert(0,str(ROOT/'research/evidence/cubase-static/cpr-map-clock-001/attributes'))
import source_tools as s
targets={int(v,16) for v in sys.argv[2:]};rows=[]
section=next(v for v in s.sections if v['name']=='__text')
blob=s.data[section['offset']:section['offset']+section['size']]
pages={v&~4095 for v in targets}
for i,(word,) in enumerate(struct.iter_unpack('<I',blob)):
    if word&0x9f000000!=0x90000000:continue
    pc=section['address']+i*4
    imm=((word>>5&0x7ffff)<<2)|(word>>29&3)
    if imm&(1<<20):imm-=1<<21
    page=(pc&~4095)+(imm<<12)
    if page not in pages:continue
    register=word&31
    for distance in range(1,13):
        if (i+distance)*4>=len(blob):break
        following=struct.unpack_from('<I',blob,(i+distance)*4)[0]
        if following&0xffc00000!=0x91000000 or following>>5&31!=register:continue
        address=page+(following>>10&4095)
        if address in targets:
            rows.append(dict(adrp=hex(pc),add=hex(pc+4*distance),target=hex(address),
                             caller_interval=hex(s.containing(pc)),distance=distance,
                             adrp_word=f'{word:08x}',add_word=f'{following:08x}'))
report=dict(source_sha256=s.PIN,targets=[hex(v) for v in sorted(targets)],candidates=rows,
            limitation='Bounded encoded address candidates. Intervening register clobbers and control flow require original-instruction review; no indirect/reference completeness or target execution.')
with (HERE/sys.argv[1]).open('x') as f:json.dump(report,f,indent=2);f.write('\n')
print(json.dumps(report,indent=2))
