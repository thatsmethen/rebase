"""Original-image linkage only; no target code execution."""
from pathlib import Path
import sys,json,struct,hashlib
h=Path(__file__).resolve().parent;r=h.parents[4]
helper=r/'research/evidence/cubase-static/cpr-map-clock-001/attributes/source_tools.py'
sys.path.insert(0,str(helper.parent));import source_tools as s
rows=[]
for name,a in [('MAudioEvent.eventClip',0x10442e898+0x258),('MAudioEvent.inverted',0x10442e898+0x500),('curveAdapter.count',0x104435d30+0x38),('auditionManager.init',0x1046b2610+0x20),('auditionManager.consume',0x1046b2610+0x78),('auditionStreamPlayer.volume',0x1046b2f50+0x38),('auditionStreamPlayer.volumeCurve',0x1046b2f50+0x40),('auditionStreamPlayer.streamInterface',0x1046b2f50+0x68),('factoryFunctor.dispatch',0x1046af8b8+0x30)]:
 v=s.region(a,8);v.update(name=name,pointer=hex(struct.unpack('<Q',bytes.fromhex(v['bytes_hex']))[0]));rows.append(v)
literals=[]
for a in [0x1038973ad,0x1038973b7,0x1038973c5,0x103892045,0x10389225a,0x1038a5779,0x10388ecc4,0x10388ecd0]:
 raw=bytes.fromhex(s.region(a,100)['bytes_hex']).split(b'\0')[0];v=s.region(a,len(raw)+1);v['ascii']=raw.decode('ascii');literals.append(v)
spans=[]
for name,a,e in [('selector ordered local layers',0x10021225c,0x1002124e4),('curve count and conditional wrapper',0x1002125e0,0x1002126a4),('inverted field getter',0x1000eaf6c,0x1000eaf74),('factor default key46746950',0x1000eae1c,0x1000eae68),('factor default key46727453',0x1000edb70,0x1000edbbc),('processing predicate checks',0x1002bb194,0x1002bb3ac),('factory nil gate',0x1002bae6c,0x1002bae90),('factory nil return',0x1002baf84,0x1002bafc0),('configuration request flags',0x1002bf008,0x1002bf0b8),('pre/post replacement gates',0x100464308,0x100464348),('missing attribute builds empty string',0x100427450,0x1004274cc),('empty string representation',0x102221d24,0x102221d44),('curve count',0x1001104c0,0x1001104d0),('cluster single-segment creation',0x100369330,0x1003693e4),('audition gain FMUL ordering',0x1019808e8,0x101980a20)]:
 v=s.region(a,e-a);v['name']=name;spans.append(v)
result={'source_sha256':'dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb','method':'LC_SEGMENT mapped original cells/literals/instruction spans. Concrete receiver bindings are established by the cited constructors; primary RTTI candidate scans alone do not establish callers.','helper':{'path':str(helper.relative_to(r)),'sha256':hashlib.sha256(helper.read_bytes()).hexdigest()},'dispatch_cells':rows,'literals':literals,'instruction_spans':spans,'target_execution':False}
(h/'final-linkage.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'cells':len(rows),'literals':len(literals),'spans':len(spans)}))
