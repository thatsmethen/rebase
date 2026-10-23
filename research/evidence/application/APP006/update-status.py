"""Advance current research status after APP006 checks; retain prior records."""
from pathlib import Path
import copy
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
def load(path): return json.loads(path.read_text())
def save(path, value): path.write_text(json.dumps(value, indent=2) + "\n")
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
validation = load(OUT / "application-validation.json")
prefix = "research/evidence/application/APP006/"
native = "research/evidence/cubase-static/cpr-audio-events-001/"
proof = [prefix + name for name in ["application-validation.json", "artifact-manifest.json",
    "v4-integration-review.json", "gui-observations.json", "gui-packages-independent-check.json", "historical-integrity.json"]]
proof += [native + area + "/finding.json" for area in ["timebase", "cluster", "audible-state"]]
cpr = ("Bounded CPR profile-v4 retains shared native fixed/jump clocks and concordant origin meter, and adds source-backed unresolved audio events with exact object/media/segment identities. "
       "LoFi has saved placement0/24s/0 under the direct zero-origin type10 contract; Classic remains unplaced. Completed-object caches preserve shared clips/files. "
       "Retained events must match preserved source replay on their original imported tracks. Playback/mixdown/exchange refuse unresolved events. Frozen V1/V2/V3 semantics remain unchanged. "
       "Actual media resolution, general placement, effective runtime rate/provider state and rendered parity remain unverified.")
scope = "124 implementation tests in18 suites, ten bounded Rebase native GUI groups, three independently checked GUI packages and historical byte custody. No Cubase execution or measured reference conformance."
gui = "Ten bounded Rebase GUI groups passed; three saved packages independently inspected, with exact source proof and Save As identity verified."
build = "0.6.0 build6 release built; strict local codesign passed; final source and application bundle snapshots retained."
paths = [ROOT / "research" / name for name in ["study.json", "coverage.json", "rea-steering.json"]]
history = ROOT / "research/status-history/pre-APP006"
history.mkdir(parents=True, exist_ok=True)
for path in paths:
    if not (history / path.name).exists(): shutil.copy2(path, history / path.name)

study = load(paths[0]); app = study["application"]
if app["version"] != "0.6.0":
    app["validation_history"].append({key: app[key] for key in ["version", "build_executable_sha256", "implementation_test_count",
        "implementation_test_suites", "implementation_test_log", "implementation_test_log_sha256", "validation_record"]})
app.update(version="0.6.0", build_executable_sha256=validation["executable"]["sha256"], implementation_test_count=124,
    implementation_test_suites=18, implementation_test_log=prefix+"core-tests-final.log",
    implementation_test_log_sha256=sha(OUT/"core-tests-final.log"), previous_validation_record="research/evidence/application/APP005/application-validation.json",
    validation_record=prefix+"application-validation.json", cpr_status=cpr, evidence_boundary=scope,
    build_status=build, gui_validation_status=gui)
for value in proof:
    if value not in app["implementation_evidence"]: app["implementation_evidence"].append(value)
entry = "Source-backed unresolved CPR audio events, bounded saved LoFi placement, explicit unplaced Classic event, shared object caches, source-replay provenance, Undo/Redo and playback/export barriers."
if entry not in app["implemented"]: app["implemented"].append(entry)
for area in ["timebase", "cluster", "audible-state"]:
    study["static_evidence"]["cpr_audio_events_"+area.replace("-", "_")] = native+area+"/finding.json"
save(paths[0], study)

coverage = load(paths[1])
if coverage["application_iteration"]["id"] != "APP006":
    coverage["previous_application_iterations"].append(copy.deepcopy(coverage["application_iteration"]))
coverage["application_iteration"] = {"id":"APP006", "version":"0.6.0", "validation_record":prefix+"application-validation.json",
    "gui_validation_status":gui, "release_verification_status":build, "swift_test_methods_passed":124, "test_suites":18,
    "test_log":prefix+"core-tests-final.log", "test_log_sha256":sha(OUT/"core-tests-final.log"),
    "implementation_evidence":proof, "scope":scope, "build_executable_sha256":validation["executable"]["sha256"]}
for domain in coverage["domains"]:
    if domain["id"] == "project-media":
        domain["application_implementation"] = "Independent project/media bundle. " + cpr
        domain["static_mapping"] += " MAudioEvent Start/Length/Offset ownership, zero-origin type10 projection, concrete cluster list/segment field binding and bounded event state now have verified original-byte traces; actual playback remains a separate gate."
        domain["static_evidence"] += [native+area+"/finding.json" for area in ["timebase", "cluster", "audible-state"]]
    if domain["id"] == "import-export":
        prior = domain["application_implementation"].split("Bounded CPR profile-v2")[0]
        domain["application_implementation"] = prior+cpr
    if domain["id"] == "audio-editing":
        domain["application_implementation"] += " Unresolved source audio events can be inspected/removed with Undo/Redo; their unverified editing/playback semantics are not converted to ordinary clips."
save(paths[1], coverage)

steering = load(paths[2])
if steering["iteration_status"]["iteration"] != "APP006":
    steering["previous_iteration_status"].append(copy.deepcopy(steering["iteration_status"]))
current = steering["iteration_status"]
current.update(version="0.6.0", iteration="APP006", validation_record=prefix+"application-validation.json",
    build_executable_sha256=validation["executable"]["sha256"], gui_validation_status=gui, release_verification_status=build)
current["application_tests"].update(passed=124, suites=18, evidence=prefix+"core-tests-final.log", sha256=sha(OUT/"core-tests-final.log"))
current["implemented_scope"] = [cpr if "CPR profile-v3" in x else x for x in current["implemented_scope"]]
current["implementation_limits"] = [cpr if x.startswith("CPR imports restore empty audio tracks") else x for x in current["implementation_limits"]]
current["evidence"] += proof
priority = steering["next_priorities"][0]
priority.update(id="audio-segment-rendering-and-media-resolution",
    question="How do stored segments and actual backend formats bind event audio to seek/read/processing behavior?",
    starting_evidence=[prefix+"application-validation.json"]+[native+area+"/finding.json" for area in ["timebase", "cluster", "audible-state"]],
    action="Trace concrete AudioClusterAccessStream segment seek/read and actual rendering selection under a bounded default restored-state contract. Implement verified interval calculations and controlled media resolution; retain rate/backend/host-mutation limits explicitly. Extend beyond zero-origin/type10 placement only with separate proof. No target execution.",
    implementation_gate="A complete original-byte consumer path, exact source/actual-media format bounds, negative controls and application integration; unresolved events must never become silently playable because a filename matches.",
    historical_compatibility="Freeze V1/V2/V3/V4 reports and source-coordinate/clock contracts. New recovery semantics require a new profile.",
    active_division={"segment_read_mapping":"target_intake", "rendering_selection":"cubase_evidence", "integration_and_validation":"root"})
save(paths[2], steering)
print(json.dumps({"updated": [str(p.relative_to(ROOT)) for p in paths], "previous_status":str(history.relative_to(ROOT))}))
