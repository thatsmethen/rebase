"""Exact pinned-image function derivatives; never executes target code.
Existing passes are checked for identity; only a missing pass is generated.
"""
from pathlib import Path
import sys,json,hashlib
ROOT=Path(__file__).resolve().parents[5]
HELPER=ROOT/'research/evidence/cubase-static/cpr-map-clock-001/attributes/source_tools.py'
sys.path.insert(0,str(HELPER.parent));import source_tools as s
H=Path(__file__).resolve().parent
PASSES={1:[0x1001f9450,0x1001f953c,0x1001f985c,0x1001f99bc,0x1001fd4f4],2:[0x1001f9b64,0x1001fbcd4],3:[0x1001f6500,0x1001f96d8,0x1001f96e8],4:[0x101a17d08,0x101a18160,0x101a18078,0x103102654],5:[0x100212d74,0x103101a0c]}
for n,aa in PASSES.items():
 p=H/f'pass{n}'
 if not (p/'derivation.json').exists():s.derive(aa,p)
 else:
  d=json.loads((p/'derivation.json').read_text());assert [int(x['entry'],16)for x in d['derivatives']]==aa
  for r in d['derivatives']:assert (p/r['raw_file']).read_bytes()==s.data[r['source_file_offset']:r['source_file_offset']+r['length']]
print(json.dumps({'helper_sha256':hashlib.sha256(HELPER.read_bytes()).hexdigest(),'pass_count':len(PASSES),'target_execution':False}))
