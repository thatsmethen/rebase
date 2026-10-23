"""Exact raw code derivatives for bounded static REA queries; never executes target."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess

HERE = Path(__file__).resolve().parent / "host-gate-service/pass8"
ROOT = HERE.parents[6]
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

rows = []
for address in (0x1016e9a18, 0x101c245e4, 0x101c247b0):
    index = starts.index(address)
    end = starts[index+1]
    segment, = [s for s in segments if s["address"] <= address and end <= s["address"]+s["file_size"]]
    offset = segment["offset"] + address - segment["address"]
    raw = data[offset:offset+end-address]
    name = f"function-{address:x}.arm64.bin"
    with (HERE / name).open("xb") as output:
        output.write(raw)
    command = ["/Library/Developer/CommandLineTools/usr/bin/llvm-objdump", "-d",
               "--start-address="+hex(address), "--stop-address="+hex(end), str(SOURCE)]
    result = subprocess.run(command, text=True, capture_output=True, check=True)
    native_name = f"native-{address:x}.txt"
    (HERE / native_name).write_text(result.stdout)
    rows.append(dict(entry=hex(address), next_declared_function_start=hex(end),
                     source_file_offset=offset, length=len(raw), raw_file=name,
                     raw_sha256=hashlib.sha256(raw).hexdigest(), original_segment=segment["name"],
                     original_native_disassembly=native_name, native_command=command,
                     native_stdout_sha256=hashlib.sha256(result.stdout.encode()).hexdigest(),
                     boundary="LC_FUNCTION_STARTS interval, not proof of exact function body; exception tails may be disconnected"))
after = SOURCE.stat()
assert (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (
    after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
(HERE / "derivation.json").write_text(json.dumps(dict(
    scope="Exact unmodified byte derivatives for static decompilation only",
    source=str(SOURCE), source_sha256=EXPECTED, source_bytes=len(data), segments=segments,
    function_starts=dict(offset=fs_offset, length=fs_size,
                         sha256=hashlib.sha256(data[fs_offset:fs_offset+fs_size]).hexdigest()),
    derivatives=rows,
    losses=["No Mach-O headers, imports, global data, typeinfo, vtables, relocations, unwind metadata or neighboring functions are mapped in each raw image.",
            "Original linked entry addresses are preserved, so PC-relative references still calculate original addresses, but their external bytes are unavailable.",
            "No fake imports, data patches, additional functions or modified instructions are introduced.",
            "Raw analysis output must be correlated with separately retained original-image evidence; this is not whole-image decompilation."]), indent=2)+"\n")
print(json.dumps({"functions":len(rows),"total_bytes":sum(r["length"] for r in rows)}))
