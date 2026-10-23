"""Read-only original Mach-O checks for the independently reviewed gain paths."""
from pathlib import Path
import hashlib
import json
import re
import struct

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
STUDY = ROOT / "research/evidence/cubase-static/cpr-audio-events-001"
TARGET = ROOT / "research/targets/derived/Cubase15-arm64"
EXPECTED = "dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb"


def record(path):
    data = path.read_bytes()
    return dict(path=str(path.relative_to(ROOT)), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def main():
    data = TARGET.read_bytes()
    assert hashlib.sha256(data).hexdigest() == EXPECTED
    assert struct.unpack_from("<I", data)[0] == 0xfeedfacf
    segments = []
    offset = 32
    for _ in range(struct.unpack_from("<I", data, 16)[0]):
        command, size = struct.unpack_from("<II", data, offset)
        if command == 0x19:
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from("<QQQQ", data, offset + 24)
            segments.append((vmaddr, fileoff, filesize))
        offset += size

    def read(address, count):
        for start, fileoff, size in segments:
            if start <= address and address + count <= start + size:
                return data[fileoff + address - start:fileoff + address - start + count]
        raise ValueError(hex(address))

    relative = [
        "rate-converter/native-10033035c.txt",
        "rate-converter/native-100326318.txt",
        "accessor-format-order/pass1/native-100326c4c.txt",
        "rate-converter/native-100330cd4.txt",
        "rate-converter/native-10032ddd0.txt",
        "rate-converter/native-10032f014.txt",
        "accessor-format-order/pass1/native-1003312c4.txt",
        "accessor-format-order/pass1/native-1037d88d4.txt",
        "segment-consumer/native-10036fb74.txt",
        "accessor-seek-state/pass1/native-10036eff0.txt",
        "accessor-gain-order/pass1/native-10032d2a8.txt",
        "accessor-gain-order/pass2/native-100333200.txt",
        "accessor-gain-order/pass2/native-1037c3b34.txt",
        "placed-rate-ownership/pass1/native-100370538.txt",
    ]
    checked = []
    for name in relative:
        path = STUDY / name
        words = re.findall(r"^([0-9a-f]+):\s+([0-9a-f]{8})\s", path.read_text(), re.M)
        assert words, name
        for address, word in words:
            assert read(int(address, 16), 4) == int(word, 16).to_bytes(4, "little"), (name, address)
        checked.append(dict(**record(path), instructions=len(words), original_bytes=4 * len(words)))
    cells = [(0x1039346b8, 3, 0x10032d2d4, 0x10032d4a4),
             (0x103934718, 2, 0x10032ddf0, 0x10032e4fc),
             (0x103934718, 3, 0x10032ddf0, 0x10032e538)]
    bindings = []
    for table, index, base, expected in cells:
        # The original LDRH / ADD LSL #2 dispatch uses unsigned halfword
        # instruction offsets relative to an ADR code address, not the table.
        address = table + index * 2
        actual = base + int.from_bytes(read(address, 2), "little") * 4
        assert actual == expected, (hex(address), hex(actual), hex(expected))
        bindings.append(dict(cell=f"0x{address:x}", table=f"0x{table:x}",
                             code_base=f"0x{base:x}", target=f"0x{actual:x}"))
    report = dict(schema_version=1, status="passed", target_executions=0,
        scope="Exact retained original instruction words and three dispatch cells; this does not execute native code.",
        target=record(TARGET), verifier=record(Path(__file__)), functions=checked, jump_bindings=bindings,
        instruction_count=sum(x["instructions"] for x in checked),
        original_bytes=sum(x["original_bytes"] for x in checked),
        count_scope="Rows in retained disassembly ranges; not a unique-address claim.",
        initial_verifier_correction="An unpublished first execution incorrectly assumed signed32 table-relative cells and failed at the first dispatch assertion. Original LDRH plus shifted code-relative dispatch was then inspected and used here; no expected target or candidate was changed.")
    output = HERE / "gain-instruction-verification.json"
    with output.open("x") as stream:
        json.dump(report, stream, indent=2); stream.write("\n")
    print(json.dumps({"output":record(output), "instruction_count":report["instruction_count"]}))


if __name__ == "__main__":
    main()
