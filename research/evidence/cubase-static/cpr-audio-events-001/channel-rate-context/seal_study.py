"""Seal or recheck this cold local study. Does not execute target code."""
from pathlib import Path
import argparse, hashlib, json
H=Path(__file__).resolve().parent; R=H.parents[4]; M=H/'artifact-manifest.json'
def pin(p):
 b=p.read_bytes();return dict(path=str(p.relative_to(R)),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def check(r):
 p=R/r['path'];assert p.is_file(),p
 q=pin(p);assert q==r,(r,q)
def env(p):
 d=json.loads(p.read_text());assert not d.get('isError'),p
 return d.get('structuredContent')or json.loads(d['content'][0]['text'])
def inventory():
 return [pin(p)for p in sorted(H.rglob('*'))if p.is_file()and p!=M and '__pycache__'not in p.parts]
a=argparse.ArgumentParser();a.add_argument('--seal',action='store_true');opts=a.parse_args()
if opts.seal:
 assert not M.exists(),'Existing seals must not be overwritten'
 v=json.loads((H/'verification.json').read_text()); assert v['passed']
 f=json.loads((H/'finding.json').read_text());assert f['canonical_import']['all_sessions_closed']
 r=env(H/'evidence-import-unique.json')['result'];assert r==dict(imported=90,unknowns_added=0,total=90)
 assert (H/'import-unique-run.log').read_text().splitlines()[-1]=='CLOSED: evidence import session'
 prior={}
 for row in v['functions']:
  for p in row['files']:
   check(p)
   if not (R/p['path']).is_relative_to(H):prior[p['path']]=p
 for p in f['prior_findings']:
  check(p);prior[p['path']]=p
  m=(R/p['path']).parent/'artifact-manifest.json'
  if m.exists(): prior[str(m.relative_to(R))]=pin(m)
 for rel in ['research/targets/derived/Cubase15-arm64','research/evidence/cubase-static/cpr-map-clock-001/attributes/source_tools.py','.tools/rea/node_modules/rea-agents/skills/reverse-engineer-anything/SKILL.md']:
  prior[rel]=pin(R/rel)
 x=dict(schema_version=1,kind='cold immutable local static study inventory',source_sha256=f['source_sha256'],target_executed=False,files=inventory(),external_references=list(prior.values()),excludes=['artifact-manifest.json itself','Python bytecode caches','independent peer review outside this study'],limits=['Local paths do not imply redistribution of proprietary inputs or raw disassembly.','Custody verification does not establish semantic completeness or hosted runtime equivalence.'])
 with M.open('x')as w:json.dump(x,w,indent=2);w.write('\n')
x=json.loads(M.read_text())
for row in x['files']+x['external_references']:check(row)
assert inventory()==x['files'],'Local study inventory drift'
print(json.dumps(dict(passed=True,files=len(x['files']),external_references=len(x['external_references']),manifest=pin(M))))
