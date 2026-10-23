"""Independently compare REA raw-slice bytes and addresses to original Mach-O."""
from pathlib import Path
import hashlib,json,re,struct,datetime
here=Path(__file__).resolve().parent
manifests=[json.loads((here/'derivation.json').read_text())]
source=Path(manifests[0]['source']);data=source.read_bytes();assert hashlib.sha256(data).hexdigest()==manifests[0]['source_sha256']
def evidence(path):
 o=json.loads(path.read_text());assert not o.get('isError',False)
 return o.get('structuredContent') or json.loads(o['content'][0]['text'])
rows=[]
for m in manifests:
 for row in m['derivatives']:
  address=int(row['entry'],16); key=row['entry'][2:];raw=(here/row['raw_file']).read_bytes();n=row['length'];off=row['source_file_offset']
  assert len(raw)==n and raw==data[off:off+n]
  assert hashlib.sha256(raw).hexdigest()==row['raw_sha256']
  read=evidence(here/f'bytes-{key}.json');rr=read['raw_result']
  assert rr['complete'] and rr['returned_bytes']==n and bytes.fromhex(rr['bytes_hex'])==raw
  native=(here/row['native_file']).read_text();words={int(a,16):int(w,16) for a,w in re.findall(r'^([0-9a-f]+):\s+([0-9a-f]{8})\s',native,re.M)}
  assert len(words)==n//4
  for a,w in words.items():assert struct.unpack_from('<I',raw,a-address)[0]==w
  f=evidence(here/f'function-{key}.json');v=f['raw_result']['value'];asm=v['assembly'];locations=[int(s.split(':')[0],16) for s in asm]
  assert all(a in words for a in locations) and len(set(locations))==len(locations)
  bundle=json.loads((here/f'bundle-{key}.json').read_text());assert not bundle.get('isError',False)
  close=json.loads((here/f'close-{key}.json').read_text());assert not close.get('isError',False)
  assert (here/f'snapshot-{key}.json').exists()
  rows.append({'entry':row['entry'],'bytes':n,'sha256':row['raw_sha256'],'readback_exact':True,'native_words_checked':len(words),'rea_instruction_addresses_in_original':len(locations),'decompiler_warnings':[line for line in v['pseudocode'].splitlines() if 'WARNING' in line],'scope':'Original source bytes/readback/LLVM words match. This does not establish external types, globals, target execution, or complete semantic recovery.'})
report={'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source':str(source),'source_sha256':hashlib.sha256(data).hexdigest(),'functions':rows,'total_bytes':sum(r['bytes'] for r in rows),'target_executed':False,'passed':True}
(here/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'functions':len(rows),'bytes':report['total_bytes'],'native_words':sum(r['native_words_checked'] for r in rows),'rea_addresses':sum(r['rea_instruction_addresses_in_original'] for r in rows),'passed':True}))
