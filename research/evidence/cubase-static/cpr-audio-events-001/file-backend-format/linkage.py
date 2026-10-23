from pathlib import Path
import sys,json,struct
H=Path(__file__).resolve().parent;R=H.parents[4]
sys.path.insert(0,str(R/'research/evidence/cubase-static/cpr-map-clock-001/attributes'));import source_tools as s
def q(a):return struct.unpack_from('<Q',s.data,s.offset(a,8))[0]
def string(a):
 o=s.offset(a);n=s.data.index(0,o)-o+1
 return dict(text=s.data[o:o+n-1].decode(),source=s.region(a,n))
classes=[]
for creator,table,name in [(0x10031697c,0x104461be8,'N9Steinberg15AIFFFileHandlerE'),(0x100343de8,0x104462d00,'N9Steinberg20AudioFileHandlerPlugE'),(0x10035ab44,0x104465c38,'N9Steinberg15REX2FileHandlerE'),(0x100370e5c,0x104466d18,'N9Steinberg17Wave64FileHandlerE'),(0x10037492c,0x104466f40,'N9Steinberg15WaveFileHandlerE')]:
 ti=q(table-8);n=string(q(ti+8));assert n['text']==name
 slots=[dict(offset=hex(i),target=hex(q(table+i)),source=s.region(table+i,8)) for i in [0xd8,0xe0,0xf0,0x100,0x108]]
 classes.append(dict(creator=hex(creator),vtable=hex(table),rtti_pointer=s.region(table-8,8),typeinfo_name_pointer=s.region(ti+8,8),name=n,slots=slots))
branches=[]
for loc,target in [(0x10037494c,0x100340d3c),(0x100378198,0x100378238),(0x100378a54,0x1003791cc),(0x10033a104,0x10033a338),(0x10033d568,0x10012c64c),(0x100379224,0x10221d5d8),(0x100379230,0x10221d38c),(0x10037923c,0x10221d068),(0x100379248,0x10221d068),(0x100379254,0x10221d38c),(0x100379268,0x10221d38c)]:
 w=struct.unpack_from('<I',s.data,s.offset(loc,4))[0];assert w&0xfc000000==0x94000000
 imm=w&0x3ffffff;imm=imm-(1<<26) if imm&(1<<25) else imm
 assert loc+4*imm==target
 branches.append(dict(address=hex(loc),target=hex(target),source=s.region(loc,4)))
literals=[string(a) for a in [0x10388f00f,0x10388f01f,0x10388f5fc,0x1038977b1,0x10389780a,0x10389781b,0x103897ae4]]
result=dict(passed=True,target_executed=False,source_sha256=s.PIN,classes=classes,direct_branches=branches,literals=literals,notes=['Names follow original RTTI, not filenames or provider execution.','Registry identifiers in BSS are not given invented contents.','The concrete WaveFileHandler +e0/+f0 dispatch is established; live selection and successful filesystem access remain preconditions.'])
with (H/'linkage.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(len(classes),len(branches),len(literals))
