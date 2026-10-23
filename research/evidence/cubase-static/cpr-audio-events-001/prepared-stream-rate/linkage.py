"""Original Mach-O linkage only; no proprietary execution."""
from pathlib import Path
import sys,struct,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[4]
sys.path.insert(0,str(ROOT/'research/evidence/cubase-static/cpr-map-clock-001/attributes'))
import source_tools as s

def u64(a):return int.from_bytes(bytes.fromhex(s.region(a,8)['bytes_hex']),'little')
def text(a):
 o=s.offset(a);b=s.data[o:o+250].split(b'\0',1)[0]
 return dict(text=b.decode(),source=s.region(a,len(b)+1))
classes=[]
for t,slots in [(0x104481010,[0xf8,0x120,0x130,0x138,0x140,0x148,0x150]),(0x104473bb0,[0xf8,0x120,0x130,0x138,0x140,0x148,0x150]),(0x10447ef48,[]),(0x104478b40,[])]:
 ti=u64(t-8);n=u64(ti+8)
 classes.append(dict(table=hex(t),rtti_pointer=s.region(t-8,8),typeinfo_name_pointer=s.region(ti+8,8),name=text(n),slots=[dict(slot=hex(z),target=hex(u64(t+z)),source=s.region(t+z,8))for z in slots]))
reader=[dict(table=hex(0x104480fc0),slot=hex(z),target=hex(u64(0x104480fc0+z)),source=s.region(0x104480fc0+z,8))for z in [0x10,0x20,0x28]]
branches=[]
for a,t in [(0x10047173c,0x100471604),(0x100465c0c,0x1004656e4),(0x1002120f8,0x100110c18),(0x10043a5c0,0x10040cf10),(0x10040cf50,0x10040b6d8),(0x10044fc80,0x10043760c),(0x10045c828,0x10043473c),(0x10043473c,0x10043394c)]:
 w=struct.unpack('<I',bytes.fromhex(s.region(a,4)['bytes_hex']))[0];assert w&0x7c000000==0x14000000
 imm=w&0x3ffffff
 if imm&0x2000000:imm-=0x4000000
 assert a+imm*4==t
 branches.append(dict(address=hex(a),target=hex(t),source=s.region(a,4)))
# Decode the selected imported function using original LC_SYMTAB/LC_DYSYMTAB and __stubs.
p=32;stub=None
for _ in range(struct.unpack_from('<I',s.data,16)[0]):
 cmd,n=struct.unpack_from('<II',s.data,p)
 if cmd==2:syms=struct.unpack_from('<6I',s.data,p)
 if cmd==11:ind=struct.unpack_from('<20I',s.data,p)
 if cmd==0x19:
  for i in range(struct.unpack_from('<I',s.data,p+64)[0]):
   v=struct.unpack_from('<16s16sQQIIIIIIII',s.data,p+72+80*i)
   if v[0].rstrip(b'\0')==b'__stubs':stub=v
 p+=n
a=0x103881008;idx=(a-stub[2])//stub[10]+stub[9];symbol=struct.unpack_from('<I',s.data,ind[14]+4*idx)[0];stridx=struct.unpack_from('<I',s.data,syms[2]+16*symbol)[0];o=syms[4]+stridx;name=s.data[o:].split(b'\0',1)[0].decode();assert name=='_bzero'
imports=[dict(address=hex(a),symbol=name,indirect_index=idx,symbol_index=symbol,symbol_file_offset=syms[2]+16*symbol,string_file_offset=o,stub_source=s.region(a,stub[10]))]
result=dict(source_sha256=s.PIN,passed=True,target_executed=False,classes=classes,silence_reader=reader,direct_branches=branches,imports=imports,literals=[text(0x103892aee)],limits=['RTTI labels identify the inspected concrete classes, not runtime behavior by themselves.','Indirect provider +0xa8/+0x58 implementations are not supplied by this host linkage record.'])
with(HERE/'linkage.json').open('x')as f:json.dump(result,f,indent=2);f.write('\n')
print('Verified classes',[(x['table'],x['name']['text'])for x in classes])
