#!/usr/bin/env python3
"""Independent read-only validation of raw-slice evidence; writes only this review directory."""
import hashlib
import json
import pathlib
import re
import struct
from datetime import datetime, timezone

OUT = pathlib.Path(__file__).resolve().parent
SRC = OUT.parent / 'main-function-slices'
def sha(b): return hashlib.sha256(b).hexdigest()
def read(name):
    value = json.loads((SRC / name).read_text())
    return value.get('structuredContent', value)
def normalized(name):
    value = read(name)['normalized_result']
    return value.get('value', value)

report = read('raw-slice-analysis.json')
source = pathlib.Path(report['source']).read_bytes()
assert sha(source) == 'dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb'
assert len(source) == report['source_bytes'] == 85691328
assert struct.unpack_from('<I', source)[0] == 0xfeedfacf
segments = []
cursor = 32
for _ in range(struct.unpack_from('<I', source, 16)[0]):
    cmd, size = struct.unpack_from('<II', source, cursor)
    if cmd == 0x19:
        name = source[cursor+8:cursor+24].split(b'\0')[0].decode()
        va, vs, off, fs = struct.unpack_from('<QQQQ', source, cursor+24)
        segments.append((name, va, vs, off, fs))
    if cmd == 0x26:
        starts_offset, starts_length = struct.unpack_from('<II', source, cursor+8)
    cursor += size
text_base = next(va for name, va, _, _, _ in segments if name == '__TEXT')
starts_bytes = source[starts_offset:starts_offset+starts_length]
starts, address, delta, shift = [], text_base, 0, 0
for byte in starts_bytes:
    delta |= (byte & 0x7f) << shift
    if byte & 0x80:
        shift += 7
    else:
        if delta == 0: break
        address += delta
        starts.append(address)
        delta, shift = 0, 0

def offset(va, length):
    matches = [off + va-start for _, start, _, off, fs in segments if start <= va and va+length <= start+fs]
    assert len(matches) == 1
    return matches[0]

def word(va): return struct.unpack_from('<I', source, offset(va,4))[0]

def branch_target(va):
    value = word(va)
    assert value >> 26 == 0b000101
    imm26 = value & 0x3ffffff
    if imm26 & 0x2000000: imm26 -= 0x4000000
    return va + (imm26 << 2)

totals = {'bytes': 0, 'native_words': 0, 'rea_instructions': 0}
results, inputs = [], []
for function in report['functions']:
    entry = int(function['entry'],16)
    end = int(function['next_declared_function_start'],16)
    assert starts[starts.index(entry)+1] == end
    assert end-entry == function['length']
    assert offset(entry,end-entry) == function['source_file_offset']
    tag = function['entry'][2:]
    raw_file = function['raw_file']
    raw = (SRC/raw_file).read_bytes()
    assert sha(raw) == function['raw_sha256']
    assert raw == source[offset(entry,end-entry):offset(entry,end-entry)+end-entry]
    b = normalized('bytes-'+tag+'.json')
    assert b['complete'] and b['requested_bytes'] == b['returned_bytes'] == len(raw)
    assert int(b['address'],16) == entry and bytes.fromhex(b['bytes_hex']) == raw
    ev = read('function-'+tag+'.json')
    assert ev['evidence_id'] == function['analyze_function_evidence_id']
    assert ev['subject']['digest']['sha256'] == sha(raw)
    assert ev['analysis_profile']['digest'] == function['profile_digest']
    n = normalized('function-'+tag+'.json')
    native_text = (SRC/function['original_native_disassembly']).read_text()
    assert sha(native_text.encode()) == function['native_stdout_sha256']
    native = {}
    for line in native_text.splitlines():
        m = re.match(r'\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(.*)',line)
        if m:
            va, w = int(m[1],16), int(m[2],16)
            assert entry <= va < end and word(va) == w
            native[va] = m[3]
    assert sorted(native) == list(range(entry,end,4))
    decoded, aliases = [], []
    for line in n['assembly']:
        address, asm = line.split(': ',1)
        va = int(address,16)
        assert va in native
        first, second = asm.split()[0], native[va].split()[0]
        if first != second:
            assert va == 0x100d7c108 and {first,second} == {'b.cs','b.hs'}
            aliases.append({'address':hex(va),'rea':first,'native':second,'word':f'{word(va):08x}'})
        decoded.append(va)
    assert len(decoded) == len(set(decoded)) == function['rea_body_instruction_count']
    assert len(native) == function['native_interval_instruction_count']
    expected_missing = list(range(0x100d7c178,0x100d7c18c,4)) if entry == 0x100d7c0cc else []
    missing = sorted(set(native)-set(decoded))
    assert missing == expected_missing
    results.append({'entry':hex(entry),'length':len(raw),'raw_sha256':sha(raw),
                    'source_readback_equality':True,'metadata_next_entry_verified':hex(end),
                    'native_words_verified':len(native),'rea_addresses_verified':len(decoded),
                    'omitted_native_addresses':[hex(v) for v in missing], 'mnemonic_aliases':aliases})
    totals['bytes'] += len(raw)
    totals['native_words'] += len(native)
    totals['rea_instructions'] += len(decoded)
    for name in [raw_file,function['dossier'],'bytes-'+tag+'.json',
                 function['original_native_disassembly'],function['pseudocode']]:
        inputs.append({'file':'../main-function-slices/'+name,'sha256':sha((SRC/name).read_bytes())})

assert totals == {'bytes':928,'native_words':232,'rea_instructions':227}
tails = []
for va,target in [(0x1007dd560,0x1007d9e40),(0x1007dd814,0x1007dd454)]:
    assert branch_target(va) == target
    tails.append({'instruction':hex(va),'word':f'{word(va):08x}',
                  'independently_decoded_B_target':hex(target),
                  'instruction_is_valid_unconditional_branch':True})
assert word(0x100d7c0e8) == 0x1f420400
assert word(0x100d7c0ec) == 0x1e780014
assert word(0x100d7c108) == 0x54000122
assert word(0x100d7c174) == 0xd65f03c0
verification_bytes = (SRC/'verification.json').read_bytes()
assert sha(verification_bytes) == report['verification']['sha256']
v = json.loads(verification_bytes)
assert v['total_native_interval_instructions'] == totals['native_words']
assert v['total_rea_body_instructions'] == totals['rea_instructions']
for name in ['raw-slice-analysis.json','verification.json','derivation.json']:
    inputs.append({'file':'../main-function-slices/'+name,'sha256':sha((SRC/name).read_bytes())})
output = {'recorded_utc':datetime.now(timezone.utc).isoformat(),
          'scope':'Independent static source/readback/boundary/address checks, not target execution or a behavioral equivalence test.',
          'target_executed':False,'new_import':False,'passed':True,
          'source_sha256':sha(source),'function_starts_blob_sha256':sha(starts_bytes),
          'totals':totals,'functions':results,'tail_branch_decoding':tails,'inputs':inputs}
(OUT/'checks.json').write_text(json.dumps(output,indent=2)+'\n')
print(json.dumps({'passed':True,'totals':totals,'tail_branches':tails},indent=2))
