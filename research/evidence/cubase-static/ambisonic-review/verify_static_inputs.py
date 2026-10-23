#!/usr/bin/env python3
"""Independent metadata/table checks; never load or execute the target library."""
import hashlib
import json
import math
import pathlib
import struct
from datetime import datetime, timezone

OUT = pathlib.Path(__file__).resolve().parent
SOURCE = OUT.parent / 'ambisonic'

def digest(data):
    return hashlib.sha256(data).hexdigest()

def read(name):
    result = json.loads((SOURCE / name).read_text())
    return result.get('structuredContent', result)

def normalized(name):
    result = read(name)['normalized_result']
    return result.get('value', result)

derivation = read('arm64-derivation.json')
original = pathlib.Path(derivation['source_path']).read_bytes()
thin = pathlib.Path(derivation['derived_path']).read_bytes()
assert digest(original) == derivation['source_sha256']
assert digest(thin) == derivation['derived_sha256']
assert original[derivation['source_offset']:derivation['source_offset'] + derivation['length']] == thin

assert struct.unpack_from('<I', thin)[0] == 0xfeedfacf
segments = []
cursor = 32
for _ in range(struct.unpack_from('<I', thin, 16)[0]):
    command, size = struct.unpack_from('<II', thin, cursor)
    if command == 0x19:
        vmaddr, vmsize, fileoff, filesize = struct.unpack_from('<QQQQ', thin, cursor + 24)
        segments.append((vmaddr, vmsize, fileoff, filesize))
    cursor += size

def source_offset(address, length):
    candidates = [fileoff + address - vmaddr for vmaddr, _, fileoff, filesize in segments
                  if vmaddr <= address and address + length <= vmaddr + filesize]
    assert len(candidates) == 1, (hex(address), candidates)
    return candidates[0]

tables = normalized('conversion-constant-tables.json')
mapping = normalized('conversion-tables-file-mapping.json')
table_bytes = bytes.fromhex(tables['bytes_hex'])
assert tables['complete'] and len(table_bytes) == 388
assert table_bytes == thin[mapping['file_offset']:mapping['file_offset'] + len(table_bytes)]
base = int(tables['address'], 16)
assert source_offset(base, len(table_bytes)) == mapping['file_offset']
maps = [list(struct.unpack_from('<16I', table_bytes, a-base)) for a in (0x18d15c, 0x18d19c)]
gains = [list(struct.unpack_from('<16d', table_bytes, a-base)) for a in (0x18d1e0, 0x18d260)]
assert maps[0][:4] == [0, 3, 1, 2]
assert maps[1][:4] == [0, 2, 3, 1]
assert all(maps[1][maps[0][i]] == i for i in range(4))

f32 = lambda x: struct.unpack('<f', struct.pack('<f', x))[0]
vt = normalized('algorithm-vtables.json')
vt_bytes = bytes.fromhex(vt['bytes_hex'])
vt_base = int(vt['address'], 16)
slots = []
for address, expected in ((0x1d7678, 0x154a8c), (0x1d76b0, 0x154b64),
                          (0x1d7798, 0x154d4c), (0x1d77d0, 0x154e28)):
    observed = struct.unpack_from('<Q', vt_bytes, address-vt_base)[0]
    file_offset = source_offset(address, 8)
    source = struct.unpack_from('<Q', thin, file_offset)[0]
    assert observed == expected == source
    slots.append({'slot_address': hex(address), 'target': hex(expected), 'source_bytes_match': True,
                  'independently_mapped_file_offset': file_offset})

evidence_names = [
    'arm64-derivation.json', 'conversion-constant-tables.json', 'conversion-tables-file-mapping.json',
    'direction-parameter-consumer.json', 'float-channel-permutation-function.json',
    'float-conversion-process-function.json', 'float-buffer-copy-function.json',
    'float-bypass-process-function.json', 'double-channel-permutation-function.json',
    'double-conversion-process-function.json', 'double-buffer-copy-function.json', 'processor-process-function.json',
    'processor-bus-arrangement-function.json', 'processor-activation-function.json',
    'algorithm-vtables.json', 'conversion-registration-function.json', 'external-abi-references.json',
    'reference-ivstaudioprocessor.h', 'reference-ivstparameterchanges.h', 'reference-vdsp-vsmul.md',
    'first-order-finding.json', 'first-order-byte-ranges.json',
]
inputs = []
for name in evidence_names:
    path = SOURCE / name
    if not path.exists():
        inputs.append({'file': '../ambisonic/' + name, 'status': 'not_yet_present'})
        continue
    data = path.read_bytes()
    item = {'file': '../ambisonic/' + name, 'bytes': len(data), 'sha256': digest(data)}
    if name.endswith('.json'):
        x = read(name)
        if 'evidence_id' in x:
            if x.get('provider', {}).get('id') == 'ghidra':
                assert x['subject']['digest']['sha256'] == derivation['derived_sha256']
            item.update({'evidence_id': x['evidence_id'], 'provider': x.get('provider'),
                         'relationship_coverage': x.get('relationship_coverage')})
    inputs.append(item)

