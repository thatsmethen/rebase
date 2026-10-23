"""Independent original-image custody checks for the bounded event review.
No target execution. Run only after the author has finished each selected pass.
"""
from pathlib import Path
import hashlib,json,re,struct,datetime
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[4];AUTHOR=HERE.parent/'event-rendering'
SOURCE=ROOT/'research/targets/derived/Cubase15-arm64'
EXPECTED='dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb'
def sha(b):return hashlib.sha256(b).hexdigest()
before=SOURCE.stat();data=SOURCE.read_bytes();after=SOURCE.stat()
assert (before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)
assert sha(data)==EXPECTED
segments=[];pos=32
for _ in range(struct.unpack_from('<I',data,16)[0]):
 cmd,n=struct.unpack_from('<II',data,pos)
 if cmd==0x19:
  name=data[pos+8:pos+24].split(b'\0')[0].decode();va,vs,off,fs=struct.unpack_from('<QQQQ',data,pos+24)
  segments.append(dict(name=name,address=va,file_offset=off,file_size=fs))
 if cmd==0x26:fs_off,fs_len=struct.unpack_from('<II',data,pos+8)
 pos+=n
starts=[];va=next(s['address']for s in segments if s['name']=='__TEXT');value=shift=0
for b in data[fs_off:fs_off+fs_len]:
 value|=(b&127)<<shift
 if b&128:shift+=7
 else:
  if not value:break
  va+=value;starts.append(va);value=shift=0
def raw(va,n):
 s,=[s for s in segments if s['address']<=va and va+n<=s['address']+s['file_size']]
 off=s['file_offset']+va-s['address'];return off,data[off:off+n]
def ev(p):
 d=json.loads(p.read_text());assert not d.get('isError');return d.get('structuredContent')or json.loads(d['content'][0]['text'])
rows=[];inputs=[]
for dirname in ['pass1','pass2','pass3']:
 p=AUTHOR/dirname
 for f in sorted(p.glob('native-*.txt')):
  key=f.stem.split('-')[1];start=int(key,16);end=starts[starts.index(start)+1]
  off,b=raw(start,end-start);actual=(p/f'function-{key}.arm64.bin').read_bytes();assert actual==b
  text=f.read_text();words={int(a,16):int(w,16)for a,w in re.findall(r'^([0-9a-f]+):\s+([0-9a-f]{8})\s',text,re.M)}
  assert len(words)*4==len(b)
  for a,w in words.items():assert struct.unpack_from('<I',b,a-start)[0]==w
  r=dict(start=hex(start),metadata_end=hex(end),source_offset=off,bytes=len(b),source_sha256=sha(b),native_words=len(words),rea_addresses=None)
  if(p/f'close-{key}.json').exists():
   rb=ev(p/f'bytes-{key}.json')['raw_result'];assert rb['complete'] and bytes.fromhex(rb['bytes_hex'])==b
   value=ev(p/f'function-{key}.json')['raw_result']['value'];pcs=[int(x.split(':')[0],16)for x in value['assembly']]
   assert all(a in words for a in pcs)and len(set(pcs))==len(pcs)
   r['rea_addresses']=len(pcs);r['body']=value['procedure']['body'];r['readback_exact']=True
  rows.append(r)
  inputs.append(dict(path=str(f.relative_to(ROOT)),sha256=sha(f.read_bytes())))
# Independently decode the exact primary PAudioSegment slots used by builder.
slots=[]
for slot,expected in [(0xd0,0x101a17ccc),(0xe0,0x101a17cdc),(0xf0,0x101a17cec),(0x100,0x101a17d14),(0x130,0x100113ce8),(0x138,0x100113cf0),(0x140,0x100113cf8),(0x148,0x100113d04)]:
 a=0x104436be0+slot;off,b=raw(a,8);value=struct.unpack('<Q',b)[0];assert value==expected
 slots.append(dict(address=hex(a),slot=hex(slot),target=hex(value),source_offset=off,hex=b.hex()))
# Tiny setter missing from author's initial pass: exact native instruction words.
a=0x101a17cdc;off,b=raw(a,8);assert struct.unpack('<II',b)==(0xfd002c00,0xd65f03c0)
extra=dict(address=hex(a),source_offset=off,hex=b.hex(),assembly=['str d0,[x0,#0x58]','ret'])
result=dict(at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),source=str(SOURCE.relative_to(ROOT)),source_sha256=EXPECTED,segments=segments,
 functions=rows,source_bound_slots=slots,duration_setter=extra,inputs=inputs,totals=dict(functions=len(rows),native_bytes=sum(r['bytes']for r in rows),native_words=sum(r['native_words']for r in rows),rea_functions=sum(r['rea_addresses']is not None for r in rows),rea_addresses=sum(r['rea_addresses']or 0 for r in rows)),
 scope='Independent original mapping/boundary/word/readback checks only, not semantic or runtime validation.',passed=True,target_execution_count=0)
with(HERE/'input-checks-initial.json').open('x')as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps(result['totals']))
