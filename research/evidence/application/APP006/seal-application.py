"""Seal the checked Rebase build; never executes the Cubase reference."""
from pathlib import Path
import datetime
import hashlib
import json
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
NOW = datetime.datetime.now(datetime.timezone.utc).isoformat()

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def record(path):
    return {"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": digest(path)}

def write(name, data):
    (OUT / name).write_text(json.dumps(data, indent=2) + "\n")

tests = OUT / "core-tests-final.log"
assert "Test run with 124 tests in 18 suites passed" in tests.read_text()
for name in ["v4-integration-review.json", "historical-integrity.json", "gui-packages-independent-check.json"]:
    assert (OUT / name).is_file()

app = ROOT / "Application/dist/Rebase.app"
binary = app / "Contents/MacOS/Rebase"
assert digest(binary) == "1dae0a89d53ec02bedc34a240b10f8e5c99255154611ac7bc2f70c31709928da"
subprocess.run(["codesign", "--verify", "--strict", str(app)], check=True)

source_files = sorted([p for folder in ["Application/Sources", "Application/Tests"]
                       for p in (ROOT / folder).rglob("*") if p.is_file()]
                      + [ROOT / "Application" / name for name in
                         ["Package.swift", "Package.resolved", "build-app.sh", "test-app.sh"]])
for p in source_files:
    dest = OUT / "final-source-snapshot" / p.relative_to(ROOT)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(p, dest)
write("final-source-manifest.json", {"created_utc": NOW, "scope": "Checked application source and tests; no proprietary target code.",
    "files": [record(p) for p in source_files]})
shutil.copytree(app, OUT / "final-build-snapshot/Rebase.app", dirs_exist_ok=True)
write("build-identity.json", {"version": "0.6.0", "build": "6", "created_utc": NOW,
    "executable": record(binary), "info_plist": record(app / "Contents/Info.plist"),
    "build_log": record(OUT / "build-final.log"), "strict_codesign_exit": 0,
    "source_manifest": record(OUT / "final-source-manifest.json"), "test_log": record(tests),
    "source_change_after_build": "Test-only historical signature assertions updated; production sources unchanged after final build."})

groups = [
    ("lofi-import-and-report", ["gui-lofi-imported.ax.txt", "gui-lofi-review.ax.txt"], "One unresolved event; exact saved start0/duration24s, declared stereo44100Hz1058400frames; native80/120BPM map retained."),
    ("playback-refusal", ["gui-playback-refused.ax.txt"], "Explicit unresolved-event error before transport starts."),
    ("mixdown-refusal", ["gui-mixdown-refused.ax.txt"], "Explicit unresolved-event error before destination selection."),
    ("dawproject-refusal", ["gui-dawproject-refused.ax.txt"], "Unplaced Classic event cannot disappear through export."),
    ("remove-undo-redo", ["gui-event-removed.ax.txt", "gui-event-undo.ax.txt", "gui-event-redo.ax.txt"], "Removal clears source event; Undo restores exact24s event and inspector; Redo removes it. Final Undo restored it before save."),
    ("lofi-save-reopen", ["gui-lofi-reopened.ax.txt", "gui-lofi-reopened.png"], "Saved event and source coordinates survive reopening."),
    ("save-as", ["gui-lofi-save-as.ax.txt"], "Independent copy retains event and source proof; separate byte audit confirms only project name differs."),
    ("classic-unplaced", ["gui-classic-review.ax.txt", "gui-classic-imported.ax.txt", "gui-classic-imported.png"], "Musical datum remains unplaced in a separate status area; no invented seconds or playable clip."),
    ("classic-reopen", ["gui-classic-reopened.ax.txt"], "Unplaced source event survives package reopening."),
    ("historical-v3-open", ["gui-v3-historical-open.ax.txt"], "Frozen APP005 package reopens with80BPM and its original empty track; it is not silently upgraded to V4."),
]
write("gui-observations.json", {"created_utc": NOW, "application_executable_sha256": digest(binary),
    "target_executed": False, "method": "Native Rebase accessibility and visual inspection through cua_repl.",
    "groups": [{"id": key, "status": "passed", "observation": observation,
                "evidence": [record(OUT / name) for name in names]} for key, names, observation in groups],
    "final_open_state": record(OUT / "gui-final-open.ax.txt"),
    "boundary": "These are Rebase workflow observations, not running Cubase measurements or audio equivalence tests."})

findings = [ROOT / "research/evidence/cubase-static/cpr-audio-events-001" / area / "finding.json"
            for area in ["timebase", "cluster", "audible-state"]]
write("application-validation.json", {"id": "APP006", "created_utc": NOW, "version": "0.6.0", "build": 6,
    "status": "bounded_source_event_slice_implemented_and_checked", "autonomous_goal_status": "active",
    "interpretation_profile": "cpr-static-subset-v4", "serialization_schema": 2,
    "executable": record(binary), "test_methods_passed": 124, "test_suites": 18,
    "test_log": record(tests), "gui_groups_passed": 10, "gui_record": record(OUT / "gui-observations.json"),
    "independent_review": record(OUT / "v4-integration-review.json"),
    "package_audit": record(OUT / "gui-packages-independent-check.json"),
    "historical_audit": record(OUT / "historical-integrity.json"), "static_findings": [record(p) for p in findings],
    "implemented": ["Versioned source-event import with exact archive object identities and completed-object caches.",
        "LoFi saved source placement0/24s/0 under direct zero-origin type10 contract; Classic retained unplaced.",
        "Source media/segment fields, unresolved timeline and inspector, removal/Undo/Redo, save/reopen/Save As.",
        "Source-replay proof for retained events on original imported tracks; tampering rejected before save or on load.",
        "Unresolved-event playback/render/exchange barriers; frozen V1/V2/V3 semantics preserved."],
    "retained_corrections": [
        {"record": "v4-tests-initial.log", "cause": "Direct Swift test invocation lacked Testing module setup; repository test-app.sh succeeds. No target execution."},
        {"record": "core-tests-round1.log", "cause": "Six assertions in historical signature controls assumed current project/facts/objects equal V2. Corrected to assert frozen V2/V3 equality and exact old subset plus V4 unresolved event."},
        {"record": "initial-build-identity.json", "cause": "Initial import report retained obsolete V1 time-unit wording; V4 report text corrected before final build and fresh GUI packages. Initial package is retained as development evidence, not a final-profile compatibility fixture."}],
    "limits": ["Cubase/proprietary runtime executions and measured reference comparisons remain0.",
        "Source projections do not establish hosted runtime rate/provider state or rendered sound parity.",
        "No automatic relink-to-playback promotion, general nonzero coordinates, nested event placement, or musical audio duration conversion.",
        "CPR writing/roundtrip, MIDI editing, recording, plugin hosting, PDC, complete mixer/routing, time stretching and full interface fidelity remain open."],
    "next": "Integrate independently verified segment/read intervals and bounded default-state rendering semantics under a new frozen profile; then actual-media resolution and explicit supported playable promotion. Full-fidelity goal stays active."})
print(json.dumps({"source_files": len(source_files), "tests": 124, "gui_groups": 10,
                  "executable_sha256": digest(binary), "validation_sha256": digest(OUT / "application-validation.json")}))
