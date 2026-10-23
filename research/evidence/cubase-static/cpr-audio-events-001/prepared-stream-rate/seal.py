from pathlib import Path
import json,hashlib
H=Path(__file__).resolve().parent;R=H.parents[4]
def pin(p):
 b=p.read_bytes();return dict(path=str(p.relative_to(R)),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
external={R/'research/targets/derived/Cubase15-arm64',R/'scripts/rea',R/'research/evidence/cubase-static/cpr-map-clock-001/attributes/source_tools.py'}
for x in ['package.json','skills/reverse-engineer-anything/SKILL.md','skills/reverse-engineer-anything/references/native-and-artifacts.md','skills/reverse-engineer-anything/references/evidence-workflows.md']:
 external.add(R/'.tools/rea/node_modules/rea-agents'/x)
for row in json.loads((H/'reused.json').read_text()):
 d=R/row['directory'];external.add(d/'derivation.json')
 for entry in row['entries']:
  ident=entry[2:]
  external.update(p for p in d.iterdir() if p.is_file() and ident in p.name)
for study in ['processed-stream-rate','renderer-selection']:
 for name in ['finding.json','artifact-manifest.json']:
  p=H.parent/study/name
  if p.exists():external.add(p)
files=[pin(p) for p in sorted(H.rglob('*')) if p.is_file() and p.name!='artifact-manifest.json' and '__pycache__' not in p.parts]
f=dict(schema_version=1,kind='cold immutable local static study inventory',target_executed=False,source_sha256=json.loads((H/'verification.json').read_text())['source_sha256'],files=files,external_references=[pin(p) for p in sorted(external)],exclusions=['Self manifest excluded to avoid circular hash.','No mutable Application source or runtime target output included.'])
with (H/'artifact-manifest.json').open('x') as o:json.dump(f,o,indent=2);o.write('\n')
for rec in files+f['external_references']:
 assert pin(R/rec['path'])==rec
print(json.dumps(dict(manifest=pin(H/'artifact-manifest.json'),local_files=len(files),external_references=len(external))))
