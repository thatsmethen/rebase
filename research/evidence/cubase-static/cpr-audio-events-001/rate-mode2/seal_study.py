"""Seal this bounded static study once, or verify its immutable manifest.

No target code is loaded or executed. --seal copies frozen application/test
sources before making a manifest; later --verify only reads files.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone

H = Path(__file__).resolve().parent
R = H.parents[4]
A = R / "research/evidence/application/APP012"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def pin(p):
    return {"path": str(p.relative_to(R)), "bytes": p.stat().st_size, "sha256": sha(p)}


def write(p, data):
    with p.open("x") as f:
        f.write(json.dumps(data, indent=2) + "\n")


def envelope(p):
    d = json.loads(p.read_text())
    assert not d.get("isError"), p
    return d.get("structuredContent") or json.loads(d["content"][0]["text"])


def verify():
    manifest = json.loads((H / "artifact-manifest.json").read_text())
    for row in manifest["files"]:
        p = R / row["path"]
        assert p.is_file(), p
        assert p.stat().st_size == row["bytes"], p
        assert sha(p) == row["sha256"], p
    print(json.dumps({
        "passed": True, "verified_files": len(manifest["files"]),
        "finding": pin(H / "finding.json"),
        "manifest": pin(H / "artifact-manifest.json"),
        "scope": "Read-only byte custody, not runtime or semantic revalidation."
    }))


def seal():
    assert not (H / "artifact-manifest.json").exists(), "Already sealed; use --verify."
    assert not (H / "finding.json").exists(), "Refuse to replace a finding."
    verification = json.loads((H / "verification.json").read_text())
    assert verification["passed"] and verification["summary"] == {
        "new_functions": 7, "reused_functions": 17,
        "original_native_words": 1866, "rea_instruction_addresses": 916,
        "bytes_verified": 7464,
    }
    imported = envelope(H / "evidence-import.json")["result"]
    assert imported == {"imported": 48, "unknowns_added": 0, "total": 48}
    for name in ("pass1", "pass2"):
        log = (H / name / "run.log").read_text()
        assert log.endswith("CLOSED: isolated raw-slice MCP session\n")
        for line in log.splitlines()[:-1]:
            assert json.loads(line)["isError"] is False
    assert (H / "import-run.log").read_text().endswith("CLOSED: evidence import session\n")
    review_path = A / "mode2-independent-review.json"
    assert sha(review_path) == "70020d6474cfccf4a8934d2f19b62ed8db61bec631c52518e968b1a1872ea5b8"
    review = json.loads(review_path.read_text())
    assert review["status"] == "no_actionable_defect_in_reviewed_bounded_domain"
    for row in review["reviewed_sources_and_evidence"]:
        p = R / row["path"]
        assert p.stat().st_size == row["bytes"] and sha(p) == row["sha256"], p
    build_path = A / "soxr-public-build/finding.json"
    assert sha(build_path) == "b1a89c059919631331be61bea29940fb39d7a0cf38fd0d685b29d2279e2d8965"
    build = json.loads(build_path.read_text())

    copies = [
        (R / "Application/Sources/RebaseTimingDSP/native_rate_mode2.c", H / "candidate/native_rate_mode2.c"),
        (R / "Application/Sources/RebaseTimingDSP/include/native_rate_mode2.h", H / "candidate/native_rate_mode2.h"),
        (R / "Application/Tests/RebaseCoreTests/NativeRateMode2Tests.swift", H / "validation/NativeRateMode2Tests.swift"),
        (R / "Application/Sources/RebaseSoXR/rebase_soxr.c", H / "validation/public-backend/rebase_soxr.c"),
        (R / "Application/Sources/RebaseSoXR/include/rebase_soxr.h", H / "validation/public-backend/rebase_soxr.h"),
        (R / build["build"]["library"]["path"], H / "validation/public-backend/libsoxr.0.1.2.dylib"),
        (R / "Application/ThirdParty/soxr-source-manifest.json", H / "validation/public-backend/source-manifest.json"),
        (build_path, H / "validation/public-backend/finding.json"),
        (A / "soxr-public-build/artifact-manifest.json", H / "validation/public-backend/artifact-manifest.json"),
    ]
    for name in (
        "mode2-wrapper-oracle.py", "mode2-wrapper-oracle.json",
        "mode2-public-oracle.py", "mode2-public-oracle.json",
        "verify-mode2-instructions.py", "mode2-instruction-verification.json",
        "mode2-tests-round1.log", "mode2-tests-round2.log",
        "mode2-independent-review.json", "mode2-swift-integration-review.json",
    ):
        copies.append((A / name, H / "validation" / name))
    snapshot_rows = []
    for src, dst in copies:
        assert not dst.exists(), dst
        dst.parent.mkdir(parents=True, exist_ok=True)
        data = src.read_bytes()
        with dst.open("xb") as f:
            f.write(data)
        assert sha(src) == sha(dst)
        snapshot_rows.append({"historical_original": pin(src), "immutable_snapshot": pin(dst)})
    write(H / "source-snapshots.json", {
        "policy": "Historical original paths are descriptive only. The study manifest pins copies, not mutable application/test/build paths.",
        "copies": snapshot_rows,
    })

    # Independent original image binding for the wrapper's actual receiver slots.
    sys.path.insert(0, str(R / "research/evidence/cubase-static/cpr-map-clock-001/attributes"))
    import source_tools as s
    slots = {0x10: 0x100313adc, 0x18: 0x100313b44, 0x20: 0x100313b74,
             0x28: 0x100313c2c, 0x30: 0x100313bcc, 0x38: 0x100313c64,
             0x40: 0x100313c78}
    bindings = []
    for slot, target in slots.items():
        region = s.region(0x104461a08 + slot, 8)
        assert int.from_bytes(bytes.fromhex(region["bytes_hex"]), "little") == target
        bindings.append({"slot": hex(slot), "target": hex(target), "original": region})
    write(H / "wrapper-slot-bindings.json", {
        "source_sha256": s.PIN, "vtable": "0x104461a08",
        "bindings": bindings,
        "limit": "Only these original pointer cells are bound; no claim about other adjacent tables."
    })

    by_address = {f["entry"]: f for f in verification["functions"]}

    def fact(number, title, claims, addresses):
        return {
            "id": f"RATE-MODE2-{number}", "title": title, "claims": claims,
            "source_functions": [{
                "entry": a, "evidence_ids": by_address[a]["evidence_ids"],
                "native": by_address[a]["files"][0]["path"],
            } for a in addresses],
        }

    facts = [
        fact("01", "Concrete fresh Float32 wrapper and child",
             [
                 "Factory 0x1003136b8 constructs wrapper vtable 0x104461a08 and child 0x104461a80; the retained packet path is wrapper +0x40 -> 0x100313c78 -> 0x1003141bc.",
                 "Wrapper source/output rates produce ratio=RN64(output/source), input capacity 65536, maximum internal positive chunk 65408. External sample format 5 selects child format 0 (Float32 interleaved).",
                 "Child quality byte is 1 with its second quality flag 0; retained initializer uses public-ABI io_spec(0,0), quality_spec(6,0), runtime_spec(0). Availability/factory-conditioned mode selection belongs to the separate rate-selection finding.",
                 "Fresh successful initialization is a precondition. Equal-rate operation still uses the wrapper, delay/discard and terminal path when this mode is explicitly selected."
             ], ["0x1003136b8", "0x100313adc", "0x100313b44", "0x100313b74", "0x100313c78", "0x100314ce0", "0x100314ff8", "0x100314fe8", "0x100315000"]),
        fact("02", "Artificial delay and actual initialized storage",
             [
                 "P=ceil(ratio)*2048. Child output capacity=ceil(RN64(FMA(65536,ratio,P)+1024)); FMA is explicit at 0x10031518c, followed by separate FADD at 0x100315198 and unsigned ceil conversion at 0x10031519c.",
                 "The full allocated Float32 output storage is cleared: 0x1003151e4 forms channels*outputCapacity and 0x100315248..250 passes it to imported _vDSP_vclr at 0x103881efc. It is not merely a P-frame prefix clear.",
                 "Fresh wrapper delay and discard are P; cumulative input/visible/ideal are zero. Child input end/consumed/pending/output read are zero; output end starts at P."
             ], ["0x100314f88", "0x100313b74", "0x100315000"]),
        fact("03", "Requested count and initial discard recurrence",
             [
                 "For positive n: ideal=RN64(n*ratio); base=trunc(ideal); drift=RN64(RN64(cumulativeIdeal+ideal)-Double(cumulativeVisible+base)); requested=base+(drift>1). A zero requested count is forced to 1.",
                 "The strict comparison is >1, not >=1. Integer accumulation and the shown binary64 operations remain distinct; they are not fused or reassociated.",
                 "Discard>=requested yields visible=0, decreases discard by requested and contributes 0 to cumulativeIdeal. Partial discard yields visible=requested-discard and contribution RN64(ideal-discard). With no discard, visible=requested and contribution=ideal.",
                 "The successful positive call adds n to cumulative input, visible to cumulative visible, and separately rounds contribution+cumulativeIdeal."
             ], ["0x1003141bc"]),
        fact("04", "One backend call, three different frame counts, and preserved tails",
             [
                 "Before append: if inputEnd+n>=inputCapacity and consumed!=0, shift only [consumed,inputEnd) to index 0 and reset consumed. If outputEnd+requested>=floor(outputCapacity/2) and outputRead!=0, shift only [outputRead,outputEnd) and reset read.",
                 "Compaction does not clear trailing allocation storage. The current input is appended; one backend call receives pending+n frames from input+consumed and output capacity exactly requested. NULL input clears pending and passes NULL/zero input.",
                 "Actual backend inputUsed and outputProduced update pending, consumed, and output end. Native code uses low 32-bit returned counts and does not branch on the backend error pointer.",
                 "The wrapper copies requested frames from outputRead, not outputProduced. Thus the returned sequence can include initialized zero or retained stale allocation cells when backend production is shorter. It then advances outputRead by requested and resets cursors only when read==end.",
                 "Float32 publication is bit copying through 0x1037bce78. This is not a retry-until-produced or plain soxr_process contract."
             ], ["0x100315434", "0x100315438", "0x1037bce78"]),
        fact("05", "Single terminal operation and conditional drain",
             [
                 "A final positive block first executes normal positive processing. It computes extra=trunc(Double(P)/ratio), repeats that caller block's last frame extra times, and processes the padding as a nonfinal positive block.",
                 "NULL/zero final skips normal child processing, uses zero padding instead, and retains the precomputed base/drift return term. The observed checked reachable states have that term zero; the reconstruction preserves the formula.",
                 "After padding, restore cumulativeInput to its saved real-input value while retaining padding's discard/cumulativeVisible/cumulativeIdeal changes. remaining=trunc(RN64(Double(savedInput)*ratio))-cumulativeVisible.",
                 "Only if remaining>0, call the child with NULL/zero input and request remaining, appending that many returned frames. This final drain does not increment cumulativeVisible.",
                 "Native oversized caller splitting is retained as an excluded branch. Its terminal last-frame expression uses the original caller pointer and the residual count; the reconstruction admits caller blocks <=65408 and does not invent a generalized oversized terminal rule."
             ], ["0x1003141bc", "0x100315438"]),
        fact("06", "Destruction and reset limits",
             [
                 "0x1003152b8 frees the selected-format owned buffers and deletes a nonnull backend handle; 0x100314eb4 invokes cleanup before base destruction.",
                 "0x100315384 clears full child output storage and child cursors, but does not reset or recreate the backend handle. Wrapper virtual +0x30 at 0x100313bcc simply returns zero; it is not a reset operation.",
                 "The reconstruction intentionally exposes no in-place reset. Application seek uses a fresh backend/wrapper and prerolls the same partition sequence; this is an explicit application policy."
             ], ["0x1003152b8", "0x100314eb4", "0x100315384", "0x100313bcc", "0x100316364"]),
    ]
    controls = json.loads((H / "candidate/controls.json").read_text())
    assert controls["passed"] and len(controls["controls"]) == 40
    stress = (H / "candidate/stress-ubsan.log").read_text()
    assert stress == "UBSan reconstructed-wrapper synthetic calls=384 passed\n"
    finding = {
        "id": "CPR-RATE-MODE2-001", "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "sealed_bounded_static_contract_and_reconstruction",
        "scope": "Native successful fresh Float32 mode2 buffered wrapper; defensive visible-region reconstruction with independently built public SoXR callback backend. No Cubase/bundled-library execution.",
        "evidence_classes": ["original-byte static analysis", "REA retained analysis", "synthetic reconstructed-code controls", "independent public-library wrapper comparisons"],
        "proprietary_target_executions": 0, "cubase_runtime_sample_comparisons": 0,
        "public_open_source_backend_executed": True,
        "target": {
            "product": "Cubase Pro 15.0.30.287 macOS arm64",
            "image": pin(R / "research/targets/derived/Cubase15-arm64"),
            "edition_limit": "Static shared executable provenance does not establish licensed runtime edition behavior."
        },
        "native_custody": {
            **verification["summary"], "retained_canonical_records": 48,
            "canonical_import": imported,
            "verification": pin(H / "verification.json"),
            "concrete_child_vtable": "0x104461a80",
            "wrapper_slots": pin(H / "wrapper-slot-bindings.json"),
            "new_raw_slice_sessions_closed": 7,
            "isolated_analysis_mcp_processes_closed": 2,
            "evidence_import_processes_closed": 1,
            "provider": "rea-agents@6.7.0; Ghidra raw arm64 slices, default analysis, 2G heap; exact retained request/tool inventories.",
            "context_limits": [
                "Raw slices omit imports, neighboring functions, globals, types and switch tables. The specified original vtable/switch/import bindings supplement these omissions.",
                "916 REA decoded addresses do not mean 1866 complete pseudocode instructions; original words and exact full interval readbacks cover the separate 7464-byte custody check.",
                "Source readback and canonical import validate evidence custody, not semantic completeness or runtime behavior."
            ],
        },
        "facts": facts,
        "candidate": {
            "source": pin(H / "candidate/native_rate_mode2.c"),
            "header": pin(H / "candidate/native_rate_mode2.h"),
            "domain": [
                "Integral finite 8000...192000 Hz input/output, mono or stereo; equal rate supported when explicitly selected.",
                "Finite Float32 normal-or-zero samples; nearest-even and hardware subnormal flushing disabled. Nonzero subnormal inputs/produced outputs are rejected.",
                "Positive caller blocks 1...65408, exactly one final positive block or NULL/zero final; cumulative source and returned frame cap 16000000.",
                "Checked allocated storage, nonoverlapping caller buffers, stable callback-owned handle, successful fresh initialization, no rates/channels change."
            ],
            "count_api": "Nonmutating count/count_blocks reproduce requested/discard/EOF arithmetic for the same partitions, without invoking the backend. Predictions concern successful returned frames, not actual backend production or guaranteed success for arbitrary providers.",
            "application_partition_policy": "Root integration uses up to8192 real source frames, last positive block final, no added empty EOF, fresh wrapper for seek/preroll, and event gain after conversion. Application acceptance is a separate record.",
            "defensive_deviations": [
                "Backend errors, impossible counts, capacity/invariant violations and invalid produced samples fail closed; original successful-call trace ignores the error pointer.",
                "Public argument/output-capacity/input-sample preflight preserves usable state. Subsequent processing errors poison state; caller must discard it.",
                "On processing failure caller output/count are not published; backend/internal state may have advanced. This is not a rollback claim.",
                "Only returned visible samples are published. Native discarded/unreturned writes outside that visible interval are not reproduced as ABI side effects.",
                "Zero-input nonfinal, oversized callers, repeated terminal calls, post-finish reuse, arbitrary pointer aliasing, other formats, unsafe state and arbitrary callback mutation are rejected or excluded.",
                "Fresh input allocation is also zeroed defensively; unused input cells are not offered to the backend in the supported contract."
            ],
        },
        "validation": {
            "independent_review": pin(H / "validation/mode2-independent-review.json"),
            "focused_swift": {"passed": 7, "suites": 1, "seconds": 1.672,
                              "log": pin(H / "validation/mode2-tests-round2.log")},
            "retained_initial_test_issue": pin(H / "validation/mode2-tests-round1.log"),
            "spy_cases": 47, "public_wrapper_cases": 27,
            "public_returned_sample_bits_checked": 561454,
            "full_source_count_ledgers": review["validation"]["full_LoFi_counts"],
            "author_synthetic_stream_controls": 40,
            "author_additional_control_groups": controls["additional_checks"],
            "ubsan_synthetic_calls": 384,
            "ubsan_log": pin(H / "candidate/stress-ubsan.log"),
            "independence_limits": review["independence"],
            "independent_native_word_check": review["original_bytes"],
            "application_integration_review": pin(H / "validation/mode2-swift-integration-review.json"),
            "release_acceptance": "Full suite, GUI and final application acceptance are owned by APP012; no future test result is asserted here."
        },
        "public_backend": {
            "finding": pin(H / "validation/public-backend/finding.json"),
            "upstream_commit": build["upstream_commit"],
            "build_choice": "Pinned scalar CR32+CR64 public SoXR0.1.3, no SIMD/OpenMP/VR, io(0,0), quality(6,0)=VHQ28bit, runtime(0).",
            "limit": "The same public backend is used on both oracle/candidate comparison sides; wrapper/bridge correctness is tested, not an independent filter implementation or equivalence to the bundled build."
        },
        "remaining_limits": [
            "No native runtime selection, sample comparison, device delivery, full Cubase project playback or whole-host equivalence.",
            "Inspected policy1 native accessors conditionally select mode2 or mode1 through availability/factory paths. This explicit mode2 application option is not a global default assertion.",
            "Bundled source modifications, toolchain/SIMD/FP settings and backend error/lifetime behavior remain unverified.",
            "Arbitrary caller partitions may change requested/discard/EOF behavior; prediction and processing must use the same partition sequence.",
            "The positive and NULL EOF cases are distinct; no silent replacement with generic backend flush or floor(total*ratio) is justified.",
            "Raw proprietary binary slices and disassembly remain local research artifacts. This manifest is custody, not authorization to redistribute vendor code."
        ],
        "snapshot_policy": pin(H / "source-snapshots.json"),
    }
    write(H / "finding.json", finding)

    # Local study records, plus immutable original evidence actually relied on.
    paths = {p for p in H.rglob("*") if p.is_file() and "__pycache__" not in p.parts
             and p.name != "artifact-manifest.json"}
    # Include the copied nested public manifest; only exclude this study's self.
    paths.add(H / "validation/public-backend/artifact-manifest.json")
    for f in verification["functions"]:
        paths.update(R / x["path"] for x in f["files"])
        directory = R / f["directory"]
        suffix = f["entry"][2:]
        for name in (f"bundle-{suffix}.json", f"function-{suffix}.arm64.bin"):
            p = directory / name
            if p.exists():
                paths.add(p)
    paths.update([
        R / "research/targets/derived/Cubase15-arm64",
        R / "research/evidence/cubase-static/cpr-map-clock-001/attributes/source_tools.py",
        H.parent / "rate-selection/mode2-wrapper-handoff.json",
        H.parent / "rate-selection/finding.json",
        H.parent / "rate-converter/finding.json",
        R / ".tools/rea/node_modules/rea-agents/package.json",
        R / ".tools/rea/node_modules/rea-agents/skills/reverse-engineer-anything/SKILL.md",
        R / ".tools/rea/node_modules/rea-agents/skills/reverse-engineer-anything/references/native-and-artifacts.md",
    ])
    assert all(p.is_file() for p in paths)
    assert not any(str(p.relative_to(R)).startswith("Application/") for p in paths)
    write(H / "artifact-manifest.json", {
        "schema_version": 1, "id": "CPR-RATE-MODE2-001-MANIFEST",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Exact local custody of this study and listed read-only inputs. Live Application/test/build paths are represented by immutable copies.",
        "proprietary_execution": False,
        "files": [pin(p) for p in sorted(paths)],
        "exclusions": ["This manifest itself", "__pycache__", "Unreferenced prior study records"],
        "distribution_limit": "Original image, raw slices and native analysis are local proprietary-source evidence; they are not public code artifacts.",
    })
    verify()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--seal", action="store_true")
    group.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    seal() if args.seal else verify()
