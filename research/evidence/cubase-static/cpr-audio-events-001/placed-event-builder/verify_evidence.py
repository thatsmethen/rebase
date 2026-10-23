"""Original/readback/instruction custody; no proprietary execution."""
from pathlib import Path
import sys,json,re,struct,hashlib
H=Path(__file__).resolve().parent;R=H.parents[4]
sys.path.insert(0,str(R/'research/evidence/cubase-static/cpr-map-clock-001/attributes'))
import source_tools as s
def pin(p):return {'path':str(p.relative_to(R)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def env(p):
 d=json.loads(p.read_text());assert not d.get('isError'),p
 return d.get('structuredContent')or json.loads(d['content'][0]['text'])
uses={H/'pass1':[0x10020f2e8,0x10020e354,0x10020e7c8],
 H.parent/'timeline-provider/pass5':[0x1016e3794,0x1016e39c8],
 H.parent/'timeline-provider/pass7':[0x101c225d0,0x1007ddd24,0x10171c5a0],
 H.parent/'event-rendering/pass3':[0x101a17ccc,0x101a17cec,0x101a17d14],
 H.parent/'timebase/pass3':[0x1016e2640],H.parent/'timebase/pass24':[0x101c26df0],
 R/'research/evidence/cubase-static/cpr-audio-timing-001':[0x101c22dc0]}
lines=(H/'pass1/run.log').read_text().splitlines()
assert lines[-1]=='CLOSED: isolated raw-slice MCP session'
assert all(json.loads(x)['isError']is False for x in lines[:-1])
for d in json.loads((H/'pass1/derivation.json').read_text())['derivatives']:
 raw=H/'pass1'/d['raw_file'];assert pin(raw)['sha256']==d['raw_sha256']
 assert raw.read_bytes()==bytes.fromhex(s.region(int(d['entry'],16),d['length'])['bytes_hex'])
 close=env(H/'pass1'/f"close-{d['entry'][2:]}.json")['result']
 assert close['evidence_records']==2 and Path(close['path']).stat().st_size==close['bytes']
rows=[]
for folder,addresses in uses.items():
 for a in addresses:
  paths=[folder/f'{prefix}-{a:x}.json'for prefix in('function','bytes','bundle')]
  native=folder/f'native-{a:x}.txt'
  words={int(pc,16):int(word,16)for pc,word in re.findall(r'^([0-9a-f]+):\s+([0-9a-f]{8})\s',native.read_text(),re.M)}
  assert words and min(words)==a
  for pc,word in words.items():assert int.from_bytes(bytes.fromhex(s.region(pc,4)['bytes_hex']),'little')==word
  doc,rd,bundle=[env(p)for p in paths];b=rd['raw_result']
  assert b['complete']and b['requested_bytes']==b['returned_bytes']
  original=bytes.fromhex(s.region(a,b['returned_bytes'])['bytes_hex'])
  assert original==bytes.fromhex(b['bytes_hex'])and len(original)==len(words)*4
  asm=doc['raw_result']['value']['assembly'];assert all(int(x.split(':')[0],16)in words for x in asm)
  assert len(bundle['result']['records'])==2
  rows.append({'entry':hex(a),'new':folder.parent==H,'directory':str(folder.relative_to(R)),
   'bytes_verified':len(original),'original_native_words':len(words),'rea_instruction_addresses':len(asm),
   'original_bytes_sha256':hashlib.sha256(original).hexdigest(),
   'evidence_ids':[doc['evidence_id'],rd['evidence_id']],'files':[pin(p)for p in[native]+paths]})
table=s.region(0x103ada008,18);assert 0x101c22600+4*bytes.fromhex(table['bytes_hex'])[10]==0x101c2267c
bindings=[]
for slot,target,n in [(0xd0,0x101a17ccc,8),(0xd8,0x101a17cd4,8),(0xe0,0x101a17cdc,8),(0xf0,0x101a17cec,32),(0xf8,0x101a17d08,12),(0x100,0x101a17d14,8),(0x108,0x101a17d1c,8)]:
 p=s.region(0x104436be0+slot,8);assert int.from_bytes(bytes.fromhex(p['bytes_hex']),'little')==target
 bindings.append({'slot':hex(slot),'target':hex(target),'pointer':p,'instructions':s.region(target,n)})
links=[('canonical_tag1_period1_initializer',0x101c26ea0,36),
 ('offset_difference_then_add',0x10020f490,48),('signed_half_and_integer_conversion',0x10020f630,28),
 ('normal_remainder_segment_stores',0x1002104fc,160),('singleton_nonoverlap_branch',0x10020ea38,76),
 ('singleton_lower_sentinel',0x10020e7ec,12),('clip_fcsel_tie_order',0x10020e4bc,28),
 ('ordinary_caller_window_and_shift',0x1002115e0,64),
 ('initial_track_range_and_context_rate',0x10020f090,104),
 ('post_builder_start_shift',0x10020f140,32)]
result={'source_sha256':s.PIN,'target_execution':False,'functions':rows,
 'original_bindings':{'segment_setters_getters':bindings,'type10_jump_table':table,
 'spans':[{'label':label,**s.region(a,n)}for label,a,n in links],
 'singleton_lower_sentinel_bits':'c14b774000000000','singleton_lower_sentinel':struct.unpack('>d',bytes.fromhex('c14b774000000000'))[0]},
 'summary':{'new_functions':sum(x['new']for x in rows),'reused_functions':sum(not x['new']for x in rows),
 'bytes_verified':sum(x['bytes_verified']for x in rows),'original_native_words':sum(x['original_native_words']for x in rows),
 'rea_instruction_addresses':sum(x['rea_instruction_addresses']for x in rows)},'passed':True,
 'limits':['Byte/readback/address equality is custody, not complete semantic proof.',
 'Raw slices lose imports, vtables, globals, neighboring callees and exception context; original listed cells supply bounded bindings.',
 'LC function intervals may include disconnected initializer/cleanup material not decoded by REA as the entry function.']}
(H/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result['summary']))
