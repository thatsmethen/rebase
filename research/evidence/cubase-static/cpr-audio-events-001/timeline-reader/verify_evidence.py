"""Original-byte/readback custody only; no proprietary execution."""
from pathlib import Path
import sys,json,re,struct,hashlib
H=Path(__file__).resolve().parent;R=H.parents[4]
sys.path.insert(0,str(R/'research/evidence/cubase-static/cpr-map-clock-001/attributes'))
import source_tools as s

def pin(p):return {'path':str(p.relative_to(R)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def envelope(p):
 x=json.loads(p.read_text());assert not x.get('isError'),p
 return x.get('structuredContent') or json.loads(x['content'][0]['text'])
uses={}
for name in ('pass1','pass2','pass3'):
 folder=H/name;derivation=json.loads((folder/'derivation.json').read_text())
 uses[folder]=[int(d['entry'],16) for d in derivation['derivatives']]
 assert (folder/'run.log').read_text().endswith('CLOSED: isolated raw-slice MCP session\n')
 for line in (folder/'run.log').read_text().splitlines()[:-1]:
  assert json.loads(line)['isError'] is False
 for d in derivation['derivatives']:
  raw=folder/d['raw_file'];assert raw.stat().st_size==d['length'];assert pin(raw)['sha256']==d['raw_sha256']
  assert raw.read_bytes()==bytes.fromhex(s.region(int(d['entry'],16),d['length'])['bytes_hex'])
  closed=envelope(folder/f"close-{int(d['entry'],16):x}.json")['result']
  assert closed['evidence_records']==2 and Path(closed['path']).stat().st_size==closed['bytes']
uses[H.parent/'live-binding/pass20']=[0x101d3e704]
uses[H.parent/'live-binding/pass21']=[0x101d3ea38,0x101d3eb24]
uses[R/'research/evidence/cubase-static/cpr-audio-timing-001']=[0x101c22884]
rows=[]
for folder,addresses in uses.items():
 for a in addresses:
  native=folder/f'native-{a:x}.txt';analysis=folder/f'function-{a:x}.json';readback=folder/f'bytes-{a:x}.json'
  words={int(pc,16):int(word,16)for pc,word in re.findall(r'^([0-9a-f]+):\s+([0-9a-f]{8})\s',native.read_text(),re.M)}
  assert words and min(words)==a
  for pc,word in words.items():assert int.from_bytes(bytes.fromhex(s.region(pc,4)['bytes_hex']),'little')==word
  rd=envelope(readback);b=rd['raw_result'];assert b['complete'] and b['requested_bytes']==b['returned_bytes']
  original=bytes.fromhex(s.region(a,b['returned_bytes'])['bytes_hex']);assert original==bytes.fromhex(b['bytes_hex'])
  assert len(words)*4==len(original),(hex(a),len(words),len(original))
  doc=envelope(analysis);asm=doc['raw_result']['value']['assembly'];assert all(int(line.split(':')[0],16)in words for line in asm)
  bundle=envelope(folder/f'bundle-{a:x}.json');assert len(bundle['result']['records'])==2
  rows.append({'entry':hex(a),'new':folder.parent==H,'directory':str(folder.relative_to(R)),
   'original_native_words':len(words),'rea_instruction_addresses':len(asm),'bytes_verified':len(original),
   'original_bytes_sha256':hashlib.sha256(original).hexdigest(),'evidence_ids':[doc['evidence_id'],rd['evidence_id']],
   'files':[pin(p)for p in(native,analysis,readback,folder/f'bundle-{a:x}.json')]})
# Type10 byte dispatch at the exact original table index, not decompiler inference.
table=s.region(0x103ada02c,18);values=bytes.fromhex(table['bytes_hex']);assert 0x101c22900+4*values[10]==0x101c22988
seed=s.region(0x103aeb310,16);assert struct.unpack('<dd',bytes.fromhex(seed['bytes_hex']))==(44100.0,1.0)
getters=[]
for slot,target,length in [(0xd8,0x101a17cd4,8),(0xf8,0x101a17d08,12),(0x108,0x101a17d1c,8)]:
 pointer=s.region(0x104436be0+slot,8)
 assert int.from_bytes(bytes.fromhex(pointer['bytes_hex']),'little')==target
 getters.append({'slot':hex(slot),'target':hex(target),'pointer':pointer,'instructions':s.region(target,length)})
# Recheck every previously pinned input without changing prior artifacts.
for row in json.loads((H/'reused-inputs.json').read_text())['files']:
 assert pin(R/row['path'])==row,row['path']
result={'source_sha256':s.PIN,'target_execution':False,'functions':rows,
 'original_bindings':{'concrete_segment_getters':getters,'datum_type10_switch':table,'type10_target':'0x101c22988','rate_ratio_constructor_pair':seed,
 'type10_setter_write':s.region(0x101c22988,16),'global_rate_setter_sequence':s.region(0x101d9b430,32),
 'reader_scale_sequence':s.region(0x101d3ebdc,64)},
 'summary':{'new_functions':sum(x['new']for x in rows),'reused_functions':sum(not x['new']for x in rows),
 'original_native_words':sum(x['original_native_words']for x in rows),'rea_instruction_addresses':sum(x['rea_instruction_addresses']for x in rows),
 'bytes_verified':sum(x['bytes_verified']for x in rows)},'passed':True,
 'limits':['Raw slices omit globals/types/neighboring calls; source bindings cover only the listed spans.',
 'Some LC_FUNCTION_STARTS intervals contain disconnected tails or other material not decoded as one function.',
 'Address/readback agreement is custody, not proof of complete host semantics.']}
(H/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result['summary']))
