#!/usr/bin/env python3
"""Accept APP009, then seal after the status documents reference acceptance.

Run without arguments for acceptance; run with --seal once status is finalized.
All output writes are exclusive. No proprietary code is executed.
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


def record(path):
    data = path.read_bytes()
    return {"path": str(path.relative_to(ROOT)), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def write(name, value):
    path = OUT / name
    with path.open("x") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")
    return record(path)


def verify_manifest(path):
    rows = json.loads(path.read_text())["files"]
    for row in rows:
        actual = record(ROOT / row["path"])
        assert actual["bytes"] == row["bytes"] and actual["sha256"] == row["sha256"], row["path"]
    return {"manifest": record(path), "files_checked": len(rows), "unchanged": True}


def accept():
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    test = OUT / "core-tests-release.log"
    assert "Test run with 171 tests in 25 suites passed" in test.read_text()
    assert "Build complete!" in (OUT / "build-release.log").read_text()
    app = ROOT / "Application/dist/Rebase.app"
    info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    assert info["CFBundleShortVersionString"] == "0.9.0" and info["CFBundleVersion"] == "9"
    binary = record(app / "Contents/MacOS/Rebase")
    assert binary["sha256"] == json.loads((OUT / "gui-release-build.json").read_text())["sha256"]

    before = json.loads((OUT / "gui-package-before.json").read_text())
    package = ROOT / before["copy"]
    assert {str(p.relative_to(package)) for p in package.rglob("*") if p.is_file()} == {r["path"] for r in before["files"]}
    for row in before["files"]:
        actual = record(package / row["path"])
        assert actual["sha256"] == row["sha256"] and actual["bytes"] == row["bytes"]
    historical = write("historical-final-integrity.json", verify_manifest(ROOT / "research/evidence/application/APP008/artifact-manifest.json"))
    native_path = ROOT / "research/evidence/cubase-static/cpr-audio-events-001/timeline-playback"
    native_integrity = write("native-final-integrity.json", verify_manifest(native_path / "artifact-manifest.json"))

    groups = [
        ("open_inspect", "Native Open loads the copied source-backed project; inspector offers the separately gated timeline action.", ["open", "inspection"]),
        ("play_pause_seek_end", "Source event plays at44100Hz with nonzero mixer tap peaks; pause retains position and silences meters; seek to16seconds and resume reach natural24-second completion.", ["playing", "paused", "paused-seek", "resumed", "natural-end"]),
        ("restart_stop_bounds", "Explicit Play at end restarts; Return to Start replaces an active schedule; Stop resets position; seeking beyond the source clamps to24seconds with no playback.", ["restart-at-end", "return-to-start", "stop", "seek-past-end"]),
        ("changed_media", "A same-size single-byte PCM change rejects resume and clears audition; original bytes restored exactly and a fresh inspection admits playback again.", ["changed-media-rejected", "rejected-mode-cleared", "restored-media-playing"]),
        ("project_barriers", "Ordinary project playback and full mixdown still reject unresolved CPR content.", ["project-play-refused", "project-export-refused"]),
        ("edit_undo", "Mute edit stops and exits audition; Undo restores the track control without reactivating source audio.", ["edit-exits-audition", "undo-stays-project-mode"]),
        ("explicit_exit", "Exit Audition stops source playback, removes the persistent mode and restores project transport.", ["exit-audition"])
    ]
    gui = write("gui-observations.json", {
        "id": "APP009-GUI", "created_utc": now, "groups_passed": len(groups), "executable": binary,
        "groups": [{"id": key, "result": "passed", "observation": explanation,
                    "records": [record(OUT / ("release-gui-" + name + ".ax.txt")) for name in names]}
                   for key, explanation, names in groups],
        "screenshot": record(OUT / "release-gui-playing.png"),
        "scope": "Final binary observed through native GUI with self-authored synthetic PCM. Meter values are engine tap observations, not DAC captures or Cubase runtime comparisons.",
        "package_files_unchanged": len(before["files"]),
        "earlier_runs": "Unprefixed gui-* and final-gui-* records retain prior observations. The release binary repeats all seven groups after two shared error strings and the edit-exit status label were corrected."})

    source = OUT / "final-source-snapshot"
    source.mkdir()
    for directory in ["Sources", "Tests"]:
        shutil.copytree(ROOT / "Application" / directory, source / directory)
    for name in ["Package.swift", "Package.resolved", "build-app.sh", "test-app.sh"]:
        shutil.copy2(ROOT / "Application" / name, source / name)
    source_manifest = write("final-source-manifest.json", {"files": [record(p) for p in sorted(source.rglob("*")) if p.is_file()]})
    bundle = OUT / "final-build-snapshot/Rebase.app"
    shutil.copytree(app, bundle)
    validation = write("application-validation.json", {
        "id": "APP009", "created_utc": now, "version": "0.9.0", "build": 9,
        "status": "bounded_native_source_event_timeline_audition_implemented_and_checked",
        "full_fidelity_objective": "incomplete", "cubase_runtime_comparisons": 0, "target_executions": 0,
        "executable": record(bundle / "Contents/MacOS/Rebase"), "source_manifest": source_manifest,
        "tests": {"passed": 171, "suites": 25, "log": record(test),
                  "scope": "Application and analytical controls, including every source sample at nine seek suffixes, independent integer IEEE encoding, actual native-selection end controls and257offline AVAudioEngine tail frames."},
        "build_log": record(OUT / "build-release.log"), "gui": gui,
        "independent_review": record(OUT / "source-playback-independent-review.json"),
        "independent_gui_check": record(OUT / "gui-release-independent-check.json"),
        "static_finding": record(native_path / "finding.json"), "native_integrity": native_integrity,
        "historical_integrity": historical,
        "implemented": [
            "REA-derived unit-agnostic segment selector: linked traversal, one binary64 end addition, inclusive endpoint, u32 generation, cached successor and caller-owned cursor.",
            "Fresh source/media verification shared by WAV export and stereo event-only timeline audition; source Float32 PCM and rate retained without the project resampler, pan or automation.",
            "Play/pause, seek, return-to-start, stop and end behavior in a persistent explicit source-event scope; context changes and failed revalidation exit the mode.",
            "Host completion waits for project duration and every dataPlayedBack callback, rejects stale callbacks by generation and avoids stopping on the audio callback thread.",
            "Normal project playback, mixdown and DAWproject remain guarded; original CPR, report and retained event are unchanged."
        ],
        "limits": [
            "One direct zero-origin complete stereo PCM24 source segment with the existing no-warp/no-fades/no-inversion gates and fresh source/no external pitch assumptions.",
            "The selector is not a proven native live PCM consumer or seek quantizer. The singleton0/24-second descriptor comes from the separate saved-source projection; host frame rounding, half-open buffers and AVAudioEngine transport are application policy.",
            "Device resampling, presentation latency and physical output samples have not been compared with Cubase. Observed meters and callbacks do not establish DAC bit equivalence.",
            "Full project MIDI, instruments, inserts, sends/routing, mixer/PDC, automation, broader event semantics and CPR writing/roundtrip remain incomplete.",
            "Matching attached-media metadata does not establish original-recording identity. Frozen import profiles V1/V2/V3/V4 are unchanged."
        ],
        "retained_corrections": [
            "Initial compilation could not see the new C symbol due to a stale Swift module cache. Only RebaseTimingDSP cached PCM modules were removed; the subsequent suite passed.",
            "Native peer review found that fresh selector traversal follows linked nodes, not array order; corrected and discriminated with a linked-order test and independent optimized C controls before acceptance.",
            "Review identified wall-clock completion truncation risk; playback now also waits for dataPlayedBack callbacks and UI no longer stops at nominal duration alone.",
            "GUI changed-media rejection exposed shared render-only wording; both strings generalized and final tests/build/seven GUI groups repeated.",
            "Independent GUI review found a stale audition-paused footer after an edit returned to project mode. Invalidation now updates the status; release tests/build and all seven GUI groups repeated."
        ],
        "next": "Trace the native live segment consumer and its coordinate/seek conversion; reconstruct rate conversion and additional event processing before admitting full native project playback."
    })
    print(json.dumps({"validation": validation, "gui": gui, "source_files": len(json.loads((OUT / "final-source-manifest.json").read_text())["files"])}))


def seal():
    assert (OUT / "application-validation.json").exists()
    status = OUT / "final-status-snapshot"
    status.mkdir()
    for name in ["README.md", "research/study.json", "research/coverage.json", "research/rea-steering.json"]:
        target = status / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    manifest = write("artifact-manifest.json", {"id": "APP009",
        "scope": "Local source/build/status snapshots, application observations, self-authored media and retained failures. Vendor fixtures and raw captures stay local.",
        "files": [record(p) for p in sorted(OUT.rglob("*")) if p.is_file() and p.name != ".DS_Store" and "__pycache__" not in p.parts]})
    write("final-integrity.json", {"manifest": manifest, "validation": record(OUT / "application-validation.json"), "sealed": True})
    print(json.dumps(manifest))


if __name__ == "__main__":
    seal() if "--seal" in sys.argv else accept()
