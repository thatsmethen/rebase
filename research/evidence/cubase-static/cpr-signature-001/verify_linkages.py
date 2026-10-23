"""Verify selected signature RTTI, literal and initializer links; target stays inert."""
import hashlib
import json
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = ROOT / 'research/targets/derived/Cubase15-arm64'
EXPECTED = 'dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb'
before = SOURCE.stat()
data = SOURCE.read_bytes()
assert hashlib.sha256(data).hexdigest() == EXPECTED
segments = []
p = 32
for _ in range(struct.unpack_from('<I', data, 16)[0]):
    command, size = struct.unpack_from('<II', data, p)
    if command == 0x19:
        v = struct.unpack_from('<II16sQQQQIIII', data, p)
        segments.append(dict(name=v[2].rstrip(b'\0').decode(), address=v[3],
                             offset=v[5], file_size=v[6], vm_size=v[4]))
    p += size

def offset(a, n):
    s, = [s for s in segments if s['address'] <= a and a+n <= s['address']+s['file_size']]
    return s['offset'] + a-s['address']

def read(a, n):
    o = offset(a, n)
    return data[o:o+n]

def u64(a):
    return struct.unpack('<Q', read(a, 8))[0]

def region(a, n):
    b = read(a, n)
    return dict(address=hex(a), source_file_offset=offset(a, n), length=n,
                bytes_hex=b.hex(), sha256=hashlib.sha256(b).hexdigest())

classes = [
    ('MSignatureTrackEvent', 0x1046742a0, 0x104673668,
     {0x98:0x101730874, 0xa0:0x1017311d8, 0x268:0x1017015b8,
      0x258:0x10174a698, 0x4f0:0x10174aa6c, 0x550:0x101734fd8,
      0x5f8:0x10174c194, 0x600:0x10172fb58, 0x608:0x10172fff4}),
    ('MTimeSignatureEvent', 0x104674250, 0x104673050,
     {0x98:0x10172b08c, 0xa0:0x10172b164, 0xa8:0x10172b250,
      0xb0:0x10172b378, 0xd8:0x10172adf0, 0xe0:0x10172ae80,
      0x498:0x101734b80, 0x4a0:0x101734b88, 0x4a8:0x10172aec0}),
    ('FAttributes', 0x104e45d20, 0x104e45ad8, {0x98:0x1031a2cf0, 0xa0:0x1031a3024}),
    ('FXmlInstance', 0x104e46818, 0x104e46730, {0xd0:0x1031ae4e8}),
    ('MTrackList', 0x104679258, 0x104678ea8, {0xf0:0x101758eec,0x150:0x1000fd154}),
    ('MTrackListAccessor', 0x104679240, 0x104679050,
     {0x120:0x101716814, 0x128:0x101716a74, 0x150:0x101716db0}),
    ('MListAccessor', 0x1046705b0, 0x1046703b8,
     {0x120:0x101716814, 0x128:0x101716a74, 0x150:0x101716db0}),
    ('MTrackVariationCollection', 0x1046821b8, 0x104682030, {0x98:0x1017a43f0}),
    ('MTrackVariation', 0x1046821a0, 0x104681f50, {0x98:0x1017a4250}),
]
rows = []
for name, ti, vt, slots in classes:
    mangled = f'N9Steinberg{len(name)}{name}E'.encode()+b'\0'
    sa = u64(ti+8)
    assert read(sa, len(mangled)) == mangled
    assert u64(vt-16) == 0 and u64(vt-8) == ti
    r = dict(class_name=name, name=region(sa,len(mangled)),
             typeinfo_name_pointer=region(ti+8,8), vtable_prefix=region(vt-16,16),
             primary_vtable=hex(vt), selected_slots=[])
    for slot, expected in slots.items():
        assert u64(vt+slot) == expected, (name, hex(slot), hex(u64(vt+slot)))
        r['selected_slots'].append(dict(slot=hex(slot), target=hex(expected), **region(vt+slot,8)))
    rows.append(r)
