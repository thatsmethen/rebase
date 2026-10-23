"""Read-only original-byte verification for the bounded Ambi process-state path."""
import hashlib
import json
import re
import struct
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
derivation = json.loads((BASE / 'arm64-derivation.json').read_text())
thin_path, fat_path = Path(derivation['derived_path']), Path(derivation['source_path'])
stats = {p: p.stat() for p in (thin_path, fat_path)}
thin, fat = thin_path.read_bytes(), fat_path.read_bytes()
sha = lambda b: hashlib.sha256(b).hexdigest()
assert sha(thin) == derivation['derived_sha256']
assert sha(fat) == derivation['source_sha256']
fat_offset = derivation['source_offset']
assert thin == fat[fat_offset:fat_offset + len(thin)]
segments = []
position = 32
for _ in range(struct.unpack_from('<I', thin, 16)[0]):
    command, size = struct.unpack_from('<II', thin, position)
    if command == 0x19:
        v = struct.unpack_from('<II16sQQQQIIII', thin, position)
        segments.append(dict(name=v[2].rstrip(b'\0').decode(), address=v[3],
                             vm_size=v[4], offset=v[5], file_size=v[6]))
    if command == 0x26:
        _, _, fs_offset, fs_size = struct.unpack_from('<IIII', thin, position)
    position += size
starts, delta, shift = [], 0, 0
address = next(s['address'] for s in segments if s['name'] == '__TEXT')
for byte in thin[fs_offset:fs_offset + fs_size]:
    delta |= (byte & 127) << shift
    if byte & 128:
        shift += 7
    else:
        if not delta:
            break
        address += delta
        starts.append(address)
        delta = shift = 0


def mapping(start, end):
    segment, = [s for s in segments if s['address'] <= start and end < s['address'] + s['file_size']]
    offset = segment['offset'] + start - segment['address']
    data = thin[offset:offset + end + 1 - start]
    return dict(start=hex(start), end_inclusive=hex(end), length=len(data),
                thin_offset=offset, universal_offset=offset + fat_offset, sha256=sha(data))


records = []
for name in ['processor-process-thunk.json', 'processor-process-function.json',
             'processor-constructor-function.json', 'direction-parameter-consumer.json',
             'float-bypass-process-function.json', 'float-channel-permutation-function.json',
             'double-channel-permutation-function.json', 'float-buffer-copy-function.json',
             'double-buffer-copy-function.json', 'float-conversion-process-function.json',
             'double-conversion-process-function.json']:
    artifact = json.loads((BASE / name).read_text())
    record = artifact.get('structuredContent', artifact)
    result = record['normalized_result']
    assembly = {int(line.split(':', 1)[0], 16): line.split(':', 1)[1].strip() for line in result['assembly']}
    native = {}
    ranges = []
    commands = []
    for i, interval in enumerate(result['procedure']['body']['ranges']):
        start, end = int(interval['start'], 16), int(interval['end'], 16)
        ranges.append(mapping(start, end))
        command = ['/Library/Developer/CommandLineTools/usr/bin/llvm-objdump', '-d',
                   '--start-address=' + hex(start), '--stop-address=' + hex(end + 1), str(thin_path)]
        output = subprocess.run(command, check=True, capture_output=True, text=True).stdout
        native_file = f'native-{result["procedure"]["address"][2:]}-{i}.txt'
        (HERE / native_file).write_text(output)
        commands.append(dict(command=command, output=native_file, sha256=sha(output.encode())))
        for m in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(.+)$', output, re.M):
            addr, word = int(m[1], 16), int(m[2], 16)
            offset = mapping(addr, addr + 3)['thin_offset']
            assert thin[offset:offset + 4] == word.to_bytes(4, 'little')
            native[addr] = dict(address=hex(addr), word=m[2], native=m[3].strip(), rea=assembly[addr])
    assert set(assembly) == set(native)
    records.append(dict(file=name, evidence_id=record['evidence_id'], file_sha256=sha((BASE/name).read_bytes()),
                        ranges=ranges, commands=commands, instructions=list(native.values())))

entry = 0x154b64
end = starts[starts.index(entry) + 1]
raw_range = mapping(entry, end - 1)
raw = thin[raw_range['thin_offset']:raw_range['thin_offset'] + raw_range['length']]
raw_name = 'double-bypass.arm64.bin'
with (HERE / raw_name).open('xb') as output:
    output.write(raw)
command = ['/Library/Developer/CommandLineTools/usr/bin/llvm-objdump', '-d',
           '--start-address=' + hex(entry), '--stop-address=' + hex(end), str(thin_path)]
output = subprocess.run(command, check=True, capture_output=True, text=True).stdout
(HERE / 'native-double-bypass.txt').write_text(output)
slots = []
vt = json.loads((BASE / 'algorithm-vtables.json').read_text())
vr = vt.get('structuredContent', vt)['normalized_result']
memory = bytes.fromhex(vr['bytes_hex'])
for base, kind in [(0x1d7620, 'double'), (0x1d7740, 'float')]:
    for slot, role in [(0x58, 'conversion'), (0x90, 'bypass')]:
        addr = base + slot
        r = mapping(addr, addr + 7)
        data = thin[r['thin_offset']:r['thin_offset'] + 8]
        assert data == memory[addr - 0x1d7620:addr - 0x1d7620 + 8]
        slots.append(dict(precision=kind, role=role, slot=hex(slot), target=hex(int.from_bytes(data, 'little')), **r))
for p, before in stats.items():
    after = p.stat()
    assert (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (
        after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
report = dict(scope='Static original-byte verification; target code never executed',
              source=derivation, segments=segments, function_starts=dict(offset=fs_offset, length=fs_size),
              retained_functions=records, dispatch_slots=slots,
              double_bypass_derivative=dict(**raw_range, raw_file=raw_name,
                  next_declared_start=hex(end), boundary='LC_FUNCTION_STARTS interval, not automatically proved body',
                  command=command, native_sha256=sha(output.encode())),
              total_retained_instructions=sum(len(r['instructions']) for r in records),
              source_stable=True, warning='Full REA vtable memory includes loader fixups elsewhere; only listed slots are asserted byte-identical.')
(HERE / 'byte-provenance.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'retained_instructions':report['total_retained_instructions'], 'double_bypass':raw_range, 'slots':slots}))
