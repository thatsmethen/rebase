"""Seal the bounded static accessor study; never executes proprietary code."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import subprocess

H = Path(__file__).resolve().parent
R = H.parents[4]


def pin(path):
    return {"path": str(path.relative_to(R)), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def write(path, value):
    with path.open("x") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")


def envelope(path):
    data = json.loads(path.read_text())
    assert not data.get("isError"), path
    return data.get("structuredContent") or json.loads(data["content"][0]["text"])


def check_pins(value):
    if isinstance(value, dict):
        if all(key in value for key in ("path", "bytes", "sha256")):
            assert pin(R / value["path"]) == {key: value[key] for key in ("path", "bytes", "sha256")}, value["path"]
        for item in value.values():
            check_pins(item)
    elif isinstance(value, list):
        for item in value:
            check_pins(item)


def verify():
    manifest = json.loads((H / "artifact-manifest.json").read_text())
    check_pins(manifest)
    print(json.dumps({"passed": True, "files": len(manifest["files"]),
                      "finding": pin(H / "finding.json"),
                      "manifest": pin(H / "artifact-manifest.json")}))


def seal():
    assert not (H / "finding.json").exists()
    assert not (H / "artifact-manifest.json").exists()
    subprocess.run(["python3", str(H / "verify_evidence.py")], check=True)
    verification = json.loads((H / "verification.json").read_text())
    assert verification["passed"]
    assert verification["summary"] == {"new_functions": 10, "reused_functions": 31,
        "bytes_verified": 14548, "original_native_words": 3637,
        "rea_instruction_addresses": 2656}
    for suffix, count in [("", 74), ("-v02", 82)]:
        imported = envelope(H / f"evidence-import{suffix}.json")["result"]
        assert imported == {"imported": count, "unknowns_added": 0, "total": count}
        assert (H / f"import-run{suffix}.log").read_text().endswith("CLOSED: evidence import session\n")
    controls = json.loads((H / "controls/seek-controls.json").read_text())
    assert controls["passed"] and len(controls["vectors"]) == 112
    assert controls["invalid_transactional_controls"] == 9
    assert controls["FP_environment_transactional_controls"] == 1
    check_pins(controls)
    analytical = json.loads((H / "lifecycle-controls.json").read_text())
    assert analytical["passed"] and len(analytical["terminal_predicate_rows"]) == 54
    assert len(analytical["budget_rows"]) == 72
    check_pins(analytical)
    code, header = H / "candidate/cpr_accessor_seek.c", H / "candidate/cpr_accessor_seek.h"
    assert pin(code)["sha256"] == "355b2818498bf35bc756ab671fbb4aa64cadd6dc823f54ed386bfb5bf997581e"
    assert pin(header)["sha256"] == "b68cb079ce507d9775560c08ba3bd384fec873ac5e2d0812a907013fe3745db4"
    review = {
        "id": "ACCESSOR-SEEK-CANDIDATE-REVIEW-001", "status": "passed_bounded_review",
        "reviewer_role": "Native-study author reviewed the independently root-authored C candidate.",
        "proprietary_target_executions": 0,
        "inputs": [pin(code), pin(header), pin(H / "pass1/native-10036f89c.txt"),
                   pin(H / "controls/check_seek.py"), pin(H / "controls/seek-controls.json")],
        "checks": [
            "Unequal-rate sequence preserves binary32 division before binary64 multiplication, signed truncation, binary64 division and second signed truncation.",
            "Equal-rate branch preserves the integer request directly; candidate diagnostic fields on this bypass are authored observability, not native intermediate operations.",
            "Candidate publishes the result only after all validation; invalid arguments and arithmetic/FP failures leave caller output untouched.",
            "112 Fraction/IEEE expected vectors compare source cursor, returned cursor and all intermediate diagnostics exactly; nine invalid controls and one non-nearest environment control preserve sentinels.",
            "Normal positive integral rates 8k..192k and requested frames 0..2^53 are explicit defensive bounds; native accepts a wider ABI domain not reconstructed here.",
            "This pure mapping has no converter handle. Retaining converter state across seek is an adapter obligation, not something this kernel by itself proves."
        ],
        "open_findings": [],
        "limits": ["Candidate C executed; proprietary native function never executed.",
                   "No target runtime equivalence, arbitrary host FP environment, or backend lifecycle claim.",
                   "App state-machine tests are separate APP016 evidence and were not required for this native/candidate seal."]
    }
    write(H / "candidate-review.json", review)
    working = json.loads((H / "working-contract.json").read_text())
    contract_keys = ["fields", "seek", "read_order", "budget", "conversion_lifecycle",
                     "after_terminal", "concrete_stream_boundary", "retry_scope"]
    finding = {
        "id": "CPR-ACCESSOR-SEEK-STATE-001", "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "sealed_bounded_static_lifecycle_and_seek_reconstruction",
        "scope": "Fixed-rate AudioAccessor seek and read state transitions, budget/terminal predicates, mode-specific ratio updates, and current AudioFile metadata/reader-factory boundaries.",
        "proprietary_target_executions": 0, "cubase_runtime_comparisons": 0,
        "target": {"product": "Cubase Pro 15.0.30.287 macOS arm64",
                   "image": pin(R / "research/targets/derived/Cubase15-arm64")},
        "evidence_classes": ["Original native instruction/dispatch bytes", "Pinned REA6.7/Ghidra raw-slice analysis/readback",
                             "Exact Fraction/IEEE analytical controls", "Own root-authored C reconstruction execution"],
        "native_custody": {**verification["summary"], "concrete_dispatch_cells": 19,
            "additional_original_bytes": 126,
            "verification": pin(H / "verification.json"),
            "provider": "rea-agents6.7.0/Ghidra default raw-arm64/2G",
            "raw_analysis_sessions_closed": 3, "new_raw_slices_closed": 10,
            "canonical_import_sessions_closed": 2,
            "current_canonical_records": 82,
            "canonical_import": pin(H / "evidence-import-v02.json"),
            "session_closure_log": pin(H / "import-run-v02.log"),
            "scope_limit": "Readback and original-word equality validate custody; they do not establish all host/backend paths or runtime behavior."},
        "contracts": {key: working[key] for key in contract_keys},
        "entry_evidence": [{key: row[key] for key in ("entry", "new", "directory", "original_bytes_sha256", "evidence_ids")}
                           for row in verification["functions"]],
        "candidate": {"source": pin(code), "header": pin(header), "api": "rb_cpr_accessor_seek",
            "review": pin(H / "candidate-review.json"),
            "defensive_domain": "arm64 IEEE nearest/ties-even; default non-flushing FPCR; positive integral binary32 rates8k..192k; requested frames0..2^53; fail-before-output publication.",
            "native_difference": "Defensive validation and transactionality are reconstruction policy. Native seek mutates only source cursor; it does not reset converter/history or rearm the first-budget byte."},
        "validation": {"seek_exact_vectors": 112, "invalid_transactional_controls": 9,
            "FP_environment_transactional_controls": 1, "candidate_controls": pin(H / "controls/seek-controls.json"),
            "terminal_truth_table_rows": 54, "budget_fraction_rows": 72,
            "analytical_controls": pin(H / "lifecycle-controls.json"),
            "application_acceptance": "Deferred to separate APP016 state/oracle/Swift/full-suite/GUI evidence; no such completion is asserted here."},
        "remaining_limits": working["nonclaims"] + [
            "An AudioFile reader factory is not its eventual sample-read implementation; registry creator/probe and active backend ABI remain unbound.",
            "Serialized PCM24 metadata is not sufficient to assert the active prepared property bag or native file decoder.",
            "A first-short terminal conversion is not equivalent to general end-of-stream. Post-terminal mode1 continuation needs its own controls; mode2 after NULL EOF is backend-dependent and not admitted.",
            "Format arithmetic/order is owned by a separate study; this lifecycle finding does not assert decoded-Float32 input equivalence for every native source format.",
            "Changing rates can retain mode0/1 state; a generic reset-on-seek or reset-on-any-rate-change is not this native contract.",
            "The read path may mutate first-byte, underlying source and converter on an error. Candidate pure-seek output transactionality must not be projected onto the whole accessor."]
    }
    write(H / "finding.json", finding)
    paths = {p for p in H.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.name != "artifact-manifest.json"}
    for row in verification["functions"]:
        paths.update(R / item["path"] for item in row["files"])
        raw = R / row["directory"] / f"function-{row['entry'][2:]}.arm64.bin"
        if raw.is_file():
            paths.add(raw)
    paths.update(R / item["path"] for item in controls["inputs"])
    paths.add(R / analytical["oracle_source"]["path"])
    paths.update([R / "research/targets/derived/Cubase15-arm64",
                  R / "research/evidence/cubase-static/cpr-map-clock-001/attributes/source_tools.py"])
    assert all(path.is_file() for path in paths)
    assert not any(str(path.relative_to(R)).startswith("Application/") for path in paths)
    write(H / "artifact-manifest.json", {
        "id": "CPR-ACCESSOR-SEEK-STATE-001-MANIFEST", "schema_version": 1,
        "scope": "Private local custody of bounded static evidence and frozen authored candidate controls; no target execution.",
        "files": [pin(path) for path in sorted(paths)],
        "exclusions": ["Manifest itself", "__pycache__", "Mutable Application/test source paths"],
        "distribution_limit": "Original proprietary image, raw slices, disassembly, REA outputs and compiled candidate controls remain private local artifacts; paths in compact reports do not imply redistribution."
    })
    verify()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--seal", action="store_true")
    group.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    seal() if args.seal else verify()
