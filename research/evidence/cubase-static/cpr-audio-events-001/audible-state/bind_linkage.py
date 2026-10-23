import hashlib,json,struct
from pathlib import Path
h=Path(__file__).resolve().parent;r=h.parents[4];p=r/'research/targets/derived/Cubase15-arm64';b=p.read_bytes();expected='dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb';assert hashlib.sha256(b).hexdigest()==expected
ss=[];at=32
for _ in range(struct.unpack_from('<I',b,16)[0]):
 c,n=struct.unpack_from('<II',b,at)
 if c==25:
  x=struct.unpack_from('<II16sQQQQIIII',b,at);ss.append((x[3],x[5],x[6]))
 at+=n
def pin(a,n):
 v,o,z=next(s for s in ss if s[0]<=a and a+n<=s[0]+s[2]);off=o+a-v;raw=b[off:off+n];return {'address':hex(a),'source_offset':off,'bytes':n,'hex':raw.hex(),'sha256':hashlib.sha256(raw).hexdigest()}
def text(a):
 raw=bytes.fromhex(pin(a,256)['hex']).split(b'\0')[0];return {**pin(a,len(raw)+1),'text':raw.decode('utf8')}
strings=[0x1038917f6,0x103891e63,0x103891ab2,0x103891e6a,0x103891e74,0x103891e7d,0x10389132d,0x103891e82,0x103891e8e,0x103891e98,0x103891e9e,0x103891eae,0x103891eb5,0x103891ebd,0x103891ed3,0x103891edc,0x103891e39,0x103891e41,0x103891f1a,0x1038973ad,0x1038973c5,0x1038972d4,0x1038972b8,0x103892aee,0x1038a5785,0x1038a5829,0x10389218b,0x1038920a3,0x103892190,0x10389212d]
slots=[]
for vt,ofs in [(0x10442e898,[0x98,0xa8,0x360]),(0x10442fee8,[0x78,0x98,0x108,0x110,0x1f8,0x208]),(0x10444bb60,[0x98]),(0x104435b40,[0x40,0x98,0xf0]),(0x1044603c0,[0x40,0x98]),(0x1044d6be0,[0x178])]:
 for ofs in ofs:
  t=pin(vt+ofs,8);t.update({'vtable':hex(vt),'slot':hex(ofs),'target':hex(int.from_bytes(bytes.fromhex(t['hex']),'little'))});slots.append(t)
spans=[(0x1000ef070,0x1000ef130,'Start/Length/Offset/SnapPoint/Priority/Lane/Volume named writer bindings'),(0x1000ef1c4,0x1000ef1fc,'FadeIn/FadeOut named writer bindings'),(0x1000ef248,0x1000ef284,'Inverted and VolCurve named writer bindings'),(0x1000ee6d4,0x1000ee730,'MAudioEvent reader callback loops; globals not mapped by raw decompiler'),(0x100301104,0x1003011e4,'Clip post-read existing Warpscale and missing StretchPreset branch'),(0x1000fdb98,0x1000fdbb8,'Fresh edit-history vector/owner fields'),(0x100201748,0x100201758,'Empty edit-history skips item processing'),(0x100200b00,0x100200b10,'Set owner then empty-history bypass'),(0x1007d9440,0x1007d9458,'Micro curve vector initialized empty before reserve'),(0x1007db86c,0x1007db8d4,'Reserve preserves old logical extent; initial begin=end remain equal')]
d={'source':str(p.relative_to(r)),'sha256':expected,'strings':[text(x) for x in strings],'vtable_slots':slots,'instruction_spans':[{**pin(a,e-a),'meaning':m} for a,e,m in spans],'scope':'Exact original linked bytes supporting separately retained raw analysis. Strings establish native labels only; dispatch targets require the cited original callers. No target execution.'}
(h/'linkage.json').write_text(json.dumps(d,indent=2)+'\n')
f=json.loads((h/'fixture-fields.json').read_text());x=f['fixtures'][0];obj=next(a['value'] for a in x['clip']['named_attributes'] if a['name']['text']=='Warpscale');data=(r/x['source']['path']).read_bytes();at=obj['body_offset'];end=obj['end'];raw=data[at:end];assert len(raw)==84 and struct.unpack_from('>i',raw)[0]==2
pairs=[{'offset':at+4+i*16,'hex':raw[4+i*16:20+i*16].hex(),'item_plus_0x10_f64':struct.unpack_from('>d',raw,4+i*16)[0],'item_plus_0x18_f64':struct.unpack_from('>d',raw,12+i*16)[0]} for i in range(2)]
w={'source':x['source'],'object':obj,'body_hex':raw.hex(),'count':2,'pairs':pairs,'four_read_discarded_v1_values':[struct.unpack_from('>d',raw,36+i*8)[0] for i in range(4)],'v2_item_plus_0x20_values':[struct.unpack_from('>d',raw,68+i*8)[0] for i in range(2)],'reader':'0x1002fc338','exact_consumption':True,'limits':'Fields are object memory offsets, not assumed sample/beat labels. Predicate1002fca24 compares plus10 against conversion of plus18 between clip+108 and clip+110 descriptors; source directions/units are owned by timebase evidence.'}
(h/'warp-fields.json').write_text(json.dumps(w,indent=2)+'\n');print(json.dumps({'literal_count':len(strings),'vtable_cells':len(slots),'warp_body_bytes':84}))
