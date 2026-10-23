"""Read-only original dispatch/instruction/import bindings for mode0 samples."""
from pathlib import Path
import sys,struct,json,hashlib
H=Path(__file__).resolve().parent;ROOT=H.parents[4]
sys.path.insert(0,str(ROOT/'research/evidence/cubase-static/cpr-map-clock-001/attributes'));import source_tools as s
cells=[]
for off in [0x10,0x18,0x20,0x28,0x30,0x40]:
 r=s.region(0x104461990+off,8);r.update(table='0x104461990',slot=hex(off),target=hex(int.from_bytes(bytes.fromhex(r['bytes_hex']),'little')));cells.append(r)
spans=[]
for name,a,e in [
 ('mode0 factory branch',0x10030a008,0x10030a0d8),
 ('mode0 rate setup',0x10030c5b8,0x10030c5c8),
 ('mode0 history and phase reset',0x10030c66c,0x10030c6c4),
 ('packet float32 entry forwards unused flush',0x10030de00,0x10030de14),
 ('finite positive count, step2 split and channel dispatch',0x10030ffb0,0x1003100dc),
 ('downsample tail branches',0x100310150,0x100310160),
 ('large ratio mono carry and loop',0x1003100dc,0x100310134),
 ('large ratio mono loop and state',0x100310160,0x1003101ec),
 ('small ratio mono body',0x1003108f0,0x100310b84),
 ('small ratio stereo body',0x100310b84,0x100310e08),
 ('large ratio stereo body',0x10031179c,0x1003118e8),
 ('inner consumer read before segment gain multiply',0x100190e00,0x100190f20),
]:
 r=s.region(a,e-a);r['name']=name;spans.append(r)
data=s.data;sections=[];pos=32
for _ in range(struct.unpack_from('<I',data,16)[0]):
 cmd,size=struct.unpack_from('<II',data,pos)
 if cmd==0x19:
  for j in range(struct.unpack_from('<I',data,pos+64)[0]):
   at=pos+72+j*80;va,n,off=struct.unpack_from('<QQI',data,at+32);flags,r1,r2=struct.unpack_from('<III',data,at+64);sections.append((va,n,off,flags,r1,r2))
 elif cmd==2:symoff,nsyms,stroff,strsize=struct.unpack_from('<IIII',data,pos+8)
 elif cmd==0xb:indirectoff,indirectcount=struct.unpack_from('<II',data,pos+56)
 pos+=size
imports=[]
for va,expected in [(0x103881008,'_bzero')]:
 sec,=[z for z in sections if z[0]<=va<z[0]+z[1]and z[3]&255==8]
 idx=sec[4]+(va-sec[0])//sec[5];assert idx<indirectcount
 symbol=struct.unpack_from('<I',data,indirectoff+idx*4)[0];assert symbol<nsyms
 strx=struct.unpack_from('<I',data,symoff+symbol*16)[0];name=data[stroff+strx:data.index(0,stroff+strx,stroff+strsize)].decode();assert name==expected
 r=s.region(va,sec[5]);r.update(symbol=name,symbol_index=symbol,indirect_index=idx);imports.append(r)
report=dict(source_sha256=s.PIN,dispatch_cells=cells,instruction_spans=spans,import_bindings=imports,scope='Explicit original-image bindings only, no loaded target or dependency',target_execution=False)
(H/'original-bindings.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'cells':len(cells),'spans':len(spans),'imports':len(imports)}))
