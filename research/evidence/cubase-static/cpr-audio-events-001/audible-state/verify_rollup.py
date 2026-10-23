from pathlib import Path
import hashlib,json,struct
h=Path(__file__).resolve().parent;r=h.parents[4];finding=json.loads((h/'finding.json').read_text())
def load(p):return json.loads(p.read_text())
def checkpin(p):
 data=(r/p['path']).read_bytes();assert hashlib.sha256(data).hexdigest()==p['sha256'];assert len(data)==p['bytes']
for p in finding['artifacts']+finding['external_references']:checkpin(p)
for f in finding['source_observations']:
 data=(r/f['source']['path']).read_bytes();assert hashlib.sha256(data).hexdigest()==f['source']['sha256'];assert len(data)==f['source']['bytes'];assert hashlib.sha256(data[f['event_body_offset']:f['event_end']]).hexdigest()==f['event_body_sha256']
for row in load(h/'support-verification.json')['functions']:
 for p in row['pins']:checkpin(p)
source=(r/'research/targets/derived/Cubase15-arm64').read_bytes();link=load(h/'linkage.json');assert hashlib.sha256(source).hexdigest()==link['sha256']
for row in link['strings']+link['vtable_slots']+link['instruction_spans']:
 b=source[row['source_offset']:row['source_offset']+row['bytes']];assert b.hex()==row['hex'] and hashlib.sha256(b).hexdigest()==row['sha256']
ids={x['evidence_id'] for x in load(h/'evidence-bundle.json')['records']}
for c in finding['contracts']:
 for e in c['evidence']:assert all(x in ids for x in e['evidence_ids'])
for i in range(1,16):
 b=h/f'pass{i}';assert 'CLOSED: isolated raw-slice MCP session' in (b/'analysis-progress.log').read_text();assert not list(b.glob('failure-*.json'))
 for p in b.glob('*.json'):
  d=load(p)
  if isinstance(d,dict):assert not d.get('isError',False),p
assert 'CLOSED: evidence import session' in (h/'import-progress.log').read_text()
out={'passed':True,'finding_sha256':hashlib.sha256((h/'finding.json').read_bytes()).hexdigest(),'source_hashes_exact':True,'reference_hashes_exact':True,'linked_literal_vtable_instruction_bytes_exact':True,'all_referenced_evidence_ids_resolve':True,'new_sessions_closed':15,'import_session_closed':True,'retained_new_tool_errors':0,'target_executions':0,'scope':'Custody and bounded rollup checks; does not convert static conditions to runtime/audio equivalence.'}
(h/'rollup-verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
