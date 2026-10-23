from pathlib import Path
import struct,hashlib,json
h=Path(__file__).resolve().parent;r=h.parents[4];p=r/'research/targets/derived/Cubase15-arm64';b=p.read_bytes();assert hashlib.sha256(b).hexdigest()=='dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb'
ss=[];at=32
for _ in range(struct.unpack_from('<I',b,16)[0]):
 c,n=struct.unpack_from('<II',b,at)
 if c==25:
  v=struct.unpack_from('<II16sQQQQIIII',b,at);ss.append((v[3],v[5],v[6]))
 at+=n
def offset(a):return next((o+a-v for v,o,n in ss if v<=a<v+n),None)
def va(off):return next((v+off-o for v,o,n in ss if o<=off<o+n),None)
def cstr(a):
 o=offset(a)
 if o is None:return None
 e=b.find(b'\0',o,o+512)
 if e<0:return None
 try:return b[o:e].decode('ascii')
 except:return None
rows=[]
for token in ['N9Steinberg24InvertedPhaseAudioStreamE','N9Steinberg14AudioAlgorithm15WarpGroupStreamE']:
 needle=token.encode()+b'\0';start=0
 while True:
  pos=b.find(needle,start)
  if pos<0:break
  start=pos+1;nameaddr=va(pos);scan=0
  while True:
   ptr=b.find(struct.pack('<Q',nameaddr),scan)
   if ptr<0:break
   scan=ptr+1
   if ptr%8:continue
   ti=va(ptr-8);sscan=0
   while True:
    cell=b.find(struct.pack('<Q',ti),sscan)
    if cell<0:break
    sscan=cell+1
    if cell%8 or b[cell-8:cell]!=b'\0'*8:continue
    table=va(cell+8);rows.append({'token':token,'typeinfo':hex(ti),'vtable':hex(table),'table_prefix_offset':cell-8,'table_prefix_hex':b[cell-8:cell+8+0x200].hex(),'slots':[{'slot':hex(x),'target':hex(struct.unpack_from('<Q',b,cell+8+x)[0])} for x in range(0,0x200,8)]})
(h/'stream-table-candidates.json').write_text(json.dumps({'source_sha256':hashlib.sha256(b).hexdigest(),'scope':'RTTI and cell candidates, semantic binding requires constructor/caller evidence','rows':rows},indent=2)+'\n')
for row in rows:print(row['token'],row['vtable'])
