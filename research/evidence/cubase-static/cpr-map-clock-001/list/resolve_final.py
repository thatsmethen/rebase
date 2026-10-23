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

rows=[]
for vt,slots in [(0x104676bb0,[0x250]),(0x104674d18,[0x258,0x268,0x2e0,0x550,0x580,0x588,0x5f8]),(0x104675ec8,[0x58,0x60,0x68,0xd0,0xd8,0xe0,0xf0,0x100,0x150,0x158]),(0x104676228,[0xd0,0xd8,0xe0,0xf8,0x100,0x120,0x128,0x150]),(0x1046746f0,[0x40,0x80,0xe0,0x288,0x348,0x3a8]),(0x104666b88,[0xd0,0xd8,0x110]),(0x104e31768,[0x10])]:
    for slot in slots:
        q=span(vt+slot,8);q.update(vtable=hex(vt),slot=hex(slot),target=hex(u64(vt+slot)));rows.append(q)
result=dict(source_sha256=EXPECTED,slots=rows,collection_constructor_literal=span(0x103915740,8),tempo_start_class_name=span(0x103891f2e,32),key_initializer_assignment=span(0x101742408,48),tempo_factory_registration=span(0x1017424d8,44),limitation="No claim that1017411c8 is a Mach-O module initializer; it is called by1017407c4 and contains both key initialization and tempo class factory registration.")
(HERE/'final-linkage.json').write_text(json.dumps(result,indent=2)+'\n')
print(len(rows),'pointer slots bound')
