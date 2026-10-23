"""Seal the mode1 static study with immutable candidate/oracle copies."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json

H = Path(__file__).resolve().parent
R = H.parents[4]
A = R / "research/evidence/application/APP013"


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def pin(p):
    return {"path": str(p.relative_to(R)), "bytes": p.stat().st_size, "sha256": digest(p)}


def write(p, value):
    with p.open("x") as f:
        f.write(json.dumps(value, indent=2) + "\n")


def envelope(p):
    doc = json.loads(p.read_text())
    assert not doc.get("isError"), p
    return doc.get("structuredContent") or json.loads(doc["content"][0]["text"])


def verify():
    manifest = json.loads((H / "artifact-manifest.json").read_text())
    for row in manifest["files"]:
        p = R / row["path"]
        assert p.is_file() and p.stat().st_size == row["bytes"] and digest(p) == row["sha256"], p
    print(json.dumps({"passed": True, "files": len(manifest["files"]),
                      "finding": pin(H / "finding.json"),
                      "manifest": pin(H / "artifact-manifest.json")}))


def seal():
    assert not (H / "artifact-manifest.json").exists()
    assert not (H / "finding.json").exists()
    validation = json.loads((H / "verification.json").read_text())
    assert validation["passed"]
    assert validation["summary"] == {
        "new_functions": 10, "reused_functions": 5,
        "original_native_words": 1091, "rea_instruction_addresses": 1084,
        "bytes_verified": 4364,
    }
    imported = envelope(H / "evidence-import.json")["result"]
    assert imported == {"imported": 30, "unknowns_added": 0, "total": 30}
    for folder in ("pass1", "pass2"):
        lines = (H / folder / "run.log").read_text().splitlines()
        assert lines[-1] == "CLOSED: isolated raw-slice MCP session"
        assert all(json.loads(x)["isError"] is False for x in lines[:-1])
    assert (H / "import-run.log").read_text().endswith("CLOSED: evidence import session\n")
    controls = json.loads((H / "controls/candidate-controls.json").read_text())
    assert controls["passed"] and len(controls["stream_controls"]) == 80
    assert len(controls["aggregate_controls"]) == 35 and len(controls["rejections"]) == 11
    assert (H / "controls/ubsan-controls.log").read_text() == (
        "PASS: reconstruction-only stream, reset, resize and native-bound controls.\n")
    assert json.loads((H / "controls/sanitizer-unavailable.json").read_text())["status"] == (
        "terminated_before_candidate_main")

    copies = [
        (R / "Application/Sources/RebaseTimingDSP/native_rate_mode1.c", H / "candidate/native_rate_mode1.c"),
        (R / "Application/Sources/RebaseTimingDSP/include/native_rate_mode1.h", H / "candidate/native_rate_mode1.h"),
        (R / "Application/Tests/RebaseCoreTests/NativeRateMode1Tests.swift", H / "validation/NativeRateMode1Tests.swift"),
        (A.parent / "APP010/native-rate-mode0-oracle.py", H / "validation/dependencies/native-rate-mode0-oracle.py"),
        (R / "Application/Sources/RebaseCore/CPRRateConvertedStream.swift", H / "validation/integration/CPRRateConvertedStream.swift"),
        (R / "Application/Sources/RebaseCore/CPRSourceEventPlayback.swift", H / "validation/integration/CPRSourceEventPlayback.swift"),
        (R / "Application/Package.swift", H / "validation/integration/Package.swift"),
    ]
    for name in (
        "mode1-oracle.py", "mode1-oracle.json", "mode1-oracle-generation.log",
        "verify-mode1-instructions.py", "mode1-instruction-verification.json",
        "mode1-combined-first.log", "mode1-combined-second.log",
        "mode1-independent-review.json", "independent-kernels-final-02.log",
    ):
        copies.append((A / name, H / "validation" / name))
    assert digest(copies[0][0]) == "9dd346c5f1a3f27d188e3475a8db6d92ddfbeb92da10c02af4b45b2741d66a80"
    assert digest(copies[1][0]) == "25cdbb819f84bddf8a6d756a16954f2ee439309668efdbe72fb8d394dcdf0bb4"
    assert digest(A / "mode1-oracle.json") == "d985ab0b74146b093ccae9ca98edd5e8a7d78e904a35f6966ec841f98340d8a9"
    assert digest(A / "mode1-oracle.py") == "f031f38172356ca244c683c35c17c2413333f52a58a1d43048f457258d8e9238"
    review = json.loads((A / "mode1-independent-review.json").read_text())
    assert digest(A / "mode1-independent-review.json") == "d9b41212d6b74d1020d0b3b2c7790e02128490791b6efee6902da325d8162905"
    assert review["status"] == "independent_mode1_controls_pass_no_open_actionable_finding"
    for row in review["reviewed_sources"] + review["evidence"]:
        p = R / row["path"]
        assert p.stat().st_size == row["bytes"] and digest(p) == row["sha256"], p
    snapshot_rows = []
    for src, dst in copies:
        assert src.is_file() and not dst.exists(), (src, dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        with dst.open("xb") as f:
            f.write(src.read_bytes())
        assert digest(src) == digest(dst)
        snapshot_rows.append({"historical_original": pin(src), "immutable_snapshot": pin(dst)})
    write(H / "source-snapshots.json", {
        "policy": "Live source/test paths are descriptive identities. Custody pins immutable copies.",
        "copies": snapshot_rows,
    })
    working = json.loads((H / "working-contract.json").read_text())
    facts = []
    functions = {x["entry"]: x for x in validation["functions"]}
    for title, key, entries in [
        ("Concrete receiver and mode1 dispatch", "dispatch", ["0x10030a008", "0x10030a634", "0x10030af58"]),
        ("Owned state and initialization", "fields", ["0x10030a634", "0x10030a728", "0x10030a738", "0x10030a748", "0x10030a7a0"]),
        ("Coefficient generator and system math boundary", "coefficient_contract", ["0x10030a748", "0x10030a974"]),
        ("Sample order, history, counts and lifecycle", "sample_contract", ["0x10030b8a8", "0x10030af58", "0x10030aeb8", "0x10030a664"]),
    ]:
        facts.append({"title": title, "contract": working[key],
                      "native_sources": [{"entry": e, "evidence_ids": functions[e]["evidence_ids"],
                                          "files": functions[e]["files"]} for e in entries]})
    finding = {
        "id": "CPR-RATE-MODE1-001", "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "sealed_bounded_static_contract_and_reconstruction",
        "scope": working["scope"],
        "evidence_classes": ["original-byte static analysis", "retained REA dossiers",
                             "independent instruction-ordered math oracle", "reconstruction-only execution"],
        "proprietary_target_executions": 0, "cubase_runtime_comparisons": 0,
        "target": {"product": "Cubase Pro15.0.30.287 macOS arm64",
                   "image": pin(R / "research/targets/derived/Cubase15-arm64")},
        "native_custody": {
            **validation["summary"], "canonical_records": 30, "canonical_import": imported,
            "verification": pin(H / "verification.json"),
            "new_raw_slice_sessions_closed": 10, "isolated_analysis_processes_closed": 2,
            "import_processes_closed": 1,
            "provider": "Pinned rea-agents6.7.0 / Ghidra raw arm64, default analyzers,2G heap.",
            "limitations": [
                "Raw-slice pseudocode omits original imports/globals/types/neighboring routines; the exact listed pointer/import/literal bindings supplement these gaps.",
                "1084 retained decoded addresses differ from1091 original words; memory readbacks cover all4364 bytes, independently of pseudocode coverage.",
                "Canonical import and byte agreement validate evidence custody; they do not establish semantic completeness or native runtime behavior.",
            ],
        },
        "facts": facts,
        "candidate": {
            "source": pin(H / "candidate/native_rate_mode1.c"),
            "header": pin(H / "candidate/native_rate_mode1.h"),
            "defensive_contract": working["defensive_contract"],
            "transactionality": "Processing stages complete storage/output and only commits after success. Every error leaves caller output/count and state unchanged.",
            "preserved_native_peculiarities": [
                "Short first blocks and zero-input nonterminal state changes are not replaced by generic padding.",
                "Metadata-only reset retains stale history. Fixed-rate create/destroy is the explicit fresh-seek policy.",
                "Caller n>capacity reallocates zeroed channel storage with capacity n+1024 while preserving phase/counters/fresh.",
                "Generated versus returned terminal counts remain separate; no floor(total*ratio) replacement of intermediate calls.",
                "Equal-rate operation retains the actual filter instead of bypassing it.",
            ],
            "application_policy": "Stereo up to8192-source-frame blocks; last positive block final; fresh create per seek/preroll; post-conversion event gain. This policy and application acceptance are separate from native host behavior.",
        },
        "validation": {
            "independent_review": pin(H / "validation/mode1-independent-review.json"),
            "oracle": pin(H / "validation/mode1-oracle.json"),
            "oracle_generator": pin(H / "validation/mode1-oracle.py"),
            "independent_original_word_check": pin(H / "validation/mode1-instruction-verification.json"),
            "independent_original_words": 895, "independent_original_bytes": 3580,
            "exact_output_samples": 2084, "calls": 24, "scenarios": 14,
            "complete_coefficient_difference_table_pairs": 6, "full_LoFi_count_ledgers": 4,
            "focused_mode1_tests": 6, "combined_tests": 10, "combined_suites": 2,
            "combined_seconds": 0.393,
            "successful_log": pin(H / "validation/independent-kernels-final-02.log"),
            "combined_suite_scope": "Six mode1 tests plus four callback-adapter tests; no claim all ten are mode1 tests.",
            "earlier_mode1_and_stream_tests": {"passed": 10, "suites": 2, "seconds": 1.848,
                "log": pin(H / "validation/mode1-combined-second.log")},
            "retained_initial_compile_failure": pin(H / "validation/mode1-combined-first.log"),
            "initial_failure_scope": "Swift test assertion throwing-expression syntax; not a native/candidate numerical failure.",
            "author_stream_controls": 80, "author_aggregate_controls": 35, "author_negative_controls": 11,
            "ubsan": {"passed": True, "log": pin(H / "controls/ubsan-controls.log")},
            "asan": {"passed": False, "status": "unavailable_before_main",
                     "evidence": pin(H / "controls/sanitizer-unavailable.json")},
            "oracle_independence_limit": "Coefficient oracle independently orders original operations but intentionally uses host libSystem sin. Samples use independent exact Fraction rounding/FMA. No proprietary filter execution is involved.",
            "release_acceptance": "APP013 owns full-suite/GUI acceptance; no future application result is asserted here.",
        },
        "remaining_limits": [
            "No Cubase runtime/default-selection, device-output, whole-project, mixer or full-timeline equivalence.",
            "Only this Float32 fixed-rate mono/stereo path is reconstructed; other formats, dynamic channel/rate changes and arbitrary corrupted state are outside scope.",
            "The traced _sin dependency is /usr/lib/libSystem.B.dylib. Native and candidate system-math identity across operating systems/builds remains unmeasured.",
            "Successful fixed-channel allocation is the native precondition; allocation/error behavior is defensively transactional rather than an ABI claim.",
            "Native terminal allocation-overrun cases, repeated final calls, nonfinite/subnormal sample domains and arbitrary aliases are rejected.",
            "Private raw target slices and native disassembly remain local; custody does not authorize their publication.",
        ],
        "early_description_correction": working["coefficient_contract"]["early_label_correction"],
        "snapshot_policy": pin(H / "source-snapshots.json"),
    }
    write(H / "finding.json", finding)
    paths = {p for p in H.rglob("*") if p.is_file() and "__pycache__" not in p.parts
             and p.name != "artifact-manifest.json"}
    for row in validation["functions"]:
        paths.update(R / x["path"] for x in row["files"])
        folder = R / row["directory"]
        suffix = row["entry"][2:]
        paths.add(folder / f"bundle-{suffix}.json")
        raw = folder / f"function-{suffix}.arm64.bin"
        if raw.is_file():
            paths.add(raw)
    paths.update([
        R / "research/targets/derived/Cubase15-arm64",
        R / "research/evidence/cubase-static/cpr-map-clock-001/attributes/source_tools.py",
        A.parent / "APP010/native-rate-mode0-oracle.py",
        H.parent / "rate-selection/finding.json", H.parent / "rate-converter/finding.json",
        R / ".tools/rea/node_modules/rea-agents/package.json",
        R / ".tools/rea/node_modules/rea-agents/skills/reverse-engineer-anything/SKILL.md",
        R / ".tools/rea/node_modules/rea-agents/skills/reverse-engineer-anything/references/native-and-artifacts.md",
    ])
    assert all(p.is_file() for p in paths)
    assert not any(str(p.relative_to(R)).startswith("Application/") for p in paths)
    write(H / "artifact-manifest.json", {
        "schema_version": 1, "id": "CPR-RATE-MODE1-001-MANIFEST",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Local custody of bounded study and immutable source/oracle copies.",
        "files": [pin(p) for p in sorted(paths)],
        "exclusions": ["Manifest itself", "__pycache__", "Mutable Application/test paths"],
        "proprietary_execution": False,
        "distribution_limit": "Target image/raw bytes/native analysis are private local research artifacts.",
    })
    verify()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seal", action="store_true")
    parser.add_argument("--verify", action="store_true")
    arguments = parser.parse_args()
    assert arguments.seal != arguments.verify
    seal() if arguments.seal else verify()
