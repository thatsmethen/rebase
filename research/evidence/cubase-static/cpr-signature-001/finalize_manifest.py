"""Pin this native study without changing the independent fixtures."""
import hashlib,json
from pathlib import Path
from datetime import datetime,timezone
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
finding=json.loads((HERE/'finding.json').read_text())
source=ROOT/finding['source']['path']
assert sha(source)==finding['source']['sha256']
bundle=json.loads((HERE/'native-evidence-bundle.json').read_text())
ids={r['evidence_id'] for r in bundle['records']}
for fact in finding['facts']:
    for reference in fact['evidence']:
        assert reference['evidence_id'] in ids
        record=json.loads((ROOT/reference['path']).read_text())['structuredContent']
        assert record['evidence_id']==reference['evidence_id']
for row in finding['functions']:
    for key in ('function_record','native_disassembly'):
        assert sha(ROOT/row[key]['path'])==row[key]['sha256']
for key in ('independent_fixture_contract','linkage','correction_record'):
    assert sha(ROOT/finding[key]['path'])==finding[key]['sha256']
files=[]
for path in sorted(HERE.rglob('*')):
    if not path.is_file() or path.name in ('manifest.json',) or 'fixtures' in path.relative_to(HERE).parts:
        continue
    files.append(dict(path=str(path.relative_to(ROOT)),bytes=path.stat().st_size,sha256=sha(path)))
report=dict(created_utc=datetime.now(timezone.utc).isoformat(),study='CPR-SIGNATURE-001',
            source_still_matches=True,all_cited_evidence_ids_resolve=True,
            evidence_records=len(ids),files=files,
            external_fixture_contract=finding['independent_fixture_contract'],
            scope='Pins owned native-study files. Independent fixture folder is referenced by its own immutable finding. No target execution.')
(HERE/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(files=len(files),records=len(ids),manifest_sha256=sha(HERE/'manifest.json'))))
