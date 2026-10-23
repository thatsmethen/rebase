"""Recheck reused source functions without another decompiler import or target execution."""
from pathlib import Path
import hashlib,json,re,struct
h=Path(__file__).resolve().parent;r=h.parents[4]
source=r/'research/targets/derived/Cubase15-arm64';data=source.read_bytes();expected='dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb';assert hashlib.sha256(data).hexdigest()==expected
requests=[('cpr-audio-events-001/audible-state/'+p,a) for p,a in [('pass3','100300eb0'),('pass3','1000eaf54'),('pass3','1000eaf6c'),('pass8','10073b9cc'),('pass14','1000edb70'),('pass15','1000e8b84'),('pass15','1000e9148')]]+[('cpr-map-clock-001/attributes/pass3','101700aac'),('cpr-map-clock-001/variation/pass2','103105d1c')]
def ev(p):
 d=json.loads(p.read_text());assert not d.get('isError',False),str(p);return d.get('structuredContent') or json.loads(d['content'][0]['text'])
def pin(p):return {'path':str(p.relative_to(r)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
rows=[]
for directory,a in requests:
 b=r/'research/evidence/cubase-static'/directory
 ms=[(p,json.loads(p.read_text())) for p in b.glob('derivation*.json')]
 matches=[(p,row) for p,m in ms for row in m['derivatives'] if int(row['entry'],16)==int(a,16)]
 assert len(matches)==1,(a,len(matches));mp,row=matches[0];raw=(b/row['raw_file']).read_bytes();assert raw==data[row['source_file_offset']:row['source_file_offset']+row['length']] and hashlib.sha256(raw).hexdigest()==row['raw_sha256']
 rb=ev(b/f'bytes-{a}.json')['raw_result'];assert rb['complete'] and bytes.fromhex(rb['bytes_hex'])==raw
 nt=b/f'native-{a}.txt';words={int(x,16):int(w,16) for x,w in re.findall(r'^([0-9a-f]+):\s+([0-9a-f]{8})\s',nt.read_text(),re.M)};assert len(words)==len(raw)//4
 for loc,w in words.items():assert struct.unpack_from('<I',raw,loc-int(a,16))[0]==w
 v=ev(b/f'function-{a}.json')['raw_result']['value'];locs=[int(x.split(':')[0],16) for x in v['assembly']];assert all(x in words for x in locs)
 bundle=ev(b/f'bundle-{a}.json');ids=[x['evidence_id'] for x in bundle['result']['records']]
 rows.append({'entry':'0x'+a,'source_bytes':len(raw),'native_words':len(words),'rea_instruction_addresses':len(locs),'readback_exact':True,'evidence_ids':ids,'pins':[pin(p) for p in [mp,b/row['raw_file'],nt,b/f'function-{a}.json',b/f'bytes-{a}.json',b/f'bundle-{a}.json',b/f'close-{a}.json',b/f'snapshot-{a}.json']]})
result={'scope':'Reused evidence verified against original linked image and readback; no new import or target execution. Distinct from newly captured functions listed in verification.json.','source_sha256':expected,'functions':rows,'totals':{'functions':len(rows),'bytes':sum(x['source_bytes'] for x in rows),'native_words':sum(x['native_words'] for x in rows),'rea_instruction_addresses':sum(x['rea_instruction_addresses'] for x in rows)},'passed':True}
(h/'support-verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result['totals']))
