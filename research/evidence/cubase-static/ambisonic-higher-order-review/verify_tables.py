#!/usr/bin/env python3
"""Independent byte/table consistency checks; never loads or executes target code."""
import hashlib
import json
import pathlib
import re
import struct
from datetime import datetime, timezone
from fractions import Fraction

OUT = pathlib.Path(__file__).resolve().parent
SRC = OUT.parent / 'ambisonic'

def sha(b):
    return hashlib.sha256(b).hexdigest()

def read(name):
    data = json.loads((SRC / name).read_text())
    return data.get('structuredContent', data)

def normalized(name):
    data = read(name)['normalized_result']
    return data.get('value', data)

def bits_fraction(bits, mantissa_bits, bias):
    exponent = (bits >> mantissa_bits) - bias
    significand = (1 << mantissa_bits) + (bits & ((1 << mantissa_bits) - 1))
    return Fraction(significand) * Fraction(2) ** (exponent - mantissa_bits)

def narrow_nearest_even(bits):
    """Positive finite normal f64 -> f32 using only exact integer/rational arithmetic."""
    x = bits_fraction(bits, 52, 1023)
    e = x.numerator.bit_length() - x.denominator.bit_length()
    if x < Fraction(2) ** e:
        e -= 1
    z = x * Fraction(2) ** (23 - e)
    q, r = divmod(z.numerator, z.denominator)
    if 2*r > z.denominator or (2*r == z.denominator and q % 2):
        q += 1
    if q == 1 << 24:
        q >>= 1
        e += 1
    assert -126 <= e <= 127
    return ((e + 127) << 23) | (q - (1 << 23))

d = read('arm64-derivation.json')
original = pathlib.Path(d['source_path']).read_bytes()
thin = pathlib.Path(d['derived_path']).read_bytes()
assert sha(original) == 'e803dd1390ee7989306b15c0fccca52e5d3097ae7a489dc6834f82b50ba485c5'
assert sha(thin) == 'e8341c6b31ac6b65cf7e8c18bdfbaa18ac24b20160b4287dc385b202eb29b883'
assert original[d['source_offset']:d['source_offset'] + d['length']] == thin
assert struct.unpack_from('<I', thin)[0] == 0xfeedfacf
segments = []
cursor = 32
for _ in range(struct.unpack_from('<I', thin, 16)[0]):
    cmd, length = struct.unpack_from('<II', thin, cursor)
    if cmd == 0x19:
        va, vs, off, fs = struct.unpack_from('<QQQQ', thin, cursor + 24)
        segments.append((va, vs, off, fs))
    cursor += length

def file_offset(va, count):
    match = [off + va - start for start, _, off, fs in segments
             if start <= va and va + count <= start + fs]
    assert len(match) == 1
    return match[0]

def raw(va, count):
    off = file_offset(va, count)
    return thin[off:off + count]

table_read = normalized('conversion-constant-tables.json')
assert table_read['complete']
table_bytes = raw(0x18d15c, 388)
assert table_bytes == bytes.fromhex(table_read['bytes_hex'])
assert sha(table_bytes) == 'c49accecf95f469477a7f57bcc31e6e35ff5d51ee1ff63479b9268bb5a3fc874'

tables = {}
for name, address, form, size in [('map_A', 0x18d15c, '<16I', 64),
                                  ('map_B', 0x18d19c, '<16I', 64),
                                  ('gain_A', 0x18d1e0, '<16Q', 128),
                                  ('gain_B', 0x18d260, '<16Q', 128)]:
    b = raw(address, size)
    values = list(struct.unpack(form, b))
    entry = {'address': hex(address), 'length': size,
             'thin_file_offset': file_offset(address, size), 'sha256': sha(b)}
    if name.startswith('gain'):
        entry['binary64_bits'] = [f'0x{v:016x}' for v in values]
        entry['binary32_nearest_even_bits'] = [f'0x{narrow_nearest_even(v):08x}' for v in values]
    else:
        entry['values'] = values
    tables[name] = entry

contract = read('higher-order-table-contract.json')
operators_checked = 0
for operator in contract['contracts']:
    n, direction = operator['channel_count'], operator['direction']
    m = tables['map_' + direction]['values'][:n]
    inverse = [m.index(j) for j in range(n)]
    assert sorted(m) == list(range(n))
    assert operator['source_to_destination'] == m
    assert operator['destination_to_source'] == inverse
    for precision in (64, 32):
        key = 'binary64_bits' if precision == 64 else 'binary32_nearest_even_bits'
        assert operator['destination_gain_' + key] == tables['gain_' + direction][key][:n]
    for row in operator['per_destination_equations']:
        j = row['destination']
        assert row['source'] == inverse[j] and row['gain_index'] == j
    operators_checked += 1

