"""Verify bounded original native words, REA readback and concrete Float32 branches.
No target code is loaded or executed. Existing sealed evidence is read only.
"""
from pathlib import Path
import sys,json,re,struct,hashlib
H=Path(__file__).resolve().parent;R=H.parents[4]
sys.path.insert(0,str(R/'research/evidence/cubase-static/cpr-map-clock-001/attributes'))
import source_tools as s

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def envelope(p):
 x=json.loads(p.read_text());assert not x.get('isError'),p
 return x.get('structuredContent') or json.loads(x['content'][0]['text'])
uses={H/'pass1':[0x10030a710,0x10030a714,0x10030a728,0x10030a738,0x10030a748,0x10030a7a0,0x10030ae8c,0x10030aeb8],H/'pass2':[0x10030a664,0x10030a974],H.parent/'rate-converter':[0x10030a634,0x10030af58,0x10030b8a8,0x10030a008,0x10030a3bc]}
rows=[]
for folder,addresses in uses.items():
 for a in addresses:
  native=folder/f'native-{a:x}.txt';analysis=folder/f'function-{a:x}.json';readback=folder/f'bytes-{a:x}.json'
  words={int(pc,16):int(word,16)for pc,word in re.findall(r'^([0-9a-f]+):\s+([0-9a-f]{8})\s',native.read_text(),re.M)}
  assert words and min(words)==a
  for pc,word in words.items():assert int.from_bytes(bytes.fromhex(s.region(pc,4)['bytes_hex']),'little')==word
  rd=envelope(readback);b=rd['raw_result'];assert b['complete'];assert b['requested_bytes']==b['returned_bytes']
  original=bytes.fromhex(s.region(a,b['returned_bytes'])['bytes_hex']);assert original==bytes.fromhex(b['bytes_hex'])
  doc=envelope(analysis);asm=doc['raw_result']['value']['assembly'];assert all(int(line.split(':')[0],16)in words for line in asm)
  rows.append({'entry':hex(a),'new':folder in (H/'pass1',H/'pass2'),'directory':str(folder.relative_to(R)),'original_native_words':len(words),'rea_instruction_addresses':len(asm),'bytes_verified':len(original),'original_bytes_sha256':hashlib.sha256(original).hexdigest(),'evidence_ids':[doc['evidence_id'],rd['evidence_id']],'files':[{'path':str(p.relative_to(R)),'sha256':digest(p)}for p in(native,analysis,readback)]})
# Concrete vtable and byte switch entries from original mapped image, not raw-slice pseudocode.
slots={0:0x10030a710,8:0x10030a714,0x10:0x10030a728,0x18:0x10030a738,0x20:0x10030a748,0x28:0x10030ae8c,0x30:0x10030aeb8,0x38:0x10030aed0,0x40:0x10030af58}
bindings=[]
for slot,target in slots.items():
 p=s.region(0x1044618f0+slot,8);assert int.from_bytes(bytes.fromhex(p['bytes_hex']),'little')==target
 bindings.append(dict(slot=hex(slot),target=hex(target),original=p))
# Import stubs: parse the source's symbol/indirect tables without running dyld.
pos=32;stubs=[];libraries=[]
for _ in range(struct.unpack_from('<I',s.data,16)[0]):
 cmd,n=struct.unpack_from('<II',s.data,pos)
 if cmd in (12,0x80000018,0x8000001f,0x80000023):
  nameoff=struct.unpack_from('<I',s.data,pos+8)[0]
  end=s.data.index(0,pos+nameoff);libraries.append(s.data[pos+nameoff:end].decode())
 if cmd==2:_,_,symoff,nsyms,stroff,strsize=struct.unpack_from('<6I',s.data,pos)
 if cmd==0xb:
  values=struct.unpack_from('<20I',s.data,pos);indirectoff,nindirect=values[14:16]
 if cmd==0x19:
  section_count=struct.unpack_from('<I',s.data,pos+64)[0]
  for j in range(section_count):
   values=struct.unpack_from('<16s16sQQIIIIIIII',s.data,pos+72+j*80)
   if values[8]&255==8:stubs.append(values)
 pos+=n
imports=[]
for address,expected in [(0x103881b24,'_sin'),(0x103881008,'_bzero'),(0x103880db0,'__Znam'),(0x103880d8c,'__ZdaPv'),(0x103880e40,'___cxa_guard_acquire'),(0x103880e4c,'___cxa_guard_release')]:
 sec,=[x for x in stubs if x[2]<=address<x[2]+x[3]]
 ordinal=sec[9]+(address-sec[2])//sec[10]
 symbol=struct.unpack_from('<I',s.data,indirectoff+ordinal*4)[0]
 strx=struct.unpack_from('<I',s.data,symoff+symbol*16)[0]
 end=s.data.index(0,stroff+strx);name=s.data[stroff+strx:end].decode();assert name==expected,(hex(address),name)
 description=struct.unpack_from('<H',s.data,symoff+symbol*16+6)[0]
 library_ordinal=description>>8
 assert 0<library_ordinal<=len(libraries)
 library=libraries[library_ordinal-1]
 if name=='_sin':assert library=='/usr/lib/libSystem.B.dylib'
 imports.append(dict(address=hex(address),name=name,indirect_ordinal=ordinal,symbol_index=symbol,library_ordinal=library_ordinal,library=library,stub=s.region(address,sec[10])))
result={'source_sha256':s.PIN,'target_execution':False,'functions':rows,'concrete_slots':bindings,'coefficient_vector_seed':s.region(0x1039168f0,8),'import_bindings':imports,'summary':{'new_functions':10,'reused_functions':5,'original_native_words':sum(x['original_native_words']for x in rows),'rea_instruction_addresses':sum(x['rea_instruction_addresses']for x in rows),'bytes_verified':sum(x['bytes_verified']for x in rows)},'passed':True,'limits':['Raw slices omit globals, types, imports and switch tables; this validation adds only the listed source bindings.','Canonical instruction addresses and memory-readback equality do not prove runtime behavior or complete native call closure.']}
(H/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result['summary']))
