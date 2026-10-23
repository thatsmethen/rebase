"""Correlate native record widths with structurally reached original template payloads."""
import json,hashlib,struct
from pathlib import Path
P=Path(__file__).resolve().parent;ROOT=P.parents[3]
contract=ROOT/'research/evidence/cubase-static/cpr-objects-001/fixtures/structural-contract-v2.json'
def sha(d):return hashlib.sha256(d).hexdigest()
def walk(x):
 if isinstance(x,dict):
  if x.get('class')=='MSignatureTrackEvent' and 'body_offset' in x:yield x
  for v in x.values():yield from walk(v)
 elif isinstance(x,list):
  for v in x:yield from walk(v)
rows=[]
for row in json.loads(contract.read_text())['records']:
 source=ROOT/row['source'];data=source.read_bytes();assert sha(data)==row['source_sha256']
 probe=ROOT/row['probe_output'];assert sha(probe.read_bytes())==row['probe_output_sha256']
 objects=list(walk(json.loads(probe.read_text())));unique={o['body_offset']:o for o in objects}
 for obj in unique.values():
  off,n=obj['body_offset'],obj['body_bytes'];raw=data[off:off+n];assert sha(raw)==obj['body_sha256']
  assert obj['version']==3
  count=struct.unpack_from('>i',raw)[0];assert 0<count<=10000 and 4+16*count<=n
  fields=[]
  for i in range(count):
   at=4+i*16;values=struct.unpack_from('>ihhhhhh',raw,at)
   fields.append({'source_file_offset':off+at,'serialized_position_i32':values[0],'pair_i16':list(values[1:3]),'extra_i16':list(values[3:]),'bytes_hex':raw[at:at+16].hex()})
  attrs_at=4+16*count
  rows.append({'source':row['source'],'source_sha256':row['source_sha256'],'probe':row['probe_output'],'probe_sha256':row['probe_output_sha256'],'object':obj,'count_i32':count,'records':fields,'attributes_file_offset':off+attrs_at,'attributes_byte_count':n-attrs_at,'prefix_hex':raw[:attrs_at].hex(),'first_attribute_count_i32':struct.unpack_from('>i',raw,attrs_at)[0],'limits':['Only record framing derived from native reader; attributes are retained opaque here and may carry replacement event state.','No time-coordinate unit or active signature-map inference is made from a matching4/4 prefix.']})
report={'source_contract':str(contract.relative_to(ROOT)),'source_contract_sha256':sha(contract.read_bytes()),'records':rows,'template_count':len(rows),'all_original_source_and_payload_hashes_match':True,'target_execution':False}
(P/'fixture-record-correlation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'templates':len(rows),'values':[{'name':Path(r['source']).name,'count':r['count_i32'],'pair':r['records'][0]['pair_i16'],'extra':r['records'][0]['extra_i16'],'attribute_count':r['first_attribute_count_i32']}for r in rows]}))
