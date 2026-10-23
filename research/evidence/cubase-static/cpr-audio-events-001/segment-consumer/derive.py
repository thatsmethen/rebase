"""Read-only original-image address candidates and bounded native derivatives."""
from pathlib import Path
from bisect import bisect_right
import hashlib, json, struct, subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
SOURCE = ROOT / 'research/targets/derived/Cubase15-arm64'
EXPECTED = 'dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb'
before = SOURCE.stat(); data = SOURCE.read_bytes(); after = SOURCE.stat()
assert (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
assert hashlib.sha256(data).hexdigest() == EXPECTED
segments=[]; sections=[]; pos=32
for _ in range(struct.unpack_from('<I',data,16)[0]):
    cmd,size=struct.unpack_from('<II',data,pos)
    if cmd==0x19:
        s=struct.unpack_from('<II16sQQQQIIII',data,pos)
        segments.append(dict(name=s[2].rstrip(b'\0').decode(),address=s[3],offset=s[5],file_size=s[6]))
        for n in range(s[-2]):
            q=struct.unpack_from('<16s16sQQIIIIIIII',data,pos+72+80*n)
            sections.append(dict(name=q[0].rstrip(b'\0').decode(),address=q[2],size=q[3],offset=q[4]))
    if cmd==0x26: _,_,fs_off,fs_len=struct.unpack_from('<IIII',data,pos)
    pos+=size
starts=[]; va=next(s['address'] for s in segments if s['name']=='__TEXT'); delta=shift=0
for b in data[fs_off:fs_off+fs_len]:
    delta|=(b&127)<<shift
    if b&128: shift+=7
    else:
        if not delta:break
        va+=delta; starts.append(va); delta=shift=0
def offset(va):
    s,=[s for s in segments if s['address']<=va<s['address']+s['file_size']]
    return s['offset']+va-s['address']
def save(name,value):
    with (HERE/name).open('x') as f: json.dump(value,f,indent=2);f.write('\n')
def derive(entries,label):
    rows=[]
    for entry in sorted(entries):
        end=starts[starts.index(entry)+1]; at=offset(entry); raw=data[at:at+end-entry]
        assert len(raw)<65536
        name=f'function-{entry:x}.arm64.bin'
        with (HERE/name).open('xb') as f:f.write(raw)
        args=['/Library/Developer/CommandLineTools/usr/bin/llvm-objdump','-d','--start-address='+hex(entry),'--stop-address='+hex(end),str(SOURCE)]
        native=subprocess.run(args,capture_output=True,text=True,check=True).stdout
        native_name=f'native-{entry:x}.txt'
        with (HERE/native_name).open('x') as f:f.write(native)
        rows.append(dict(entry=hex(entry),next_declared_function_start=hex(end),length=len(raw),source_file_offset=at,raw_file=name,raw_sha256=hashlib.sha256(raw).hexdigest(),native_file=native_name,native_sha256=hashlib.sha256(native.encode()).hexdigest(),native_command=args))
    save(label,dict(source=str(SOURCE),source_sha256=EXPECTED,segments=segments,derivatives=rows,scope='Exact static raw intervals. Metadata boundaries are not proven bodies; raw REA images lack global/import/vtable context.'))
    return rows

