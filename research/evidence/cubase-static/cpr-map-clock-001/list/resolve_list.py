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


def span(a,n):
    s,=[s for s in segments if s['address']<=a and a+n<=s['address']+s['file_size']]
    off=s['offset']+a-s['address'];raw=data[off:off+n]
    return dict(address=hex(a),source_file_offset=off,bytes_hex=raw.hex(),sha256=hashlib.sha256(raw).hexdigest())
def u64(a):return struct.unpack('<Q',bytes.fromhex(span(a,8)['bytes_hex']))[0]
vt=0x104675ec8
ti=u64(vt-8);st=u64(ti+8)
raw=span(st,128);name=bytes.fromhex(raw['bytes_hex']).split(b'\0')[0].decode()
print('list',hex(vt),hex(ti),name)
slots=[]
for slot in (0,8,0x10,0x60,0x68,0xd0,0xd8,0xe0,0xf0,0xf8,0x128,0x150,0x158):
    q=span(vt+slot,8);q.update(slot=hex(slot),target=hex(u64(vt+slot)));slots.append(q)
print(json.dumps(slots,indent=2))
mod=[];o=32
for _ in range(struct.unpack_from('<I',data,16)[0]):
    c,n=struct.unpack_from('<II',data,o)
    if c==0x19:
        ns=struct.unpack_from('<I',data,o+64)[0]
        for k in range(ns):
            q=o+72+80*k;v=struct.unpack_from('<16s16sQQIIIIIIII',data,q)
            if v[0].rstrip(b'\0')!=b'__mod_init_func':continue
            for z in range(v[4],v[4]+v[3],8):
                if struct.unpack_from('<Q',data,z)[0]==0x1017411c8:mod.append(dict(section_address=hex(v[2]),file_offset=z,address=hex(v[2]+z-v[4]),bytes_hex=data[z:z+8].hex()))
    o+=n
with (HERE/'tempo-list-linkage.json').open('x') as f:json.dump(dict(source_sha256=EXPECTED,vtable=hex(vt),typeinfo=span(ti,24),typeinfo_name=raw,decoded_name=name,slots=slots,global_key_initializer_registration=mod,global_key_assignment='10174242c..434 sets1050802e4 to0x6b636f4c'),f,indent=2)
print('module initializers',mod)
