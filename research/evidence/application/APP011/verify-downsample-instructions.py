"""Read-only verification of the exact original instruction words reviewed."""
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
position = 32
segments = []
for _ in range(struct.unpack_from("<I", data, 16)[0]):
    command, size = struct.unpack_from("<II", data, position)
    assert size >= 8 and position + size <= len(data)
    if command == 0x19:
        _, _, name, vm, vm_size, file_offset, file_size = struct.unpack_from("<II16sQQQQ", data, position)
        segments.append((vm, file_size, file_offset))
    position += size
study = ROOT / "research/evidence/cubase-static/cpr-audio-events-001"
paths = [study / "rate-downsample/pass1" / f"native-{address}.txt"
         for address in ["1003108f0", "100310b84", "10031179c"]]
paths.append(study / "rate-converter/native-10030ffb0.txt")
records = []
for path in paths:
    count = 0
    for match in re.finditer(r"^([0-9a-f]+): ([0-9a-f]{8})\s", path.read_text(), re.M):
        address, word = (int(x, 16) for x in match.groups())
        vm, length, file_offset = next(s for s in segments if s[0] <= address < s[0] + s[1])
        offset = file_offset + address - vm
        assert data[offset:offset + 4] == struct.pack("<I", word)
        count += 1
    assert count > 0
    records.append(dict(path=str(path.relative_to(ROOT)),
                        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                        original_instruction_words_verified=count))
print(json.dumps(dict(source_sha256=source_sha,
                      instructions=sum(x["original_instruction_words_verified"] for x in records),
                      original_bytes=sum(x["original_instruction_words_verified"] * 4 for x in records),
                      records=records), indent=2))
