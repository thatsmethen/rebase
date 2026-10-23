#!/usr/bin/env python3
"""Accept APP011 after independent GUI review; seal after status updates.

All output creation is exclusive. This script hashes/copies local evidence and
does not run the application, tests, libraries, or proprietary target code.
"""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import plistlib
import shutil

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
NATIVE = ROOT / "research/evidence/cubase-static/cpr-audio-events-001"
FINAL_BINARY = "48f957c4c3df0224f0322b9abfc88535a94fcad03a80d57a4abcb6ad4938b995"
FINAL_TEST_LOG = "74c2a05b6c7d6a2413b04f71818cb5a683d8676dbc9c157653cdc7ea548220d9"
NATIVE_PINS = {
    "rate-downsample": {
        "finding": "c3b4f2e05b0f7a7095e9f412d6087de65c3a095f1302d4608a59d61278e8aec6",
        "manifest": "edc9594c3c83acf474f50f66b9975a3be72b0caafe5510c3170464dbadfc1d95",
        "count": 173, "relative_to_study": False,
    },
    "rate-selection": {
        "finding": "2b0d82f0b5922b0e7bd279f1a19955803b982b629b6508d941be58ebf75e376b",
        "manifest": "29a2deefdabf2b15c715ccc897e9b47c349b3fd98f18f9ed54a3a608faf48658",
        "count": 158, "relative_to_study": True,
    },
}


