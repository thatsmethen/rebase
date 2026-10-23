"""Native-reader-guided, bounded serialized-field observations; no target execution."""
import hashlib, importlib.util, json, struct
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
spec=importlib.util.spec_from_file_location('pinned_probe',ROOT/'research/evidence/cubase-static/cpr-signature-001/fixtures/cpr-probe-v09-generation.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
def digest(b):return hashlib.sha256(b).hexdigest()
def walk(x):
 if isinstance(x,dict):
  yield x
  for y in x.values():yield from walk(y)
 elif isinstance(x,list):
  for y in x:yield from walk(y)
rows=[]
for name in ['classic-house','lofi-hip-hop']:
 fixture=ROOT/f'research/evidence/cubase-static/cpr-objects-001/fixtures/{name}-v09.json'
 j=json.loads(fixture.read_text());data=(ROOT/j['source']).read_bytes();assert digest(data)==j['sha256']
 event,=[x for x in walk(j) if x.get('kind')=='object' and x.get('class')=='MAudioEvent'];clip=event['audio_clip']
 archive_origin=event['size_offset']-event['relative_object_identity'];a=p.Archive(data,archive_origin,len(data))
 for x in walk(j):
  if x.get('kind')=='object':
   a.objects[x['relative_object_identity']]=x
   for decl in x['declarations']:a.classes[decl['relative_offset']]=decl
 fields=[]
 def number(r,fmt,target,label):
  at=r.pos;v=r.number(fmt);b=data[at:r.pos];fields.append({'offset':at,'end':r.pos,'hex':b.hex(),'sha256':digest(b),'format':fmt,'value':v,'target_field':target,'native_named_writer_label':label});return v
 r=p.Reader(data,clip['end'],event['end'])
 count=number(r,'I','event+0x20 attribute collection','Additional Attributes');assert count==0
 number(r,'i','event+0x80','Priority')
 fade_in=a.object(r);fade_out=a.object(r);assert fade_in['kind']==fade_out['kind']=='null'
 number(r,'d','event+0x78','SnapPoint')
 description=r.string()
 number(r,'i','event+0x84 initial read','Lane')
 number(r,'f','event+0x58','Volume')
 number(r,'i','event+0x84 v>3 overwrite','Lane')
 number(r,'H','event+0xa0 serialized u16->bool','Inverted')
 curve=a.object(r);assert curve['class']=='VolumeCurveDataNode' and curve['version']==0
 q=a.body(curve);cn=q.string();dt=q.number('i');datum_at=q.pos
 if dt in (0,17):datum={'type':dt,'objects':[a.object(q),a.object(q)]}
 elif dt in (1,10):datum={'type':dt,'value':q.number('d')}
 else:raise ValueError('unsupported curve datum')
 curve_count_at=q.pos;cc=q.number('I');assert cc==0 and q.pos==q.end and r.pos==r.end
 cr=p.Reader(data,clip['opaque_tail_offset'],clip['end']);history_word_at=cr.pos;history_word=cr.number('H');history_count=cr.number('i');assert cr.pos==cr.end and history_word==1 and history_count==0
 rows.append({'fixture':{'path':str(fixture.relative_to(ROOT)),'sha256':digest(fixture.read_bytes())},'source':{'path':j['source'],'sha256':j['sha256'],'bytes':len(data)},'archive_origin':archive_origin,'event':{'body_offset':event['body_offset'],'end':event['end'],'body_sha256':event['body_sha256'],'prefix':event['event_prefix'],'tail_offset':clip['end'],'tail_sha256':digest(data[clip['end']:event['end']]),'fields':fields,'fade_in':fade_in,'fade_out':fade_out,'description':description,'volume_curve':{'object':curve,'name':cn,'datum_offset':datum_at,'datum':datum,'count_offset':curve_count_at,'count':cc,'exact_body_consumption':True},'exact_tail_consumption':True},'clip':{'body_offset':clip['body_offset'],'end':clip['end'],'body_sha256':clip['body_sha256'],'edit_history':{'offset':history_word_at,'end':cr.pos,'hex':data[history_word_at:cr.pos].hex(),'sha256':digest(data[history_word_at:cr.pos]),'list_word':history_word,'count':history_count,'exact_tail_consumption':True},'named_attributes':clip['descriptor_suffix']['attributes']}})
out={'scope':'Observed source fields under the retained v6 event/v4 clip reader ordering, with native named-writer labels. Names are not playback/DSP equivalence. Existing shared probe is reused only for bounded archive/string framing.','fixtures':rows,'limits':['No source audio decoded or target code executed.','Empty fade objects and zero point/history counts are serialized facts; surrounding default initialization, clip transforms, event callbacks and host processing remain separate.','No phase, mute, gain, warp or loop playback result is inferred solely from labels.','The event prefix flags are masked with native0x585a; zero source word does not independently establish all constructor/runtime flags.']}
(HERE/'fixture-fields.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({'fixtures':len(rows),'exact_event_tail_bytes':sum(x['event']['end']-x['event']['tail_offset'] for x in rows),'clip_tail_bytes':12}))
