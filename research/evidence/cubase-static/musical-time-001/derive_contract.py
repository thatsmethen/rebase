#!/usr/bin/env python3
"""Read-only source/byte observations. Does not execute any Cubase code."""
import collections
import hashlib
import json
import pathlib
import plistlib
import struct
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[4]
OUT = pathlib.Path(__file__).resolve().parent
CONTENTS = ROOT / 'research/targets/full-reference/expanded/Cubase 15.app.pkg/Payload/Cubase 15.app/Contents'

def sha(data): return hashlib.sha256(data).hexdigest()
seal_bytes = (CONTENTS / '_CodeSignature/CodeResources').read_bytes()
seal = plistlib.loads(seal_bytes)
assert sha(seal_bytes) == 'c7b8e3234e2efefb0c7aa2ddf815d413c69ac710460b6908ccdcfdf655ac2c8e'

def source(path):
    data = path.read_bytes()
    relative = str(path.relative_to(CONTENTS))
    expected = seal['files2'][relative]['hash2'].hex()
    assert sha(data) == expected, relative
    return {'path': relative, 'bytes': len(data), 'sha256': sha(data),
            'CodeResources_hash2': expected, 'matches_resource_declaration': True}

presets = []
payloads = []
for path in sorted((CONTENTS / 'presets/Project Logical Editor/Quantize').glob('Quantize Selected Data*.xml')):
    blob = bytes.fromhex(''.join(ET.fromstring(path.read_bytes()).find('bin').itertext()))
    payloads.append(blob)
    presets.append({**source(path), 'decoded_payload_bytes': len(blob), 'payload_sha256': sha(blob),
                    'candidate_u32_le_offset': 179, 'candidate_u32_le_value': struct.unpack_from('<I', blob, 179)[0],
                    'context_offset': 167, 'context_hex': blob[167:191].hex()})
assert len(payloads) == 6 and all(len(p) == 625 for p in payloads)
differences = [i for i in range(625) if len({p[i] for p in payloads}) > 1]
assert differences == [179, 180]
api_path = CONTENTS / 'midiremote_factory_scripts/.api/v1/midiremote_api_v1.js'
api = source(api_path)
lines = api_path.read_text().splitlines()
api['declarations'] = [
    {'lines': [7376, 7389], 'claim': 'JSDoc declares change callbacks with time:string, format:string, and tempoBPM:number.'},
    {'lines': [7405, 7445], 'claim': 'Primary and secondary transport display details construct left/right cycle locators and transport locators.'},
    {'lines': [7450, 7495], 'claim': 'setTempoBPM(activeMapping, tempoBPM) and setTime(activeMapping, timeString), plus corresponding callbacks, have empty bodies in the shipped declaration source.'}
]
api['line_ranges_sha256'] = [{'lines':[a,b], 'sha256_utf8_LF':sha(('\n'.join(lines[a-1:b])+'\n').encode())}
                             for a,b in [(7376,7389),(7405,7445),(7450,7495)]]
inventory = collections.Counter(p.suffix.lower() for p in CONTENTS.rglob('*') if p.is_file())
view_path = OUT / 'rea-transport-source-module-view.json'
view = json.loads(view_path.read_text())
assert view['operation'] == 'inspect_analysis_view'
assert view['normalized_result']['item']['hashes'] == [api['sha256']]
result = {
    'id':'MUSICAL-TIME-001', 'target':'Cubase Pro 15.0.30.287 macOS bundle',
    'mode':'static-only; no target code execution',
    'resource_manifest_sha256':sha(seal_bytes),
    'bounded_inventory': {'scope':'Contents tree only; case-insensitive suffix counts; not installer-wide',
        'counts':{k:inventory[k] for k in ['.cpr','.trackarchive','.mid','.midi','.h','.xml','.json','.xsd','.dtd','.js']}},
    'quantize_presets': {'sources':presets, 'only_varying_payload_byte_offsets':differences,
        'interpretation':'The filenames and isolated LE-u32 changes identify a candidate quantize-size field. Straight names store quarter=480, eighth=240, sixteenth=120. Names containing Triplet store 360,180,90 respectively. This is a byte observation; operation semantics and hidden scaling are unproved. It does not establish native PPQ or prove that the named triplet presets execute an incorrect grid.'},
    'transport_api_declarations':api,
    'rea': {'version':'6.7.0', 'view_evidence_id':view['evidence_id'],
        'parent_evidence_id':view['parameters']['parent_evidence_id'],
        'view_file':str(view_path.relative_to(ROOT)), 'view_sha256':sha(view_path.read_bytes()),
        'coverage':'Exact selected source module from previously retained three-source partial JS analysis; no producer rerun, no native implementation recovered.',
        'failed_attempts':[{'file':'rea-quantize-artifact.json','reason':'XML rejected as unsupported binary format; no analysis produced'},
                           {'file':'rea-transport-module-view.json','reason':'Path selector ambiguous; corrected to exact source-module node_id'}]},
    'limitations':['The API source declares strings and BPM but does not define their parsing, precision, native transport implementation, or time-map integration.',
                   'No MIDI files or trackarchives were found within this app Contents tree; absence outside that bounded scope is unknown.',
                   'No native timing instructions were traced in this investigation.',
                   'CPR parsing is a separate investigation and is not inferred from these XML presets.'],
    'implementation_boundary':'New MusicalTime model is an application implementation guided by documented user-visible contracts. Its arithmetic, validation bounds, rounding, and unsupported ramps are explicit app policies, not reconstructed native Cubase arithmetic.'
}
(OUT / 'finding.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps({'finding_sha256':sha((OUT/'finding.json').read_bytes()),'resource_matches':len(presets)+1,'view_evidence_id':view['evidence_id']}))
