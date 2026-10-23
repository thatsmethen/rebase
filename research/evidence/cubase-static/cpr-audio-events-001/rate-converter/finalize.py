"""Add the narrow peer budget challenge and final evidence links; retain draft."""
from pathlib import Path
import hashlib,json,datetime
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[4]
def ref(name):
 p=HERE/name;return dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
p=HERE/'finding.json';draft=HERE/'finding-draft-01.json'
assert not draft.exists();p.rename(draft)
f=json.loads(draft.read_text())
f['evidence']['original-import-bindings.json']=ref('original-import-bindings.json')
f['caller_count_binding']['ranges'][0]='10036f0c4..0e0 and10036f208..20c'
f['independent_challenge']=dict(reviewer='/root/cubase_evidence',scope='Read-only instruction-to-budget correspondence for10030a430 and100313bf8 only; no vector rerun or NoFlushState review.',
 result='No discrepancy found within the declared bounded domain. Reviewer independently confirmed FDIV/FMUL/FCVTPS initial ceiling; reverse FDIV/FMUL/FCVTZS; signed comparison/decrement and saved tested-count return; FRINTP plus fixed-point FCVTZU #11 allowance; equal-rate early return.',
 evidence_type='Peer static source review communicated in this session; not target output or external library conformance.')
f['buffered_soxr_boundary']['setup']='Initialization places delayP at outputEnd and0 at outputRead. The format0 output buffer is cleared via original Mach-O stub103881efc bound to_vDSP_vclr. Thus wrapper-visible output can include retained/initialized storage, not just newly produced frames.'
f['revision_note']='Finalization adds original import binding, corrects the caller budget range to10036f0c4..0e0, and retains narrow peer challenge. No arithmetic contract changed.'
# Improve narrative spacing without changing address/value tokens.
def tidy(x):
 if isinstance(x,dict):return{k:tidy(v)for k,v in x.items()}
 if isinstance(x,list):return[tidy(v)for v in x]
 if isinstance(x,str):
  for a,b in [('soxr_process','soxr_process'),('ifn','if n'),('If0','If 0'),('iftrunc','if trunc'),('Ifremaining','If remaining'),('doesnot','does not'),('thefactory','the factory'),('not61fullyreconstructed','not 61 fully reconstructed'),('Firstmode2','First mode2'),('latermode2','later mode2'),('unavailablelibrary','unavailable library'),('testwithouttreating availabilityasstatic BSSvalue','test without treating availability as a static BSS value'),('versusdrift','versus drift'),('initialdiscard versussteady','initial discard versus steady'),('aroundsoxr_process','around soxr_process'),('nonnull','non-null')]:x=x.replace(a,b)
 return x
f=tidy(f)
with p.open('x')as out:json.dump(f,out,indent=2);out.write('\n')
record=dict(final_finding=ref('finding.json'),draft=ref('finding-draft-01.json'),at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
 independent_review=f['independent_challenge'],mcp_sessions_closed=True,app_files_changed=False,target_execution_count=0)
with (HERE/'finalization.json').open('x')as out:json.dump(record,out,indent=2);out.write('\n')
rows=[]
for path in sorted(HERE.rglob('*')):
 if path.is_file()and'__pycache__'not in path.parts and path.name!='artifact-manifest.json':
  data=path.read_bytes();rows.append(dict(path=str(path.relative_to(ROOT)),bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
with (HERE/'artifact-manifest.json').open('x')as out:json.dump(dict(scope='New rate-converter static evidence and analytical controls only. No target execution or app source mutation. Manifest excludes itself and caches.',files=rows),out,indent=2);out.write('\n')
print(json.dumps(dict(finding=ref('finding.json'),manifest=ref('artifact-manifest.json'),files=len(rows))))
