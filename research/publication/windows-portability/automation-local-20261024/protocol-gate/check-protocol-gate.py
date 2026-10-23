#!/usr/bin/env python3
"""Authored negative controls for the production automation receipt gate."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
parser = argparse.ArgumentParser()
parser.add_argument('--root', type=Path, default=Path.cwd())
parser.add_argument('--receipt', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
root = args.root.resolve()
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=False)
gate_path = root / 'Application/scripts/windows_automation_gate.py'
spec = importlib.util.spec_from_file_location('subject_automation_gate', gate_path)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
receipt_bytes = args.receipt.read_bytes()
session = json.loads(receipt_bytes)
example_path = root / 'Application/Examples/Rebase Preview.rebaseproj/Project.json'
lock_path = root / 'Application/scripts/example-render-lock.json'
example = json.loads(example_path.read_bytes())
lock = json.loads(lock_path.read_bytes())
rows = []

def check(name, transform=None, accept=False):
    s, e, l = copy.deepcopy(session), copy.deepcopy(example), copy.deepcopy(lock)
    if transform:
        transform(s, e, l)
    try:
        gate.require_automation_protocol(s, e, l)
    except RuntimeError as error:
        actual = False
        detail = str(error)
    except Exception as error:
        actual = None
        detail = type(error).__name__
    else:
        actual, detail = True, None
    rows.append({'name': name, 'expected_acceptance': accept, 'accepted': actual,
                 'passed': actual is accept, 'detail': detail})

def set_record(key, value):
    return lambda s, e, l: s['automation'].__setitem__(key, value)

check('actual-production-helper-receipt-accepted', accept=True)
for key in gate.PROTOCOL_GATES:
    for value, suffix in [(False, 'false'), (1, 'integer-truthiness')]:
        check(f'{key}-{suffix}-rejected', set_record(key, value))
    check(f'{key}-missing-rejected', lambda s, e, l, key=key: s['automation'].pop(key))
for value in [None, [], 'passed']:
    check(f'automation-container-{type(value).__name__}-rejected', lambda s, e, l, value=value: s.__setitem__('automation', value))
for key, values in {
    'original_point_count': [4, 6, True, 5.0],
    'mutation_count': [7, 8, 9, True, 10.0],
    'invalid_requests_checked': [14, True, 15.0],
    'evidence_class': ['target-reference-observation', None],
    'playback_tested': [True, 0, None],
}.items():
    for index, value in enumerate(values):
        check(f'{key}-invalid-{index + 1}-rejected', set_record(key, value))
for key in ['original_track_id', 'original_lane_id']:
    check(f'{key}-binding-mismatch-rejected', set_record(key, '00000000-0000-0000-0000-000000000000'))
    def malformed(s, e, l, key=key):
        s['automation'][key] = 'not-a-uuid'
        target = e['tracks'][1] if key == 'original_track_id' else next(x for x in e['tracks'][1]['automation'] if x['parameter'] == 'gainDB')
        target['id'] = 'not-a-uuid'
    check(f'{key}-matching-malformed-identity-rejected', malformed)
for key in ['restored_wav_sha256', 'restored_pcm_sha256', 'edited_wav_sha256', 'edited_pcm_sha256']:
    check(f'{key}-malformed-rejected', set_record(key, 'a' * 63))
    check(f'{key}-nonstring-rejected', set_record(key, 1))
for key in ['restored_wav_sha256', 'restored_pcm_sha256']:
    check(f'{key}-wrong-original-rejected', set_record(key, '0' * 64))
for key, original in [('edited_wav_sha256', 'restored_wav_sha256'), ('edited_pcm_sha256', 'restored_pcm_sha256')]:
    check(f'{key}-unchanged-render-rejected', set_record(key, session['automation'][original]))
check('missing-authored-track-rejected', lambda s, e, l: e.__setitem__('tracks', e['tracks'][:1]))
check('wrong-authored-track-name-rejected', lambda s, e, l: e['tracks'][1].__setitem__('name', 'Another pad'))
check('missing-authored-gain-lane-rejected', lambda s, e, l: e['tracks'][1].__setitem__('automation', []))
check('duplicate-authored-gain-lane-rejected', lambda s, e, l: e['tracks'][1]['automation'].append(copy.deepcopy(e['tracks'][1]['automation'][0])))
check('authored-point-count-mismatch-rejected', lambda s, e, l: e['tracks'][1]['automation'][0]['points'].pop())
assert args.receipt.read_bytes() == receipt_bytes
record = {
    'schema': 'rebase.automation-protocol-gate-controls.v1',
    'evidence_class': 'authored-instrument-controls',
    'status': 'passed' if all(row['passed'] for row in rows) else 'failed',
    'checks': len(rows), 'passed': sum(row['passed'] for row in rows),
    'failed': sum(not row['passed'] for row in rows),
    'subject_sha256': hashlib.sha256(gate_path.read_bytes()).hexdigest(),
    'input_receipt_sha256': hashlib.sha256(receipt_bytes).hexdigest(),
    'example_sha256': hashlib.sha256(example_path.read_bytes()).hexdigest(),
    'render_lock_sha256': hashlib.sha256(lock_path.read_bytes()).hexdigest(),
    'controls': rows,
    'limitations': ['Protocol packaging gate controls only; no native UI, device audio or reference behavior claim.'],
}
(out / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps({key:record[key] for key in ['status','checks','passed','failed','subject_sha256']}))
sys.exit(0 if record['status'] == 'passed' else 1)
