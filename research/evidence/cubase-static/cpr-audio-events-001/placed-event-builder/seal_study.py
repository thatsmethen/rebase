"""Seal bounded static evidence and immutable candidate/control snapshots."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,hashlib,subprocess
H=Path(__file__).resolve().parent;R=H.parents[4];A=R/'research/evidence/application/APP015'
def pin(p):return {'path':str(p.relative_to(R)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def write(p,v):
 with p.open('x')as f:f.write(json.dumps(v,indent=2)+'\n')
def envelope(p):
 d=json.loads(p.read_text());assert not d.get('isError'),p
 return d.get('structuredContent')or json.loads(d['content'][0]['text'])
def checkpins(v):
 if isinstance(v,dict):
  if all(k in v for k in('path','bytes','sha256')):assert pin(R/v['path'])==v,v['path']
  for x in v.values():checkpins(x)
 elif isinstance(v,list):
  for x in v:checkpins(x)
def verify():
 d=json.loads((H/'artifact-manifest.json').read_text())
 for row in d['files']:assert pin(R/row['path'])==row,row['path']
 print(json.dumps({'passed':True,'files':len(d['files']),'finding':pin(H/'finding.json'),'manifest':pin(H/'artifact-manifest.json')}))
def seal():
 assert not(H/'finding.json').exists()and not(H/'artifact-manifest.json').exists()
 subprocess.run(['python3',str(H/'verify_evidence.py')],check=True)
 v=json.loads((H/'verification.json').read_text());assert v['passed']
 assert v['summary']=={'new_functions':3,'reused_functions':11,'bytes_verified':12492,'original_native_words':3123,'rea_instruction_addresses':2611}
 imported=envelope(H/'evidence-import.json')['result'];assert imported=={'imported':28,'unknowns_added':0,'total':28}
 assert(H/'import-run.log').read_text().endswith('CLOSED: evidence import session\n')
 controls=json.loads((H/'controls/result.json').read_text());assert controls['passed']and controls['controls']==32;checkpins(controls)
 checkpins(json.loads((H/'reused-inputs.json').read_text()))
 author=json.loads((H/'author-integration-review.json').read_text());checkpins(author)
 review=A/'placed-source-independent-review.json';rd=json.loads(review.read_text())
 assert rd['status'].startswith('passed')and not rd.get('open_findings');checkpins(rd)
 oracle=json.loads((A/'placed-source-oracle.json').read_text())
 assert len(oracle['builder_vectors'])==180
 assert pin(A/'placed-source-oracle.py')['sha256']==oracle['generator_sha256']
 copies=[]
 def copy(source,dest):
  assert source.is_file()and not dest.exists();dest.parent.mkdir(parents=True,exist_ok=True)
  with dest.open('xb')as f:f.write(source.read_bytes())
  assert pin(source)['sha256']==pin(dest)['sha256']
  copies.append({'historical_source':pin(source),'immutable_snapshot':pin(dest)})
 for source,dest in [
  (R/'Application/Sources/RebaseTimingDSP/cpr_timeline_builder.c',H/'candidate/cpr_timeline_builder.c'),
  (R/'Application/Sources/RebaseTimingDSP/include/cpr_timeline_builder.h',H/'candidate/cpr_timeline_builder.h'),
  (R/'Application/Tests/RebaseCoreTests/NativeTimelineBuilderTests.swift',H/'validation/NativeTimelineBuilderTests.swift'),
  (R/'Application/Tests/RebaseCoreTests/CPRPlacedSourceEventTests.swift',H/'validation/CPRPlacedSourceEventTests.swift'),
  (A.parent/'APP010/native-rate-mode0-oracle.py',H/'validation/APP010/native-rate-mode0-oracle.py')]:copy(source,dest)
 for n in('placed-source-oracle.py','placed-source-oracle.json','verify-placed-instructions.py','placed-instruction-verification.json','placed-source-independent-review.json'):
  copy(A/n,H/'validation/APP015'/n)
 # Retain exactly the independent review's pinned log inputs, including failed
 # attempts, plus the already completed author/root focused run. No active logs.
 logs=set()
 def findlogs(x):
  if isinstance(x,dict):
   if all(k in x for k in('path','bytes','sha256'))and x['path'].endswith('.log'):logs.add(R/x['path'])
   for z in x.values():findlogs(z)
  elif isinstance(x,list):
   for z in x:findlogs(z)
 findlogs(rd)
 logs.update(A/n for n in('placed-tests-first.log','placed-tests-second.log'))
 for p in sorted(logs):copy(p,H/'validation/APP015'/p.name)
 for row in author['inputs']:copy(R/row['path'],H/'validation/integration'/Path(row['path']).name)
 write(H/'source-snapshots.json',{'scope':'Historical source pins are descriptive; manifest custody uses immutable copies, not mutable app/test paths.','copies':copies})
 w=json.loads((H/'working-contract.json').read_text())
 d={'id':w['id'],'schema_version':1,'created_utc':datetime.now(timezone.utc).isoformat(),
  'status':'sealed_bounded_static_singleton_builder_and_reconstruction',
  'scope':w['scope'],'proprietary_target_executions':0,'cubase_runtime_comparisons':0,
  'target':{'product':'Cubase Pro15.0.30.287 macOS arm64','image':pin(R/'research/targets/derived/Cubase15-arm64')},
  'evidence_classes':['Original native instruction/byte analysis','Pinned REA6.7/Ghidra raw-slice analysis/readback','Independent Fraction IEEE expectations','Own reconstruction C/Swift execution'],
  'native_custody':{**v['summary'],'verification':pin(H/'verification.json'),'canonical_import':imported,
   'new_raw_slices_closed':3,'analysis_sessions_closed':1,'import_sessions_closed':1,
   'provider':'rea-agents6.7.0/Ghidra default raw-arm64/2G','coverage_limit':'LC_FUNCTION_STARTS intervals include disconnected code; decoded-address equality and complete readback are custody, not complete hosted semantic coverage.'},
  'contracts':{k:w[k]for k in('rounding','canonical_datum','intersection','source_offset','quantization','stores','admission')},
  'candidate':{'source':pin(H/'candidate/cpr_timeline_builder.c'),'header':pin(H/'candidate/cpr_timeline_builder.h'),'api':'rb_cpr_timeline_builder_project','defensive_domain':w['candidate_domain']},
  'validation':{'author_c_controls':32,'optimized_and_ubsan':pin(H/'controls/result.json'),
   'author_swift_tests':5,'author_root_focused_log':pin(H/'validation/APP015/placed-tests-second.log'),
   'independent_review':pin(H/'validation/APP015/placed-source-independent-review.json'),
   'independent_oracle':pin(H/'validation/APP015/placed-source-oracle.json'),
   'independent_instruction_verification':pin(H/'validation/APP015/placed-instruction-verification.json'),
   'builder_vectors':180,'independent_tests':rd.get('tests'),
   'independent_expected_outputs':'Exact Fraction/IEEE operation order; no candidate-generated expected values and no target execution.',
   'author_integration_review':pin(H/'author-integration-review.json'),
   'release_acceptance':'APP015 owns full-suite/GUI/package acceptance; this native study does not assert it.'},
  'source_context_reference':pin(H.parent/'placed-event-context/finding.json'),
  'source_context_boundary':'Fresh resource/context and explicit source-rate root are reconstruction conditions. Arbitrary hosted callback, rate, transform and resource mutation remain unestablished.',
  'remaining_limits':w['limits'],'source_snapshots':pin(H/'source-snapshots.json')}
 write(H/'finding.json',d)
 paths={p for p in H.rglob('*')if p.is_file()and'__pycache__'not in p.parts and p.name!='artifact-manifest.json'}
 for row in v['functions']:
  paths.update(R/x['path']for x in row['files'])
  raw=R/row['directory']/f"function-{row['entry'][2:]}.arm64.bin"
  if raw.is_file():paths.add(raw)
 paths.update(R/x['path']for x in json.loads((H/'reused-inputs.json').read_text())['files'])
 paths.update([R/'research/targets/derived/Cubase15-arm64',R/'research/evidence/cubase-static/cpr-map-clock-001/attributes/source_tools.py',H.parent/'placed-event-context/finding.json'])
 assert all(p.is_file()for p in paths)
 assert not any(str(p.relative_to(R)).startswith('Application/')for p in paths)
 write(H/'artifact-manifest.json',{'id':'CPR-PLACED-EVENT-BUILDER-001-MANIFEST','schema_version':1,
  'scope':'Private local native custody plus immutable authored candidate/control snapshots. No target execution.',
  'files':[pin(p)for p in sorted(paths)],'exclusions':['Manifest itself','__pycache__','Mutable Application/test paths'],
  'distribution_limit':'Original proprietary bytes, disassembly and REA dumps remain private local research artifacts.'})
 verify()
if __name__=='__main__':
 p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True);g.add_argument('--seal',action='store_true');g.add_argument('--verify',action='store_true');a=p.parse_args();seal()if a.seal else verify()
