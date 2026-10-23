"""Verify retained raw-image REA results against immutable original bytes.

This checks custody, instruction addresses/words and decoded mnemonics. It does
not prove the decompiler's types, function boundaries or runtime behavior.
"""
import sys
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(name):
    return json.loads((ROOT / name).read_text())


def tool(name):
    result = load(name)
    assert not result.get("isError"), name
    return result["structuredContent"]


def save(name, value):
    (ROOT / name).write_text(json.dumps(value, indent=2) + "\n")


derivation = load("derivation.json")
source = Path(derivation["source"])
before = source.stat()
original = source.read_bytes()
assert sha(original) == derivation["source_sha256"]
assert len(original) == derivation["source_bytes"]
rows = []
for row in derivation["derivatives"]:
    entry = int(row["entry"], 16)
    ident = row["entry"][2:]
    raw = (ROOT / row["raw_file"]).read_bytes()
    offset, size = row["source_file_offset"], row["length"]
    assert raw == original[offset:offset + size]
    assert sha(raw) == row["raw_sha256"]
    native_text = (ROOT / row["original_native_disassembly"]).read_text()
    assert sha(native_text.encode()) == row["native_stdout_sha256"]
    native = {}
    for match in re.finditer(r"^([0-9a-f]+):\s+([0-9a-f]{8})\s+(.+)$", native_text, re.M):
        addr, word, instruction = int(match[1], 16), int(match[2], 16), match[3].strip()
        assert entry <= addr < entry + size and addr not in native
        assert raw[addr - entry:addr - entry + 4] == word.to_bytes(4, "little")
        native[addr] = {"word": f"{word:08x}", "assembly": instruction}
    assert set(native) == set(range(entry, entry + size, 4))

    opened = tool(f"open-{ident}.json")["result"]
    assert opened["sha256"] == row["raw_sha256"]
    assert opened["entry_point"] == row["entry"]
    record = tool(f"function-{ident}.json")
    result = record["normalized_result"]
    profile = record["analysis_profile"]
    assert profile["parameters"]["analyzer_preset"] == "ghidra-default"
    assert profile["parameters"]["entry_point"] == row["entry"]
    assert profile["parameters"]["target_format"] == "raw-binary"
    assert profile["parameters"]["language_id"] == "AARCH64:LE:64:v8A"
    assert record["subject"]["digest"]["sha256"] == sha(raw)
    byte_record = tool(f"bytes-{ident}.json")
    readback = byte_record["normalized_result"]
    assert readback["complete"] and readback["returned_bytes"] == size
    assert readback["address"] == row["entry"]
    assert bytes.fromhex(readback["bytes_hex"]) == raw
    instructions = []
    seen = set()
    for line in result["assembly"]:
        match = re.fullmatch(r"(0x[0-9a-f]+): (.+)", line)
        assert match, line
        addr, assembly = int(match[1], 16), match[2]
        assert addr in native and addr not in seen
        seen.add(addr)
        instructions.append({
            "address": hex(addr), "original_word": native[addr]["word"],
            "source_file_offset": offset + addr - entry,
            "rea_assembly": assembly, "native_assembly": native[addr]["assembly"],
            "mnemonic_matches": assembly.split()[0].lower() == native[addr]["assembly"].split()[0].lower(),
        })
    body = result["procedure"]["body"]
    body_addresses = set()
    for interval in body["ranges"]:
        start, end = int(interval["start"], 16), int(interval["end"], 16)
        assert start >= entry and end < entry + size
        body_addresses.update(range(start, end + 1, 4))
    assert seen == body_addresses
    assert len(seen) * 4 == body["total_bytes"]
    bundle = tool(f"bundle-{ident}.json")["result"]
    assert {r["evidence_id"] for r in bundle["records"]} == {
        record["evidence_id"], byte_record["evidence_id"]}
    closed = tool(f"close-{ident}.json")["result"]
    assert closed["evidence_records"] == 2
    assert Path(closed["path"]).is_file()
    snapshot = json.loads(Path(closed["path"]).read_text())
    assert snapshot["evidence_bundle"] == bundle
    warnings = [line.strip() for line in result["pseudocode"].splitlines() if "WARNING:" in line]
    (ROOT / f"pseudocode-{ident}.txt").write_text(result["pseudocode"])
    (ROOT / f"assembly-{ident}.txt").write_text("\n".join(result["assembly"]) + "\n")
    rows.append({
        "entry": row["entry"], "raw_sha256": sha(raw),
        "source_range_and_rea_readback_exact": True,
        "analyze_function_evidence_id": record["evidence_id"],
        "read_bytes_evidence_id": byte_record["evidence_id"],
        "analysis_profile": profile,
        "native_interval_instruction_count": len(native),
        "rea_body_instruction_count": len(seen), "rea_body": body,
        "omitted_native_instruction_addresses": [hex(a) for a in sorted(set(native) - seen)],
        "mnemonic_differences": [x for x in instructions if not x["mnemonic_matches"]],
        "instruction_checks": instructions, "pseudocode_warnings": warnings,
        "snapshot": closed, "bundle_file": f"bundle-{ident}.json",
    })
after = source.stat()
assert (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (
    after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
report = {
    "created_utc": datetime.now(timezone.utc).isoformat(),
    "scope": "Static byte/address/decoded-mnemonic verification; no target execution or semantic equivalence test",
    "source": str(source), "source_sha256": sha(original),
    "source_stable_during_verification": True,
    "passed": True, "functions": rows,
    "total_native_interval_instructions": sum(x["native_interval_instruction_count"] for x in rows),
    "total_rea_body_instructions": sum(x["rea_body_instruction_count"] for x in rows),
    "limits": [
        "REA assembly lines do not contain instruction words. Every line address was checked against original-image native disassembly; its original word was separately matched to complete REA initialized-memory readback.",
        "Mnemonic differences may be decoder aliases. This does not automatically prove all operand rendering or decompiler semantics.",
        "Ghidra inferred body boundaries are observations, not source-level or unwind-metadata proof.",
    ],
}
save("verification.json", report)
print(json.dumps({"passed": report["passed"], "native_instructions": report["total_native_interval_instructions"],
                  "rea_instructions": report["total_rea_body_instructions"],
                  "mnemonic_differences": sum(len(x["mnemonic_differences"]) for x in rows)}))
