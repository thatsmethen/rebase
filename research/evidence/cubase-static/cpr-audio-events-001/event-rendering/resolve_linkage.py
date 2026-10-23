"""Retain exact original-image receiver/field/format linkage, static only."""
from pathlib import Path
import sys, json, struct, hashlib

h = Path(__file__).resolve().parent
r = h.parents[4]
helper = r / 'research/evidence/cubase-static/cpr-map-clock-001/attributes/source_tools.py'
sys.path.insert(0, str(helper.parent))
import source_tools as s

cells = []
for name, table, slots in [
    ('PAudioSegment', 0x104436be0, [0xd0,0xd8,0xe0,0xe8,0xf0,0x100,0x108]),
    ('MAudioTrackEvent', 0x10444a208, [0x618]),
    ('MAutoFadeSetting', 0x104440de0, [0x98]),
    ('MAudioTrack', 0x10444aa98, [0x110,0x118,0x148,0x1b0]),
    ('AudioAccessor', 0x1044664f0, [0x108,0x118,0x128,0x130,0x138,0x140,0x170,0x198,0x1a0]),
]:
    for slot in slots:
        v = s.region(table+slot,8)
        v.update(receiver=name,table=hex(table),slot=hex(slot),target=hex(int.from_bytes(bytes.fromhex(v['bytes_hex']),'little')))
        cells.append(v)

literals=[]
for a in [0x10389270f,0x10389225a,0x1038937ad,0x103891e55,0x1038932c7,
          0x1038928d3,0x1038928d9,0x1038928de,0x1038928e4,0x1038928ea,0x1038928f0,0x1038928f8]:
    raw=bytes.fromhex(s.region(a,100)['bytes_hex']).split(b'\0')[0]
    v=s.region(a,len(raw)+1);v['ascii']=raw.decode('ascii');literals.append(v)

formats=[]
for a in range(0x10391d0f0,0x10391d160,16):
    v=s.region(a,16);v['four_little_endian_u32']=struct.unpack('<IIII',bytes.fromhex(v['bytes_hex']));formats.append(v)

spans=[]
for name,a,e in [
    ('PAudioSegment constructor concrete vptr, stream and unity gain',0x10011376c,0x10011380c),
    ('normal remainder segment fields and event gain',0x100210508,0x1002105c4),
    ('effective automatic fade zero gate',0x10020f708,0x10020f78c),
    ('serialized auto-fade settings reader',0x10018cd6c,0x10018ce3c),
    ('track builder flags128 and list commit',0x1001f91d4,0x1001f9274),
    ('offline action temporarily sets event attribute before construction',0x1001901d0,0x100190304),
    ('offline consumer constants half and unity',0x10018fff8,0x100190008),
    ('consumer exact PAudioSegment type and field loads',0x100190b08,0x100190b78),
    ('consumer offset length conversion clone and format setup',0x100190c9c,0x100190db8),
    ('consumer seek count read EOF check',0x100190dbc,0x100190e5c),
    ('consumer Float32 volume and write',0x100190e5c,0x100190f20),
    ('consumer remaining count and error flags',0x100190f20,0x100190fa4),
    ('format5 float32 descriptor materialization',0x10012c564,0x10012c57c),
]:
    v=s.region(a,e-a);v['name']=name;spans.append(v)

out={'source_sha256':'dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb',
     'method':'Original LC_SEGMENT mapped cells, literals and instruction spans. Candidate table dumps may cross adjacent headers; only these explicitly bound slots are used.',
     'helper':{'path':str(helper.relative_to(r)),'sha256':hashlib.sha256(helper.read_bytes()).hexdigest()},
     'dispatch_cells':cells,'literals':literals,'sample_format_descriptor_constants':formats,
     'instruction_spans':spans,'target_execution':False}
(h/'final-linkage.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'cells':len(cells),'literals':len(literals),'format_constants':len(formats),'spans':len(spans)}))
