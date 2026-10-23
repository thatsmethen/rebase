"""Static custody and analytical branch controls; never load target libraries."""
from pathlib import Path
import hashlib
import json
import re
import struct
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT / "research/evidence/cubase-static/cpr-map-clock-001/attributes"))
import source_tools as source


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def envelope(path):
    obj = json.loads(path.read_text())
    assert not obj.get("isError", False), path
    return obj.get("structuredContent") or json.loads(obj["content"][0]["text"])


# Reuse retained original dossiers without changing or copying sealed artifacts.
old = HERE.parent
uses = {
    "rate-converter": [
        0x100323688, 0x1003237d8, 0x1003261a8, 0x10030a008,
        0x1003136b8, 0x100314ca0, 0x100314ce0, 0x100315000,
        0x100316414, 0x10031659c, 0x100316648, 0x100330cd4,
        0x10033035c, 0x100326318, 0x10030a534,
        0x100313adc, 0x100313b74, 0x100313c2c, 0x1003141bc,
        0x100315438, 0x10030a408, 0x100330d84,
    ],
    "segment-consumer": [0x10036eff0],
    "live-consumer/pass1": [0x10036e458],
}
reuse = []
for folder, addresses in uses.items():
    for address in addresses:
        directory = old / folder
        native = directory / f"native-{address:x}.txt"
        analysis = directory / f"function-{address:x}.json"
        readback = directory / f"bytes-{address:x}.json"
        words = [(int(a, 16), int(w, 16)) for a, w in re.findall(
            r"^([0-9a-f]+):\s+([0-9a-f]{8})\s", native.read_text(), re.M)]
        assert words and words[0][0] == address
        for pc, word in words:
            assert struct.unpack_from("<I", source.data, source.offset(pc, 4))[0] == word
        read = envelope(readback)["raw_result"]
        byte_count = read["returned_bytes"]
        assert read["complete"]
        assert bytes.fromhex(read["bytes_hex"]) == source.data[
            source.offset(address, byte_count):source.offset(address, byte_count) + byte_count]
        value = envelope(analysis)["raw_result"]["value"]
        assert all(int(line.split(":")[0], 16) in dict(words) for line in value["assembly"])
        reuse.append(dict(entry=hex(address), original_words=len(words),
                          exact_readback_bytes=byte_count,
                          evidence_ids=[envelope(analysis)["evidence_id"],
                                        envelope(readback)["evidence_id"]],
                          files=[dict(path=str(p.relative_to(ROOT)), sha256=digest(p))
                                 for p in (native, analysis, readback)]))

# These two larger retained callers are needed only for exact instruction sites.
for pattern, sites in [
    ("renderer-selection/pass*/native-10046e60c.txt",
     [0x10046e744, 0x10046e748, 0x10046e74c]),
    ("event-rendering/pass8/native-10018fb40.txt",
     [0x100190d60, 0x100190d64, 0x100190d68]),
]:
    path, = old.glob(pattern)
    words = {int(a, 16): int(w, 16) for a, w in re.findall(
        r"^([0-9a-f]+):\s+([0-9a-f]{8})\s", path.read_text(), re.M)}
    for pc in sites:
        assert struct.unpack_from("<I", source.data, source.offset(pc, 4))[0] == words[pc]
    reuse.append(dict(path=str(path.relative_to(ROOT)), sha256=digest(path),
                      bounded_sites=[source.region(pc, 4) for pc in sites]))

tables = json.loads((HERE / "receiver-tables.json").read_text())
for row in tables["records"]:
    assert source.region(int(row["address"], 16), row["length"]) == {
        k: row[k] for k in ("address", "file_offset", "length", "bytes_hex", "sha256")}

quality_table = source.region(0x103933bf8, 20)
assert list(struct.unpack("<5I", bytes.fromhex(quality_table["bytes_hex"]))) == [2, 1, 3, 0, 1]
assert bytes.fromhex(quality_table["bytes_hex"])[12:16] == b"\0" * 4  # format5 -> float32 code0

# Exhaustive finite truth table of the inspected branches, not execution results.
controls = []
for policy in (0, 1, 2, 255):
    for available in (False, True):
        requested = 0 if policy == 0 else 2 if available else 1
        for factory_returns_child in (False, True):
            actual = 1 if requested == 2 and not factory_returns_child else requested
            controls.append(dict(policy_byte=policy, soxr_available=available,
                                 requested_mode=requested,
                                 mode2_factory_returns_child=factory_returns_child,
                                 final_mode=actual))
assert all(r["requested_mode"] != 0 for r in controls if r["policy_byte"])
assert all(r["final_mode"] == 0 for r in controls if not r["policy_byte"])
assert any(r["requested_mode"] == 2 and r["final_mode"] == 1 for r in controls)
qualities = [dict(quality_byte=q, extra_byte=x,
                  recipe=(4 if q == 0 else 6 if x == 0 else 70), flags=0)
             for q in (0, 1, 255) for x in (0, 1, 255)]
assert next(r["recipe"] for r in qualities
            if r["quality_byte"] == 1 and r["extra_byte"] == 0) == 6

result = dict(source_sha256=source.PIN, target_execution=False,
              reused_evidence=reuse, type_mapping=quality_table,
              controls=dict(evidence_class="analytical decoded-branch controls",
                            backend=controls, quality=qualities,
                            limitation="Factory failure controls are conditional inputs; "
                            "they do not assert that the cached availability changes in a run."),
              passed=True)
(HERE / "contract-verification.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(dict(reused_functions=len(uses["rate-converter"]) + 2,
                      caller_site_checks=6, backend_controls=len(controls),
                      quality_controls=len(qualities), passed=True)))
