from pathlib import Path
import hashlib,json,datetime
h=Path(__file__).resolve().parent;r=h.parents[4]
finding=h/'finding.json';digest=hashlib.sha256(finding.read_bytes()).hexdigest()
review={'reviewer':'/root/fidelity_protocol','finding_sha256':digest,'scope':'Independent semantic overclaim check against reviewer-owned timebase/default-provider evidence; not an independent reread of all38 new slices.','result':'No substantive correction found in the checked scope.','checked':['A7 conditions factor1 on absence at call time and distinguishes fresh nil from count0 preserving prior attributes.','A4/A5 do not turn source absence of Warpscale into active rendering identity.','The consumer cross-reference separates parent-track placement from child/clip transform context.','Explicit105025688 callback, backend and rendering-selection limits agree with peer evidence.'],'target_executions':0}
(h/'scoped-peer-review.json').write_text(json.dumps(review,indent=2)+'\n')
rows=[]
for p in sorted(h.rglob('*')):
 if p.is_file() and p.name!='manifest.json':
  data=p.read_bytes();rows.append({'path':str(p.relative_to(r)),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
m={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'Audible-state source-field/conditional native contract and preserved static evidence. No app source edits, target execution or playable-media promotion.','finding_sha256':digest,'files':rows,'file_count':len(rows),'total_bytes':sum(x['bytes'] for x in rows),'new_native_functions':38,'reused_native_functions':7,'canonical_evidence_records':90,'capture_mcp_sessions_closed':15,'import_session_closed':True,'target_executions':0,'native_runtime_comparisons':0,'self_exclusion':'manifest.json excluded to avoid a recursive digest'}
(h/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
for row in rows:
 data=(r/row['path']).read_bytes();assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256']
print(json.dumps({'finding_sha256':digest,'manifest_sha256':hashlib.sha256((h/'manifest.json').read_bytes()).hexdigest(),'files':len(rows),'bytes':m['total_bytes'],'all_file_hashes_rechecked':True}))