strings = []
for address, name in [
    (0x1038d9918,'SignatureEvent'), (0x1038948fb,'MTimeSignatureEvent'),
    (0x1038b554e,'MSignatureTrackEvent'), (0x103891aea,'Bar'),
    (0x1038cbc95,'Numerator'), (0x1038cbc9f,'Denominator'),
    (0x1038d98b0,'SubNumerator1'), (0x1038d98be,'SubNumerator2'),
    (0x1038d98cc,'SubNumerator3'), (0x1038d98da,'TimeSignatureDisplayFlags'),
    (0x103892747,'Position'), (0x103891e98,'Flags'),
    (0x1038917f6,'Start'), (0x103891e63,'Length'), (0x103891ab2,'Offset'),
    (0x103891ebd,'Additional Attributes'),
    (0x1038fe6fb,'FXmlObject'), (0x1038da6ca,'MTrackVariationCollection'),
    (0x103891a55,'MDataNode'),
]:
    expected = name.encode()+b'\0'
    assert read(address, len(expected)) == expected
    strings.append(dict(value=name, **region(address,len(expected))))

# Derive the complete immediate value from actual MOVZ/MOVK W instructions.
# BSS addresses are destinations of native stores, not file-backed data.
initializers = []
for name, first, second, store, address, expected in [
    ('track flags attribute',0x101737548,0x10173754c,0x101737550,0x10507ff34,0x53636f4c),
    ('old signature attribute',0x101737554,0x101737558,0x101737560,0x105006320,0x6b696c43),
    ('replacement container attribute',0x101737564,0x101737568,0x101737570,0x105006324,0x736b6c43),
    ('event position attribute',0x1017375e0,0x1017375e4,0x1017375e8,0x10507ff38,0x504c4153),
]:
    w0, w1 = struct.unpack('<I',read(first,4))[0], struct.unpack('<I',read(second,4))[0]
    assert w0 & 0xff800000 == 0x52800000 and w1 & 0xff800000 == 0x72800000
    assert w0 & 31 == w1 & 31 == 8
    value = ((w0 >> 5)&65535) << (16*((w0>>21)&3))
    shift = 16*((w1>>21)&3)
    value = (value & ~(65535<<shift)) | (((w1>>5)&65535)<<shift)
    assert value == expected
    initializers.append(dict(purpose=name, global_destination=hex(address),
        value_u32=expected, value_hex=hex(expected), serialized_big_endian_bytes=expected.to_bytes(4,'big').hex(),
        immediate_instruction_ranges=[region(first,4),region(second,4)],
        store_instruction=region(store,4),
        limit='Store destination is additionally checked in retained original native disassembly; current runtime BSS value is not observed.'))
tiny_functions = []
for address, expected, meaning in [
    (0x1000fd154,'c0035fd6','RET only: MTrackList +150 called while binding a null-list variation; no target memory stores.'),
    (0x10174aa6c,'003440f9c0035fd6','LDR X0,[X0,#0x68]; RET: signature +4f0 getter, no target memory stores.'),
]:
    assert read(address,len(bytes.fromhex(expected))).hex() == expected
    tiny_functions.append(dict(instructions=meaning, **region(address,len(bytes.fromhex(expected)))))
jump_table = region(0x103c7a6d2, 8)
jump_table['use'] = 'Original 1031ab5b8 reads uint16 type, subtracts 1, checks <=7, then branches to 1031ab678 + 4*uint8(table[type-1]). Raw REA image does not map this external table.'
jump_table['selected_targets'] = []
for typ, expected in [(1,0x1031ab6e8),(2,0x1031ab760),(4,0x1031ab724),(8,0x1031ab944)]:
    delta = read(0x103c7a6d2+typ-1,1)[0]
    assert 0x1031ab678+4*delta == expected
    jump_table['selected_targets'].append(dict(type=typ,delta_words=delta,target=hex(expected)))
after = SOURCE.stat()
assert (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns) == (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)
report = dict(source=str(SOURCE),source_sha256=EXPECTED,source_stable=True,classes=rows,
              strings=strings,initializer_constants=initializers,named_attribute_type_dispatch=jump_table,
              exact_tiny_function_bytes=tiny_functions,
              limits=['Only selected slots are asserted; raw locator neighboring words are not all vtable members.',
                      'Class/vtable and initializer links establish native static dispatch. They do not observe runtime relocation, compatibility globals, current track variations or complete host restoration behavior.',
                      'No BSS globals are read as file-backed bytes. No target code is executed.'])
(HERE/'linkage-provenance.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(passed=True,classes=len(rows),strings=len(strings),initializers=len(initializers))))
