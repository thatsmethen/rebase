"""Independent original-byte/readback audit. No target execution or reanalysis."""
from pathlib import Path
import hashlib,json,re,struct,datetime
H=Path(__file__).resolve().parent; R=H.parents[4]; B=H.parent/'list'
sha=lambda x:hashlib.sha256(x).hexdigest()
def pin(p):return {'path':str(p.relative_to(R)),'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())}
source=R/'research/targets/derived/Cubase15-arm64'; data=source.read_bytes(); digest=sha(data)
assert digest=='dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb'
segments=[]; pos=32
for _ in range(struct.unpack_from('<I',data,16)[0]):
 command,size=struct.unpack_from('<II',data,pos)
 if command==0x19:
  v=struct.unpack_from('<II16sQQQQIIII',data,pos);segments.append((v[3],v[5],v[6]))
 pos+=size
def original(a,n):
 seg,=[x for x in segments if x[0]<=a and a+n<=x[0]+x[2]];o=seg[1]+a-seg[0];return o,data[o:o+n]
rows=[];attempts=[];derivation_pins=[]
for p in sorted(B.glob('derivation-pass*.json'))+[B/'retry-factory/derivation.json']:
 d=json.loads(p.read_text());assert d['source_sha256']==digest;derivation_pins.append(pin(p))
 for r in d['derivatives']:
  base=p.parent;ident=r['entry'][2:];start=int(r['entry'],16);raw_path=(base/r['raw_file']).resolve();raw=raw_path.read_bytes();o,sourcebytes=original(start,len(raw));assert raw==sourcebytes and o==r['source_file_offset'] and sha(raw)==r['raw_sha256']
  np=(base/r['original_native_disassembly']).resolve(); assert sha(np.read_bytes())==r['native_stdout_sha256']
  words={}
  for m in re.finditer(r'^([0-9a-f]+):\s+([0-9a-f]{8})\s+(.+)$',np.read_text(),re.M):
   a,w=int(m[1],16),int(m[2],16);assert start<=a<start+len(raw);assert raw[a-start:a-start+4]==w.to_bytes(4,'little');words[a]=w
  assert set(words)==set(range(start,start+len(raw),4))
  out={};pins=[pin(raw_path),pin(np)]
  for kind in ['open','function','bytes','bundle','close','snapshot']:
   q=base/f'{kind}-{ident}.json'
   if not q.exists():out[kind]={'present':False};continue
   v=json.loads(q.read_text());pins.append(pin(q));out[kind]={'present':True,'isError':bool(v.get('isError',False))}
   if v.get('isError'):out[kind]['error']=v.get('content')
  function=json.loads((base/f'function-{ident}.json').read_text());bw=json.loads((base/f'bytes-{ident}.json').read_text())
  success=not function.get('isError') and not bw.get('isError') and bool(function.get('structuredContent')) and bool(bw.get('structuredContent'))
  addresses=[];f=None;bb=None
  if success:
   f=function['structuredContent'];bb=bw['structuredContent'];br=bb['normalized_result'];assert f['subject']['digest']['sha256']==sha(raw);assert br['complete'] and br['returned_bytes']==len(raw) and int(br['address'],16)==start and bytes.fromhex(br['bytes_hex'])==raw
   addresses=[int(x.split(':',1)[0],16) for x in f['normalized_result']['assembly']]; assert len(addresses)==len(set(addresses)) and all(a in words for a in addresses)
  row={'entry':r['entry'],'attempt_directory':str(base.relative_to(R)),'derivation':p.name,'length':len(raw),'original_native_words':len(words),'source_and_raw_and_native_words_equal':True,'rea_success':success,'rea_readback_exact':success,'rea_instruction_addresses':len(addresses),'function_evidence_id':f['evidence_id'] if f else None,'readback_evidence_id':bb['evidence_id'] if bb else None,'outcomes':out,'pins':pins}
  rows.append(row)
  if not success:attempts.append(row)
link=json.loads((B/'final-linkage.json').read_text()); assert link['source_sha256']==digest
spans=[]
def walk(x):
 if isinstance(x,dict):
  if 'source_file_offset'in x and 'bytes_hex'in x:
   raw=bytes.fromhex(x['bytes_hex']);o=x['source_file_offset'];assert data[o:o+len(raw)]==raw
   if 'address'in x:assert original(int(x['address'],16),len(raw))==(o,raw)
   if 'sha256'in x:assert sha(raw)==x['sha256']
   if 'slot'in x and 'vtable'in x:assert int(x['address'],16)==int(x['vtable'],16)+int(x['slot'],16) and struct.unpack('<Q',raw)[0]==int(x['target'],16)
   spans.append({'source_file_offset':o,'length':len(raw),'sha256':sha(raw)})
  for v in x.values():walk(v)
 elif isinstance(x,list):
  for v in x:walk(v)
walk(link)
assert sha(source.read_bytes())==digest
unique={r['entry']:r for r in rows}
report={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'Independent byte/readback/outcome audit of all seven root list derivations and isolated retry. No target execution or native behavior comparison.','source_sha256':digest,'unique_functions':len(unique),'attempts':len(rows),'unique_source_bytes':sum(r['length'] for r in unique.values()),'unique_native_words':sum(r['original_native_words'] for r in unique.values()),'successful_unique_rea_instructions':sum(r['rea_instruction_addresses'] for r in unique.values()),'failed_attempt_count':len(attempts),'failed_attempts':[{'entry':r['entry'],'derivation':r['derivation'],'attempt_directory':r['attempt_directory'],'failed_outputs':[k for k,v in r['outcomes'].items() if v.get('isError')]} for r in attempts],'all_unique_functions_have_successful_attempt':all(r['rea_success']for r in unique.values()),'functions':rows,'derivation_pins':derivation_pins,'linkage':{'pin':pin(B/'final-linkage.json'),'checked_spans':len(spans),'spans':spans},'limits':['Instruction-address coverage is provider-decoded coverage, not all LC_FUNCTION_STARTS interval words; omitted disconnected tails remain original native evidence.','Raw-slice types and external-call semantics require separate concrete linkage. A successful query is not a runtime equivalence claim.','Original failed attempt is retained and never counted as successful.']}
(H/'peer-byte-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k]for k in ['unique_functions','attempts','unique_source_bytes','unique_native_words','successful_unique_rea_instructions','failed_attempt_count','failed_attempts','all_unique_functions_have_successful_attempt']}))
