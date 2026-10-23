"""Seal local static custody and immutable reconstruction/control snapshots."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,hashlib
H=Path(__file__).resolve().parent;R=H.parents[4];A=R/'research/evidence/application/APP014'
def pin(p):return {'path':str(p.relative_to(R)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def write(p,value):
 with p.open('x')as f:f.write(json.dumps(value,indent=2)+'\n')
def envelope(p):
 d=json.loads(p.read_text());assert not d.get('isError'),p
 return d.get('structuredContent')or json.loads(d['content'][0]['text'])
def verify():
 m=json.loads((H/'artifact-manifest.json').read_text())
 for row in m['files']:assert pin(R/row['path'])==row,row['path']
 print(json.dumps({'passed':True,'files':len(m['files']),'finding':pin(H/'finding.json'),'manifest':pin(H/'artifact-manifest.json')}))
def seal():
 assert not(H/'finding.json').exists()and not(H/'artifact-manifest.json').exists()
 v=json.loads((H/'verification.json').read_text());assert v['passed']
 assert v['summary']=={'new_functions':12,'reused_functions':4,'original_native_words':5936,'rea_instruction_addresses':2410,'bytes_verified':23744}
 imported=envelope(H/'evidence-import.json')['result'];assert imported=={'imported':32,'unknowns_added':0,'total':32}
 assert(H/'import-run.log').read_text().endswith('CLOSED: evidence import session\n')
 for name in ('pass1','pass2','pass3'):
  lines=(H/name/'run.log').read_text().splitlines();assert lines[-1]=='CLOSED: isolated raw-slice MCP session'
  assert all(json.loads(line)['isError']is False for line in lines[:-1])
 controls=json.loads((H/'controls/result.json').read_text());assert controls['passed']and controls['controls']==16
 for row in controls['inputs']+controls['logs']:assert pin(R/row['path'])==row
 assert 'Test run with 10 tests in 2 suites passed' in(A/'timeline-tests-second.log').read_text()
 assert pin(A/'timeline-reader-oracle.json')['sha256']=='0df450ef24e5124574b720c7eeb020cd9136f3267f037ad8808426faa34641cf'
 review=A/'timeline-reader-independent-review.json';assert review.is_file()
 rd=json.loads(review.read_text())
 assert rd['status']=='passed_no_open_defect_in_reviewed_bounded_domain'and not rd['open_findings']
 def recheck(value):
  if isinstance(value,dict):
   if all(k in value for k in ('path','bytes','sha256')):assert pin(R/value['path'])==value
   for child in value.values():recheck(child)
  elif isinstance(value,list):
   for child in value:recheck(child)
 recheck(rd)
 for key in ('reviewed_sources','inputs','reviewed_inputs','source_pins','reviewed_sources_and_evidence'):
  for row in rd.get(key,[]):
   if 'sha256'in row and 'path'in row:assert pin(R/row['path'])==row
 copylist=[(R/'Application/Sources/RebaseTimingDSP/cpr_timeline_reader.c',H/'candidate/cpr_timeline_reader.c'),
  (R/'Application/Sources/RebaseTimingDSP/include/cpr_timeline_reader.h',H/'candidate/cpr_timeline_reader.h'),
  (R/'Application/Sources/RebaseCore/CPRNativeTimelineStream.swift',H/'validation/integration/CPRNativeTimelineStream.swift'),
  (R/'Application/Tests/RebaseCoreTests/NativeTimelineReaderTests.swift',H/'validation/NativeTimelineReaderTests.swift'),
  (R/'Application/Tests/RebaseCoreTests/CPRNativeTimelineStreamTests.swift',H/'validation/CPRNativeTimelineStreamTests.swift'),
  (A.parent/'APP010/native-rate-mode0-oracle.py',H/'validation/APP010/native-rate-mode0-oracle.py')]
 for name in ('timeline-reader-oracle.py','timeline-reader-oracle.json','timeline-tests-first.log','timeline-tests-second.log','timeline-reader-independent-review.json','verify-timeline-instructions.py','timeline-instruction-verification.json','core-tests-first.log'):
  copylist.append((A/name,H/'validation/APP014'/name))
 copies=[]
 for source,dst in copylist:
  assert source.is_file()and not dst.exists();dst.parent.mkdir(parents=True,exist_ok=True)
  with dst.open('xb')as f:f.write(source.read_bytes())
  assert pin(source)['sha256']==pin(dst)['sha256'];copies.append({'historical_source':pin(source),'immutable_snapshot':pin(dst)})
 write(H/'source-snapshots.json',{'scope':'Live source identities are descriptive; manifest custody uses immutable snapshots.','copies':copies})
 working=json.loads((H/'working-contract.json').read_text())
 finding={'id':'CPR-TIMELINE-READER-001','schema_version':1,'created_utc':datetime.now(timezone.utc).isoformat(),
  'status':'sealed_bounded_static_reader_contract_and_reconstruction','scope':working['scope'],
  'proprietary_target_executions':0,'cubase_runtime_comparisons':0,
  'target':{'product':'Cubase Pro15.0.30.287 macOS arm64','image':pin(R/'research/targets/derived/Cubase15-arm64')},
  'evidence_classes':['Original native byte/instruction analysis','Pinned REA/Ghidra raw-slice dossiers','Independent exact Fraction IEEE controls','Own reconstruction-only C/Swift execution'],
  'native_custody':{**v['summary'],'verification':pin(H/'verification.json'),'canonical_import':imported,
   'new_raw_slices_closed':12,'isolated_analysis_sessions_closed':3,'import_sessions_closed':1,
   'provider':'rea-agents6.7.0; Ghidra default analyzers/raw arm64/2G heap',
   'coverage_limit':'All23744 slice bytes agree;2410 retained decoded addresses differ from5936 native words. LC_FUNCTION_STARTS intervals can contain disconnected tails or neighboring material; no full semantic coverage is inferred.'},
  'contracts':{key:working[key]for key in('quantization','datum_lifecycle','window','read_contract','mapped_partition')},
  'candidate':{'source':pin(H/'candidate/cpr_timeline_reader.c'),'header':pin(H/'candidate/cpr_timeline_reader.h'),
   'defensive_contract':working['candidate_domain'],
   'api':['rb_cpr_timeline_quantize','rb_cpr_timeline_plan','rb_cpr_timeline_partition','rb_cpr_timeline_read_result'],
   'scope':'Pure planning, one mapped entry and exact-read status. No provider callback, source samples, accessor allocation/cache or mapper creation is implemented by C helpers.'},
  'validation':{'author_controls':16,'author_compile_and_ubsan':pin(H/'controls/result.json'),
   'independent_review':pin(H/'validation/APP014/timeline-reader-independent-review.json'),
   'independent_oracle':pin(H/'validation/APP014/timeline-reader-oracle.json'),
   'oracle_generator':pin(H/'validation/APP014/timeline-reader-oracle.py'),
   'independent_original_verification':pin(H/'validation/APP014/timeline-instruction-verification.json'),
   'independent_original_words':1174,'independent_original_intervals':9,
   'controls':{'quantizers':254,'mapped_partitions':560,'integer_windows':110,'read_results':126,'total':1050,
    'fma_discriminators':19,'float32_narrowing_discriminators':15,'partition_endpoint_discriminators':176},
   'focused_tests':10,'focused_suites':2,'log':pin(H/'validation/APP014/timeline-tests-second.log'),
   'test_scope':'Five numerical reader tests and five direct-memory Swift-stream tests using synthetic media and retained CPR fixtures. No proprietary reader execution.',
   'retained_initial_test_compile_failure':pin(H/'validation/APP014/timeline-tests-first.log'),
   'initial_failure_scope':'Swift test-only nested throwing expression syntax; production C/Swift compiled.',
   'author_integration_review':pin(H/'author-integration-review.json'),
   'release_acceptance':'APP014 owns full-suite, GUI and package acceptance; these are not asserted by this native study.'},
  'remaining_limits':['The actual datum period, provider membership, mapper/loop/locator state and host callbacks remain runtime context, not fabricated constants.',
   'Concrete segment getter pointer/instruction bindings are checked; channel/provider ownership is independently covered by timeline-provider.',
   'The active-project mapping branch was retained but is not reconstructed; one already-mapped entry rounding does not prove identity mapping.',
   'Accessor creation, cache invalidation, layout remapping, asynchronous I/O, outer retry and downstream mixer/plugin/poststage behavior are outside the pure candidate.',
   'App equal-rate immutable-memory copying/gain and worker/device scheduling are application compositions, not Cubase live output comparisons.',
   'Raw-slice Ghidra pseudocode loses imports, types, globals and neighboring calls; original listed bindings supply only bounded context.',
   'Private native image/raw bytes/disassembly remain local research artifacts and are not intended for publication.'],
  'provider_ownership_reference':pin(H.parent/'timeline-provider/finding.json'),
  'source_snapshots':pin(H/'source-snapshots.json')}
 write(H/'finding.json',finding)
 paths={p for p in H.rglob('*')if p.is_file()and'__pycache__'not in p.parts and p.name!='artifact-manifest.json'}
 for row in v['functions']:
  paths.update(R/x['path']for x in row['files'])
  raw=R/row['directory']/f"function-{row['entry'][2:]}.arm64.bin"
  if raw.is_file():paths.add(raw)
 paths.update(R/x['path']for x in json.loads((H/'reused-inputs.json').read_text())['files'])
 paths.update([R/'research/targets/derived/Cubase15-arm64',R/'research/evidence/cubase-static/cpr-map-clock-001/attributes/source_tools.py',R/'.tools/rea/node_modules/rea-agents/package.json',H.parent/'timeline-provider/finding.json'])
 assert all(p.is_file()for p in paths);assert not any(str(p.relative_to(R)).startswith('Application/')for p in paths)
 write(H/'artifact-manifest.json',{'id':'CPR-TIMELINE-READER-001-MANIFEST','schema_version':1,
  'scope':'Local static custody and immutable reconstruction/oracle copies; no proprietary execution.',
  'files':[pin(p)for p in sorted(paths)],'exclusions':['Manifest itself','__pycache__','Mutable Application/test paths'],
  'distribution_limit':'Native target bytes and provider outputs remain private local research artifacts.'})
 verify()
if __name__=='__main__':
 p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True);g.add_argument('--seal',action='store_true');g.add_argument('--verify',action='store_true');a=p.parse_args();seal()if a.seal else verify()
