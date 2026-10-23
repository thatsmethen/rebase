from pathlib import Path
import hashlib,json,re,struct
H=Path(__file__).resolve().parent;ROOT=H.parents[4]
def ev(p):
 d=json.loads(p.read_text());assert not d.get('isError',False),str(p);return d.get('structuredContent')or json.loads(d['content'][0]['text'])
reused=[('event-rendering/pass7','1001f91a0'),('event-rendering/pass8','1001f96f8'),('event-rendering/pass8','1001f9854'),('event-rendering/pass9','1001fd4e4'),('event-rendering/pass2','10011376c'),('event-rendering/pass3','101a181b0'),('event-rendering/pass4','1002115a0')]
items=[]
for p in sorted(H.glob('pass*')):
 if p.is_dir():
  d=json.loads((p/'derivation.json').read_text());items.extend((p,r,False)for r in d['derivatives'])
for path,id in reused:
 p=H.parent/path;d=json.loads((p/'derivation.json').read_text());r,=[r for r in d['derivatives']if r['entry']=='0x'+id];items.append((p,r,True))
rows=[];ids=[];source_cache={}
for p,r,reuse in items:
 m=json.loads((p/'derivation.json').read_text());source=Path(m['source']);key=str(source)
 if key not in source_cache:
  source_cache[key]=source.read_bytes();assert hashlib.sha256(source_cache[key]).hexdigest()==m['source_sha256']
 b=source_cache[key];a=int(r['entry'],16);id=r['entry'][2:];raw=(p/r['raw_file']).read_bytes();n=r['length'];assert raw==b[r['source_file_offset']:r['source_file_offset']+n]and hashlib.sha256(raw).hexdigest()==r['raw_sha256']
 rb=ev(p/f'bytes-{id}.json')['raw_result'];assert rb['complete']and rb['returned_bytes']==n and bytes.fromhex(rb['bytes_hex'])==raw
 native=(p/r['original_native_disassembly']).read_text();assert hashlib.sha256(native.encode()).hexdigest()==r['native_stdout_sha256']
 words={int(a,16):int(w,16)for a,w in re.findall(r'^([0-9a-f]+):\s+([0-9a-f]{8})\s',native,re.M)};assert len(words)==n//4
 for loc,w in words.items():assert struct.unpack_from('<I',raw,loc-a)[0]==w
 e=ev(p/f'function-{id}.json');v=e['raw_result']['value'];locs=[int(z.split(':')[0],16)for z in v['assembly']];assert len(set(locs))==len(locs)and all(x in words for x in locs)
 bu=ev(p/f'bundle-{id}.json');ev(p/f'close-{id}.json');assert(p/f'snapshot-{id}.json').exists();records=bu['result']['records'];ids.extend(z['evidence_id']for z in records)
 assert'CLOSED: isolated raw-slice MCP session'in(p/'analysis-progress.log').read_text()
 rows.append(dict(entry=r['entry'],directory=str(p.relative_to(ROOT)),reused=reuse,source_bytes=n,raw_sha256=r['raw_sha256'],native_words=len(words),rea_instruction_addresses=len(locs),readback_exact=True,evidence_ids=[z['evidence_id']for z in records],warnings=[z for z in v['pseudocode'].splitlines()if'WARNING'in z]))
assert len(set(ids))==len(ids)
totals={}
for label,group in [('new',[r for r in rows if not r['reused']]),('reused',[r for r in rows if r['reused']]),('all',rows)]:totals[label]=dict(functions=len(group),source_bytes=sum(r['source_bytes']for r in group),native_words=sum(r['native_words']for r in group),rea_instruction_addresses=sum(r['rea_instruction_addresses']for r in group),records=sum(len(r['evidence_ids'])for r in group))
out=dict(source_sha256=m['source_sha256'],functions=rows,totals=totals,passed=True,target_execution=False,scope='Original bytes/readbacks/native word and REA instruction-address custody; not executed semantics. External calls/unwind/disconnected tails remain raw context losses.')
(H/'verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(totals))
