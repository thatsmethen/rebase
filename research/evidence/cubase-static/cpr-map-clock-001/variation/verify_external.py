"""Read-only original/readback check of peer-owned supporting REA dossiers."""
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sha = lambda data: hashlib.sha256(data).hexdigest()
derivation = json.loads((HERE / "derivation.json").read_text())
source = Path(derivation["source"]).read_bytes()
assert sha(source) == derivation["source_sha256"]
selections = [
    ("cpr-map-clock-001/list", entry) for entry in [
        "10173a5ac", "10173a7c0", "10173a5ec", "101747fe4", "10174a630", "1016e9a30", "103103ed0", "1016e8a68",
        "1017409ec", "1016c29ac", "1000fd13c", "1016e9990", "1016e8fe8", "101740948", "1016e8ff4",
    ]
] + [("cpr-objects-001/audio-native", "1000ee8c4")]
rows = []
for directory, ident in selections:
    base = ROOT / "research/evidence/cubase-static" / directory
    function_path = base / f"function-{ident}.json"
    byte_path = base / f"bytes-{ident}.json"
    raw_path = base / f"function-{ident}.arm64.bin"
    native_path = base / f"native-{ident}.txt"
    function_wrapper = json.loads(function_path.read_text())
    byte_wrapper = json.loads(byte_path.read_text())
    function = function_wrapper.get("structuredContent")
    byte_record = byte_wrapper.get("structuredContent")
    raw = raw_path.read_bytes()
    start = int(ident, 16)
    segment, = [s for s in derivation["segments"] if s["address"] <= start and start + len(raw) <= s["address"] + s["file_size"]]
    offset = segment["offset"] + start - segment["address"]
    assert raw == source[offset:offset + len(raw)]
    rea_success = not function_wrapper.get("isError") and function is not None and not byte_wrapper.get("isError") and byte_record is not None
    if rea_success:
        assert function["subject"]["digest"]["sha256"] == sha(raw)
        readback = byte_record["normalized_result"]
        assert readback["complete"] and readback["returned_bytes"] == len(raw) and int(readback["address"], 16) == start
        assert bytes.fromhex(readback["bytes_hex"]) == raw
    words = {}
    for match in re.finditer(r"^([0-9a-f]+):\s+([0-9a-f]{8})\s+(.+)$", native_path.read_text(), re.M):
        address, word = int(match[1], 16), int(match[2], 16)
        assert start <= address < start + len(raw)
        assert raw[address - start:address - start + 4] == word.to_bytes(4, "little")
        words[address] = word
    assert set(words) == set(range(start, start + len(raw), 4))
    rea_addresses = [int(line.split(":", 1)[0], 16) for line in function["normalized_result"]["assembly"]] if rea_success else []
    assert all(address in words for address in rea_addresses)
    rows.append({"entry": hex(start), "function_evidence_id": function["evidence_id"] if rea_success else None,
                 "readback_evidence_id": byte_record["evidence_id"] if rea_success else None, "source_file_offset": offset,
                 "bytes": len(raw), "original_native_words": len(words), "rea_instruction_addresses": len(rea_addresses),
                 "source_and_raw_equal": True, "rea_analysis_and_readback_success": rea_success,
                 "failure_limit": None if rea_success else "Retained provider failure; only original raw slice/native disassembly checked. No successful REA semantic/readback claim.",
                 "pins": [{"path": str(p.relative_to(ROOT)), "bytes": p.stat().st_size, "sha256": sha(p.read_bytes())}
                          for p in [function_path, byte_path, raw_path, native_path]]})
(HERE / "external-evidence-checks.json").write_text(json.dumps({
    "scope": "Independent custody and original-word verification of selected peer-owned dossiers; no new target import.",
    "source_sha256": derivation["source_sha256"], "functions": rows,
    "limits": ["Checks do not certify inferred decompiler types, external callbacks or live lifecycle.",
               "Selected peer files are pinned; unrelated peer analysis files may still be under construction."]}, indent=2) + "\n")
print(json.dumps({"functions": len(rows), "bytes": sum(row["bytes"] for row in rows),
                  "native_words": sum(row["original_native_words"] for row in rows),
                  "rea_addresses": sum(row["rea_instruction_addresses"] for row in rows)}))
