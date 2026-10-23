"""Pin reused REA dossiers and recheck their original code bytes without import."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sha = lambda data: hashlib.sha256(data).hexdigest()
derivation = json.loads((HERE / "derivation.json").read_text())
source = Path(derivation["source"]).read_bytes()
assert sha(source) == derivation["source_sha256"]
paths = [
    ("cpr-objects-001/native/pass2", "10173bdac"),
    ("cpr-signature-001/pass5", "10174c194"),
    ("cpr-signature-001/pass6", "1017a5898"),
    ("cpr-signature-001/pass6", "1017064c4"),
    ("cpr-signature-001/pass7", "1017a4fb4"),
    ("cpr-signature-001/pass7", "1017a3f98"),
    ("cpr-signature-001/pass13", "1017a43f0"),
    ("cpr-signature-001/pass13", "1030f2cdc"),
    ("cpr-signature-001/pass13", "1030f91c4"),
    ("cpr-signature-001/pass13", "1017a4250"),
]
rows = []
for directory, ident in paths:
    base = ROOT / "research/evidence/cubase-static" / directory
    function_path = base / f"function-{ident}.json"
    raw_path = base / f"function-{ident}.arm64.bin"
    readback_path = base / f"bytes-{ident}.json"
    bundle_path = base / f"bundle-{ident}.json"
    function = json.loads(function_path.read_text())["structuredContent"]
    readback = json.loads(readback_path.read_text())["structuredContent"]
    raw = raw_path.read_bytes()
    entry = int(ident, 16)
    segment, = [s for s in derivation["segments"] if s["address"] <= entry and entry + len(raw) <= s["address"] + s["file_size"]]
    offset = segment["offset"] + entry - segment["address"]
    assert raw == source[offset:offset + len(raw)]
    assert function["subject"]["digest"]["sha256"] == sha(raw)
    value = readback["normalized_result"]
    assert value["complete"] and value["returned_bytes"] == len(raw) and int(value["address"], 16) == entry
    assert bytes.fromhex(value["bytes_hex"]) == raw
    bundle = json.loads(bundle_path.read_text())["structuredContent"]["result"]
    assert {v["evidence_id"] for v in bundle["records"]} == {function["evidence_id"], readback["evidence_id"]}
    pins = [{"path": str(p.relative_to(ROOT)), "bytes": p.stat().st_size, "sha256": sha(p.read_bytes())}
            for p in (function_path, raw_path, readback_path, bundle_path, base / f"native-{ident}.txt")]
    rows.append({"entry": hex(entry), "source_file_offset": offset, "length": len(raw),
                 "source_and_raw_and_rea_memory_equal": True, "function_evidence_id": function["evidence_id"],
                 "readback_evidence_id": readback["evidence_id"], "pins": pins,
                 "bundle_path": str(bundle_path.relative_to(ROOT))})
output = {"scope": "Existing static evidence reused; no reanalysis or prior-file mutation.",
          "source": derivation["source"], "source_sha256": derivation["source_sha256"],
          "functions": rows, "limits": ["Original byte/readback identity does not prove decompiler types, external dispatch or runtime behavior."]}
(HERE / "reused-evidence.json").write_text(json.dumps(output, indent=2) + "\n")
print(json.dumps({"reused_functions": len(rows), "bytes_rechecked": sum(row["length"] for row in rows)}))
