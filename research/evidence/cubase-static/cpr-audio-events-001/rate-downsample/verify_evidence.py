from pathlib import Path
import hashlib,json,re,struct
H=Path(__file__).resolve().parent;ROOT=H.parents[4];P=H.parent/'rate-converter'
REUSE=['10030a008','10030c4a4','10030de00','10030ffb0','10030a534','10030a3bc']
def ev(p):
 d=json.loads(p.read_text());assert not d.get('isError',False),str(p);return d.get('structuredContent')or json.loads(d['content'][0]['text'])
new=json.loads((H/'pass1/derivation.json').read_text());source=Path(new['source']);b=source.read_bytes();assert hashlib.sha256(b).hexdigest()==new['source_sha256']
items=[(H/'pass1',r,False,H/'pass1/derivation.json')for r in new['derivatives']]
for id in REUSE:
 found=[]
 for mf in [P/'derivation.json']+[P/f'derivation-pass{i}.json'for i in range(2,13)]:
  m=json.loads(mf.read_text());found.extend((P,r,True,mf)for r in m['derivatives']if r['entry']=='0x'+id)
 assert len(found)==1,id;items+=found
M=H.parent/'rate-samples/pass1';mf=M/'derivation.json';m=json.loads(mf.read_text())
for id in ['10030c5b8','10030c5c8','10030c620','10030c664','10030c66c']:
 r,=[r for r in m['derivatives']if r['entry']=='0x'+id];items.append((M,r,True,mf))
rows=[]
for p,r,reuse,mf in items:
 a=int(r['entry'],16);id=r['entry'][2:];raw=(p/r['raw_file']).read_bytes();n=r['length'];assert raw==b[r['source_file_offset']:r['source_file_offset']+n]and hashlib.sha256(raw).hexdigest()==r['raw_sha256']
 nativefile=r.get('native_file',r.get('original_native_disassembly'));native=(p/nativefile).read_text();assert hashlib.sha256(native.encode()).hexdigest()==r.get('native_sha256',r.get('native_stdout_sha256'))
 words={int(x,16):int(w,16)for x,w in re.findall(r'^([0-9a-f]+):\s+([0-9a-f]{8})\s',native,re.M)};assert len(words)==n//4
 for loc,w in words.items():assert struct.unpack_from('<I',raw,loc-a)[0]==w
 rb=ev(p/f'bytes-{id}.json')['raw_result'];assert rb['complete']and rb['returned_bytes']==n and bytes.fromhex(rb['bytes_hex'])==raw
 f=ev(p/f'function-{id}.json');v=f['raw_result']['value'];pcs=[int(x.split(':')[0],16)for x in v['assembly']];assert len(set(pcs))==len(pcs)and all(x in words for x in pcs)
 bu=ev(p/f'bundle-{id}.json');ev(p/f'close-{id}.json');assert(p/f'snapshot-{id}.json').exists()
 rows.append(dict(entry=r['entry'],directory=str(p.relative_to(ROOT)),derivation=str(mf.relative_to(ROOT)),reused=reuse,raw_sha256=r['raw_sha256'],source_bytes=n,native_words=len(words),rea_instruction_addresses=len(pcs),evidence_ids=[z['evidence_id']for z in bu['result']['records']],warnings=[z for z in v['pseudocode'].splitlines()if'WARNING'in z]))
assert 'CLOSED: isolated raw-slice MCP session'in(H/'pass1/analysis-progress.log').read_text()
totals={}
for label,group in [('new',[x for x in rows if not x['reused']]),('reused',[x for x in rows if x['reused']]),('all',rows)]:totals[label]=dict(functions=len(group),source_bytes=sum(x['source_bytes']for x in group),native_words=sum(x['native_words']for x in group),rea_instruction_addresses=sum(x['rea_instruction_addresses']for x in group),records=sum(len(x['evidence_ids'])for x in group))
out=dict(source_sha256=new['source_sha256'],functions=rows,totals=totals,passed=True,target_execution=False,scope='Original bytes, exact REA memory readbacks, native words and REA address custody; semantic and runtime equivalence not inferred.')
(H/'verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(totals))
