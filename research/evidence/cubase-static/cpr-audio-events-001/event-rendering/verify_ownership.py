"""Verify only the bounded root/list ownership appendix; never execute Cubase."""
from pathlib import Path
import hashlib, json, re, struct, sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
STATIC = ROOT / 'research/evidence/cubase-static'
sys.path.insert(0, str(STATIC / 'cpr-map-clock-001/attributes'))
import source_tools as source

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def evidence(p):
    value = json.loads(p.read_text())
    assert not value.get('isError', False), p
    return value.get('structuredContent') or json.loads(value['content'][0]['text'])

inputs = []
for number in [12, 13]:
    base = HERE / f'pass{number}'
    derivation = json.loads((base/'derivation.json').read_text())
    for item in derivation['derivatives']:
        inputs.append((base, item['entry'][2:], 'new ownership capture'))
    assert 'CLOSED: isolated raw-slice MCP session' in (base/'analysis-progress.log').read_text()
for relative, entries in [
    ('cpr-signature-001/pass9', ['101758eec', '1017154a0']),
    ('cpr-signature-001/pass11', ['101716448', '1016c137c']),
    ('cpr-audio-events-001/autofade-source/pass1', ['101722120']),
    ('cpr-audio-events-001/autofade-source/pass2', ['1017017a0']),
    ('cpr-audio-events-001/timebase/pass23', ['10171759c']),
    ('cpr-audio-events-001/timebase/pass12', ['10174a698']),
    ('cpr-map-clock-001/list', ['101700eb4', '1016e9058', '1016e9a30']),
    ('cpr-audio-events-001/event-rendering/pass3', ['1001f7554']),
    ('cpr-audio-events-001/event-rendering/pass5', ['1001fcf1c', '101720d58']),
]:
    inputs.extend((STATIC/relative, entry, 'reused retained capture') for entry in entries)

rows = []
for base, entry, kind in inputs:
    rb = evidence(base/f'bytes-{entry}.json')['raw_result']
    start = int(rb['address'], 16)
    raw = bytes.fromhex(rb['bytes_hex'])
    assert rb['complete'] and rb['returned_bytes'] == rb['requested_bytes'] == len(raw)
    original = source.region(start, len(raw))
    assert raw.hex() == original['bytes_hex']
    native = (base/f'native-{entry}.txt').read_text()
    words = {int(a,16):int(w,16) for a,w in re.findall(r'^([0-9a-f]+):\s+([0-9a-f]{8})\s', native,re.M)}
    assert len(words) == len(raw)//4
    assert all(struct.unpack_from('<I', raw, a-start)[0] == w for a,w in words.items())
    record = evidence(base/f'function-{entry}.json')
    assembly = record['raw_result']['value']['assembly']
    addresses = [int(x.split(':')[0],16) for x in assembly]
    assert len(addresses) == len(set(addresses)) and all(a in words for a in addresses)
    records = evidence(base/f'bundle-{entry}.json')['result']['records']
    evidence(base/f'close-{entry}.json')
    assert (base/f'snapshot-{entry}.json').is_file()
    files = [base/f'{prefix}-{entry}.json' for prefix in ['function','bytes','bundle','close','snapshot']]
    files.append(base/f'native-{entry}.txt')
    rows.append(dict(entry=hex(start), kind=kind, directory=str(base.relative_to(ROOT)),
        source_bytes=len(raw), source_range_sha256=original['sha256'],
        native_words=len(words), rea_instruction_addresses=len(addresses),
        evidence_ids=[r['evidence_id'] for r in records],
        files=[dict(path=str(p.relative_to(ROOT)), sha256=sha(p)) for p in files],
        bytes_and_instruction_words_match_original=True))

def totals(kind):
    selected=[r for r in rows if r['kind']==kind]
    return dict(functions=len(selected), source_bytes=sum(r['source_bytes'] for r in selected),
        native_words=sum(r['native_words'] for r in selected),
        rea_instruction_addresses=sum(r['rea_instruction_addresses'] for r in selected),
        unique_evidence_records=len({v for r in selected for v in r['evidence_ids']}))

out = dict(source_sha256='dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb',
    scope='Exact original/readback/native-word/address custody; semantic conclusions are separately bounded.',
    target_execution=False, passed=True, new=totals('new ownership capture'),
    reused=totals('reused retained capture'), functions=rows,
    sessions='Both new pass12/pass13 sessions explicitly closed; every cited function has retained close and snapshot.')
(HERE/'ownership-verification.json').write_text(json.dumps(out, indent=2)+'\n')
print(json.dumps({k:out[k] for k in ['passed','new','reused']}))
