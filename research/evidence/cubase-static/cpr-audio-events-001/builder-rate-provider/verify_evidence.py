"""Recheck immutable source slices and bounded bindings; never executes target code."""
from pathlib import Path
import sys,json,re,hashlib,struct
H=Path(__file__).resolve().parent;R=H.parents[4]
sys.path.insert(0,str(R/'research/evidence/cubase-static/cpr-map-clock-001/attributes'));import source_tools as s
pin=lambda p:dict(path=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def env(p):
 d=json.loads(p.read_text());assert not d.get('isError'),p
 return d.get('structuredContent')or json.loads(d['content'][0]['text'])
uses={};discovery=[]
for folder in sorted(H.glob('pass*')):
 if not folder.is_dir():continue
 d=json.loads((folder/'derivation.json').read_text());assert d['source_sha256']==s.PIN
 for row in d['derivatives']:
  p=folder/row['raw_file'];assert pin(p)['sha256']==row['raw_sha256']
  assert p.read_bytes()==bytes.fromhex(s.region(int(row['entry'],16),row['length'])['bytes_hex'])
 if folder.name=='pass4':
  discovery.extend(d['derivatives']);continue
 lines=(folder/'run.log').read_text().splitlines();assert lines[-1]=='CLOSED: isolated raw-slice MCP session'
 assert all(json.loads(v)['isError']is False for v in lines[:-1]),folder
 uses[folder]=[int(r['entry'],16)for r in d['derivatives']]
 for a in uses[folder]:
  x=env(folder/f'close-{a:x}.json')['result'];assert x['evidence_records']==2 and Path(x['path']).stat().st_size==x['bytes']
uses[H.parent/'timeline-provider/pass7']=[0x10171c5a0]
uses[H.parent/'channel-rate-context/pass15']=[0x10171c5c4]
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
bindings=[]
for label,a,value in [('PArrangement primary RTTI',0x10450d538,0x10450d868),('PArrangement rate-interface RTTI',0x10450d6e8,0x10450d868),('PArrangement rate with factor',0x10450d6f0,0x1009573dc),('PArrangement base rate',0x10450d6f8,0x10095742c),('PArrangement RTTI name pointer',0x10450d870,0x10399b23b)]:
 p=s.region(a,8);assert int.from_bytes(bytes.fromhex(p['bytes_hex']),'little')==value;bindings.append(dict(label=label,value=hex(value),source=p))
ranges=[]
for label,a,n in [('PArrangement RTTI name',0x10399b23b,27),('registry lookup literal',0x1038928a2,13),('provider table install',0x1009563ec,36),('configuration allocation and pointer',0x1009564b8,28),('provider root install',0x1009565e0,28),('config default base/factor immediate stores',0x100965bd4,16),('optional config device getters',0x100965c6c,88),('optional arrangement device test and assignment',0x100956524,112)]:ranges.append(dict(label=label,**s.region(a,n)))
assert bytes.fromhex(ranges[0]['bytes_hex'])==b'N9Steinberg12PArrangementE\0'
assert bytes.fromhex(ranges[1]['bytes_hex'])==b'PAudioDevice\0'
for row in json.loads((H/'concrete-table-cells.json').read_text()):assert row['bytes_hex']==s.region(int(row['address'],16),row['length'])['bytes_hex']
for row in json.loads((H/'owner-rtti.json').read_text()):
 for k in ['rtti','name']:
  x=row[k];assert x['bytes_hex']==s.region(int(x['address'],16),x['length'])['bytes_hex']
x=dict(source_sha256=s.PIN,target_executed=False,functions=rows,dispatch=bindings,original_ranges=ranges,summary=dict(new_captures=sum(r['new']for r in rows),reused_captures=sum(not r['new']for r in rows),bytes_verified=sum(r['bytes_verified']for r in rows),original_native_words=sum(r['original_native_words']for r in rows),rea_instruction_addresses=sum(r['rea_instruction_addresses']for r in rows),closed_raw_sessions=len(uses)-2,discovery_only_intervals=len(discovery)),passed=True,limits=['Readback/address verification is custody, not proof of semantic completeness.','Raw imports omit external functions, globals, runtime types, relocations and unwind context; only listed original bindings are restored.','pass4 is original-image discovery only and has no REA analysis claim.','The whole-image store/address searches produce candidates; only typed constructor/provider chain is promoted.'])
(H/'verification.json').write_text(json.dumps(x,indent=2)+'\n');print(x['summary'])
