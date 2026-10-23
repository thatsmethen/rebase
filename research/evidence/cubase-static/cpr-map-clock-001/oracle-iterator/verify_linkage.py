#!/usr/bin/env python3
"""Recheck source-bound vtable slots, reused instructions and native helpers."""
from pathlib import Path
import hashlib
import json
import re
import struct
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
manifest = json.loads((HERE / "derivation.json").read_text())
source = Path(manifest["source"])
before = source.stat()
data = source.read_bytes()
assert hashlib.sha256(data).hexdigest() == manifest["source_sha256"]


def offset(va):
    for s in manifest["segments"]:
        if s["address"] <= va < s["address"] + s["file_size"]:
            return s["offset"] + va - s["address"]
    raise ValueError(hex(va))


def check_words(text):
    words = re.findall(r"^([0-9a-f]+):\s+([0-9a-f]{8})\s", text, re.M)
    for a, w in words:
        assert struct.unpack_from("<I", data, offset(int(a, 16)))[0] == int(w, 16)
    return len(words)


starts, va, delta, shift = [], 0x100000000, 0, 0
fs = manifest["function_starts"]
for byte in data[fs["offset"]:fs["offset"] + fs["length"]]:
    delta |= (byte & 127) << shift
    if byte & 128:
        shift += 7
    else:
        if not delta:
            break
        va += delta
        starts.append(va)
        delta = shift = 0

slots = []
for slot, target in [(0xd0, 0x1016c3478), (0xd8, 0x1016c36f0), (0xe0, 0x1016c37d4),
                     (0xe8, 0x1016c38b8), (0xf8, 0x1016c34b8), (0x100, 0x1016c35c4),
                     (0x108, 0x1016c3ee0), (0x140, 0x1016c3c18), (0x148, 0x1016c3d34)]:
    va = 0x104676228 + slot
    raw = data[offset(va):offset(va) + 8]
    assert struct.unpack("<Q", raw)[0] == target
    slots.append({"vtable": "0x104676228", "slot": hex(slot), "source_address": hex(va),
                  "source_offset": offset(va), "bytes_hex": raw.hex(), "target": hex(target)})

helpers = []
for entry in [0x1016c34b0, 0x1016c3c18, 0x1016c3d34]:
    end = starts[starts.index(entry) + 1]
    raw = data[offset(entry):offset(entry) + end - entry]
    args = ["/Library/Developer/CommandLineTools/usr/bin/llvm-objdump", "-d",
            "--start-address=" + hex(entry), "--stop-address=" + hex(end), str(source)]
    text = subprocess.run(args, text=True, capture_output=True, check=True).stdout
    name = f"native-support-{entry:x}.txt"
    (HERE / name).write_text(text)
    count = check_words(text)
    assert count * 4 == len(raw)
    helpers.append({"entry": hex(entry), "end_lc_function_starts": hex(end),
                    "source_offset": offset(entry), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                    "native_file": name, "native_words_checked": count, "command": args,
                    "scope": "Native-only original-image helper check; no new REA or execution"})

reused = []
paths = ["research/evidence/cubase-static/cpr-signature-001/pass11/native-1016c137c.txt"]
paths += ["research/evidence/cubase-static/cpr-audio-timing-001/native-" + a + ".txt"
          for a in ["1016c31b0", "1016c36f0", "1016c38b8", "1016c1424", "1016c3ee0",
                    "10173b064", "10173ad50", "10173b1d4"]]
for path in paths:
    p = ROOT / path
    reused.append({"path": path, "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                   "native_words_checked": check_words(p.read_text())})
after = source.stat()
assert (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (
    after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
record = {"source_sha256": manifest["source_sha256"], "slots": slots, "support_helpers": helpers,
          "reused_original_native_files": reused, "target_executed": False}
(HERE / "iterator-linkage-checks.json").write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps({"slots": len(slots), "support_words": sum(x["native_words_checked"] for x in helpers),
                  "reused_words": sum(x["native_words_checked"] for x in reused)}))
