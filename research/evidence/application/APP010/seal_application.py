#!/usr/bin/env python3
"""Accept APP010, then seal after status documents reference the acceptance.

Writes are exclusive. This checks local evidence and runs no proprietary code.
The private repository contains authored source/controls/reports, while raw
vendor artifacts, QA packages, logs and build snapshots remain local.
"""
from pathlib import Path
import datetime
import hashlib
import json
import plistlib
import shutil
import sys

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
NATIVE = ROOT / "research/evidence/cubase-static/cpr-audio-events-001"
FINAL_BINARY = "d88fc0761b23ef0cb91c15b9cf67abf3e92c9e23a24a04563fc3ea6c15a0dc33"
FINAL_TEST_LOG = "96b68e3fbd0ef38a32be53d6ba0aefe980e52601ab893919710bffc5a38ef4af"
SUPERSEDED_TEST = "Application/Tests/RebaseCoreTests/NativeRateMode0Tests.swift"


def record(path):
    data = path.read_bytes()
    return {"path": str(path.relative_to(ROOT)), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def write(name, value):
    path = OUT / name
    with path.open("x") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")
    return record(path)


def matches(path, expected):
    actual = record(path)
    return actual["bytes"] == expected["bytes"] and actual["sha256"] == expected["sha256"]


def verify_manifest(path, superseded=None):
    rows = json.loads(path.read_text())["files"]
    changes = []
    for row in rows:
        current = ROOT / row["path"]
        if matches(current, row):
            continue
        assert superseded and row["path"] in superseded, row["path"]
        archived = superseded[row["path"]]
        assert matches(archived, row), row["path"]
        changes.append({"original_manifest_entry": row, "preserved_bytes": record(archived),
                        "current": record(current),
                        "reason": "Independent high-ratio ring test added after the native rate study was sealed; kernel and header unchanged."})
    return {"manifest": record(path), "files_checked": len(rows),
            "unchanged_at_original_path": len(rows) - len(changes),
            "superseded_application_files": changes,
            "all_original_bytes_verified": True}


def accept():
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    test = OUT / "core-tests-final.log"
    assert record(test)["sha256"] == FINAL_TEST_LOG
    assert "Test run with 191 tests in 28 suites passed" in test.read_text()
    assert "Build complete!" in (OUT / "build-release.log").read_text()
    app = ROOT / "Application/dist/Rebase.app"
    info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    assert info["CFBundleShortVersionString"] == "0.10.0" and info["CFBundleVersion"] == "10"
    binary = record(app / "Contents/MacOS/Rebase")
    assert binary["sha256"] == FINAL_BINARY
    assert binary["sha256"] == json.loads((OUT / "gui-release-build.json").read_text())["sha256"]

    independent = json.loads((OUT / "gui-independent-check.json").read_text())
    assert independent["status"] == "passed" and len(independent["groups"]) == 8
    assert independent["release"]["binary"] == binary
    assert independent["tests"]["log"] == record(test)
    for row in independent["gui_evidence"]:
        assert matches(ROOT / row["path"], row)
    package_files = 0
    for name in ["gui-package-before.json", "gui-equal-rate-package-before.json"]:
        before = json.loads((OUT / name).read_text())
        package = ROOT / before["copy"]
        actual_paths = {str(p.relative_to(package)) for p in package.rglob("*") if p.is_file()}
        assert actual_paths == {r["path"] for r in before["files"]}
        for row in before["files"]:
            assert matches(package / row["path"], row), row["path"]
            package_files += 1
    assert package_files == 10

    historical = write("historical-final-integrity.json", {
        "APP009": verify_manifest(ROOT / "research/evidence/application/APP009/artifact-manifest.json"),
        "timeline_playback": verify_manifest(NATIVE / "timeline-playback/artifact-manifest.json")})
    native_integrity = write("native-final-integrity.json", {
        "rate_samples": verify_manifest(NATIVE / "rate-samples/artifact-manifest.json", {
            SUPERSEDED_TEST: OUT / "historical-source-snapshot/NativeRateMode0Tests.swift"}),
        "live_consumer": verify_manifest(NATIVE / "live-consumer/artifact-manifest.json")})

    gui = write("gui-observations.json", {
        "id": "APP010-GUI", "created_utc": now, "groups_passed": 8, "executable": binary,
        "groups": [{"id": g["name"], "result": "passed", "observation": g["observations"],
                    "records": [record(OUT / name) for name in g["files"]]}
                   for g in independent["groups"]],
        "screenshot": record(OUT / "gui-converted-playing.png"),
        "package_files_unchanged": package_files,
        "scope": "Final application binary and self-authored synthetic PCM, observed through native UI. Mixer peaks are engine telemetry, not DAC captures or Cubase runtime comparisons.",
        "converted_fixture": {"source_rate": 44100, "output_rate": 48000,
                              "input_frames": 1058400, "output_frames": 1151999,
                              "displayed_end_seconds": "23.999", "added_tail_frames": 0},
        "setup_observations": [
            "A snapshot after quitting returned procNotFound; the application was subsequently relaunched.",
            "The first pause attempt occurred after the24-second event had already ended. Restart/pause/resume and completion were then explicitly exercised."
        ]})

    source = OUT / "final-source-snapshot"
    source.mkdir()
    for directory in ["Sources", "Tests"]:
        shutil.copytree(ROOT / "Application" / directory, source / directory)
    for name in ["Package.swift", "Package.resolved", "build-app.sh", "test-app.sh"]:
        shutil.copy2(ROOT / "Application" / name, source / name)
    source_manifest = write("final-source-manifest.json", {
        "files": [record(p) for p in sorted(source.rglob("*")) if p.is_file()]})
    bundle = OUT / "final-build-snapshot/Rebase.app"
    shutil.copytree(app, bundle)
    validation = write("application-validation.json", {
        "id": "APP010", "created_utc": now, "version": "0.10.0", "build": 10,
        "status": "bounded_native_mode0_rate_conversion_and_stereo_transfer_integrated_and_checked",
        "full_fidelity_objective": "incomplete", "cubase_runtime_comparisons": 0, "target_executions": 0,
        "executable": record(bundle / "Contents/MacOS/Rebase"), "source_manifest": source_manifest,
        "tests": {"passed": 191, "suites": 28, "log": record(test),
                  "scope": "Application regression suite, exact rational/IEEE rate oracle, partition and seek suffix controls, gain order, stereo ring branches and high-ratio wrapper delivery.",
                  "earlier_release_run": "core-tests-release.log records190tests; the final191test run adds an independent test only, with no application source change."},
        "build_log": record(OUT / "build-release.log"), "gui": gui,
        "independent_reviews": [record(OUT / name) for name in [
            "rate-stream-independent-review.json", "rate-stream-ring-review-addendum.json",
            "rate-gain-order-review.json", "gui-independent-check.json"]],
        "independent_oracles": [record(OUT / name) for name in [
            "native-rate-mode0-oracle.py", "native-rate-mode0-oracle.json",
            "native-rate-mode0-ring-oracle.py", "native-rate-mode0-ring-oracle.json"]],
        "static_findings": [record(NATIVE / name / "finding.json") for name in ["rate-samples", "live-consumer"]],
        "native_integrity": native_integrity, "historical_integrity": historical,
        "implemented": [
            "Explicit project-rate audition uses the recovered native mode0 upsampling recurrence, preserving binary64 phase/history, FMA operation order, binary32 outputs and exact emitted count across8192-source-frame blocks.",
            "Verified PCM is converted before a separate binary32 event-gain multiplication. Conversion admission, floating-point environment, capacity and finite sample checks reject unsupported inputs.",
            "Recovered32768-frame stereo ring producer/consumer value operations are integrated through a serialized fill/drain wrapper; output blocks larger than ring capacity split into at most8192-frame transfers.",
            "Four converted buffers are retained and queued to AVAudioEngine, with generation checks, refill error handling and completion waiting for delivered buffers and stream EOF.",
            "Seek resets and prerolls the converter from source zero, retaining the crossing-block suffix; pause/resume/seek revalidate source and attached media.",
            "Original-rate audition remains the default. Explicit selection, edit/undo and failed verification preserve the existing barriers on unresolved full-project playback and export."
        ],
        "limits": [
            "One admitted direct zero-origin complete stereo PCM24 source event; other event processing, routing, instruments, mixer/PDC, automation and CPR writing remain incomplete.",
            "Only explicitly selected mode0 upsampling at integral8000..192000Hz rates is admitted. Downsampling, equal-rate conversion, SoXR/default converter selection and upstream native engine routing are unresolved.",
            "The recovered ring is filled and drained before AVAudioEngine scheduling. This does not reproduce the native callback graph, polling, concurrent producer scheduling or device timing.",
            "Source PCM remains resident in memory. Four-buffer refill runs on the main actor and can underrun during sufficiently long UI stalls; it is not a hard real-time streaming engine.",
            "Preroll seeking, output frame rounding and host scheduling are application policy. No native seek quantizer, DAC output, device resampling or Cubase runtime equivalence has been established.",
            "Exact original bytes, earlier failures and superseded application test identity are retained. Raw vendor artifacts and local build/GUI captures are not distributed with the private repository."
        ],
        "retained_corrections": [
            "Initial full-suite compilation hit a Swift type-check timeout in a nested test helper expression; an explicit typed loop resolved it before final tests/build.",
            "A throwing-initializer probe confirmed Swift runs deinit after stored properties initialize; manual failure-branch deallocation was removed to avoid double-free before the final build.",
            "The earlier renderer-selection inference from w2=5 at10046e60c was corrected by the new live-consumer study: the argument is open flags, not a PCM format.",
            "The native rate study sealed an earlier test-file identity. The later independent high-ratio test supersedes it; both byte identities are verified without rewriting that study's manifest."
        ],
        "next": "Trace the native default rate backend and downsampling behavior, then bind the live consumer to upstream engine/event routing and recover native seek coordinates before broadening project playback."
    })
    print(json.dumps({"validation": validation, "gui": gui,
                      "source_files": len(json.loads((OUT / "final-source-manifest.json").read_text())["files"])}))


def seal():
    assert (OUT / "application-validation.json").exists()
    verify_manifest(OUT / "final-source-manifest.json")
    source = OUT / "final-source-snapshot"
    for path in source.rglob("*"):
        if path.is_file():
            assert (ROOT / "Application" / path.relative_to(source)).read_bytes() == path.read_bytes(), path
    assert record(ROOT / "Application/dist/Rebase.app/Contents/MacOS/Rebase")["sha256"] == FINAL_BINARY
    status = OUT / "final-status-snapshot"
    status.mkdir()
    for name in ["README.md", "research/study.json", "research/coverage.json", "research/rea-steering.json"]:
        target = status / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    manifest = write("artifact-manifest.json", {"id": "APP010",
        "scope": "Local source/build/status snapshots, analytical controls, native application observations, synthetic media and retained failures. Vendor fixtures and raw captures stay local.",
        "files": [record(p) for p in sorted(OUT.rglob("*")) if p.is_file()
                  and p.name != ".DS_Store" and "__pycache__" not in p.parts]})
    verified = verify_manifest(OUT / "artifact-manifest.json")
    write("final-integrity.json", {"manifest": manifest,
        "validation": record(OUT / "application-validation.json"), "sealed": True,
        "files_verified": verified["files_checked"]})
    print(json.dumps(manifest))


if __name__ == "__main__":
    seal() if "--seal" in sys.argv else accept()
