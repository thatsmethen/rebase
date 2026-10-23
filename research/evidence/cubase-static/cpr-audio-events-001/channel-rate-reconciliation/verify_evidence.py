"""Read-only source/readback/dispatch verification. No vendor execution."""
from pathlib import Path
import sys,json,re,hashlib
from derive import P
H=Path(__file__).resolve().parent; R=H.parents[4]
sys.path.insert(0,str(R/'research/evidence/cubase-static/cpr-map-clock-001/attributes'));import source_tools as s
pin=lambda p:dict(path=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def env(p):
 d=json.loads(p.read_text());assert not d.get('isError'),p
 return d.get('structuredContent')or json.loads(d['content'][0]['text'])
uses={H/f'pass{n}':a for n,a in P.items()}
uses.update({H.parent/'channel-rate-context/pass1':[0x101d3fc3c],H.parent/'channel-rate-context/pass2':[0x101d437e0],H.parent/'channel-rate-context/pass15':[0x101f46378]})
for n,addresses in P.items():
 folder=H/f'pass{n}';d=json.loads((folder/'derivation.json').read_text())
 assert d['source_sha256']==s.PIN
 for row in d['derivatives']:
  raw=folder/row['raw_file'];assert pin(raw)['sha256']==row['raw_sha256']
  assert raw.read_bytes()==bytes.fromhex(s.region(int(row['entry'],16),row['length'])['bytes_hex'])
 lines=(folder/'run.log').read_text().splitlines();assert lines[-1]=='CLOSED: isolated raw-slice MCP session'
 assert all(json.loads(v)['isError']is False for v in lines[:-1]),folder
 for a in addresses:
  x=env(folder/f'close-{a:x}.json')['result'];assert x['evidence_records']==2 and Path(x['path']).stat().st_size==x['bytes']
rows=[]
for folder,addresses in uses.items():
 for a in addresses:
  paths=[folder/f'{v}-{a:x}.json'for v in ['function','bytes','bundle']];native=folder/f'native-{a:x}.txt'
  words={int(pc,16):int(w,16)for pc,w in re.findall(r'^([0-9a-f]+):\s+([0-9a-f]{8})\s',native.read_text(),re.M)}
  for pc,w in words.items():assert int.from_bytes(bytes.fromhex(s.region(pc,4)['bytes_hex']),'little')==w
  d,read,b=[env(p)for p in paths];q=read['raw_result'];assert q['complete']and q['requested_bytes']==q['returned_bytes']
  original=bytes.fromhex(s.region(a,q['returned_bytes'])['bytes_hex']);assert original==bytes.fromhex(q['bytes_hex'])and len(original)==len(words)*4
  asm=d['raw_result']['value']['assembly'];assert all(int(v.split(':')[0],16)in words for v in asm)
  assert len(b['result']['records'])==2
  rows.append(dict(entry=hex(a),new=folder.parent==H,directory=str(folder.relative_to(R)),bytes_verified=len(original),original_native_words=len(words),rea_instruction_addresses=len(asm),evidence_ids=[d['evidence_id'],read['evidence_id']],files=[pin(p)for p in [native]+paths]))
x=dict(source_sha256=s.PIN,target_execution=False,functions=rows,summary=dict(new_captures=sum(r['new']for r in rows),reused_captures=sum(not r['new']for r in rows),bytes_verified=sum(r['bytes_verified']for r in rows),original_native_words=sum(r['original_native_words']for r in rows),rea_instruction_addresses=sum(r['rea_instruction_addresses']for r in rows),closed_raw_sessions=len(P)),passed=True,limits=['Address and readback checks establish custody, not semantic completeness.','Raw slices omit global/relocation/RTTI context; exact selected original bindings are retained separately.','Nearby discovery functions are retained but not all their behavior is used in the contract.'])
(H/'verification.json').write_text(json.dumps(x,indent=2)+'\n');print(x['summary'])
