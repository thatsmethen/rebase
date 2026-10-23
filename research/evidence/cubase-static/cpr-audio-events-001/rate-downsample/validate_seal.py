"""Read-only revalidation of the immutable seal; never refresh hashes."""
from pathlib import Path
import json,hashlib
H=Path(__file__).resolve().parent;ROOT=H.parents[4]
m=json.loads((H/'artifact-manifest.json').read_text());failures=[]
for x in m['files']:
 p=ROOT/x['path']
 if not p.exists()or p.stat().st_size!=x['bytes']or hashlib.sha256(p.read_bytes()).hexdigest()!=x['sha256']:failures.append(x['path'])
print(json.dumps({'checked':len(m['files']),'failures':failures,'target_execution':False}));assert not failures
