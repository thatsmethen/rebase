"""Bind concrete dispatch and upstream source roles to the untouched Mach-O."""
from pathlib import Path
import hashlib, json, re, struct, sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT / 'research/evidence/cubase-static/cpr-map-clock-001/attributes'))
import source_tools as s

def pin(path):
    raw = path.read_bytes()
    return dict(path=str(path.relative_to(ROOT)), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())

def slot(base, offset, expected, role):
    row = s.region(base + offset, 8)
    assert int.from_bytes(bytes.fromhex(row['bytes_hex']), 'little') == expected
    return dict(base=hex(base), slot=hex(offset), target=hex(expected), role=role, source=row)

tables = []
for offset, target, role in [
    (0xd8,0x10036e858,'copy current source format'),
    (0xe8,0x1003704cc,'Float32 output-rate getter'),
    (0xf0,0x1003704d4,'Float32 output-rate setter; plain store'),
    (0xf8,0x1003704e0,'layout getter'),
    (0x100,0x1003704e8,'layout setter'),
    (0x110,0x10036ec30,'frame-byte-size setter; NOT rate setter'),
    (0x120,0x10036ed34,'bit-width setter'),
    (0x130,0x10037050c,'format-kind setter'),
    (0x140,0x10036ef28,'channel-count setter'),
    (0x150,0x100370528,'alignment/endian field setter'),
    (0x160,0x100370538,'Float32 gain setter'),
    (0x168,0x10036eff0,'read'), (0x178,0x10036f89c,'seek'),
    (0x1a0,0x10036fca0,'copy accessor-format interface'),
    (0x1a8,0x10036fea0,'copy stream-format interface')]:
    tables.append(slot(0x1044664f0,offset,target,role))
for offset,target,role in [
    (0x120,0x10036ae90,'layout'), (0x128,0x10036aea0,'frame bytes'),
    (0x130,0x10036aee8,'alignment/endian'), (0x138,0x10036af30,'channels'),
    (0x140,0x10036af9c,'first-file Float32 rate'),
    (0x150,0x10036b0bc,'first-file format-ID descriptor kind'),
    (0x158,0x10036b244,'first-file format-ID descriptor bits')]:
    tables.append(slot(0x104466150,offset,target,'AudioCluster primary: '+role))
tables.append(slot(0x1044662f0,0x40,0x10036afc8,
                   'AudioCluster secondary format interface: first-file rate (adjusted receiver)'))
for offset,target,role in [(0x140,0x10033cb0c,'rate'),(0x150,0x10033d024,'kind'),
                           (0x158,0x10033d308,'bits'),(0x168,0x10033d530,'format ID')]:
    tables.append(slot(0x104462178,offset,target,'AudioFile primary: '+role))

# These original-image excerpts are independently checked; they are not new REA bodies.
builder = ROOT/'research/evidence/cubase-static/cpr-audio-events-001/placed-event-builder/pass1/native-10020f2e8.txt'
native = {int(a,16):int(w,16) for a,w in re.findall(r'^([0-9a-f]+):\s+([0-9a-f]{8})\s',builder.read_text(),re.M)}
spans = []
for begin,end,claim in [
    (0x10020f318,0x10020f338,'Builder context root supplies its own type10 period'),
    (0x10020f400,0x10020f440,'Selected stream result retained in stack+90'),
    (0x1002104fc,0x10021051c,'Ordinary remainder constructor receives stack+90 selected stream')]:
    for a in range(begin,end,4):
        assert native[a] == struct.unpack_from('<I',s.data,s.offset(a,4))[0]
    spans.append(dict(claim=claim, source=s.region(begin,end-begin), native_record=pin(builder)))

external = [
    'research/evidence/cubase-static/cpr-audio-events-001/renderer-selection/finding.json',
    'research/evidence/cubase-static/cpr-audio-events-001/renderer-selection/pass8/native-10021225c.txt',
    'research/evidence/cubase-static/cpr-audio-events-001/placed-event-builder/finding.json',
    'research/evidence/cubase-static/cpr-audio-events-001/placed-event-context/finding.json',
    'research/evidence/cubase-static/cpr-audio-events-001/timeline-reader/finding.json',
    'research/evidence/cubase-static/cpr-audio-events-001/timeline-provider/finding.json',
    'research/evidence/cubase-static/cpr-audio-events-001/cluster/finding.json',
    'research/evidence/cubase-static/cpr-audio-events-001/rate-selection/receiver-tables.json',
    'research/evidence/cubase-static/cpr-audio-events-001/rate-selection/finding.json',
    'research/evidence/cubase-static/cpr-audio-events-001/segment-consumer/finding.json',
    'research/evidence/cubase-static/cpr-audio-events-001/segment-consumer/bound-source-bytes.json',
    'research/evidence/cubase-static/cpr-map-clock-001/attributes/source_tools.py',
    '.tools/rea/node_modules/rea-agents/skills/reverse-engineer-anything/SKILL.md',
    '.tools/rea/node_modules/rea-agents/skills/reverse-engineer-anything/references/native-and-artifacts.md',
    '.tools/rea/node_modules/rea-agents/skills/reverse-engineer-anything/references/evidence-workflows.md',
]
literal=s.region(0x10389225a,12)
assert bytes.fromhex(literal['bytes_hex']) == b'AudioStream\0'
report=dict(source=pin(s.SOURCE), dispatch=tables, original_instruction_spans=spans,
            cache_type_literal=literal, cache_key='runtime uint32 at global105028978; initializer/value not established here',
            external_references=[pin(ROOT/p) for p in external]+[pin(builder)],
            scope='Exact original bytes/cells. A class-specific slot has no meaning on another receiver. No live object or proprietary code executed.',
            passed=True)
with (HERE/'original-bindings.json').open('x') as f: json.dump(report,f,indent=2); f.write('\n')
print(json.dumps(dict(dispatch_cells=len(tables), external_references=len(report['external_references']), passed=True)))
