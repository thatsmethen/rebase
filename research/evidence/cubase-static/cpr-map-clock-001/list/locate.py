"""Exact raw code derivatives for bounded static REA queries; never executes target."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
SOURCE = ROOT / "research/targets/derived/Cubase15-arm64"
EXPECTED = "dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb"
before = SOURCE.stat()
data = SOURCE.read_bytes()
assert hashlib.sha256(data).hexdigest() == EXPECTED
segments = []
position = 32
for _ in range(struct.unpack_from("<I", data, 16)[0]):
    command, size = struct.unpack_from("<II", data, position)
    if command == 0x19:
        v = struct.unpack_from("<II16sQQQQIIII", data, position)
        segments.append(dict(name=v[2].rstrip(b"\0").decode(), address=v[3],
                             vm_size=v[4], offset=v[5], file_size=v[6]))
    if command == 0x26:
        _, _, fs_offset, fs_size = struct.unpack_from("<IIII", data, position)
    position += size
text = next(s for s in segments if s["name"] == "__TEXT")
starts, address, delta, shift = [], text["address"], 0, 0
for byte in data[fs_offset:fs_offset+fs_size]:
    delta |= (byte & 127) << shift
    if byte & 128:
        shift += 7
    else:
        if delta == 0:
            break
        address += delta
        starts.append(address)
        delta = shift = 0


import bisect
rows=[]
# Bounded static pattern search, not generalized register/dataflow recovery.
for s in segments:
    if s['name']!='__TEXT':continue
    raw=data[s['offset']:s['offset']+s['file_size']]
    words=list(struct.unpack('<'+'I'*(len(raw)//4),raw[:len(raw)//4*4]))
    for i,w in enumerate(words):
        if w & 0x9f000000 != 0x90000000:continue
        at=s['address']+4*i; rd=w&31
        imm=((w>>29)&3)|(((w>>5)&0x7ffff)<<2)
        if imm&(1<<20):imm-=1<<21
        page=(at&~4095)+(imm<<12)
        if page not in (0x104674000,0x105080000,0x105006000):continue
        for j in range(i+1,min(i+12,len(words))):
            v=words[j];kind=None;target=None
            if (v>>5)&31!=rd:continue
            if v&0xffc00000==0x91000000:target=page+((v>>10)&4095);kind='ADD immediate'
            elif v&0xffc00000 in (0xb9400000,0xb9000000):target=page+(((v>>10)&4095)*4);kind='LDR32' if v&0xffc00000==0xb9400000 else 'STR32'
            if target not in (0x104674d18,0x1050802e4,0x1050064f0):continue
            k=bisect.bisect_right(starts,at)-1
            rows.append(dict(adrp=hex(at),use=hex(s['address']+4*j),kind=kind,target=hex(target),function_interval=[hex(starts[k]),hex(starts[k+1])],distance=j-i,adrp_word=hex(w),use_word=hex(v)))
linkages=[]
for a,n in [(0x104674d18,0x610),(0x103891dda,32)]:
    seg,=[s for s in segments if s['address']<=a and a+n<=s['address']+s['file_size']]
    off=seg['offset']+a-seg['address'];raw=data[off:off+n]
    linkages.append(dict(address=hex(a),file_offset=off,bytes_hex=raw.hex(),sha256=hashlib.sha256(raw).hexdigest()))
with (HERE/'initial-linkage.json').open('x') as f:json.dump(dict(source_sha256=EXPECTED,linkages=linkages,candidates=rows,limits=['ADRP+limited forward immediate pattern candidates; register clobbers and full function context require disassembly verification.','1050802e4 is not file-backed; initial file read correctly rejected it. Its value must be established through an initializer, not zero-filled.']),f,indent=2)
print(json.dumps(rows,indent=2))
