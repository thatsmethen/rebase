"""Original-image custody and typed binding checks. Never executes target code."""
from pathlib import Path
import sys,json,re,hashlib
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent;R=H.parents[4]
sys.path.insert(0,str(R/'research/evidence/cubase-static/cpr-map-clock-001/attributes'));import source_tools as s
pin=lambda p:dict(path=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def env(p):
 d=json.loads(p.read_text());assert not d.get('isError'),p
 return d.get('structuredContent') or json.loads(d['content'][0]['text'])
uses={}
for folder in sorted(H.glob('pass*')):
 if not folder.is_dir():continue
 deriv=json.loads((folder/'derivation.json').read_text());assert deriv['source_sha256']==s.PIN
 for row in deriv['derivatives']:
  raw=folder/row['raw_file'];assert pin(raw)['sha256']==row['raw_sha256']
  assert raw.read_bytes()==bytes.fromhex(s.region(int(row['entry'],16),row['length'])['bytes_hex'])
 lines=(folder/'run.log').read_text().splitlines();assert lines[-1]=='CLOSED: isolated raw-slice MCP session'
 assert all(json.loads(line)['isError']is False for line in lines[:-1])
 uses[folder]=[int(row['entry'],16)for row in deriv['derivatives']]
 for a in uses[folder]:
  close=env(folder/f'close-{a:x}.json')['result'];assert close['evidence_records']==2
  assert Path(close['path']).stat().st_size==close['bytes']
prior=[('cpr-objects-001/audio-native',0x100959278),('cpr-audio-events-001/builder-rate-provider/pass9',0x100965b50),('cpr-audio-events-001/builder-rate-provider/pass7',0x1009573dc),('cpr-audio-events-001/builder-rate-provider/pass7',0x10095742c),('cpr-audio-events-001/timeline-provider/pass7',0x10171c5a0),('cpr-audio-events-001/timebase/pass25',0x101c23cf0),('cpr-map-clock-001/list-review/constructor-context',0x101c246b4),('cpr-objects-001/native/pass3',0x101c23184),('cpr-objects-001/native/pass2',0x10221e188),('cpr-objects-001/native/pass2',0x10221e3fc),('cpr-objects-001/native',0x10221d068),('cpr-objects-001/native',0x10221d38c)]
for d,a in prior:uses.setdefault(R/'research/evidence/cubase-static'/d,[]).append(a)
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
for label,a,value in [('PArrangement reader',0x10450d5d8,0x100959278),('PArrangement post-read callback',0x10450d648,0x100956f80),('PArrangement rate with factor',0x10450d6f0,0x1009573dc),('PArrangeSetup RTTI pointer',0x10450e378,0x10450e5f8),('PArrangeSetup RTTI name pointer',0x10450e600,0x10399c6e2),('PArrangeSetup reader',0x10450e418,0x100966640),('PArrangeSetup writer',0x10450e420,0x100966a54),('embedded datum reader',0x104781020,0x101c25998),('embedded datum writer',0x104781028,0x101c259d8),('FFileType reader',0x104e45620,0x10319b8b8),('FFileType writer',0x104e45628,0x10319b860),('FFileType RTTI pointer',0x104e45580,0x104e456c0),('FFileType RTTI name pointer',0x104e456c8,0x103c7a3f4)]:
 region=s.region(a,8);got=int.from_bytes(bytes.fromhex(region['bytes_hex']),'little');assert got==value,(label,hex(got),hex(value))
 bindings.append(dict(label=label,value=hex(value),source=region))
literals=[]
for a,b in [(0x103893358,b'MRoot\0'),(0x1038b14e7,b'PArrangeSetup\0'),(0x10389d8cf,b'PArrangement\0'),(0x10399c6e2,b'N9Steinberg13PArrangeSetupE\0'),(0x103c7a3f4,b'N9Steinberg9FFileTypeE\0'),(0x1038928a2,b'PAudioDevice\0')]:
 region=s.region(a,len(b));assert bytes.fromhex(region['bytes_hex'])==b;literals.append(dict(text=b[:-1].decode(),source=region))
spans=[]
for label,a,n in [('typed root read/store',0x100959290,32),('typed setup read/store and owner links',0x100959300,56),('setup base rate read and guard',0x1009666c8,92),('factor version branch/read',0x1009667ac,24),('factor legacy default',0x1009668a4,8),('normal reader status return',0x1009669fc,20),('literal provider product',0x1009573e8,36),('FFileType ctor vtable materialization',0x10319b1dc,52)]:spans.append(dict(label=label,source=s.region(a,n)))
x=dict(source_sha256=s.PIN,target_executed=False,functions=rows,dispatch=bindings,literals=literals,original_ranges=spans,summary=dict(new_captures=sum(r['new']for r in rows),reused_captures=sum(not r['new']for r in rows),bytes_verified=sum(r['bytes_verified']for r in rows),original_native_words=sum(r['original_native_words']for r in rows),rea_instruction_addresses=sum(r['rea_instruction_addresses']for r in rows),closed_raw_sessions=5,canonical_records=sum(len(r['evidence_ids'])for r in rows)),passed=True,limits=['Custody checks do not establish semantic completeness.','LC_FUNCTION_STARTS intervals can include disconnected exception tails.','Raw Ghidra imports omit external globals/types and can misrepresent floating-point unordered comparisons and inferred signatures. Original instructions govern stated local contracts.','New captures may recapture functions retained in earlier studies; counts describe this study capture/reuse inventory, not unique discoveries across the repository.'])
(H/'verification.json').write_text(json.dumps(x,indent=2)+'\n');print(x['summary'])
