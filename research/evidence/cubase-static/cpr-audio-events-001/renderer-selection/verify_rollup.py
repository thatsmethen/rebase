from pathlib import Path
import json,hashlib
h=Path(__file__).resolve().parent;r=h.parents[4]
def read(p):return json.loads(p.read_text())
f=read(h/'finding.json');b=read(h/'evidence-bundle.json');ids={x['evidence_id'] for x in b['records']};assert len(ids)==124
for c in f['contracts']:
 for p in c['evidence']:assert all(i in ids for i in p['evidence_ids'])
for p in list(f['artifacts'].values())+f['external_references']:
 data=(r/p['path']).read_bytes();assert len(data)==p['bytes'] and hashlib.sha256(data).hexdigest()==p['sha256']
i=read(h/'evidence-import.json');assert not i.get('isError',False);imp=i['structuredContent']['result'];assert imp['imported']==124 and imp['total']==124
assert 'CLOSED:' in (h/'import.log').read_text()
for n in range(1,18):assert 'CLOSED:' in (h/f'pass{n}/analysis-progress.log').read_text()
old=read(h.parent/'audible-state/manifest.json')
for p in old['files']:
 data=(r/p['path']).read_bytes();assert len(data)==p['bytes'] and hashlib.sha256(data).hexdigest()==p['sha256']
result={'passed':True,'all_claim_evidence_ids_resolve':True,'all_pinned_external_and_artifact_digests_match':True,'canonical_records_imported':124,'capture_sessions_closed':17,'import_session_closed':True,'previous_audible_state_artifact_hashes_unchanged':len(old['files']),'target_executions':0,'scope':'Custody/mechanical checks, not target output comparison or blanket semantic validation.'}
(h/'rollup-verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