composition_checks = []
for entry in contract['coefficient_only_compositions']:
    n = entry['channel_count']
    first, second = entry['order'].split('_then_')
    m1 = tables['map_' + first]['values'][:n]
    m2 = tables['map_' + second]['values'][:n]
    g1 = [bits_fraction(int(b,16), 52, 1023) for b in tables['gain_' + first]['binary64_bits'][:n]]
    g2 = [bits_fraction(int(b,16), 52, 1023) for b in tables['gain_' + second]['binary64_bits'][:n]]
    rows = []
    for i in range(n):
        j, k = m1[i], m2[m1[i]]
        assert k == i
        product = g1[j] * g2[k]
        author = entry['rows'][i]
        assert (author['source'], author['intermediate_destination'], author['final_destination']) == (i,j,k)
        assert (author['first_gain_index'], author['second_gain_index']) == (j,k)
        assert Fraction(author['exact_stored_coefficient_product']) == product
        if abs(product - 1) > Fraction(1, 1000000):
            rows.append({'source': i, 'intermediate_destination': j,
                         'exact_stored_coefficient_product': str(product),
                         'decimal_for_display_only': float(product)})
    composition_checks.append({'channels': n, 'order': entry['order'],
                               'permutation_composition_is_identity': True,
                               'coefficient_deviation_exceeding_one_part_per_million': rows})

provenance = read('higher-order-byte-provenance.json')
for table in provenance['tables']:
    independent = tables[table['name']]
    for key in ('sha256', 'length', 'thin_file_offset'):
        assert table[key] == independent[key]

callflow = read('higher-order-callflow-checks.json')
range_checks = []
for fn in callflow['source_function_ranges']:
    ev = read(fn['evidence_file'])
    assert ev['evidence_id'] == fn['evidence_id']
    for r in fn['ranges']:
        addr = int(r['address_start'], 16)
        assert r['thin_file_offset'] == file_offset(addr, r['length'])
        assert r['original_file_offset'] == d['source_offset'] + r['thin_file_offset']
        assert r['sha256'] == sha(raw(addr, r['length']))
        range_checks.append({'evidence_file': fn['evidence_file'], **r})

# Independent raw-word matching validates retained native disassembly's provenance.
word_count = 0
native_counts = []
for name in ['higher-order-instruction-validation.txt',
             'higher-order-double-configuration-assembly.txt',
             'higher-order-configuration-cleanup-assembly.txt']:
    local_count = 0
    for line in (SRC / name).read_text().splitlines():
        match = re.match(r'\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+', line)
        if match:
            address, word = [int(x, 16) for x in match.groups()]
            assert struct.unpack('<I', raw(address, 4))[0] == word
            local_count += 1
    word_count += local_count
    native_counts.append({'file': '../ambisonic/' + name, 'words_matching_source': local_count})
assert word_count > 250

slots = []
for address, expected in ((0x1d7678, 0x154a8c), (0x1d7798, 0x154d4c)):
    assert struct.unpack('<Q', raw(address, 8))[0] == expected
    slots.append({'address': hex(address), 'target': hex(expected), 'source_bytes_match': True})

finding = read('higher-order-finding.json')
inputs = []
for evidence in finding['evidence']:
    name = evidence['file']
    b = (SRC / name).read_bytes()
    ev = read(name)
    assert sha(b) == evidence['file_sha256']
    assert ev['evidence_id'] == evidence['evidence_id']
    assert ev['subject']['digest']['sha256'] == sha(thin)
    inputs.append({'file': '../ambisonic/' + name, 'sha256': sha(b),
                   'evidence_id': ev['evidence_id'], 'provider': ev.get('provider'),
                   'relationship_coverage': ev.get('relationship_coverage')})
for name in ['higher-order-finding.json', 'higher-order-byte-provenance.json',
             'higher-order-table-contract.json', 'higher-order-callflow-checks.json',
             'higher-order-instruction-validation.txt', 'higher-order-instruction-commands.json',
             'higher-order-double-configuration-assembly.txt', 'higher-order-double-configuration-provenance.json',
             'higher-order-configuration-cleanup-assembly.txt', 'higher-order-configuration-cleanup-provenance.json',
             'reference-ivstaudioprocessor.h', 'reference-ivstparameterchanges.h',
             'reference-vdsp-vsmul.md', 'reference-vdsp-vsmuld.md']:
    inputs.append({'file': '../ambisonic/' + name, 'sha256': sha((SRC / name).read_bytes())})

report = {
    'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
    'scope': 'Independent source byte, exact rational coefficient, retained instruction and metadata checks only.',
    'target_executed': False, 'new_ghidra_import': False,
    'original_sha256': sha(original), 'arm64_sha256': sha(thin),
    'source_slice_identical': True,
    'full_388_byte_table_read_equals_source': True, 'table_read_sha256': sha(table_bytes),
    'tables': tables, 'operators_checked': operators_checked,
    'float_narrowing_method': 'Independent exact rational nearest-even conversion. Not a claim about runtime FPCR.',
    'compositions': composition_checks,
    'composition_scope': 'Exact products of stored binary64 coefficients, no simulated or observed target samples. Nonidentity is conditional on the reviewed static operator being invoked without intervening routing/state transformations.',
    'instruction_words_matched_to_source': word_count,
    'native_disassembly_checks': native_counts,
    'source_function_ranges_checked': range_checks, 'normal_dispatch_vtable_slots': slots,
    'inputs': inputs,
}
(OUT / 'table-checks.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'status': 'pass', 'operators_checked': operators_checked,
                  'instruction_words_matched': word_count, 'source_ranges_checked': len(range_checks),
                  'composition_summaries': composition_checks}, indent=2))
