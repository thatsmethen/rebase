"""Pin original-image vtable and RTTI bytes used by the bounded stream finding."""
import hashlib, struct
import derive as d

def raw(va, size):
    off = d.offset(va)
    value = d.data[off:off+size]
    assert len(value) == size
    return dict(address=hex(va), file_offset=off, length=size,
                bytes_hex=value.hex(), sha256=hashlib.sha256(value).hexdigest())

def pointer(va, expected):
    record = raw(va, 8)
    value = int.from_bytes(bytes.fromhex(record['bytes_hex']), 'little')
    assert value == expected, (hex(va), hex(value), hex(expected))
    return dict(**record, target=hex(value))

def rtti(vtable, expected):
    typeinfo = struct.unpack_from('<Q', d.data, d.offset(vtable-8))[0]
    name = struct.unpack_from('<Q', d.data, d.offset(typeinfo+8))[0]
    off = d.offset(name)
    text = d.data[off:d.data.index(b'\0', off)].decode()
    assert text == expected, text
    return dict(vtable=hex(vtable), typeinfo_pointer=pointer(vtable-8, typeinfo),
                name_pointer=pointer(typeinfo+8, name), name=raw(name, len(text)+1), text=text)

slots = []
for table, mapping in {
    0x104466150: {0xf8:0x10036a52c},
    0x1044662f0: {0x40:0x10036afc8},
    0x104466378: {0x10:0x10036d22c,0x18:0x10036d668,0x20:0x10036d848,0x28:0x10036d87c,0x30:0x10036d154},
    0x1044663c8: {0xc8:0x10036dddc},
    0x1044664f0: {0xd0:0x1003704bc,0xd8:0x10036e858,0x168:0x10036eff0,0x178:0x10036f89c,
                  0x180:0x10036fa3c,0x188:0x10036fb74,0x1a8:0x10036fea0},
    0x104462178: {0xf8:0x10033a4f8,0x118:0x100113068},
    0x104e31300: {0x108:0x103104730,0x140:0x103104dd0,0x148:0x1030f9b20},
    0x104e31478: {0x10:0x1031041f8,0x18:0x103104208},
}.items():
    for slot, target in mapping.items():
        slots.append(dict(vtable=hex(table), slot=hex(slot), **pointer(table+slot, target)))

d.save('bound-source-bytes.json', dict(source=str(d.SOURCE), source_sha256=d.EXPECTED,
    method='Mach-O segment mapping; exact on-disk pointer words, not initialized Ghidra memory.',
    slots=slots, rtti=[rtti(0x104466378,'N9Steinberg24AudioClusterAccessStreamE'),
                      rtti(0x1044664f0,'N9Steinberg13AudioAccessorE')],
    corrections=['secondary-vtable-candidates.json is a mechanical address inventory crossing a vtable boundary. '
                 'AudioCluster secondary interface starts1044662f0;104466368/370 are the next header; '
                 'AudioClusterAccessStream starts104466378. Entries past the boundary are not cluster-interface methods.',
                 'The clone metadata interval10036dddc..10036de90 includes a separate registration routine '
                 'starting10036de2c after the clone RET at10036de28; only the preceding body establishes copying.'],
    target_executed=False))
print('Pinned', len(slots), 'vtable slots and two RTTI names')
