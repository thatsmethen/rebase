"""One-time coordinated seal. Never overwrite a sealed finding/manifest.

Historical app/test/oracle inputs are copied before hashing; live application
paths are provenance labels only and are not immutable manifest inputs.
"""
from pathlib import Path
import hashlib,json,shutil,subprocess,datetime
H=Path(__file__).resolve().parent;ROOT=H.parents[4];V=H/'validation'
assert not(H/'artifact-manifest.json').exists(),'already sealed; use validation, not resealing'
assert not(H/'finding.json').exists(),'finding already exists'
for command in [['python3',str(H/'verify_evidence.py')],['python3',str(H/'bind_source.py')]]:subprocess.run(command,check=True)
ref=lambda p:dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
inputs=[
 ('Application/Tests/RebaseCoreTests/NativeRateMode0DownTests.swift','NativeRateMode0DownTests.swift'),
 ('Application/Sources/RebaseCore/CPRRateConvertedStream.swift','CPRRateConvertedStream.swift'),
 ('research/evidence/application/APP011/native-rate-down-oracle.py','native-rate-down-oracle.py'),
 ('research/evidence/application/APP011/native-rate-down-oracle.json','native-rate-down-oracle.json'),
 ('research/evidence/application/APP011/native-rate-down-count-oracle.py','native-rate-down-count-oracle.py'),
 ('research/evidence/application/APP011/native-rate-down-count-oracle.json','native-rate-down-count-oracle.json'),
 ('research/evidence/application/APP011/native-rate-down-tests-first.log','native-rate-down-tests-first.log'),
 ('research/evidence/application/APP011/native-rate-down-tests-round2.log','native-rate-down-tests-round2.log'),
 ('research/evidence/application/APP011/native-rate-down-tests-round3.log','native-rate-down-tests-round3.log'),
 ('research/evidence/application/APP011/rate-down-independent-review.json','rate-down-independent-review.json'),
 ('research/evidence/application/APP011/rate-down-stream-review.json','rate-down-stream-review.json'),
 ('research/evidence/application/APP010/native-rate-mode0-oracle.py','prior-ieee-arithmetic-helper.py'),
]
V.mkdir(exist_ok=False);mapping=[]
for source,name in inputs:
 p=ROOT/source;q=V/name;before=p.read_bytes();q.write_bytes(before);assert q.read_bytes()==p.read_bytes()
 mapping.append({'original_source_at_capture':ref(p),'immutable_snapshot':ref(q)})
(V/'snapshot-map.json').write_text(json.dumps({'purpose':'Preserve exact reviewed historical revisions; source paths may evolve after capture. These copies, not mutable live paths, are manifest inputs.','files':mapping},indent=2)+'\n')
for name in ['native_rate_mode0_down.c','native_rate_mode0_down.h']:
 live=ROOT/('Application/Sources/RebaseTimingDSP/'+('include/'if name.endswith('.h')else'')+name)
 assert live.read_bytes()==(H/'candidate'/name).read_bytes()
r=json.loads((H/'contract-draft.json').read_text());r['status']='sealed static arithmetic contract and independently validated bounded reconstruction'
r['sealed_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
r['candidate']['files']=[ref(H/'candidate/native_rate_mode0_down.c'),ref(H/'candidate/native_rate_mode0_down.h')]
r['validation']={
 'scope':'Independent analytical instruction interpretation and reconstructed-code tests only; no proprietary target runtime comparisons.',
 'independent_review':ref(V/'rate-down-independent-review.json'),
 'independent_sample_oracle':ref(V/'native-rate-down-oracle.json'),
 'independent_count_oracle':ref(V/'native-rate-down-count-oracle.json'),
 'sample_vectors':105,'large_partition_vectors':18,'fma_discriminators':6,
 'focused_swift_tests':{'passed':8,'log':ref(V/'native-rate-down-tests-round3.log'),'source':ref(V/'NativeRateMode0DownTests.swift'),'earlier_attempt_logs_retained':True},
 'own_wrapper_controls':{'passed':41,'report':ref(H/'candidate/controls.json')},
 'undefined_behavior_sanitizer':{'candidate_calls_passed':22400,'report':ref(H/'candidate/sanitizer-verification.json')},
 'address_sanitizer':'No pass claimed. Runtime initialization stalled before candidate main in sampled stacks; owned process terminated; exact sample and empty log retained. UBSan is a distinct successful run.',
 'stream_source_review':ref(V/'rate-down-stream-review.json'),
 'full_application_suite_and_gui':'Owned and reported separately by root; not asserted by this native study.'}
r['candidate']['snapshot_map']=ref(V/'snapshot-map.json')
r['known_discriminators']=[
 'Equal-rate first block100frames ABOVE yields98, so childkernel is not an identity copy.',
 'Small-ratio ABOVE/BELLOW queue terminal count can differ; ordinary block repartitioning can alter sample count and values.',
 'Reachable48k→32k input8192+8192+1 reaches single-frame unsupported source access; application8192+8191+2 avoids it.',
 'Large-ratio manualphase−2^-54/history1/firstinput0 yields mono2^-54 but stereo0 from distinct native weight rounding.',
 'LoFi1,058,400 sourceframes44.1k→32k under chosen ABOVE8192 policy yield767,967;44.1k→16k yields384,000. These are actual count recurrences, not nominalduration padding.'
]
r['references']=[ref(ROOT/x['path'])for x in r['references']]
(H/'finding.json').write_text(json.dumps(r,indent=2)+'\n')
files=set(p for p in H.rglob('*')if p.is_file() and p.name!='artifact-manifest.json' and'__pycache__'not in p.parts)
v=json.loads((H/'verification.json').read_text())
for row in v['functions']:
 if not row['reused']:continue
 directory=ROOT/row['directory'];derivation=ROOT/row['derivation'];files.add(derivation)
 d=json.loads(derivation.read_text());item,=[x for x in d['derivatives']if x['entry']==row['entry']];id=row['entry'][2:]
 for name in [item['raw_file'],item.get('native_file',item.get('original_native_disassembly')),f'function-{id}.json',f'bytes-{id}.json',f'bundle-{id}.json',f'close-{id}.json',f'snapshot-{id}.json']:files.add(directory/name)
for x in r['references']:files.add(ROOT/x['path'])
files.add(ROOT/'research/evidence/cubase-static/cpr-map-clock-001/attributes/source_tools.py')
manifest={'schema_version':1,'scope':'Exact sealed study/candidate/validation snapshots and immutable reused native references. Mutable live Application/test/oracle files deliberately excluded; see validation/snapshot-map.json. Manifest excludes itself.','files':[ref(p)for p in sorted(files)],'target_execution_count':0}
(H/'artifact-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
for x in manifest['files']:
 p=ROOT/x['path'];assert p.stat().st_size==x['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==x['sha256'],x['path']
print(json.dumps({'finding':ref(H/'finding.json'),'manifest':ref(H/'artifact-manifest.json'),'files':len(files)},indent=2))
