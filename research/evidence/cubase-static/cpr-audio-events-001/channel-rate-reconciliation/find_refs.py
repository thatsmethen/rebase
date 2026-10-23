"""Exact encoded B/BL candidates in original __text, not indirect call completeness."""
from pathlib import Path
import json, struct, sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
sys.path.insert(0,str(ROOT/'research/evidence/cubase-static/cpr-map-clock-001/attributes'))
import source_tools as s
targets={int(v,16) for v in sys.argv[2:]}
rows=[]
for section in s.sections:
    if section['name']!='__text': continue
    lo=section['offset']; hi=lo+section['size']
    for delta,(word,) in enumerate(struct.iter_unpack('<I',s.data[lo:hi])):
        if word & 0x7c000000 != 0x14000000: continue
        imm=word&0x3ffffff
        if imm&0x2000000: imm-=0x4000000
        address=section['address']+4*delta; target=address+4*imm
        if target in targets:
            rows.append(dict(address=hex(address),word=f'{word:08x}',target=hex(target),
                             caller_interval=hex(s.containing(address)),kind='BL' if word>>31 else 'B'))
report=dict(source=str(s.SOURCE.relative_to(ROOT)),source_sha256=s.PIN,
            targets=[hex(a) for a in sorted(targets)],candidates=rows,
            limitation='Instruction encoding matches in __text; inspect caller dataflow before assigning roles. Indirect calls and references are not enumerated. No target execution.')
with (HERE/sys.argv[1]).open('x') as f:json.dump(report,f,indent=2);f.write('\n')
print(json.dumps(report,indent=2))
