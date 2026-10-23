"""Resolve original Mach-O stubs, without loading any image or dependency."""
import struct,hashlib
from derive import data,offset,save,EXPECTED
sections=[];cursor=32
for _ in range(struct.unpack_from('<I',data,16)[0]):
 cmd,size=struct.unpack_from('<II',data,cursor)
 if cmd==0x19:
  for i in range(struct.unpack_from('<I',data,cursor+64)[0]):
   at=cursor+72+80*i;va,n,off=struct.unpack_from('<QQI',data,at+32);flags,res1,res2=struct.unpack_from('<III',data,at+64)
   sections.append((va,n,off,flags,res1,res2))
 elif cmd==2:symoff,nsyms,stroff,strsize=struct.unpack_from('<IIII',data,cursor+8)
 elif cmd==0xb:indirect_off,indirect_count=struct.unpack_from('<II',data,cursor+56)
 cursor+=size
rows=[]
for va,expected in [(0x103881efc,'_vDSP_vclr'),(0x103881f08,'_vDSP_vclrD'),(0x103881560,'_memcpy'),(0x10388153c,'_malloc')]:
 sec=next(s for s in sections if s[0]<=va<s[0]+s[1]and s[3]&255==8)
 idx=sec[4]+(va-sec[0])//sec[5];assert idx<indirect_count
 sym=struct.unpack_from('<I',data,indirect_off+4*idx)[0];assert sym<nsyms
 strx=struct.unpack_from('<I',data,symoff+16*sym)[0];end=data.index(0,stroff+strx,stroff+strsize)
 name=data[stroff+strx:end].decode();assert name==expected,(name,expected)
 raw=data[offset(va):offset(va)+sec[5]]
 rows.append(dict(stub=hex(va),source_offset=offset(va),bytes_hex=raw.hex(),sha256=hashlib.sha256(raw).hexdigest(),symbol=name,indirect_index=idx,symbol_index=sym))
save('original-import-bindings.json',dict(source_sha256=EXPECTED,records=rows))
print(rows)
