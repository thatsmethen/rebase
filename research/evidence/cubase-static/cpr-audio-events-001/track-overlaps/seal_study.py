"""Seal/recheck local retained static evidence without running the reference."""
from pathlib import Path
import argparse
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
MANIFEST = HERE / 'artifact-manifest.json'


def pin(path):
    data = path.read_bytes()
    return dict(path=str(path.relative_to(ROOT)), bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest())


def check(row):
    assert pin(ROOT / row['path']) == row, row['path']


def inventory():
    return [pin(path) for path in sorted(HERE.rglob('*'))
            if path.is_file() and path != MANIFEST and '__pycache__' not in path.parts]


parser = argparse.ArgumentParser(__doc__)
parser.add_argument('--seal', action='store_true')
args = parser.parse_args()
if args.seal:
    assert not MANIFEST.exists(), 'Never replace an existing seal'
    finding = json.loads((HERE / 'finding.json').read_text())
    verification = json.loads((HERE / 'verification.json').read_text())
    controls = json.loads((HERE / 'branch-controls.json').read_text())
    review_path = HERE / 'independent-review-01/review.json'
    review = json.loads(review_path.read_text())
    assert str(review['status']).startswith('passed')
    assert verification['passed'] and controls['passed']
    assert verification['target_executed'] is False
    assert verification['summary']['canonical_records'] == 40
    for name in ['verification', 'analytical_controls', 'analytical_model']:
        check(finding[name])
    references = {}
    for row in verification['functions']:
        for record in row['files']:
            check(record)
            if not (ROOT / record['path']).is_relative_to(HERE):
                references[record['path']] = record
    for record in finding['prior_findings']:
        check(record)
        references[record['path']] = record
        path = (ROOT / record['path']).parent / 'artifact-manifest.json'
        references[str(path.relative_to(ROOT))] = pin(path)
    for path in [ROOT / 'research/targets/derived/Cubase15-arm64',
                 ROOT / 'research/evidence/cubase-static/cpr-map-clock-001/attributes/source_tools.py']:
        references[str(path.relative_to(ROOT))] = pin(path)
    assert pin(ROOT / 'research/targets/derived/Cubase15-arm64')['sha256'] == finding['source_sha256']
    for log in sorted(HERE.glob('pass*/run.log')):
        assert log.read_text().splitlines()[-1] == 'CLOSED: isolated raw-slice MCP session'
    value = dict(schema_version=1, kind='immutable local static study inventory',
        source_sha256=finding['source_sha256'], target_executed=False,
        independent_review=pin(review_path),
        files=inventory(), external_references=list(references.values()),
        limits=['Custody recheck of listed records, not complete native behavioral validation.',
                'The manifest does not authorize redistribution of referenced private artifacts.'])
    with MANIFEST.open('x') as output:
        json.dump(value, output, indent=2)
        output.write('\n')
value = json.loads(MANIFEST.read_text())
for row in value['files'] + value['external_references']:
    check(row)
assert inventory() == value['files'], 'Closed-world inventory drift'
print(json.dumps(dict(passed=True, files=len(value['files']),
                     external_references=len(value['external_references']), manifest=pin(MANIFEST))))
