"""Finalize static custody checks using retained evidence; no target execution."""
import hashlib,json,struct,datetime
from pathlib import Path
H=Path(__file__).resolve().parent; R=H.parents[4]; S=R/'research/targets/derived/Cubase15-arm64'
sha=lambda b:hashlib.sha256(b).hexdigest()
def pin(p):return {'path':str(p.relative_to(R)),'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())}
data=S.read_bytes();digest=sha(data);assert digest=='dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb'
pos=32;segments=[]
for _ in range(struct.unpack_from('<I',data,16)[0]):
 cmd,size=struct.unpack_from('<II',data,pos)
 if cmd==0x19:
  v=struct.unpack_from('<II16sQQQQIIII',data,pos);segments.append({'address':v[3],'offset':v[5],'size':v[6]})
 pos+=size
def original(a,n):
 sg,=[x for x in segments if x['address']<=a and a+n<=x['address']+x['size']];o=sg['offset']+a-sg['address'];return o,data[o:o+n]
rows=[];diffs=[];sessions=[]
for p in sorted(H.rglob('verification.json')):
 v=json.loads(p.read_text());assert v['passed'] and v['source_sha256']==digest
 der=json.loads((p.parent/'derivation.json').read_text());by={r['entry']:r for r in der['derivatives']}
 for f in v['functions']:
  e=f['entry'][2:];r=by[f['entry']];raw=(p.parent/r['raw_file']).read_bytes();assert sha(raw)==r['raw_sha256'];off,ob=original(int(f['entry'],16),len(raw));assert off==r['source_file_offset']and ob==raw
  ids=[]
  for kind in ['open','function','bytes','bundle','close']:
   q=p.parent/f'{kind}-{e}.json';w=json.loads(q.read_text());assert not w.get('isError'),q
   if kind in ['function','bytes']:
    ids.append(w['structuredContent']['evidence_id'])
   if kind=='bytes':assert bytes.fromhex(w['structuredContent']['normalized_result']['bytes_hex'])==raw
   if kind=='close':assert Path(w['structuredContent']['result']['path']).is_file()
  for q in f['mnemonic_differences']:
   a=q['rea_assembly'].split()[0].lower();b=q['native_assembly'].split()[0].lower()
   assert (a,b)in [('movi','movi.2d'),('b.cs','b.hs')],q
   diffs.append({**q,'interpretation':'Known rendering alias only; exact instruction word independently equal.'})
  rows.append({'entry':f['entry'],'bytes':len(raw),'original_words':f['native_interval_instruction_count'],'rea_addresses':f['rea_body_instruction_count'],'evidence_ids':ids,'verification':pin(p),'raw':pin(p.parent/r['raw_file']),'dossier':pin(p.parent/f'function-{e}.json'),'readback':pin(p.parent/f'bytes-{e}.json'),'close':pin(p.parent/f'close-{e}.json'),'omitted_native_addresses':f['omitted_native_instruction_addresses'],'pseudocode_warnings':f['pseudocode_warnings']})
 log=p.parent/'analysis-progress.log';assert 'CLOSED: isolated raw-slice MCP session'in log.read_text();sessions.append({'directory':str(p.parent.relative_to(R)),'close_log':pin(log),'closed':True})
assert len({r['entry']for r in rows})==len(rows)
peer=json.loads((H/'peer-byte-audit.json').read_text());pin_count=0
for r in peer['functions']:
 for p in r['pins']:
  q=R/p['path'];assert q.stat().st_size==p['bytes']and sha(q.read_bytes())==p['sha256'];pin_count+=1
for p in peer['derivation_pins']+[peer['linkage']['pin']]:assert sha((R/p['path']).read_bytes())==p['sha256'];pin_count+=1
support=json.loads((H/'supporting-evidence-checks-v2.json').read_text())
for r in support['functions']:
 assert r['rea_analysis_and_readback_success']
 for p in r['pins']:assert sha((R/p['path']).read_bytes())==p['sha256'];pin_count+=1
rootbundle=H.parent/'list/list-evidence-bundle.json';rb=json.loads(rootbundle.read_text());assert len(rb['records'])==90
imp=H.parent/'list/evidence-import.json';ri=json.loads(imp.read_text());assert not ri.get('isError')and ri['structuredContent']['result']['imported']==90
bundle=H/'closure-evidence-bundle-v2.json';b=json.loads(bundle.read_text());assert len(b['records'])==82
imp2=H/'closure-evidence-import-v2.json';i=json.loads(imp2.read_text());assert not i.get('isError')and i['structuredContent']['result']['imported']==82
assert 'CLOSED: evidence import session'in(H/'closure-import-progress-v2.log').read_text()
result={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'Original source, all retained local query outcomes/readbacks, peer audit pins and canonical imports; not runtime equivalence.','source':pin(S),'new_unique_functions':len(rows),'new_source_bytes':sum(r['bytes']for r in rows),'new_original_words':sum(r['original_words']for r in rows),'new_rea_addresses':sum(r['rea_addresses']for r in rows),'mnemonic_aliases':diffs,'mnemonic_semantic_discrepancies':0,'functions':rows,'sessions':sessions,'peer_pins_rechecked':pin_count,'root_unique_functions':peer['unique_functions'],'root_unique_bytes':peer['unique_source_bytes'],'root_original_words':peer['unique_native_words'],'root_rea_addresses':peer['successful_unique_rea_instructions'],'failed_root_attempts_preserved':peer['failed_attempts'],'supporting_reused_functions':len(support['functions']),'canonical_imports':[{'records':90,'bundle':pin(rootbundle),'import':pin(imp)},{'records':82,'bundle':pin(bundle),'import':pin(imp2)}],'no_target_execution':True,'limits':['Raw imported boundaries can omit disconnected exception tails; exact native ranges retained separately.','The original failed factory query remains failed. Retry success applies only to its separate wrapper.','External environment, arbitrary registered providers and observers are not certified by these checks.']}
assert sha(S.read_bytes())==digest
(H/'final-verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:result[k]for k in ['new_unique_functions','new_source_bytes','new_original_words','new_rea_addresses','root_unique_functions','supporting_reused_functions','mnemonic_semantic_discrepancies']}))
