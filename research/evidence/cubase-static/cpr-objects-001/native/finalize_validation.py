"""Validate local evidence references and pin this native investigation's files."""
import hashlib,json
from pathlib import Path
from datetime import datetime,timezone
P=Path(__file__).resolve().parent; ROOT=P.parents[4]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
f=load(P/'finding.json'); b=load(P/'native-evidence-bundle.json'); ids={r['evidence_id'] for r in b['records']}
assert len(ids)==62
assert load(P/'evidence-import-validation.json')=={'imported':62,'unknowns_added':0,'total':62}
for key in ['archive_contract','primitive_contract','node_contract','tempo_contract']:
 for r in f[key]['evidence']:
  assert sha(ROOT/r['path'])==r['sha256']
  assert r['evidence_id'] in ids and r['readback_evidence_id'] in ids
for r in f['verification']['reports']+[f['verification']['canonical_bundle'],f['verification']['REA_bundle_validation'],f['linkage_provenance']]:
 assert sha(ROOT/r['path'])==r['sha256']
assert len(list(P.glob('**/close-*.json')))==31
assert all(not load(p).get('isError',False) for p in P.glob('**/close-*.json'))
assert all('CLOSED: isolated raw-slice MCP session' in (d/'analysis-progress.log').read_text()for d in [P,P/'pass2',P/'pass3',P/'pass4'])
parsed=0
for p in P.rglob('*.json'):
 load(p);parsed+=1
v={'created_utc':datetime.now(timezone.utc).isoformat(),'passed':True,'finding_sha256':sha(P/'finding.json'),'retained_evidence_records':62,'functions':31,'all_cited_paths_hashes_and_evidence_ids_verified':True,'all_close_responses_successful':True,'four_mcp_clients_closed':True,'JSON_files_parsed_before_report':parsed,'target_execution_count':0,'limits':['Validation authenticates retained records, byte custody and references. It does not independently establish native semantic correctness or runtime equivalence.']}
(P/'validation.json').write_text(json.dumps(v,indent=2)+'\n')
files=[p for p in P.rglob('*')if p.is_file()and p.name!='manifest.json']
m={'created_utc':datetime.now(timezone.utc).isoformat(),'scope':'This native evidence directory only; manifest excludes itself','files':[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p)}for p in sorted(files)]}
(P/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
print(json.dumps({'passed':True,'finding_sha256':sha(P/'finding.json'),'manifest_sha256':sha(P/'manifest.json'),'files':len(files),'JSON_files':parsed}))
