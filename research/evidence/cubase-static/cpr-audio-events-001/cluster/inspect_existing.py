#!/usr/bin/env python3
"""Exact shipped fixture correlation and bounded original ARM64 candidates.

No target execution; no field semantics are inferred from numerical matches.
New outputs are exclusive-create. Original CPR/Mach-O files are read only.
"""
from pathlib import Path
import hashlib
import json
import re
import struct
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
SOURCE = ROOT / "research/targets/derived/Cubase15-arm64"
EXPECTED = "dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb"
sha = lambda data: hashlib.sha256(data).hexdigest()


def read(path):
    before = path.stat(); data = path.read_bytes(); after = path.stat()
    identity = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
    assert identity(before) == identity(after) and len(data) == before.st_size
    return data


def write(name, value):
    with (HERE / name).open("x") as stream:
        json.dump(value, stream, indent=2); stream.write("\n")


def objects(value):
    if isinstance(value, dict):
        if value.get("kind") == "object": yield value
        for child in value.values(): yield from objects(child)
    elif isinstance(value, list):
        for child in value: yield from objects(child)


fixtures = []
for path in sorted((ROOT / "research/evidence/cubase-static/cpr-objects-001/fixtures").glob("*-v09.json")):
    fixture_bytes = read(path); fixture = json.loads(fixture_bytes)
    data = read(ROOT / fixture["source"])
    assert sha(data) == fixture["sha256"] and len(data) == fixture["bytes"]
    clusters = []
    for cluster in [obj for obj in objects(fixture) if obj["class"] == "AudioCluster"]:
        vectors = cluster["decoded"]["vectors"]
        assert cluster["version"] == 0 and cluster["decoded"]["consumed_exactly"]
        assert [(v["unbound_word"], v["count"]) for v in vectors] == [(2, 1), (1, 1)]
        file, = vectors[0]["objects"]; segment, = vectors[1]["objects"]
        assert file["class"] == "AudioFile" and file["version"] == 1 and file["body_bytes"] == 26
        assert segment["class"] == "AClusterSegment" and segment["version"] == 0 and segment["body_bytes"] == 28
        for obj in [cluster, file, segment]:
            assert struct.unpack_from(">I", data, obj["size_offset"])[0] == obj["body_bytes"]
            assert obj["body_offset"] == obj["size_offset"] + 4
            assert sha(data[obj["body_offset"]:obj["end"]]) == obj["body_sha256"]
        raw = data[segment["body_offset"]:segment["end"]]
        token, scalar0, scalar1, scalar2 = struct.unpack(">IQQQ", raw)
        archive_origin = file["size_offset"] - file["relative_object_identity"]
        assert token == file["relative_object_identity"] and archive_origin + token == file["size_offset"]
        clusters.append({"cluster": {key: cluster[key] for key in ("offset", "size_offset", "body_offset", "body_bytes", "end", "body_sha256")},
            "vectors": [{"offset": v["offset"], "serialized_flags": v["unbound_word"], "count": v["count"]} for v in vectors],
            "audio_file": {key: file[key] for key in ("offset", "size_offset", "body_offset", "body_bytes", "end", "body_sha256", "decoded")},
            "segment": {**{key: segment[key] for key in ("offset", "size_offset", "body_offset", "body_bytes", "end", "body_sha256")},
                        "raw_hex": raw.hex(), "archive_origin": archive_origin,
                        "positive_object_reference": {"offset": segment["body_offset"], "token": token,
                            "resolved_file_identity_offset": archive_origin + token},
                        "candidate_three_big_endian_u64": [scalar0, scalar1, scalar2],
                        "middle_candidate_equals_declared_file_frame_count": scalar1 == file["decoded"]["media_frame_count_u64"],
                        "limit": "Reference resolution follows established archive identity. Three-u64 split and numerical equality are observations until a native reader/consumer binds widths and meaning."}})
    fixtures.append({"fixture": str(path.relative_to(ROOT)), "fixture_sha256": sha(fixture_bytes),
        "source": fixture["source"], "source_sha256": sha(data), "clusters": clusters})
write("fixture-byte-correlations.json", {"scope": "Exact retained v09 structural fixtures independently checked against original bytes; no native execution.", "fixtures": fixtures})

data = read(SOURCE); assert sha(data) == EXPECTED
segments = []; position = 32
for _ in range(struct.unpack_from("<I", data, 16)[0]):
    command, size = struct.unpack_from("<II", data, position)
    if command == 0x19:
        value = struct.unpack_from("<II16sQQQQIIII", data, position)
        segments.append(dict(name=value[2].rstrip(b"\0").decode(), address=value[3], offset=value[5], file_size=value[6]))
    if command == 0x26: _, _, start_offset, start_size = struct.unpack_from("<IIII", data, position)
    position += size


