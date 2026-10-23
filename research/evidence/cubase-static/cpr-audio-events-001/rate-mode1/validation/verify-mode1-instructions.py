"""Read-only original Mach-O verification for the independent mode1 oracle."""
import hashlib
import json
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[4]
source = ROOT / "research/targets/derived/Cubase15-arm64"
data = source.read_bytes()
source_sha = hashlib.sha256(data).hexdigest()
assert source_sha == "dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb"
assert struct.unpack_from("<I", data)[0] == 0xfeedfacf
position, segments = 32, []
for _ in range(struct.unpack_from("<I", data, 16)[0]):
    command, size = struct.unpack_from("<II", data, position)
    assert size >= 8 and position + size <= len(data)
    if command == 0x19:
        _, _, name, vm, vm_size, file_offset, file_size = struct.unpack_from("<II16sQQQQ", data, position)
        segments.append((vm, file_size, file_offset))
    position += size


def original(address, count):
    vm, size, offset = next(s for s in segments if s[0] <= address and address + count <= s[0] + s[1])
    return data[offset + address - vm:offset + address - vm + count]


study = ROOT / "research/evidence/cubase-static/cpr-audio-events-001"
records = []
for folder, address in [
    ("rate-mode1/pass1", "10030a748"), ("rate-mode1/pass1", "10030a7a0"),
    ("rate-mode1/pass1", "10030aeb8"), ("rate-mode1/pass2", "10030a974"),
    ("rate-converter", "10030af58"), ("rate-converter", "10030b8a8"),
]:
    path = study / folder / f"native-{address}.txt"
    count = 0
    for match in re.finditer(r"^([0-9a-f]+): ([0-9a-f]{8})\s", path.read_text(), re.M):
        at, word = (int(x, 16) for x in match.groups())
        assert original(at, 4) == struct.pack("<I", word)
        count += 1
    assert count
    records.append(dict(path=str(path.relative_to(ROOT)), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                        original_instruction_words_verified=count))
lane = original(0x1039168F0, 8)
assert struct.unpack("<ii", lane) == (1, 2)
print(json.dumps(dict(source_sha256=source_sha,
    instructions=sum(x["original_instruction_words_verified"] for x in records),
    original_bytes=sum(x["original_instruction_words_verified"] * 4 for x in records),
    generator_simd_initial_indices=dict(address="1039168f0", bytes_hex=lane.hex(), values=[1, 2]),
    beta_correction="Original MOVKs encode8.96 (4021eb851eb851ec), half4.48 (4011eb851eb851ec); early descriptive8.6 label is rejected.",
    records=records), indent=2))