def record(path):
    before = path.stat()
    data = path.read_bytes()
    after = path.stat()
    fields = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    assert fields(before) == fields(after), f"Changed while reading: {path}"
    return {"path": str(path.relative_to(ROOT)), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def write(name, value):
    path = OUT / name
    with path.open("x") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")
    return record(path)


def matches(path, expected):
    actual = record(path)
    return all(actual[key] == expected[key] for key in ("bytes", "sha256"))


def verify_manifest(path, *, base=ROOT):
    rows = json.loads(path.read_text())["files"]
    assert len({r["path"] for r in rows}) == len(rows), path
    for row in rows:
        assert matches(base / row["path"], row), row["path"]
    return {"manifest": record(path), "files_checked": len(rows),
            "all_original_bytes_verified": True}


def require_new(names):
    for name in names:
        assert not (OUT / name).exists(), f"Refusing overwrite: {name}"


def accept():
    require_new(["application-validation.json", "gui-observations.json",
                 "historical-final-integrity.json", "native-final-integrity.json",
                 "final-source-snapshot", "final-source-manifest.json", "final-build-snapshot"])
    test = OUT / "core-tests-first.log"
    assert record(test)["sha256"] == FINAL_TEST_LOG
    assert "Test run with 200 tests in 29 suites passed" in test.read_text()
    assert "Build complete!" in (OUT / "build-release.log").read_text()
    app = ROOT / "Application/dist/Rebase.app"
    info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    assert info["CFBundleShortVersionString"] == "0.11.0" and info["CFBundleVersion"] == "11"
    binary = record(app / "Contents/MacOS/Rebase")
    assert binary["sha256"] == FINAL_BINARY
    observed_build = json.loads((OUT / "gui-release-build.json").read_text())
    assert all(observed_build[key] == binary[key] for key in ("path", "bytes", "sha256"))

    independent = json.loads((OUT / "gui-independent-check.json").read_text())
    assert independent["status"] == "passed"
    expected = independent["expected_group_names"]
    groups = independent["groups"]
    assert expected and len(set(expected)) == len(expected)
    assert sorted(g["name"] for g in groups) == sorted(expected)
    assert independent["release"]["binary"] == binary
    assert independent["tests"]["log"] == record(test)
    assert independent["tests"]["passed"] == 200 and independent["tests"]["suites"] == 29
    for row in independent["gui_evidence"]:
        assert matches(ROOT / row["path"], row), row["path"]
    for group in groups:
        assert group["files"] and group["observations"]
        assert all(any(row["path"] == str((OUT / name).relative_to(ROOT))
                       for row in independent["gui_evidence"]) for name in group["files"])

    baseline = json.loads((OUT / "gui-package-baselines.json").read_text())
    assert len(baseline["controls"]) == 3
    package_files = 0
    for control in baseline["controls"]:
        package = ROOT / control["copy"]
        actual = {str(p.relative_to(package)) for p in package.rglob("*") if p.is_file()}
        assert actual == {row["path"] for row in control["files"]}
        for row in control["files"]:
            assert matches(package / row["path"], row), row["path"]
            package_files += 1
    assert package_files == 15

    previous = ROOT / "research/evidence/application/APP010/artifact-manifest.json"
    previous_pin = json.loads((OUT / "baseline-integrity.json").read_text())["prior_manifest"]
    assert matches(previous, previous_pin)
    historical_result = {"APP010": verify_manifest(previous)}
    native_result = {}
    for name, pin in NATIVE_PINS.items():
        directory = NATIVE / name
        manifest = directory / "artifact-manifest.json"
        assert record(manifest)["sha256"] == pin["manifest"]
        assert record(directory / "finding.json")["sha256"] == pin["finding"]
        checked = verify_manifest(manifest, base=directory if pin["relative_to_study"] else ROOT)
        assert checked["files_checked"] == pin["count"]
        native_result[name] = checked

    reviews = ["rate-down-independent-review.json", "rate-down-stream-review.json",
               "gui-independent-check.json"]
    for name in reviews:
        review = json.loads((OUT / name).read_text())
        for row in review.get("source_pins", []) + review.get("inputs", []):
            if row["path"].startswith("Application/"):
                assert matches(ROOT / row["path"], row), row["path"]

    # All acceptance predicates passed before any acceptance output is created.
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    historical = write("historical-final-integrity.json", historical_result)
    native_integrity = write("native-final-integrity.json", native_result)
    gui = write("gui-observations.json", {
        "id": "APP011-GUI", "created_utc": now, "groups_passed": len(groups),
        "executable": binary,
        "groups": [{"id": g["name"], "result": "passed", "observation": g["observations"],
                    "records": [record(OUT / name) for name in g["files"]]} for g in groups],
        "package_files_unchanged": package_files,
        "scope": "Native application UI with authored synthetic PCM; output peaks are engine "
                 "telemetry, not DAC captures or Cubase runtime comparisons.",
        "fixture_counts": [
            {"source_rate": 44100, "output_rate": row["output_rate"],
             "input_frames": row["input_frames"], "output_frames": row["output_frames"]}
            for row in json.loads((OUT / "native-rate-down-count-oracle.json").read_text())["vectors"]
            if row["source_rate"] == 44100 and row["output_rate"] in (16000, 32000)
            and row["input_frames"] == 1058400],
    })

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
    assert record(bundle / "Contents/MacOS/Rebase")["sha256"] == FINAL_BINARY
    validation = write("application-validation.json", {
        "id": "APP011", "created_utc": now, "version": "0.11.0", "build": 11,
        "status": "explicit_mode0_downsample_source_audition_integrated_and_checked",
        "full_fidelity_objective": "incomplete", "cubase_runtime_comparisons": 0,
        "target_executions": 0, "executable": record(bundle / "Contents/MacOS/Rebase"),
        "source_manifest": source_manifest,
        "tests": {"passed": 200, "suites": 29, "log": record(test),
                  "scope": "Application regression suite, rational/IEEE downsample sample/state "
                           "controls, large partition/count controls, source-event seek suffix "
                           "and provenance barriers. No target execution."},
        "build_log": record(OUT / "build-release.log"), "gui": gui,
        "independent_reviews": [record(OUT / name) for name in reviews],
        "independent_oracles": [record(OUT / name) for name in [
            "native-rate-down-oracle.py", "native-rate-down-oracle.json",
            "native-rate-down-count-oracle.py", "native-rate-down-count-oracle.json",
            "downsample-instruction-verification.json"]],
        "static_findings": [record(NATIVE / name / "finding.json") for name in NATIVE_PINS],
        "native_integrity": native_integrity, "historical_integrity": historical,
        "implemented": [
            "Explicit project-rate audition now supports both previously accepted mode0 "
            "upsampling and the bounded mono/stereo Float32 downsampling recurrence.",
            "Downsample processing and count prediction share the same partition sequence. "
            "An input-then-output arena explicitly chooses ABOVE pointer order, and partitions "
            "avoid an unsupported singleton pending call.",
            "Zero-output blocks advance source/state; actual aggregate emitted count controls "
            "duration. No padding or flush invents an extra ending frame.",
            "Conversion precedes separate Float32 event gain; seek rebuilds and prerolls the "
            "same blocks and retains the crossing suffix. Fresh preparation checks provenance.",
            "The existing stereo transfer and four-buffer AVAudioEngine queue carry the selected "
            "source event. Original-rate audition and full-project barriers remain explicit."
        ],
        "limits": [
            "One admitted zero-origin source event; MIDI, plugins, routing, automation, mixer/PDC, "
            "general CPR event playback and CPR writing remain incomplete.",
            "Mode0 is an explicit reconstruction option. Neither inspected enabled native "
            "event-stream consumer selects it: those choose availability-selected mode2/1, "
            "with successful Float32 mode2 configured as SoXR recipe6/flags0 (VHQ).",
            "Native pointer ordering affects the slow downsample branch. ABOVE arena placement "
            "and singleton-avoidance partitions are application policies; native host allocation "
            "order and arbitrary block equivalence are not established.",
            "The ring-to-AVAudioEngine adapter, source-resident PCM, main-actor refill and preroll "
            "seek are application policies, not a recovered native engine callback graph.",
            "Bundled SoXR version identity is static. Public-source build equivalence, actual "
            "library availability, mode2 sample wrapping and live callback invocation remain open.",
            "No DAC capture, device-rate equivalence, Cubase runtime comparison or full fidelity "
            "claim follows from static instructions, analytical controls or application GUI checks."
        ],
        "retained_corrections": [
            "Generated Swift umbrella-module caches omitted the added C header; only the "
            "generated PCM caches were removed before successful test and release builds.",
            "Earlier oracle/test failures and prototypes remain retained; accepted oracle controls "
            "preserve the address-sensitive branch and distinguish singleton bounds.",
            "An early research message called quality recipe6 HQ; pinned0.1.3 headers identify "
            "VHQ. Exact native argument6 and the final sealed finding use the corrected meaning."
        ],
        "next": "Build pinned public SoXR0.1.3 with complete license custody, reconstruct native "
                "mode2 buffering/carry/EOF under explicit successful-call bounds, and trace the "
                "remaining live engine callback edge before expanding playback claims.",
    })
    print(json.dumps({"validation": validation, "groups": len(groups), "package_files": package_files}))


def seal():
    require_new(["final-status-snapshot", "artifact-manifest.json", "final-integrity.json"])
    assert (OUT / "application-validation.json").exists()
    verify_manifest(OUT / "final-source-manifest.json")
    source = OUT / "final-source-snapshot"
    for path in source.rglob("*"):
        if path.is_file():
            assert (ROOT / "Application" / path.relative_to(source)).read_bytes() == path.read_bytes()
    assert record(ROOT / "Application/dist/Rebase.app/Contents/MacOS/Rebase")["sha256"] == FINAL_BINARY
    status = OUT / "final-status-snapshot"
    status.mkdir()
    for name in ["README.md", "research/study.json", "research/coverage.json", "research/rea-steering.json"]:
        target = status / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    manifest = write("artifact-manifest.json", {
        "id": "APP011",
        "scope": "Local source/build/status snapshots, analytical controls, native UI observations, "
                 "synthetic media and retained failures. Raw/vendor/build material remains local.",
        "files": [record(p) for p in sorted(OUT.rglob("*")) if p.is_file()
                  and p.name != ".DS_Store" and "__pycache__" not in p.parts]})
    checked = verify_manifest(OUT / "artifact-manifest.json")
    write("final-integrity.json", {"manifest": manifest,
          "validation": record(OUT / "application-validation.json"),
          "sealed": True, "files_verified": checked["files_checked"]})
    print(json.dumps(manifest))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--accept", action="store_true")
    mode.add_argument("--seal", action="store_true")
    args = parser.parse_args()
    seal() if args.seal else accept()
