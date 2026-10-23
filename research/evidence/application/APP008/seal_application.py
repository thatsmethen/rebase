#!/usr/bin/env python3
"""Seal the bounded APP008 implementation checks; never execute Cubase."""
from pathlib import Path
import datetime
import hashlib
import json
import plistlib
import shutil

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent


def record(path):
    path = Path(path)
    data = path.read_bytes()
    return {"path": str(path.relative_to(ROOT)), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def write(name, value):
    path = OUT / name
    assert not path.exists(), f"Refusing to replace sealed output: {path}"
    path.write_text(json.dumps(value, indent=2) + "\n")
    return record(path)


def main():
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    test = OUT / "core-tests-source-render-final.log"
    assert "Test run with 158 tests in 23 suites passed" in test.read_text()
    assert "Build complete!" in (OUT / "build-final.log").read_text()
    bundle = ROOT / "Application/dist/Rebase.app"
    info = plistlib.loads((bundle / "Contents/Info.plist").read_bytes())
    assert info["CFBundleShortVersionString"] == "0.8.0" and info["CFBundleVersion"] == "8"
    review = json.loads((OUT / "gui-source-render-independent-check.json").read_text())
    assert review["status"] == "passed"
    final_output = json.loads((OUT / "gui-release-output-check.json").read_text())
    assert final_output["bitwise_equal_to_independently_checked_export"]
    assert record(ROOT / final_output["final_output"])["sha256"] == review["output"]["sha256"]

    before = json.loads((OUT / "gui-package-before.json").read_text())
    package = ROOT / before["copy"]
    assert {str(p.relative_to(package)) for p in package.rglob("*") if p.is_file()} == {
        entry["path"] for entry in before["files"]}
    for entry in before["files"]:
        assert record(package / entry["path"])["sha256"] == entry["sha256"]

    historical = ROOT / "research/evidence/application/APP007/artifact-manifest.json"
    old = json.loads(historical.read_text())
    for entry in old["files"]:
        actual = record(ROOT / entry["path"])
        assert actual["bytes"] == entry["bytes"] and actual["sha256"] == entry["sha256"]
    historical_check = write("historical-final-integrity.json", {
        "manifest": record(historical), "files_checked": len(old["files"]), "unchanged": True})

    source = OUT / "final-source-snapshot"
    assert not source.exists()
    source.mkdir()
    application = ROOT / "Application"
    for name in ["Sources", "Tests"]:
        shutil.copytree(application / name, source / name)
    for name in ["Package.swift", "Package.resolved", "build-app.sh", "test-app.sh"]:
        shutil.copy2(application / name, source / name)
    source_manifest = write("final-source-manifest.json", {
        "scope": "Exact application source, tests and build inputs at APP008 sealing",
        "files": [record(p) for p in sorted(source.rglob("*")) if p.is_file()]})
    build = OUT / "final-build-snapshot/Rebase.app"
    assert not build.exists()
    shutil.copytree(bundle, build)
    executable = record(build / "Contents/MacOS/Rebase")

    gui_groups = [
        {"id": "open", "result": "passed",
         "observation": "Final build opened the copied APP007 project through Cmd-O/Go To/Open, preserving 80 BPM, one unresolved event and its attached PCM; repeated Open/Cancel returned to the project.",
         "records": ["gui-release-open-success.ax.txt", "gui-release-open-cancel.ax.txt"]},
        {"id": "inspection", "result": "passed",
         "observation": "Source inspector showed gain1, inversionoff, no explicit fades/Warpscale, project automatic-fade flags0 and saved duration0.01s. Layout inspected in native screenshot.",
         "records": ["gui-final-source-inspection.ax.txt", "gui-source-inspection.png"]},
        {"id": "render", "result": "passed",
         "observation": "Separate WAV exported through the native panel. Final build repeated the export under a new filename after opening through the corrected Open workflow. Both entire outputs are identical; independent integer IEEE encoding matched all2116800samples. All5packagefiles remain unchanged.",
         "records": ["gui-final-render-success.ax.txt", "gui-release-render-success.ax.txt", "gui-source-render-independent-check.json", "gui-release-output-check.json"]},
        {"id": "cancel_reopen", "result": "passed",
         "observation": "After successful export, Cancel returned to arrangement; reopening the inspector/export kept Save enabled. This was observed after the async render-panel correction, before the final Open-only change.",
         "records": ["gui-final-render-cancel.ax.txt", "gui-final-render-reopened.ax.txt"]},
        {"id": "playback_barrier", "result": "passed",
         "observation": "Play displayed unresolved-Cubase-event refusal after source export. Rendering did not create a playable Clip. Observed before final Open-only change; core gate unchanged.",
         "records": ["gui-final-play-refused.ax.txt"]}
    ]
    for group in gui_groups:
        group["records"] = [record(OUT / name) for name in group["records"]]
    gui = write("gui-observations.json", {
        "id": "APP008-GUI", "created_utc": now, "groups_passed": len(gui_groups),
        "groups": gui_groups,
        "scope": "Selected native application workflows; self-authored attached PCM, no Cubase reference execution.",
        "correction_history": [
            "Initial nested modal save-panel cancellation/reopen left Save disabled. Changed to dismiss the inspector then asynchronously begin the native panel.",
            "Bound queued render to Project value snapshot and package root; check context before panel and again on acceptance.",
            "The existing synchronous Open panel also became disabled under CUA. Replaced runModal with asynchronous begin; final GUI open/cancel/export succeeded.",
            "During diagnosis the app was also initialized with its existing --project argument. Final build Open verification used the real dialog; that workaround is not the final acceptance path."
        ]})

    evidence_root = ROOT / "research/evidence/cubase-static/cpr-audio-events-001"
    findings = [record(evidence_root / name) for name in [
        "rate-converter/finding.json", "autofade-source/finding.json",
        "event-rendering/ownership-finding.json", "event-rendering/finalization-finding.json",
        "event-rendering-review/pcm24-float32/finding.json"]]
    validation = write("application-validation.json", {
        "id": "APP008", "created_utc": now, "version": "0.8.0", "build": 8,
        "status": "bounded_source_event_rendering_implemented_and_checked",
        "full_fidelity_objective": "incomplete", "cubase_runtime_comparisons": 0,
        "interpretation_profiles": "Frozen CPR V1/V2/V3/V4 unchanged; source inspection is a separate verified read",
        "executable": executable, "source_manifest": source_manifest,
        "tests": {"passed": 158, "suites": 23, "log": record(test),
                  "scope": "Application/analytical controls. Core and test source unchanged after this run; final UI-only changes built and checked through native GUI."},
        "build_log": record(OUT / "build-final.log"), "gui": gui,
        "independent_pcm_and_package_check": record(OUT / "gui-source-render-independent-check.json"),
        "final_output_repeat_check": record(OUT / "gui-release-output-check.json"),
        "reviews": [record(OUT / name) for name in ["rate-budget-independent-review.json",
            "source-render-independent-review.json", "source-render-ui-review.json",
            "source-render-ui-final-review.json", "source-render-open-review.json"]],
        "historical_integrity": historical_check, "static_findings": findings,
        "implemented": [
            "Forward typed source automatic-fade/project/track parsing with exact boundaries and counted identity checks.",
            "Verified-source inspector and original-rate source-event Float32 WAV export from one complete attached PCM24 mono/stereo segment.",
            "Exact signed24/2^23 conversion and separate Float32 gain operation; nearest-rounding and bounded normal-or-zero arithmetic domain.",
            "Original-source replay, attachment hash, bounded RIFF validation and atomic publication outside source package.",
            "Asynchronous Open/render dialogs, consume-once render request bound to unchanged project snapshot.",
            "Separately tested source-frame rate budget; no audio resampling is claimed."
        ],
        "limits": [
            "No executed Cubase reference, measured runtime fidelity, full product reconstruction or CPR writing/roundtrip.",
            "Renderer is an explicitly conditional fresh source-event reconstruction, with no external pitch context, track mixer/effects/automation or full timeline scheduling.",
            "Direct-track zero-origin complete PCM24 segment only; no inversion, explicit/enabled automatic fades, warp, unsupported child/lane state or differing-rate output.",
            "Source eligibility does not preflight actual attached-media bytes. Missing/changed/non-WAV attachments are safely rejected at render time.",
            "Native ownership study has original-byte custody checks; a further independent instruction-level peer review was not completed in this checkpoint.",
            "Unknown curve/resource/automation bodies remain opaque. Selected file metadata does not establish that the user chose the missing original recording."
        ],
        "retained_failures": [
            "Initial source/test integration compilation errors remain in logs; corrected before passing core run.",
            "A raw swift test invocation lacked Testing module paths; the repository test-app.sh wrapper subsequently passed158tests.",
            "Initial synchronous native panel failures and review findings are retained separately; final asynchronous workflows were observed working."
        ],
        "next": "Recover native timeline scheduling and additional event processing, then differing-rate samples and broader CPR compatibility, while retaining current source/output checks."
    })
    status = OUT / "final-status-snapshot"
    assert not status.exists()
    status.mkdir()
    for name in ["README.md", "research/study.json", "research/coverage.json", "research/rea-steering.json"]:
        target = status / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    manifest = write("artifact-manifest.json", {
        "id": "APP008", "created_utc": now,
        "scope": "Local source/build/status snapshots, retained failures, synthetic audio and bounded application evidence. Raw artifacts are not all distributed in the private source repository.",
        "files": [record(p) for p in sorted(OUT.rglob("*")) if p.is_file() and p.name != ".DS_Store" and "__pycache__" not in p.parts]})
    write("final-integrity.json", {"validation": validation, "manifest": manifest,
                                   "sealed": True, "target_executions": 0})
    print(json.dumps({"validation": validation, "manifest": manifest}))


if __name__ == "__main__":
    main()
