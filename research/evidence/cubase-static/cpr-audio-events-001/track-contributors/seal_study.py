"""Cold local seal/recheck. This inventories evidence, never executes target code."""
from pathlib import Path
import argparse,hashlib,json
H=Path(__file__).resolve().parent;R=H.parents[4];M=H/'artifact-manifest.json'
def pin(p):
 b=p.read_bytes();return dict(path=str(p.relative_to(R)),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def check(r):assert pin(R/r['path'])==r,r['path']
def inventory():return [pin(p)for p in sorted(H.rglob('*'))if p.is_file()and p!=M and '__pycache__'not in p.parts]
a=argparse.ArgumentParser();a.add_argument('--seal',action='store_true');args=a.parse_args()
if args.seal:
 assert not M.exists(),'Never replace existing seal'
 f=json.loads((H/'finding.json').read_text());v=json.loads((H/'verification.json').read_text());c=json.loads((H/'branch-controls.json').read_text())
 assert v['passed']and c['passed']and f['canonical_import']['all_sessions_closed']
 assert v['summary']['canonical_records']==102
 x=json.loads((H/'evidence-import-final.json').read_text());assert not x.get('isError');assert x['structuredContent']['result']==dict(imported=102,unknowns_added=0,total=102)
 assert(H/'import-final-run.log').read_text().splitlines()[-1]=='CLOSED: evidence import session'
 refs={}
 for row in v['functions']:
  for r in row['files']:
   check(r)
   if not(R/r['path']).is_relative_to(H):refs[r['path']]=r
 for r in f['prior_findings']:
  check(r);refs[r['path']]=r
  for name in ['artifact-manifest.json','finalization-manifest.json','ownership-manifest.json']:
   q=(R/r['path']).parent/name
   if q.exists():refs[str(q.relative_to(R))]=pin(q)
 for r in [f['verification'],f['analytical_controls'],f['canonical_import']['response'],f['canonical_import']['run_log']]:check(r)
 for rel in ['research/targets/derived/Cubase15-arm64','research/evidence/cubase-static/cpr-map-clock-001/attributes/source_tools.py','.tools/rea/node_modules/rea-agents/skills/reverse-engineer-anything/SKILL.md','.tools/rea/node_modules/rea-agents/skills/reverse-engineer-anything/references/native-and-artifacts.md','.tools/rea/node_modules/rea-agents/skills/reverse-engineer-anything/references/evidence-workflows.md']:
  refs[rel]=pin(R/rel)
 x=dict(schema_version=1,kind='immutable local static study inventory',source_sha256=f['source_sha256'],target_executed=False,files=inventory(),external_references=list(refs.values()),excludes=['manifest itself','Python bytecode','external independent review'],limits=['Referenced paths do not imply inclusion or redistribution of proprietary bytes/disassembly.','Checks validate listed custody only; no target runtime or hosted behavioral equivalence.','Prior manifests are pinned; this local checker directly rechecks listed references, not all recursively referenced historical inputs.'])
 with M.open('x')as w:json.dump(x,w,indent=2);w.write('\n')
x=json.loads(M.read_text())
for row in x['files']+x['external_references']:check(row)
assert inventory()==x['files'],'closed-world inventory drift'
print(json.dumps(dict(passed=True,files=len(x['files']),external_references=len(x['external_references']),manifest=pin(M))))
