"""Read-only checks for independent candidate scan and original PCM lead."""
from pathlib import Path
import struct,json,re,hashlib,subprocess
H=Path(__file__).resolve().parent;R=H.parents[4];S=R/'research/targets/derived/Cubase15-arm64'
before=S.stat();b=S.read_bytes();expected='dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb';assert hashlib.sha256(b).hexdigest()==expected
pos=32;segments=[]
for _ in range(struct.unpack_from('<I',b,16)[0]):
 c,n=struct.unpack_from('<II',b,pos)
 if c==25:
  v=struct.unpack_from('<II16sQQQQIIII',b,pos);segments.append((v[3],v[5],v[6]))
 pos+=n
def raw(a,n):
 v,o,s=next(x for x in segments if x[0]<=a and a+n<=x[0]+x[2]);k=o+a-v;return k,b[k:k+n]
checks=[]
for p in sorted(H.glob('native-candidate-*.txt')):
 words=[(int(a,16),int(w,16))for a,w in re.findall(r'^([0-9a-f]+):\s+([0-9a-f]{8})\s',p.read_text(),re.M)];assert words
 for a,w in words:assert struct.unpack('<I',raw(a,4)[1])[0]==w
 assert [a for a,w in words]==list(range(words[0][0],words[-1][0]+4,4))
 a=words[0][0];n=4*len(words);off,block=raw(a,n)
 checks.append(dict(path=str(p.relative_to(R)),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),start=hex(a),end_exclusive=hex(a+n),words=len(words),source_offset=off,source_bytes_sha256=hashlib.sha256(block).hexdigest()))
slots=[]
for slot,target,instruction in [(0xd8,0x101a17cd4,0xfd402800),(0xe8,0x101a17ce4,0xfd402c00),(0x108,0x101a17d1c,0xfd403000)]:
 off,x=raw(0x104436be0+slot,8);assert struct.unpack('<Q',x)[0]==target
 of,y=raw(target,8);assert struct.unpack('<II',y)==(instruction,0xd65f03c0)
 slots.append(dict(slot=hex(slot),target=hex(target),slot_source_offset=off,slot_hex=x.hex(),function_source_offset=of,function_hex=y.hex(),meaning={0xd8:'load Double at object+0x50',0xe8:'load Double at object+0x58',0x108:'load Double at object+0x60'}[slot]))
strings=[]
for a,text in [(0x10389225a,b'AudioStream\0'),(0x10389270f,b'PAudioSegment\0')]:
 off,x=raw(a,len(text));assert x==text;strings.append(dict(address=hex(a),source_offset=off,hex=x.hex(),text=text[:-1].decode()))
after=S.stat();assert (before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)
r=dict(source=str(S.relative_to(R)),sha256=expected,native_captures=checks,source_bound_slots=slots,literals=strings,scope='Original bytes and instruction-word custody; no target execution, indirect-call completeness, or runtime verification.',passed=True,target_execution_count=0)
with(H/'consumer-lead-checks.json').open('x')as f:json.dump(r,f,indent=2);f.write('\n')
print(json.dumps(dict(captures=len(checks),native_words=sum(c['words']for c in checks),slots=len(slots),passed=True)))
