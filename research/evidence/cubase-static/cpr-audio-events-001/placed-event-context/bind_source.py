"""Original-image receiver bindings and read-only source field observations."""
from pathlib import Path
import hashlib
import json
import struct
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT/'research/evidence/cubase-static/cpr-map-clock-001/attributes'))
import source_tools as s

cells = []
for table, slots in [
    (0x10466BE98, {0xD0:0x1016E70EC, 0xD8:0x1016E70F4,
        0xE8:0x1016E2194, 0xF8:0x1016E300C, 0x100:0x1016E3990,
        0x108:0x1016E4D98, 0x118:0x1016E222C}),
    (0x10444A208, {0x258:0x10174A698, 0x280:0x1017014E4,
        0x2E0:0x10174B56C, 0x2E8:0x101700D6C, 0x558:0x10174B610}),
    (0x10444AA98, {0x98:0x1001FC8B0}),
    (0x104671208, {0x40:0x101725D9C, 0x258:0x10171759C,
        0x280:0x1017014E4, 0x2E0:0x101700D64, 0x2E8:0x1001F5430}),
    (0x104670218, {0x110:0x1016E9A20}),
]:
    for slot, target in slots.items():
        r = s.region(table+slot, 8)
        assert int.from_bytes(bytes.fromhex(r['bytes_hex']), 'little') == target
        r.update(table=hex(table), slot=hex(slot), target=hex(target))
        cells.append(r)

spans = []
for name, a, b in [
    ('Resource base constructor initializes +18 to positive zero',0x1017427F8,0x101742818),
    ('Resource copy constructor instead preserves source +18',0x101742AC8,0x101742AD8),
    ('MTrackEvent constructor initializes +90 among two zero vectors',0x101748034,0x101748048),
    ('MTrackEvent v2 reads saved f64 into +90',0x10174B724,0x10174B754),
    ('MTrackEvent reads required MTrack into +50',0x10174B680,0x10174B6A0),
    ('Concrete additive shift getter',0x10174B610,0x10174B630),
    ('Track shift argument selection and ordinary window',0x1002115E0,0x100211620),
    ('Builder root receiver and segment start-only shift',0x10020F0D4,0x10020F164),
    ('Original native normal-track caller enables shift argument',0x1001F91A0,0x1001F9264),
    ('Default root sample-rate getter or exact44100 fallback',0x10171C5A0,0x10171C5C4),
    ('Canonical datum initializer tag1 scalar1',0x101C26EA0,0x101C26EC4),
]:
    r=s.region(a,b-a);r['label']=name;spans.append(r)

fixture_source=HERE.parent/'autofade-source/source-forward-probe.json'
source_projection=json.loads((HERE.parent/'timebase/fixture-projection.json').read_text())
by_hash={x['source_sha256']:x for x in source_projection['fixtures']}
fields=[]
for f in json.loads(fixture_source.read_text())['fixtures']:
    source=ROOT/by_hash[f['source_sha256']]['source']
    data=source.read_bytes()
    assert hashlib.sha256(data).hexdigest()==f['source_sha256']
    for track in f['tracks']:
        at=track['number_offset']; value=data[at:at+8]
        assert value.hex()==track['number_bits']=='0000000000000000'
        word=struct.unpack_from('>i',data,track['word_offset'])[0]
        assert word==track['word']
        fields.append(dict(fixture=f['fixture'], source_sha256=f['source_sha256'],
            track_identity=track['track_identity'], track_word=word,
            number_file_offset=at, number_bits=value.hex(), number_bytes_sha256=hashlib.sha256(value).hexdigest(),
            resource_identity=track['resource_token']['relative_object_identity'],
            resource_class=track['resource_token']['class'], resource_body_sha256=track['resource_token']['body_sha256']))

prior_paths=[
    'timebase/finding.json', 'timebase/class-name-bindings.json',
    'timebase/transform-provider-vtable.json','timebase/containing-node-slots.json',
    'timebase/event-data-slots.json','timebase/edit-method-vtables.json',
    'timebase/fixture-projection.json','timebase/pass13/native-1016f2d88.txt',
    'timebase/pass13/native-1001c4840.txt',
    'event-rendering/ownership-finding.json','event-rendering/ownership-linkage.json',
    'event-rendering/pass7/native-1001f91a0.txt',
    'timeline-playback/pass3/native-1001f6500.txt',
    'timeline-provider/finding.json','timeline-provider/original-bindings.json',
    'timeline-provider/pass7/native-10171c5a0.txt',
    'autofade-source/finding.json','autofade-source/source-forward-probe.json',
]
external=[]
for p in [HERE.parent/x for x in prior_paths]+[
    ROOT/'research/evidence/cubase-static/cpr-audio-timing-001/finding-v1.json',
    ROOT/'research/evidence/cubase-static/cpr-map-clock-001/finding.json',
    ROOT/'research/evidence/cubase-static/cpr-map-clock-001/attributes/source_tools.py',
]:
    raw=p.read_bytes();external.append(dict(path=str(p.relative_to(ROOT)),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
for r in json.loads((HERE.parent/'timebase/finding.json').read_text())['verification']['ranges']:
    if int(r['entry'],16) in [0x100300954,0x100300950,0x100300694,0x1001FCD0C,
        0x101716FA0,0x101759568,0x101725D9C,0x10170F3A4,0x101C26DF0]:
        p=ROOT/Path(r['dossier']).with_name('native-'+r['entry'][2:]+'.txt')
        raw=p.read_bytes();external.append(dict(path=str(p.relative_to(ROOT)),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))

output=dict(source_sha256=s.PIN, dispatch_cells=cells, instruction_spans=spans,
    saved_track_fields=fields, external_references=external, target_executed=False,
    limits=['Original-image static reads. Pointer tables bind named concrete receivers, not a live host.',
            'Resource+18 constructor zero is a fresh-state condition; copying or later host writes are not excluded.',
            'Exploratory table/store candidate files are inventories, not additional semantic bindings.'])
(HERE/'original-bindings.json').write_text(json.dumps(output,indent=2)+'\n')
print(json.dumps(dict(cells=len(cells),spans=len(spans),fixtures=len(fields),external=len(external))))
