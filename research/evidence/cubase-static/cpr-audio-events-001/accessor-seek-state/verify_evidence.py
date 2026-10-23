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
uses={H/'pass2':[0x10033d530,0x100339108],H/'pass3':[0x10033d024,0x10033d308],H/'pass1':[0x10036f89c,0x10036eff0,0x1003261a8,0x10030a1dc,0x10033a4f8,0x10033a054],
 H.parent/'segment-consumer':[0x10036e34c,0x10036e858,0x10036fb74,0x10036d22c,0x10036d848,0x10036d87c,0x10036cd94],
 H.parent/'rate-converter':[0x100323904,0x100323b24,0x1003237d8,0x100323688,0x100330d84,0x100330cd4,0x10030a3bc,0x10030a3a4,0x10030a430,0x100313bf8,0x100313adc,0x100313b74,0x100313c2c,0x10031542c,0x10030af58,0x10030b8a8,0x1003141bc,0x100315438],
 H.parent/'rate-samples/pass1':[0x10030c5b8,0x10030c620,0x10030c664],
 H.parent/'rate-mode1/pass1':[0x10030a728,0x10030a748,0x10030ae8c]}
for passname in ['pass1','pass2','pass3']:
 folder=H/passname;lines=(folder/'run.log').read_text().splitlines()
 assert lines[-1]=='CLOSED: isolated raw-slice MCP session'
 assert all(json.loads(x)['isError']is False for x in lines[:-1])
 for d in json.loads((folder/'derivation.json').read_text())['derivatives']:
  raw=folder/d['raw_file'];assert pin(raw)['sha256']==d['raw_sha256']
  assert raw.read_bytes()==bytes.fromhex(s.region(int(d['entry'],16),d['length'])['bytes_hex'])
  close=env(folder/f"close-{d['entry'][2:]}.json")['result']
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
bindings=[]
for name,table,slot,target in [('accessor_reset_format',0x1044664f0,0xd8,0x10036e858),('accessor_needs_conversion',0x1044664f0,0x188,0x10036fb74),('cluster_read',0x104466378,0x10,0x10036d22c),('cluster_seek',0x104466378,0x20,0x10036d848),('cluster_tell',0x104466378,0x28,0x10036d87c),('mode0_rate',0x104461990,0x10,0x10030c5b8),('mode0_init',0x104461990,0x20,0x10030c620),('mode0_ready',0x104461990,0x28,0x10030c664),('mode1_rate',0x1044618f0,0x10,0x10030a728),('mode1_init',0x1044618f0,0x20,0x10030a748),('mode1_ready',0x1044618f0,0x28,0x10030ae8c),('mode2_rate',0x104461a08,0x10,0x100313adc),('mode2_init',0x104461a08,0x20,0x100313b74),('mode2_ready',0x104461a08,0x28,0x100313c2c),('mode2_child_ready',0x104461a80,0x60,0x10031542c),('AudioFile_kind',0x104462178,0x150,0x10033d024),('AudioFile_bits',0x104462178,0x158,0x10033d308),('AudioFile_formatID',0x104462178,0x168,0x10033d530),('AudioFile_reader_factory',0x104462178,0xf8,0x10033a4f8)]:
 p=s.region(table+slot,8);assert int.from_bytes(bytes.fromhex(p['bytes_hex']),'little')==target
 bindings.append({'label':name,'vtable':hex(table),'slot':hex(slot),'target':hex(target),'source':p})
result={'source_sha256':s.PIN,'target_execution':False,'functions':rows,'concrete_dispatch':bindings,'additional_original_ranges':[{'label':'AudioSampleFormat',**s.region(0x10388f5fc,18)},{'label':'AudioSampleSize',**s.region(0x10388f01f,16)},{'label':'sample_bits_fallback',**s.region(0x10036e084,92)}],
 'summary':{'new_functions':sum(x['new']for x in rows),'reused_functions':sum(not x['new']for x in rows),'bytes_verified':sum(x['bytes_verified']for x in rows),'original_native_words':sum(x['original_native_words']for x in rows),'rea_instruction_addresses':sum(x['rea_instruction_addresses']for x in rows)},'passed':True,
 'limits':['Byte/readback/address equality validates custody, not full semantic completeness.','Raw slices omit original imports, globals, classes and neighbor code; separately verified concrete dispatch cells supplement this.','LC function intervals may contain disconnected exception tails not part of the decompiled entry.','No proprietary target or backend was executed.']}
(H/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result['summary']))
