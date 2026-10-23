"""Snapshot status and inventory checked APP007 artifacts once."""
from pathlib import Path
import datetime,hashlib,json,shutil,subprocess
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).resolve().parent
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def record(p):return {'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p)}
def write(n,d):(OUT/n).write_text(json.dumps(d,indent=2)+'\n')
assert not (OUT/'artifact-manifest.json').exists(),'Final evidence already sealed'
validation=json.loads((OUT/'application-validation.json').read_text())
source=json.loads((OUT/'final-source-manifest.json').read_text())
for row in source['files']:
    p=ROOT/row['path'];snapshot=OUT/'final-source-snapshot'/row['path']
    assert sha(p)==row['sha256']==sha(snapshot),row['path']
app=ROOT/'Application/dist/Rebase.app';snapshot=OUT/'final-build-snapshot/Rebase.app'
assert sha(app/'Contents/MacOS/Rebase')==validation['executable']['sha256']==sha(snapshot/'Contents/MacOS/Rebase')
subprocess.run(['codesign','--verify','--strict',str(snapshot)],check=True)
prior=[]
for iteration in ['APP005','APP006']:
    manifest=ROOT/'research/evidence/application'/iteration/'artifact-manifest.json';d=json.loads(manifest.read_text())
    for row in d['files']:assert sha(ROOT/row['path'])==row['sha256'],row['path']
    prior.append({'id':iteration,'files':len(d['files']),'manifest':record(manifest)})
for relative in ['README.md','research/study.json','research/coverage.json','research/rea-steering.json']:
    p=ROOT/relative;destination=OUT/'final-status-snapshot'/relative;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,destination)
write('next-slice.json',{'created_utc':now,'autonomous_goal_status':'active','scope':'Full Cubase fidelity remains the objective; APP007 is a completed bounded attachment slice.','next_application_contract':'Event rendering consumer and actual source/backend format/rate state, then supported native-event rendering in a new frozen interpretation profile.','starting_findings':[record(ROOT/'research/evidence/cubase-static/cpr-audio-events-001'/a/'finding.json') for a in ['segment-consumer','renderer-selection','rate-converter']],'active_static_trace':{'agent':'cubase_evidence','peer':'target_intake','path':'research/evidence/cubase-static/cpr-audio-events-001/event-rendering/','status':'in progress, not a sealed finding at APP007 completion','consumer':'0x10020f2e8 and caller0x10020ee24 construct PAudioSegment objects','discriminator':'Source-null event fade fields are insufficient for no-fade promotion: track/project automatic fade settings are a remaining source-state gate. Caller flag suppression is not a substitute for source fidelity.'},'constraints':['No proprietary target execution.','Preserve all original evidence and frozen V1/V2/V3/V4 reports.','No automatic native-event playback from attachment or filename/format matching.','Differentiate static-derived candidates and self-authored controls from measured reference conformance.'],'broader_open_scope':['CPR writing/roundtrip','general placement and musical event durations','MIDI editing and recording','VST hosting and PDC','complete mixer/routing/automation','complete interaction and DSP fidelity']})
write('final-integrity.json',{'created_utc':now,'status':'passed','source_files':len(source['files']),'live_source_matches_snapshot':True,'live_binary_matches_snapshot':True,'executable_sha256':sha(app/'Contents/MacOS/Rebase'),'snapshot_strict_codesign_exit':0,'prior_manifests_unchanged':prior,'valid_gui_packages':['LoFi Attached.rebaseproj','LoFi Attached Copy.rebaseproj'],'intentional_invalid_package':'Changed Media Control.rebaseproj','target_runtime_executions':0})
files=sorted(p for p in OUT.rglob('*') if p.is_file() and p.name not in ['.DS_Store','artifact-manifest.json'])
write('artifact-manifest.json',{'id':'APP007','at_utc':now,'scope':'Bounded attachment release, original test compilation failure, self-authored PCM controls, intentional invalid package, checked source/bundle/status snapshots. No Cubase runtime conformance. Excludes this manifest and ephemeral .DS_Store.','files':[record(p) for p in files]})
d=json.loads((OUT/'artifact-manifest.json').read_text())
for row in d['files']:assert sha(ROOT/row['path'])==row['sha256']
print(json.dumps({'files':len(files),'manifestSHA256':sha(OUT/'artifact-manifest.json'),'validationSHA256':sha(OUT/'application-validation.json'),'goal':'active'}))
