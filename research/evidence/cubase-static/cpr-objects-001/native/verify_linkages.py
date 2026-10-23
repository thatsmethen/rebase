"""Read-only verification of selected RTTI/vtable links in the pinned thin image."""
import hashlib,json,struct
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
SOURCE=ROOT/'research/targets/derived/Cubase15-arm64'
EXPECTED='dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb'
before=SOURCE.stat(); data=SOURCE.read_bytes()
assert hashlib.sha256(data).hexdigest()==EXPECTED
segments=[];p=32
for _ in range(struct.unpack_from('<I',data,16)[0]):
 command,size=struct.unpack_from('<II',data,p)
 if command==0x19:
  v=struct.unpack_from('<II16sQQQQIIII',data,p)
  segments.append(dict(name=v[2].rstrip(b'\0').decode(),address=v[3],offset=v[5],file_size=v[6]))
 p+=size

def offset(a,n):
 s,=[s for s in segments if s['address']<=a and a+n<=s['address']+s['file_size']]
 return s['offset']+a-s['address']
def read(a,n):
 o=offset(a,n);return data[o:o+n]
def u64(a):return struct.unpack('<Q',read(a,8))[0]
def region(a,n):
 b=read(a,n);return dict(address=hex(a),source_file_offset=offset(a,n),length=n,bytes_hex=b.hex(),sha256=hashlib.sha256(b).hexdigest())
classes=[
 ('FNewArchive',0x104e44bc8,0x104e44b70,{0x20:0x10319284c,0x28:0x1031930f8,0x30:0x1031696b0,0x38:0x103193a04}),
 ('FArchive',0x104e3f570,0x104e3f518,{0x30:0x1031696b0}),
 ('MDataNode',0x10466c440,0x10466c2d8,{0x98:0x1016ea554}),
 ('MListNode',0x104670598,0x104670218,{0x98:0x101715fb0}),
 ('MTrackList',0x104679258,0x104678ea8,{0x98:0x101759190}),
 ('MTempoTrackEvent',0x104675df8,0x104674d18,{0x98:0x10173bdac,0xa0:0x10173c17c,0x5f8:0x10174c194,0x600:0x10173ac84,0x610:0x10173ad50}),
 ('MTempoEvent',0x1046761e0,0x1046746f0,{0x190:0x101739f00,0x1a0:0x101739f3c,0x498:0x101740db0,0x4a0:0x101740dc4}),
]
rows=[]
for name,ti,vt,slots in classes:
 mangled=f'N9Steinberg{len(name)}{name}E'.encode()+b'\0'
 sa=u64(ti+8);assert read(sa,len(mangled))==mangled,(name,hex(sa))
 assert u64(vt-16)==0 and u64(vt-8)==ti,name
 r=dict(class_name=name,name=region(sa,len(mangled)),typeinfo_name_pointer=region(ti+8,8),vtable_prefix=region(vt-16,16),primary_vtable=hex(vt),selected_slots=[])
 for slot,expected in slots.items():
  actual=u64(vt+slot);assert actual==expected,(name,hex(slot),hex(actual),hex(expected))
  r['selected_slots'].append(dict(slot=hex(slot),target=hex(actual),**region(vt+slot,8)))
 rows.append(r)
strings=[]
for address,value in [(0x103891f2e,b'MEvent\0'),(0x103896416,b'MTempoTrackEvent\0')]:
 assert read(address,len(value))==value
 strings.append(dict(value=value[:-1].decode(),**region(address,len(value))))
# This wrapper is two native instructions: archive->wrapped stream, then external tail branch.
assert read(0x10310a240,8).hex()=='210440f96bffff17'
constants={hex(v):struct.unpack('>d',v.to_bytes(8,'big'))[0] for v in [0x407e000000000000,0x3e45798ee2308c3a]}
after=SOURCE.stat();assert (before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_size,after.st_mtime_ns,after.st_ctime_ns)
report=dict(source=str(SOURCE),source_sha256=EXPECTED,source_stable=True,classes=rows,strings=strings,string_archive_wrapper=region(0x10310a240,8),decoded_immediate_binary64_constants=constants,limits=['Only selected slots are asserted; neighboring raw pointer words from earlier locator output are not all vtable members.','This verifies linked-file bytes. It does not prove runtime object identity, address relocation, current compatibility globals, or an entire CPR load call chain.','Static typeinfo and virtual-slot association are supplemented by constructor/reader native instructions in retained REA slices; no target code was executed.'])
(HERE/'linkage-provenance.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(classes=len(rows),slots=sum(len(r['selected_slots'])for r in rows),passed=True)))
