"""Pin the two existing structural decodes to original bytes; no target execution.
This deliberately is a fixture projection, not a general CPR parser or runtime oracle.
"""
from pathlib import Path
import hashlib,json,struct,math
P=Path(__file__).resolve().parent;R=P.parents[4]
H=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
B=lambda v:struct.pack('>d',v).hex()
rows=[]
for name in ['lofi-hip-hop','classic-house']:
 f=R/f'research/evidence/cubase-static/cpr-objects-001/fixtures/{name}-v09.json'
 d=json.loads(f.read_text());src=R/d['source'];raw=src.read_bytes();assert H(src)==d['sha256']
 root=d['roots'][1]['decoded']['root'];track=root['track_list']['decoded']['children'][2]
 assert track['class']=='MAudioTrackEvent' and track['version']==1
 node=track['node'];ev,=node['decoded']['children'];assert ev['class']=='MAudioEvent'and ev['version']==6
 clip=ev['audio_clip'];nd=clip['decoded_node_prefix'];prefix=[]
 for obj,label in [(root,'root'),(track,'audio_track'),(ev,'audio_event')]:
  o=obj['body_offset'];chunk=raw[o:o+26];values=struct.unpack('>Hddd',chunk)
  if 'event_prefix_hex'in obj:assert chunk.hex()==obj['event_prefix_hex']
  else:assert obj['event_prefix']['offset']==o
  prefix.append(dict(role=label,source_offset=o,bytes_hex=chunk.hex(),word=values[0],start=values[1],length=values[2],offset=values[3],double_bits=[chunk[i:i+8].hex()for i in (2,10,18)]))
 do=nd['datum_offset'];tag=struct.unpack_from('>i',raw,do)[0];assert tag==nd['datum_type']
 scalar=None
 if tag==10:
  scalar=struct.unpack_from('>d',raw,do+4)[0];assert scalar==nd['datum']['scalar']
  length=prefix[-1]['length'];product=scalar*length;canonical=product/1.0
  projection=dict(position_seconds=0.0,offset_seconds=0.0,duration_seconds=canonical,duration_bits=B(canonical),operations=['f64(storedScalar * rawLength)','f64(product / 1.0)'],scalar_bits=B(scalar),reciprocal_of_44100_matches_bits=B(1.0/44100.0)==B(scalar),note='Analytical serialized-source projection, not a Cubase measurement; runtime rate refresh and host transformations are separate boundaries.')
 else:projection=dict(accepted=False,reason='Own clip datum is musical type0; type10 source-coordinate gate excludes it. No sample interpretation inferred from raw length.')
 assert all(r['double_bits'][0]=='0000000000000000'and r['double_bits'][2]=='0000000000000000'for r in prefix)
 rows.append(dict(name=name,source=str(src.relative_to(R)),source_sha256=H(src),structural_decode=str(f.relative_to(R)),structural_decode_sha256=H(f),ancestry=prefix,track_name=node['decoded']['name']['text'],track_datum=node['decoded']['datum'],clip_identity=clip['size_offset'],clip_datum=dict(offset=do,type=tag,bytes_hex=raw[do:do+12].hex(),scalar=scalar),projection=projection))
result=dict(schema_version=1,target_executed=False,scope='Pinned source-coordinate comparison; only direct counted audio event ancestry is projected, no broad source parser.',fixtures=rows)
(P/'fixture-projection.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps([dict(name=x['name'],projection=x['projection'])for x in rows],indent=2))
