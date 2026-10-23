"""Original-image linkage for the concrete default handler path."""
import json,hashlib,struct
from pathlib import Path
H=Path(__file__).resolve().parent;R=H.parents[4];S=R/'research/targets/derived/Cubase15-arm64';s=S.read_bytes();sha=lambda b:hashlib.sha256(b).hexdigest();assert sha(s)=='dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb'
d=json.loads((H/'derivation.json').read_text());spans=[]
def region(label,a,n):
 seg,=[x for x in d['segments']if x['address']<=a and a+n<=x['address']+x['file_size']];o=seg['offset']+a-seg['address'];b=s[o:o+n];r={'label':label,'address':hex(a),'source_file_offset':o,'length':n,'bytes_hex':b.hex(),'sha256':sha(b)};spans.append(r);return b
def slot(label,v,k,target):
 b=region(label,v+k,8);assert struct.unpack('<Q',b)[0]==target;spans[-1].update(vtable=hex(v),slot=hex(k),target=hex(target))
def string(label,a,expected):
 b=region(label,a,len(expected)+1);assert b==expected.encode()+b'\0';spans[-1]['text']=expected
for label,v,k,t in [
 ('base track list getter',0x104676bb0,0x258,0x10174a698),
 ('tempo track class predicate',0x104674d18,0x40,0x10173f4b8),
 ('tempo track flag predicate',0x104674d18,0x588,0x1001fcf00),
 ('tempo list datum getter',0x104675ec8,0x108,0x1016e9a18),
 ('root primary lookup',0x104f73d78,0x20,0x10307eefc),
 ('root embedded registry factory registration',0x104e288c0,0x38,0x10307eac8),
 ('TrackLoopHandler factory wrapper',0x1044b0160,0,0x1005ca8c0)]:slot(label,v,k,t)
a=region('root secondary virtual-base adjustment',0x104f73e48-0x60,8);assert struct.unpack('<q',a)[0]==-24
for label,a,t in [
 ('constructor parameter key',0x104f86491,'TrackLoopHandlerParam'),
 ('product registration key',0x104f866e1,'TrackLoopHandlerParam'),
 ('root context subscription key',0x104fe6fd3,'Lego::IRootContext'),
 ('base track class check',0x103890885,'MTrackEvent')]:string(label,a,t)
for label,a,n in [
 ('root construction primary-secondary vptr stores',0x103806784,24),
 ('embedded registry vptr store',0x10307ed68,12),
 ('TrackLoopHandler product key and stored factory',0x1005ca4ec,72),
 ('root post-registration external callback',0x1005ca578,28),
 ('factory-wrapper invocation and ownership return',0x1005ca8cc,40),
 ('handler saved track pointer and scalar copies',0x1017661ac,172),
 ('host constructor context and returned object store',0x101748124,72),
 ('base list scalar datum and owner-pointer initialization',0x1016e8a68,244),
 ('factory selects empty tempo ctor',0x10173a5ac,64),
 ('empty tempo ctor list bit8 clear',0x10173a7c0,260)]:region(label,a,n)
# Original vtable construction offsets for the three non-list base subobjects.
subobjects=[]
for base,vtt in [(0xb0,0x10444b038),(0xe8,0x10444b370),(0x128,0x10444b6a8)]:
 p=struct.unpack('<Q',region('base subobject construction table',vtt,8))[0];offset=struct.unpack('<q',region('base subobject construction adjustment',p-0x28,8))[0]
 subobjects.append({'track_subobject_offset':hex(base),'construction_table':hex(vtt),'primary_vtable':hex(p),'virtual_base_store_offset':hex(base+offset),'fixed_field_writes':'receiver+0,+8,+16,+24,+32,+36,+40; these do not overlap track+0x50/0x58/0x68 or list contents.'})
result={'scope':'Exact original-image linkage; selection of these defaults at runtime is conditional. No target execution.','source_sha256':sha(s),'spans':spans,'base_subobjects':subobjects,'zero_fill_runtime_globals':['0x104feeee0 IComponents selected pointer','0x10501e350 IRootContext selected pointer','0x104fefc10 optional root-context callback receiver'],'limits':['No zero-fill global is assigned a runtime value from file bytes.','Registration keys match literally; alternative registry values/overwrites remain supported and outside the default-path claim.','Code spans include immutable native words; semantics refer to the retained full raw-slice dossiers/native disassembly.']}
(H/'closure-linkage.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'spans':len(spans),'subobjects':subobjects}))
