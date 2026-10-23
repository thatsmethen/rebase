"""Independent original-image readbacks and REA evidence custody checks.

This verifies byte identities and typed slots, not behavioral completeness.
No proprietary code is executed or emulated.
"""
from pathlib import Path
import hashlib
import json
import re
import sys
sys.dont_write_bytecode = True
H = Path(__file__).resolve().parent
R = H.parents[4]
sys.path.insert(0, str(R / 'research/evidence/cubase-static/cpr-map-clock-001/attributes'))
import source_tools as s


def pin(p):
    data = p.read_bytes()
    return dict(path=str(p.relative_to(R)), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def envelope(p):
    w = json.loads(p.read_text())
    assert not w.get('isError'), p
    return w.get('structuredContent') or json.loads(w['content'][0]['text'])


uses = {}
for folder in sorted(H.glob('pass*')):
    if not folder.is_dir():
        continue
    deriv = json.loads((folder / 'derivation.json').read_text())
    assert deriv['source_sha256'] == s.PIN
    for row in deriv['derivatives']:
        raw = folder / row['raw_file']
        assert pin(raw)['sha256'] == row['raw_sha256']
        assert raw.read_bytes() == bytes.fromhex(s.region(int(row['entry'], 16), row['length'])['bytes_hex'])
    lines = (folder / 'run.log').read_text().splitlines()
    assert lines[-1] == 'CLOSED: isolated raw-slice MCP session'
    assert all(json.loads(line)['isError'] is False for line in lines[:-1])
    uses[folder] = [int(row['entry'], 16) for row in deriv['derivatives']]
    for a in uses[folder]:
        close = envelope(folder / f'close-{a:x}.json')['result']
        assert close['evidence_records'] == 2
        assert Path(close['path']).stat().st_size == close['bytes']

prior = [
    ('cpr-audio-events-001/placed-event-builder/pass1', 0x10020e354),
    ('cpr-audio-events-001/placed-event-builder/pass1', 0x10020e7c8),
    ('cpr-audio-events-001/placed-event-builder/pass1', 0x10020f2e8),
    ('cpr-audio-events-001/track-contributors/pass1', 0x1000ea130),
    ('cpr-audio-events-001/track-contributors/pass1', 0x1002136ec),
    ('cpr-signature-001/pass12', 0x103101e50),
    ('cpr-audio-events-001/track-contributors/pass4', 0x1031016e4),
    ('cpr-audio-events-001/track-contributors/pass4', 0x1030f9c44),
    ('cpr-map-clock-001/attributes/pass3', 0x1030f9c20),
    ('cpr-objects-001/audio-native', 0x1000ee164),
    ('cpr-audio-events-001/audible-state/pass15', 0x1000e9148),
    ('cpr-audio-events-001/event-rendering/pass2', 0x1000ea704),
    ('cpr-audio-events-001/event-rendering/pass2', 0x1000ea694),
    ('cpr-audio-events-001/event-rendering/pass2', 0x100212f3c),
    ('cpr-audio-events-001/timeline-provider/pass7', 0x1007ddd24),
]
for folder, a in prior:
    uses.setdefault(R / 'research/evidence/cubase-static' / folder, []).append(a)

rows = []
for folder, addresses in uses.items():
    for a in addresses:
        paths = [folder / f'{v}-{a:x}.json' for v in ['function', 'bytes', 'bundle']]
        native = folder / f'native-{a:x}.txt'
        words = {int(pc, 16): int(w, 16) for pc, w in
                 re.findall(r'^([0-9a-f]+):\s+([0-9a-f]{8})\s', native.read_text(), re.M)}
        for pc, w in words.items():
            assert int.from_bytes(bytes.fromhex(s.region(pc, 4)['bytes_hex']), 'little') == w
        dossier, read, bundle = [envelope(p) for p in paths]
        q = read['raw_result']
        assert q['complete'] and q['requested_bytes'] == q['returned_bytes']
        original = bytes.fromhex(s.region(a, q['returned_bytes'])['bytes_hex'])
        assert original == bytes.fromhex(q['bytes_hex']) and len(original) == len(words) * 4
        asm = dossier['raw_result']['value']['assembly']
        assert all(int(v.split(':')[0], 16) in words for v in asm)
        assert len(bundle['result']['records']) == 2
        rows.append(dict(entry=hex(a), new=folder.parent == H, directory=str(folder.relative_to(R)),
            bytes_verified=len(original), original_native_words=len(words), rea_instruction_addresses=len(asm),
            evidence_ids=[dossier['evidence_id'], read['evidence_id']], files=[pin(p) for p in [native] + paths]))

bindings = []
for table, label, slots in [
    (0x10442e898, 'MAudioEvent', {0x98: 0x1000ee164, 0x1a8: 0x1000ea130}),
    (0x10444da18, 'range', {0xc8: 0x1002136ec}),
]:
    for slot, value in slots.items():
        reg = s.region(table + slot, 8)
        assert int.from_bytes(bytes.fromhex(reg['bytes_hex']), 'little') == value
        bindings.append(dict(label=label, table=hex(table), slot=hex(slot), target=hex(value), source=reg))

spans = []
for label, a, n in [
    ('epsilon and initial watermark constants', 0x10020e7ec, 28),
    ('overlap epsilon comparison', 0x10020e884, 32),
    ('signed priority and ordinal comparisons', 0x10020e91c, 108),
    ('weaker following removal tail threshold', 0x10020e988, 48),
    ('tail reinsertion backward scan', 0x10020e9c8, 60),
    ('current split threshold and copied tail start', 0x10020ea84, 60),
    ('prefix epsilon and publication', 0x10020eb3c, 104),
    ('ordinal event context clone values', 0x10021372c, 44),
    ('serialized priority direct read', 0x1000ee2f0, 20),
    ('collector ordinal initialize', 0x10020e42c, 4),
    ('collector ordinal store and increment', 0x10020e524, 48),
    ('builder original source offset compensation', 0x10020f480, 64),
    ('plain remainder build', 0x1002104fc, 220),
]:
    spans.append(dict(label=label, source=s.region(a, n)))

result = dict(source_sha256=s.PIN, target_executed=False, functions=rows, dispatch=bindings,
    original_ranges=spans, summary=dict(new_captures=sum(r['new'] for r in rows),
        reused_captures=sum(not r['new'] for r in rows), bytes_verified=sum(r['bytes_verified'] for r in rows),
        original_native_words=sum(r['original_native_words'] for r in rows),
        rea_instruction_addresses=sum(r['rea_instruction_addresses'] for r in rows),
        closed_raw_sessions=len(list(H.glob('pass*/run.log'))), canonical_records=2 * len(rows)),
    passed=True, limits=['Source readbacks and canonical identities are custody, not hosted semantic coverage.',
        'LC_FUNCTION_STARTS intervals include possible disconnected tails; assembly addresses are checked individually.',
        'Raw imports omit external globals/types/callbacks; original instructions govern the finite-value contract.',
        'No proprietary target code is run or emulated.'])
(H / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result['summary']))
