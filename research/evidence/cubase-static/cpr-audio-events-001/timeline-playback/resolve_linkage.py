"""Original-image dispatch and instruction custody for bounded selector claims."""
from pathlib import Path
import sys,json,hashlib
H=Path(__file__).resolve().parent;ROOT=H.parents[4]
HELPER=ROOT/'research/evidence/cubase-static/cpr-map-clock-001/attributes/source_tools.py'
sys.path.insert(0,str(HELPER.parent));import source_tools as s
cells=[]
for name,vt,slots in [('PAudioSegment',0x104436be0,[0xd8,0xe8,0xf8,0x108]),('MAudioTrack',0x10444aa98,[0x118,0x148,0x1b0,0x1b8]),('MAudioTrack secondary owner+120',0x10444acc0,[0,8,16,24,32]),('list iterator',0x104e30f00,[0x10,0x18]),('temporary segment list',0x1046cafc0,[0x108,0x140,0x148])]:
 for slot in slots:
  v=s.region(vt+slot,8);v.update(receiver=name,table=hex(vt),slot=hex(slot),target=hex(int.from_bytes(bytes.fromhex(v['bytes_hex']),'little')));cells.append(v)
spans=[]
for name,a,e in [
 ('MAudioTrack primary and adjusted receiver construction',0x1001f6560,0x1001f6584),
 ('MAudioTrack bound track pointer setter',0x1001fd4e4,0x1001fd4ec),
 ('track virtual118 producer caller',0x1001f9090,0x1001f91a0),
 ('track virtual148 producer caller',0x1001f95f8,0x1001f96d8),
 ('producer admission builder and generation commit',0x1001f91bc,0x1001f9274),
 ('secondary selector adjustment',0x1001f9854,0x1001f985c),
 ('reset primary and adjusted',0x1001f96d8,0x1001f96f8),
 ('selector normal path',0x1001f970c,0x1001f980c),
 ('secondary interface matching and result',0x1001fd508,0x1001fd554),
 ('exact end operation',0x101a17d08,0x101a17d14),
 ('iterator constructor from list head',0x10310266c,0x103102680),
 ('iterator exhausted predicate',0x100212d74,0x100212d84),
 ('iterator yield and successor',0x103101a0c,0x103101a24),
 ('remainder segment concrete fields and gain',0x100210508,0x1002105c4),
 ('segment insertion link writes',0x101a18230,0x101a18264),
]:
  v=s.region(a,e-a);v['name']=name;spans.append(v)
report=dict(source_sha256=s.PIN,source=str(s.SOURCE),helper_sha256=hashlib.sha256(HELPER.read_bytes()).hexdigest(),dispatch_cells=cells,instruction_spans=spans,interface_id_storage={'address':'0x104feb498','length':16,'file_backed':False,'status':'Compared global storage; initializer/value not traced. No concrete GUID value claimed.'},target_execution=False,limits=['Only listed cells are bound. Adjacent table cells may belong to other receivers.','Interface existence and producer relation do not establish a live audio callback or seek quantization.','Original instruction spans are static evidence, not executed target traces.'])
(H/'linkage.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'cells':len(cells),'spans':len(spans)}))
