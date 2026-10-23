#!/usr/bin/env python3
"""Create one immutable analytical negative control; never execute target code."""
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
import cpr_probe


def sha(data):
    return hashlib.sha256(data).hexdigest()


manifest_path = ROOT / 'research/evidence/cubase-static/cpr-audio-timing-001/reviewer-template-state.json'
manifest_bytes = manifest_path.read_bytes()
fixture = next(x for x in json.loads(manifest_bytes)['fixtures']
               if x['source'].endswith('/LoFi Hip Hop.cpr'))
source = ROOT / fixture['source']
original = source.read_bytes()
assert sha(original) == fixture['source_sha256'] == '2795af70cbc6651fbd6aa4cfbcb546d606d25d5970722a6c553384f3d196e495'
probe = cpr_probe.probe(source)
objects = {}


def visit(value):
    if isinstance(value, dict):
        if value.get('class') == 'MTempoTrackEvent' and value.get('kind') == 'object':
            objects[value['size_offset']] = value
        for child in value.values():
            visit(child)
    elif isinstance(value, list):
        for child in value:
            visit(child)


visit(probe)
assert len(objects) == 1
tempo, = objects.values()
expected = fixture['tempo_objects'][0]
assert tempo['body_offset'] == expected['object']['body_offset']
assert tempo['body_sha256'] == expected['object']['body_sha256']
decoded = tempo['decoded']
assert decoded['count'] == 2 and decoded['fixed_enabled_u16'] == 0
record = decoded['records'][1]
assert record['offset'] == expected['prefix']['records'][1]['offset']
# Serialized record: f32 period, f64 seconds, f64 ticks, u16 kind.
offset = record['offset'] + 4
before_bits, = struct.unpack_from('>Q', original, offset)
assert before_bits == 0x4082c00000000000  # 600 seconds, exactly.
after_bits = before_bits + 1
changed = bytearray(original)
struct.pack_into('>Q', changed, offset, after_bits)
changed = bytes(changed)
assert len(changed) == len(original)
differences = [i for i, (a, b) in enumerate(zip(original, changed)) if a != b]
assert differences == [offset + 7]
assert source.read_bytes() == original
destination = HERE / 'Synthetic Noncanonical LoFi.cpr'
if destination.exists():
    assert destination.read_bytes() == changed
else:
    destination.write_bytes(changed)
control_probe = cpr_probe.probe(destination)
assert control_probe['sha256'] == sha(changed)
report = {
    'schema_version': 1,
    'kind': 'Self-authored one-ULP mutation of a pinned shipped file; not a Cubase runtime output',
    'target_executed': False,
    'source': fixture['source'], 'source_sha256': sha(original), 'source_bytes': len(original),
    'control': str(destination.relative_to(ROOT)), 'control_sha256': sha(changed),
    'control_bytes': len(changed), 'source_unchanged_after_derivation': True,
    'derivation': {'field': 'Second tempo record saved seconds anchor (A1)',
                   'tempo_object_identity_offset': tempo['size_offset'],
                   'tempo_payload_offset': tempo['body_offset'],
                   'record_offset': record['offset'], 'field_offset': offset, 'field_bytes': 8,
                   'before_bits': f'0x{before_bits:016x}', 'after_bits': f'0x{after_bits:016x}',
                   'before_seconds': struct.unpack('>d', struct.pack('>Q', before_bits))[0],
                   'after_seconds': struct.unpack('>d', struct.pack('>Q', after_bits))[0],
                   'changed_byte_offsets': differences,
                   'all_other_bytes_equal': True},
    'instrument': str(Path(__file__).relative_to(ROOT)), 'instrument_sha256': sha(Path(__file__).read_bytes()),
    'offset_authority': {'manifest': str(manifest_path.relative_to(ROOT)), 'manifest_sha256': sha(manifest_bytes),
                         'fresh_structural_probe': 'scripts/cpr_probe.py',
                         'probe_sha256': sha((ROOT/'scripts/cpr_probe.py').read_bytes()),
                         'probe_exact_tempo_body_agrees_with_manifest': True},
    'prospective_gui_expectation': {
        'native_clock': None, 'tempo': 'Explicit application default 120 BPM',
        'reason': 'Saved A1 differs by one ULP from the native cache recurrence, which remains exactly 600 seconds.',
        'project_subset': 'Audio track skeletons may still be imported; the original control is preserved.',
        'validation_status': 'Expected from the reviewed contract and passing analogous core control; this artifact does not itself record a GUI run.'}
}
report_path = HERE / 'synthetic-noncanonical-lofi-provenance.json'
report_data = (json.dumps(report, indent=2) + '\n').encode()
if report_path.exists():
    assert report_path.read_bytes() == report_data
else:
    report_path.write_bytes(report_data)
print(json.dumps({'control': str(destination), 'sha256': sha(changed),
                  'provenance': str(report_path), 'provenance_sha256': sha(report_data)}))
