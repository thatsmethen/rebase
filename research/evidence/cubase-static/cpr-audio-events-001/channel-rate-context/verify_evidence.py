"""Read-only source/readback/dispatch verification. No vendor execution."""
from pathlib import Path
import sys,json,re,hashlib
from derive_missing import P
H=Path(__file__).resolve().parent; R=H.parents[4]
sys.path.insert(0,str(R/'research/evidence/cubase-static/cpr-map-clock-001/attributes'));import source_tools as s
pin=lambda p:dict(path=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def env(p):
 d=json.loads(p.read_text());assert not d.get('isError'),p
 return d.get('structuredContent')or json.loads(d['content'][0]['text'])
uses={H/f'pass{n}':a for n,a in P.items()if n!=10}
uses.update({H.parent/'timeline-reader/pass2':[0x101d983c0,0x101d99034],H.parent/'timeline-reader/pass3':[0x101d9b3b4],H.parent/'live-binding/pass11':[0x102fc7564],H.parent/'live-binding/pass12':[0x102fc756c],H.parent/'live-binding/pass6':[0x101d0d034],H.parent/'live-binding/pass7':[0x101d0d038],H.parent/'live-binding/pass16':[0x101d0cc58],H.parent/'live-binding/pass19':[0x101d3f7d8],H.parent/'live-binding/pass20':[0x101d3e704],H.parent/'live-binding/pass21':[0x101d3eb24,0x101d3ea38]})
for n,addresses in P.items():
 folder=H/f'pass{n}';d=json.loads((folder/'derivation.json').read_text())
 assert d['source_sha256']==s.PIN
 for row in d['derivatives']:
  raw=folder/row['raw_file'];assert pin(raw)['sha256']==row['raw_sha256']
  assert raw.read_bytes()==bytes.fromhex(s.region(int(row['entry'],16),row['length'])['bytes_hex'])
 if n==10:continue
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
bindings=[]
for label,table,slot,target in [('Components transport getter',0x1044aced8,0x40,0x1005c078c),('VstDeck rate setter',0x1047b70b0,0x500,0x101d9b3b4),('VstDeck factor getter',0x1047b70b0,0x508,0x101d9b5d8),('VstDeck device rate getter',0x1047b70b0,0x510,0x101d9b5f0),('TGTransport rate setter',0x10478ae90,0x240,0x101c6d040),('TGTransport factor setter',0x10478ae90,0x260,0x101c6d160),('SequencerEngine rate getter',0x1047d9968,0x98,0x102fc7564),('SequencerEngine rate setter',0x1047d9968,0xa0,0x102fc756c),('Engine rate setter',0x104e201e0,0xa0,0x102fc756c)]:
 p=s.region(table+slot,8);assert int.from_bytes(bytes.fromhex(p['bytes_hex']),'little')==target
 bindings.append(dict(label=label,table=hex(table),slot=hex(slot),target=hex(target),source=p))
ranges=[]
for label,a,n in [('TGTransport registry key',0x104f86418,23),('Engine registry key',0x104f864f2,21),('VstDeck RTTI name',0x103aea74f,24),('TGTransport RTTI name',0x103ade3c7,39),('SequencerEngine RTTI name',0x103af8c5d,46),('PDevice literal',0x10388d060,8),('PBaiosDevice literal',0x10389a8ec,13),('Engine update numeric chain',0x101ed7098,84),('Reader multiplier chain',0x101d3ebc0,92),('Ordinary or alternate branch',0x101d3fcd0,80),('Components default transport acquisition',0x1005c038c,24),('Root builder rate getter',0x10171c5a0,36)]:ranges.append(dict(label=label,**s.region(a,n)))
x=dict(source_sha256=s.PIN,target_execution=False,functions=rows,dispatch=bindings,original_ranges=ranges,summary=dict(new_captures=sum(r['new']for r in rows),new_unique_functions=len({r['entry']for r in rows if r['new']}),reused_captures=sum(not r['new']for r in rows),bytes_verified=sum(r['bytes_verified']for r in rows),original_native_words=sum(r['original_native_words']for r in rows),rea_instruction_addresses=sum(r['rea_instruction_addresses']for r in rows),closed_raw_sessions=len(P)-1,discovery_only_intervals=len(P[10])),passed=True,limits=['Addresses/readback verify custody, not semantic completeness.','Raw imports omit target globals, imports, neighboring instructions, relocation and RTTI; selected original dispatch cells restore only listed context.','One repeated101d99584 capture is retained and counted separately; unique count supplied.','Pass10 consists of original-image candidate disassemblies only; not promoted to REA evidence or contract.'])
(H/'verification.json').write_text(json.dumps(x,indent=2)+'\n');print(x['summary'])
