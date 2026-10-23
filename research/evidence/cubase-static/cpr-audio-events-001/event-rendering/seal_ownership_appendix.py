"""Seal only newly appended ownership evidence; preserve prior report bytes."""
from pathlib import Path
import hashlib,json
h=Path(__file__).resolve().parent
r=h.parents[4]
paths=[]
for base in [h/'pass12',h/'pass13']:
    paths.extend(p for p in base.rglob('*') if p.is_file())
for name in ['derive_pass12.py','analyze_pass12.mjs','derive_pass13.py','analyze_pass13.mjs',
             'verify_ownership.py','ownership-verification.json','write_ownership_appendix.py',
             'ownership-linkage.json','ownership-finding.json','combine_ownership_evidence.mjs',
             'import_ownership_evidence.mjs','ownership-evidence-bundle.json',
             'ownership-evidence-import.json','ownership-import-run.log',
             'ownership-import.stderr.txt','ownership-mcp-tool-inventory-import.json',
             'seal_ownership_appendix.py']:
    p=h/name
    if p.is_file():paths.append(p)
paths=sorted(set(paths))
for p in paths:
    if p.suffix=='.json':json.loads(p.read_text())
finding=json.loads((h/'ownership-finding.json').read_text())
for item in [finding['custody'],finding['linkage'],finding['source_fixture_correlation']['source']]:
    assert hashlib.sha256((r/item['path']).read_bytes()).hexdigest()==item['sha256']
assert 'CLOSED: evidence import session' in (h/'ownership-import-run.log').read_text()
imported=json.loads((h/'ownership-evidence-import.json').read_text())
assert not imported.get('isError',False)
assert imported['structuredContent']['result']==dict(imported=16,unknowns_added=0,total=16)
files=[dict(path=str(p.relative_to(r)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths]
out=dict(scope='New MRoot ownership appendix only. Previous event-rendering report/import and all application source are excluded and unchanged by these scripts.',
         target_execution=False,files=files,file_count=len(files),total_bytes=sum(f['bytes'] for f in files),
         new_capture_sessions_closed=2,canonical_import_sessions_closed=1,new_imported_records=16,
         reused_evidence='14 prior functions referenced and verified in ownership-verification.json, not recounted as new analysis.',
         verification_passed=True)
(h/'ownership-manifest.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:out[k] for k in ['file_count','total_bytes','verification_passed']}))
print('manifest_sha256='+hashlib.sha256((h/'ownership-manifest.json').read_bytes()).hexdigest())