byte_ranges = read('first-order-byte-ranges.json')
range_count = 0
for function in byte_ranges['functions']:
    record = read(function['evidence_file'])
    assert record['evidence_id'] == function['evidence_id']
    ranges = normalized(function['evidence_file'])['procedure']['body']['ranges']
    assert len(ranges) == len(function['ranges'])
    for entry, analyzed in zip(function['ranges'], ranges):
        assert entry['address_start'] == analyzed['start']
        assert entry['address_end_inclusive'] == analyzed['end']
        start = int(entry['address_start'], 16)
        assert int(entry['address_end_inclusive'], 16)-start+1 == entry['length']
        assert source_offset(start, entry['length']) == entry['thin_file_offset']
        block = thin[entry['thin_file_offset']:entry['thin_file_offset']+entry['length']]
        assert digest(block) == entry['sha256']
        assert original[entry['original_file_offset']:entry['original_file_offset']+entry['length']] == block
        range_count += 1
finding = read('first-order-finding.json')
for evidence in finding['evidence']:
    assert read(evidence['file'])['evidence_id'] == evidence['evidence_id']
references = read('external-abi-references.json')['references']
for reference in references:
    assert digest((SOURCE / reference['local_file']).read_bytes()) == reference['sha256']

report = {
    'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
    'scope': 'Independent source-byte and retained-analysis consistency checks, not target execution.',
    'target_executed': False,
    'source_sha256_verified': digest(original),
    'arm64_sha256_verified': digest(thin),
    'exact_architecture_slice_match': True,
    'finalized_contract_integrity': {
        'function_ranges_checked': range_count, 'functions_checked': len(byte_ranges['functions']),
        'range_digests_and_source_mappings_match': True,
        'finding_evidence_ids_checked': len(finding['evidence']),
        'external_reference_digests_checked': len(references),
    },
    'constant_tables': {
        'address': tables['address'], 'length': len(table_bytes), 'sha256': digest(table_bytes),
        'rea_read_equals_source': True,
        'map_low_first_order': maps[0][:4], 'map_high_first_order': maps[1][:4],
        'first_order_maps_are_inverses': True,
        'gain_low_first_order': gains[0][:4], 'gain_high_first_order': gains[1][:4],
        'w_gain_binary64_le_hex': [struct.pack('<d', g[0]).hex() for g in gains],
        'w_gain_binary32_values': [f32(g[0]) for g in gains],
        'w_gain_binary32_le_hex': [struct.pack('<f', g[0]).hex() for g in gains],
        'reverse_gain_differs_from_sqrt_half_binary64': gains[1][0] != math.sqrt(0.5),
    },
    'relevant_vtable_slots': slots,
    'entire_vtable_read_equals_raw_source': vt_bytes == thin[source_offset(vt_base, len(vt_bytes)):source_offset(vt_base, len(vt_bytes))+len(vt_bytes)],
    'vtable_note': 'Four relevant slots match original source bytes. Other read bytes differ; REA reads initialized analysis memory including loader fixups. Do not claim full read equality.',
    'synthetic_numeric_checks': {
        'meaning': 'Arithmetic sanity checks only; not observed Accelerate or Cubase behavior.',
        'unit_w_float32_two_step_roundtrip': f32(f32(gains[0][0]) * f32(gains[1][0])),
        'unit_w_float64_two_step_roundtrip': gains[0][0] * gains[1][0],
        'no_exact_roundtrip_claim': True,
    },
    'inputs': inputs,
}
(OUT / 'static-input-checks.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: report[k] for k in ('source_sha256_verified', 'arm64_sha256_verified', 'constant_tables', 'relevant_vtable_slots')}, indent=2))
