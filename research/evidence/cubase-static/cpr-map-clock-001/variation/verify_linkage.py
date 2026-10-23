"""Read original linked bytes and independently recheck retained fixture scalars."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
SOURCE = ROOT / "research/targets/derived/Cubase15-arm64"
EXPECTED = "dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb"
sha = lambda data: hashlib.sha256(data).hexdigest()
before = SOURCE.stat()
data = SOURCE.read_bytes()
assert sha(data) == EXPECTED
segments = json.loads((HERE / "derivation.json").read_text())["segments"]


def span(address, size):
    segment, = [s for s in segments if s["address"] <= address and address + size <= s["address"] + s["file_size"]]
    offset = segment["offset"] + address - segment["address"]
    raw = data[offset:offset + size]
    return {"address": hex(address), "source_file_offset": offset, "length": size,
            "bytes_hex": raw.hex(), "sha256": sha(raw)}


def pointer(address):
    return int.from_bytes(bytes.fromhex(span(address, 8)["bytes_hex"]), "little")


def string(address):
    start = span(address, 1)["source_file_offset"]
    end = data.index(b"\0", start, start + 4096)
    return {**span(address, end - start + 1), "ascii": data[start:end].decode("ascii")}


classes = []
for name, table, slots in [
    ("MTempoTrackEvent", 0x104674d18, [8, 0x98, 0x258, 0x268, 0x4f0, 0x550, 0x5f8]),
    ("MTempoTrackNode", 0x104675ec8, [8, 0x58, 0x60, 0x68, 0xd0, 0xd8, 0xe0, 0xf0, 0x150, 0x158]),
    ("MTrackVariationCollection", 0x104682030, [8, 0x40, 0x98, 0xd8, 0xe0, 0x110]),
    ("MTrackVariation", 0x104681f50, [8, 0x98]),
    ("FIntIDAttribute", 0x104e33638, [0x78, 0x80]),
    ("CmOrderedArray", 0x104e315f0, [0xe8, 0x108, 0x118]),
]:
    typeinfo = pointer(table - 8)
    rtti = string(pointer(typeinfo + 8))
    assert name in rtti["ascii"]
    classes.append({"class_name": name, "primary_vtable": hex(table), "vtable_prefix": span(table - 16, 16),
                    "typeinfo_name_pointer": span(typeinfo + 8, 8), "rtti_name": rtti,
                    "slots": [{"slot": hex(slot), "target": hex(pointer(table + slot)), **span(table + slot, 8)} for slot in slots]})
getters = []
for address, size, expected in [(0x10174a698, 8, "002c40f9c0035fd6"),
                                (0x10174aa6c, 8, "003440f9c0035fd6")]:
    record = span(address, size)
    assert record["bytes_hex"] == expected
    getters.append(record)
features = [{"pointer": span(at, 8), "literal": string(pointer(at))} for at in (0x10450a7b0, 0x10450a7b8)]
command = ["/Library/Developer/CommandLineTools/usr/bin/llvm-objdump", "--macho", "--indirect-symbols", str(SOURCE)]
symbols = subprocess.run(command, capture_output=True, text=True, check=True).stdout
selected = [line for line in symbols.splitlines() if "0x0000000103881bcc" in line]
assert len(selected) == 1 and selected[0].endswith(" _strcmp")
source_after = SOURCE.stat()
assert (before.st_size, before.st_ino, before.st_mtime_ns) == (source_after.st_size, source_after.st_ino, source_after.st_mtime_ns)

state_path = ROOT / "research/evidence/cubase-static/cpr-audio-timing-001/reviewer-template-state.json"
state_bytes = state_path.read_bytes()
state = json.loads(state_bytes)
fixtures = []
for fixture in state["fixtures"]:
    source = ROOT / fixture["source"]
    raw = source.read_bytes()
    assert sha(raw) == fixture["source_sha256"]
    for tempo in fixture["tempo_objects"]:
        fields = tempo["track_attributes"]["fields"]
        attr_count = struct.unpack_from(">i", raw, tempo["track_attributes"]["offset"])[0]
        assert attr_count == tempo["track_attributes"]["count"] == len(fields) and attr_count > 0
        keys = []
        for field in fields:
            key, code = struct.unpack_from(">IH", raw, field["offset"])
            assert key == int(field["key"], 16) and code == int(field["type"], 16)
            keys.append(key)
        assert len(set(keys)) == len(keys) and 0x64696854 not in keys
        variation_field, = [field for field in fields if int(field["key"], 16) == 0x69435654]
        assert variation_field["type"] == "0x22"
        collection = variation_field["value"]
        assert collection["class"] == "MTrackVariationCollection" and collection["version"] == 0
        assert sha(raw[collection["body_offset"]:collection["end"]]) == collection["body_sha256"]
        index, flags, count = struct.unpack_from(">iHi", raw, collection["body_offset"])
        assert (index, flags, count) == (10, 2, 1)
        item, = collection["reviewer_decoded"]["objects"]
        assert item["class"] == "MTrackVariation" and item["version"] == 0
        assert sha(raw[item["body_offset"]:item["end"]]) == item["body_sha256"]
        decoded = item["reviewer_decoded"]
        alternate = decoded["alternate_MDataNode"]
        assert alternate["kind"] == "null" and struct.unpack_from(">i", raw, alternate["offset"])[0] == 0
        assert struct.unpack_from(">i", raw, decoded["trailing_i32_offset"])[0] == 0
        assert decoded["trailing_i32_offset"] + 4 == item["end"] == collection["end"]
        fixtures.append({"source": str(source), "source_sha256": sha(raw), "tempo_payload_offset": tempo["object"]["body_offset"],
                         "tempo_payload_sha256": tempo["object"]["body_sha256"], "numeric_attribute_keys": [hex(k) for k in keys],
                         "serialized_track_attribute_count": attr_count,
                         "visibility_key_0x64696854_absent": True, "variation_attribute_type": "0x22",
                         "collection_payload_offset": collection["body_offset"], "collection_payload_sha256": collection["body_sha256"],
                         "collection_header": {"serialized_index": index, "flags": flags, "count": count},
                         "variation_payload_offset": item["body_offset"], "variation_payload_sha256": item["body_sha256"],
                         "alternate_reference_offset": alternate["offset"], "alternate_reference": 0,
                         "trailing_i32_offset": decoded["trailing_i32_offset"], "trailing_i32": 0})
result = {"source": str(SOURCE), "source_sha256": EXPECTED, "source_stable_during_read": True,
          "classes": classes, "getters": getters, "features": features,
          "strcmp_import": {"command": command, "original_output_lines": selected},
          "collection_class_literal": string(0x1038da6ca),
          "fixture_evidence": {"path": str(state_path), "sha256": sha(state_bytes)}, "fixtures": fixtures,
          "limits": ["Original file-backed linkage/fixture bytes, not live memory or target execution.",
                     "Concrete allocation, attachment and callbacks require separately retained instruction evidence; RTTI alone is not a runtime receiver proof.",
                     "The fixture parser's structural relationships are reused, while source hashes, payload hashes, keys and selected scalar bytes are independently reread."]}
(HERE / "linkage-and-fixtures.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps({"classes": len(classes), "selected_slots": sum(len(c["slots"]) for c in classes), "factory_fixture_variations_checked": len(fixtures)}))
