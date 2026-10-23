"""Exact original-image context bindings; no execution of target code."""
from pathlib import Path
import sys,json
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent;R=H.parents[4]
sys.path.insert(0,str(R/'research/evidence/cubase-static/cpr-map-clock-001/attributes'));import source_tools as s
u=lambda a:int.from_bytes(bytes.fromhex(s.region(a,8)['bytes_hex']),'little')
rows=[]
for t,expected,slots in [
 (0x104790820,'TScrubCalculator',{0x28:0x101c90954,0x30:0x101c90990,0x38:0x101c909ac}),
 (0x1047e9bd8,'TScrubClockProvider',{0x10:0x101c21d84}),
 (0x104780ec0,'TScrubClockCore',{0x10:0x101c21d84}),
 (0x1047e9b68,'DefaultProvider',{0x10:0x101f464f0}),
 (0x1047e9c70,'LinearSampleRampingFunction',{0x10:0x101c912ec,0x20:0x101c91584}),
 (0x1047ad3f8,'VsResampleQuadratic',{0x30:0x101d44a34}),
 (0x1047ad618,'VsResampleSpline',{0x30:0x101d47358})]:
 r=u(t-8);n=u(r+8);o=s.offset(n,1);end=s.data.index(b'\0',o);name=s.data[o:end].decode();assert expected in name
 dispatch=[]
 for slot,target in slots.items():assert u(t+slot)==target;dispatch.append(dict(slot=hex(slot),target=hex(target),source=s.region(t+slot,8)))
 rows.append(dict(vtable=hex(t),rtti=hex(r),mangled_type_name=name,rtti_pointer=s.region(t-8,8),name_pointer=s.region(r+8,8),name=s.region(n,end-o+1),dispatch=dispatch))
assert u(0x104fa4ce8)==0x1047e9b68
ranges=[]
for label,a,n in [
 ('Selector active flag, override, ordinary reader',0x101d3fcd0,80),
 ('New generation signed integer coordinate conversion',0x101d3fda8,12),
 ('Default factory pointer in original static data',0x104fa4ce8,8),
 ('Default core inactive initialization',0x101c21a30,4),
 ('Supplied speed activation threshold and state writes',0x101c21dd4,124),
 ('Mapper interpolation object selection',0x101d43830,48),
 ('Mapper initial floor and fraction',0x101d43910,24),
 ('Mapper two-return coefficient consumption',0x101d439d8,68),
 ('Coefficient two-Float32 return arithmetic',0x101c909c4,60),
 ('Typed default factory and fresh zero allocation',0x101f464f0,96),
 ('Channel bool setter',0x101d70c58,36)]:ranges.append(dict(label=label,**s.region(a,n)))
x=dict(source_sha256=s.PIN,target_executed=False,passed=True,types=rows,ranges=ranges,limits=['The original default-provider object is concrete; complete subscription/override wiring of each live owner +0x658 is not established.','RTTI names support classification only in combination with constructor, selector and coefficient consumers.','Channel byte +0x2ec is not assigned a product-facing label.'])
(H/'original-bindings.json').write_text(json.dumps(x,indent=2)+'\n');print('verified',len(rows),'types',len(ranges),'ranges')
