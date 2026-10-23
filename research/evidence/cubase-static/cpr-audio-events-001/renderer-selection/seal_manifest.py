from pathlib import Path
import hashlib,json,datetime
h=Path(__file__).resolve().parent;r=h.parents[4]
rows=[]
for p in sorted(h.rglob('*')):
 if p.is_file() and p.name!='manifest.json':
  data=p.read_bytes();rows.append({'path':str(p.relative_to(r)),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
finding=hashlib.sha256((h/'finding.json').read_bytes()).hexdigest()
m={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'Bounded static native event stream selector, distinct audition exploration and retained context limitations. No app edit or target execution.','finding_sha256':finding,'files':rows,'file_count':len(rows),'total_bytes':sum(x['bytes'] for x in rows),'new_native_functions':53,'reused_native_functions':9,'canonical_evidence_records':124,'capture_mcp_sessions_closed':17,'import_session_closed':True,'target_executions':0,'native_runtime_comparisons':0,'self_exclusion':'manifest.json excluded to avoid recursive digest'}
(h/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
for row in rows:
 data=(r/row['path']).read_bytes();assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256']
print(json.dumps({'finding_sha256':finding,'manifest_sha256':hashlib.sha256((h/'manifest.json').read_bytes()).hexdigest(),'files':len(rows),'bytes':m['total_bytes'],'all_file_hashes_rechecked':True}))
