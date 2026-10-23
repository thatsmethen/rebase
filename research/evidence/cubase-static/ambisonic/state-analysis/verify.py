"""Validate new double-bypass REA evidence against the original-byte derivative."""
from pathlib import Path
import hashlib
import json
import re

P = Path(__file__).resolve().parent
sha = lambda b: hashlib.sha256(b).hexdigest()
def tool(name):
    r = json.loads((P / name).read_text())
    assert not r.get('isError'), name
    return r['structuredContent']

raw = (P / 'double-bypass.arm64.bin').read_bytes()
provenance = json.loads((P / 'byte-provenance.json').read_text())
assert sha(raw) == provenance['double_bypass_derivative']['sha256']
record = tool('double-bypass-function.json')
r = record['normalized_result']
b = tool('double-bypass-bytes.json')['normalized_result']
assert b['complete'] and b['returned_bytes'] == len(raw) == 120
assert bytes.fromhex(b['bytes_hex']) == raw
assert record['subject']['digest']['sha256'] == sha(raw)
assert record['analysis_profile']['parameters']['analyzer_preset'] == 'ghidra-default'
assert r['procedure']['body']['ranges'] == [{'start': '0x154b64', 'end': '0x154bdb'}]
native = {}
for m in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(.+)$',
                     (P / 'native-double-bypass.txt').read_text(), re.M):
    addr, word = int(m[1], 16), int(m[2], 16)
    assert raw[addr - 0x154b64:addr - 0x154b64 + 4] == word.to_bytes(4, 'little')
    native[addr] = {'address': hex(addr), 'word': m[2], 'native': m[3].strip()}
assert len(native) == len(r['assembly']) == 30
for line in r['assembly']:
    addr, asm = line.split(': ', 1)
    native[int(addr, 16)]['rea'] = asm
assert all('rea' in row for row in native.values())
bundle = tool('evidence-bundle.json')['result']
snapshot = json.loads((P / 'snapshot.json').read_text())
assert snapshot['evidence_bundle'] == bundle
assert len(bundle['records']) == tool('close.json')['result']['evidence_records'] == 2
report = dict(passed=True, scope='Static source/REA-readback and native word-address verification only',
              bytes=120, instructions=list(native.values()), evidence_id=record['evidence_id'],
              analysis_profile=record['analysis_profile'], snapshot_and_bundle_match=True,
              source_original_range=provenance['double_bypass_derivative'],
              raw_context_loss='Raw slice lacks external copy helper bytes and import/vtable metadata; correlate separately with retained original-image evidence.',
              total_original_words_checked=provenance['total_retained_instructions'] + len(native))
(P / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
(P / 'double-bypass-pseudocode.txt').write_text(r['pseudocode'])
(P / 'double-bypass-assembly.txt').write_text('\n'.join(r['assembly']) + '\n')
print(json.dumps({'passed': True, 'new_words':len(native), 'all_words':report['total_original_words_checked']}))