def address(offset):
    seg, = [s for s in segments if s["offset"] <= offset < s["offset"] + s["file_size"]]
    return seg["address"] + offset - seg["offset"]


def offset(va):
    seg, = [s for s in segments if s["address"] <= va < s["address"] + s["file_size"]]
    return seg["offset"] + va - seg["address"]


def matches(needle, aligned=False):
    start = 0
    while True:
        found = data.find(needle, start)
        if found < 0: return
        if not aligned or found % 8 == 0: yield found
        start = found + 1


va = next(s["address"] for s in segments if s["name"] == "__TEXT")
starts = []; delta = shift = 0
for byte in data[start_offset:start_offset+start_size]:
    delta |= (byte & 127) << shift
    if byte & 128: shift += 7
    else:
        if not delta: break
        va += delta; starts.append(va); delta = shift = 0

candidates = []
for name in ("AClusterSegment", "AudioCluster", "AudioFile"):
    token = f"N9Steinberg{len(name)}{name}E".encode() + b"\0"
    for name_at in matches(token):
        for pointer in matches(struct.pack("<Q", address(name_at)), True):
            typeinfo = address(pointer - 8)
            for type_pointer in matches(struct.pack("<Q", typeinfo), True):
                if struct.unpack_from("<Q", data, type_pointer - 8)[0] != 0: continue
                vtable = address(type_pointer + 8)
                slots = []
                for slot in [0x98, 0xa0, 0x140]:
                    at = offset(vtable + slot); target = struct.unpack_from("<Q", data, at)[0]
                    slots.append({"slot": hex(slot), "source_va": hex(vtable+slot), "source_offset": at,
                                  "original_hex": data[at:at+8].hex(), "target": hex(target)})
                candidates.append({"class": name, "name_va": hex(address(name_at)), "name_offset": name_at,
                    "typeinfo": hex(typeinfo), "vtable": hex(vtable), "slots": slots})
assert len(candidates) == 3
write("reader-rate-candidates.json", {"source_sha256": EXPECTED, "classes": candidates,
      "limit": "Original RTTI/primary-vtable pointers. Names/slot addresses alone do not establish consumer behavior."})

targets = set()
for row in candidates:
    for slot in row["slots"]:
        if (row["class"] == "AClusterSegment" and slot["slot"] in ["0x98", "0xa0"]) or (row["class"] != "AClusterSegment" and slot["slot"] == "0x140"):
            targets.add(int(slot["target"], 16))
derivatives = []
for entry in sorted(targets):
    end = starts[starts.index(entry)+1]
    assert end-entry < 4096
    at = offset(entry); raw = data[at:at+end-entry]
    filename = f"function-{entry:x}.arm64.bin"
    with (HERE / filename).open("xb") as stream: stream.write(raw)
    args = ["/Library/Developer/CommandLineTools/usr/bin/llvm-objdump", "-d", "--start-address="+hex(entry), "--stop-address="+hex(end), str(SOURCE)]
    native = subprocess.run(args, capture_output=True, text=True, check=True).stdout
    native_name = f"native-{entry:x}.txt"
    with (HERE / native_name).open("x") as stream: stream.write(native)
    words = re.findall(r"^([0-9a-f]+):\s+([0-9a-f]{8})\s", native, re.M)
    assert len(words)*4 == len(raw)
    for location, word in words:
        assert struct.unpack_from("<I", data, offset(int(location,16)))[0] == int(word,16)
    derivatives.append(dict(entry=hex(entry), next_declared_function_start=hex(end), length=len(raw), raw_file=filename,
        source_file_offset=at, raw_sha256=sha(raw), native_file=native_name, native_sha256=sha(native.encode()),
        native_words_checked=len(words), native_command=args))
write("derivation.json", {"source":str(SOURCE), "source_sha256":EXPECTED, "segments":segments,
    "function_starts": {"offset":start_offset,"length":start_size,"sha256":sha(data[start_offset:start_offset+start_size])},
    "derivatives":derivatives,"scope":"Exact static-only raw intervals; LC_FUNCTION_STARTS boundary is metadata, not proof of complete body. Raw images omit imports/data/vtables/exception context."})
print(json.dumps({"fixtures":len(fixtures),"clusters":sum(len(f["clusters"]) for f in fixtures),"functions":len(derivatives),"bytes":sum(d["length"] for d in derivatives)}))
