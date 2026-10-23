from pathlib import Path
import hashlib,json,re,struct,datetime
h=Path(__file__).resolve().parent;rows=[];src=None;ids=[]
def ev(p):
 d=json.loads(p.read_text());assert not d.get('isError',False),str(p);return d.get('structuredContent') or json.loads(d['content'][0]['text'])
for base in sorted(h.glob('pass*'),key=lambda p:int(p.name[4:])):
 if not base.is_dir():continue
 m=json.loads((base/'derivation.json').read_text());source=Path(m['source']);b=source.read_bytes();assert hashlib.sha256(b).hexdigest()==m['source_sha256'];src={'path':str(source),'sha256':m['source_sha256']}
 for r in m['derivatives']:
  a=int(r['entry'],16);id=r['entry'][2:];raw=(base/r['raw_file']).read_bytes();n=r['length'];assert raw==b[r['source_file_offset']:r['source_file_offset']+n] and hashlib.sha256(raw).hexdigest()==r['raw_sha256']
  rb=ev(base/f'bytes-{id}.json')['raw_result'];assert rb['complete'] and rb['returned_bytes']==n and bytes.fromhex(rb['bytes_hex'])==raw
  native=(base/r['original_native_disassembly']).read_text();words={int(x,16):int(w,16) for x,w in re.findall(r'^([0-9a-f]+):\s+([0-9a-f]{8})\s',native,re.M)};assert len(words)==n//4
  for loc,w in words.items():assert struct.unpack_from('<I',raw,loc-a)[0]==w
  e=ev(base/f'function-{id}.json');v=e['raw_result']['value'];locs=[int(s.split(':')[0],16) for s in v['assembly']];assert len(set(locs))==len(locs) and all(x in words for x in locs)
  bu=ev(base/f'bundle-{id}.json');cl=ev(base/f'close-{id}.json');assert (base/f'snapshot-{id}.json').exists();recs=bu['result']['records'];ids.extend(x['evidence_id'] for x in recs)
  rows.append({'entry':r['entry'],'directory':str(base.relative_to(h)),'source_bytes':n,'source_range_sha256':r['raw_sha256'],'native_words':len(words),'rea_instruction_addresses':len(locs),'readback_exact':True,'evidence_ids':[x['evidence_id'] for x in recs],'warnings':[s for s in v['pseudocode'].splitlines() if 'WARNING' in s]})
 assert 'CLOSED: isolated raw-slice MCP session' in (base/'analysis-progress.log').read_text()
result={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source':src,'functions':rows,'totals':{'functions':len(rows),'source_bytes':sum(r['source_bytes'] for r in rows),'native_words':sum(r['native_words'] for r in rows),'rea_instruction_addresses':sum(r['rea_instruction_addresses'] for r in rows),'unique_evidence_ids':len(set(ids))},'passed':True,'target_execution':False,'scope':'Exact-byte readback and original instruction-word/address verification only. Disconnected raw-slice tails/external data and whole-host runtime semantics remain distinct.'}
(h/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result['totals']))
