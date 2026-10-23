"""Read-only original-byte check for independently reviewed timeline intervals."""
from pathlib import Path
import hashlib
import json
import mmap
import re
import struct

ROOT = Path(__file__).resolve().parents[4]
TARGET = ROOT / "research/targets/derived/Cubase15-arm64"
STUDY = Path("research/evidence/cubase-static/cpr-audio-events-001")
PATHS = [
    STUDY / "live-binding/pass21/native-101d3eb24.txt",
    STUDY / "live-binding/pass21/native-101d3ea38.txt",
    STUDY / "live-binding/pass20/native-101d3e704.txt",
    STUDY / "timeline-provider/pass3/native-1001f9090.txt",
    STUDY / "timeline-provider/pass3/native-101d3e5a8.txt",
    STUDY / "timeline-provider/pass4/native-101d42e70.txt",
    STUDY / "timeline-provider/pass2/native-101a17cd4.txt",
    STUDY / "timeline-provider/pass2/native-101a17d08.txt",
    STUDY / "timeline-provider/pass2/native-101a17d1c.txt",
]


def main():
    records = []
    with TARGET.open("rb") as source, mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ) as data:
        target_digest = hashlib.sha256(data).hexdigest()
        assert target_digest == "dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb"
        magic, _, _, _, count, _, _, _ = struct.unpack_from("<8I", data)
        assert magic == 0xfeedfacf
        command, segments = 32, []
        for _ in range(count):
            kind, size = struct.unpack_from("<II", data, command)
            assert size >= 8
            if kind == 0x19:
                address, _, offset, length = struct.unpack_from("<4Q", data, command + 24)
                segments.append((address, offset, length))
            command += size
        for path in PATHS:
            original = (ROOT / path).read_bytes()
            words = re.findall(rb"^\s*([0-9a-f]{9,16}):\s+([0-9a-f]{8})\s", original, re.M)
            assert words, path
            for address, word in words:
                address, word = int(address, 16), int(word, 16)
                locations = [offset + address - vm for vm, offset, length in segments if vm <= address < vm + length - 3]
                assert len(locations) == 1, hex(address)
                assert data[locations[0]:locations[0] + 4] == struct.pack("<I", word), hex(address)
            records.append(dict(path=str(path), bytes=len(original),
                                sha256=hashlib.sha256(original).hexdigest(),
                                checked_words=len(words),
                                first=f"0x{int(words[0][0], 16):x}",
                                last=f"0x{int(words[-1][0], 16):x}"))
    report = dict(schema_version=1, target_path=str(TARGET.relative_to(ROOT)),
                  target_sha256=target_digest, target_executed=False,
                  verified_original_words=sum(row["checked_words"] for row in records),
                  records=records)
    destination = Path(__file__).with_name("timeline-instruction-verification.json")
    with destination.open("x") as output:
        json.dump(report, output, indent=2)
        output.write("\n")
    print(json.dumps(dict(intervals=len(records), words=report["verified_original_words"],
                          sha256=hashlib.sha256(destination.read_bytes()).hexdigest())))


if __name__ == "__main__":
    main()
