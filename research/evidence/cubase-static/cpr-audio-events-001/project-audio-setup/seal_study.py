"""Seal/recheck this local static study; never executes target code."""
from pathlib import Path
import argparse,hashlib,json
H=Path(__file__).resolve().parent;R=H.parents[4];M=H/'artifact-manifest.json'
def pin(p):
 b=p.read_bytes();return dict(path=str(p.relative_to(R)),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def check(row):
 p=R/row['path'];assert p.is_file(),p
 assert pin(p)==row,(row,pin(p))
def inventory():return [pin(p)for p in sorted(H.rglob('*'))if p.is_file()and p!=M and '__pycache__'not in p.parts]
p=argparse.ArgumentParser();p.add_argument('--seal',action='store_true');a=p.parse_args()
if a.seal:
 assert not M.exists(),'Existing seal must not be replaced'
 v=json.loads((H/'verification.json').read_text());f=json.loads((H/'finding.json').read_text());probe=json.loads((H/'schema-probe.json').read_text())
 assert v['passed']and f['canonical_import']['all_sessions_closed']
 imp=json.loads((H/'evidence-import-final.json').read_text());assert not imp.get('isError')
 assert imp['structuredContent']['result']==dict(imported=62,unknowns_added=0,total=62)
 assert (H/'import-final-run.log').read_text().splitlines()[-1]=='CLOSED: evidence import session'
 prior={}
 for row in v['functions']:
  for record in row['files']:
   check(record)
   if not(R/record['path']).is_relative_to(H):prior[record['path']]=record
 for record in f['prior_findings']:
  check(record);prior[record['path']]=record
  m=(R/record['path']).parent/'artifact-manifest.json'
  if m.exists():prior[str(m.relative_to(R))]=pin(m)
 for record in [f['field_schema'],f['fixture_probe'],f['verification'],f['canonical_import']['response'],f['canonical_import']['run_log']]:check(record)
 for row in probe['fixtures']:check(row['source']);prior[row['source']['path']]=row['source']
 for rel in ['research/targets/derived/Cubase15-arm64','research/evidence/cubase-static/cpr-map-clock-001/attributes/source_tools.py','scripts/cpr_probe.py','.tools/rea/node_modules/rea-agents/skills/reverse-engineer-anything/SKILL.md','.tools/rea/node_modules/rea-agents/skills/reverse-engineer-anything/references/native-and-artifacts.md','.tools/rea/node_modules/rea-agents/skills/reverse-engineer-anything/references/evidence-workflows.md']:
  prior[rel]=pin(R/rel)
 x=dict(schema_version=1,kind='cold immutable local static study inventory',source_sha256=f['source_sha256'],target_executed=False,files=inventory(),external_references=list(prior.values()),excludes=['artifact-manifest.json itself','Python bytecode caches','independent peer reviews outside this study'],limits=['Referenced local paths do not imply inclusion in a publication or redistribution of proprietary input bytes/disassembly.','Custody checks and synthetic instrument controls do not establish native runtime equivalence.','External prior manifests are pinned as immutable references; this script verifies referenced files directly listed here, not a recursive replay of all historical studies.'])
 with M.open('x')as w:json.dump(x,w,indent=2);w.write('\n')
x=json.loads(M.read_text())
for row in x['files']+x['external_references']:check(row)
assert inventory()==x['files'],'Study inventory drift'
print(json.dumps(dict(passed=True,files=len(x['files']),external_references=len(x['external_references']),manifest=pin(M))))
