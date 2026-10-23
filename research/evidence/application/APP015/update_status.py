"""Publish APP015 status only after its application acceptance exists."""
from pathlib import Path
import copy
import json

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
v = json.loads((HERE / "application-validation.json").read_text())
assert v["id"] == "APP015" and v["version"] == "0.15.0"
record = "research/evidence/application/APP015/application-validation.json"
tests = v["tests"]
gui = json.loads((ROOT / v["gui"]["path"]).read_text())
scope = (
    "Native timeline audition now reconstructs supported nonzero saved event starts, "
    "whole-frame trims and source offsets through the source clock and clip datum, "
    "then the separate native builder and reader rounding stages. Full media capacity "
    "is validated independently of the event span. Source-backed derived CPR controls "
    "cover placements before, at and after the original 600-second tempo-map knot. "
    "Absolute timeline bounds extend to 24 hours without allocating leading silence. "
    "The inspector and audition timeline expose the ephemeral source range while "
    "frozen V4 imports stay unchanged. Saved track delay must be zero; fresh resource "
    "state without later host delay mutations and a source-rate builder context are "
    "explicit reconstruction choices. Differing-rate placed events, overlaps, fades, "
    "full channels and full-project playback remain unresolved. Existing zero-origin "
    "mode0/1/2 conversion remains separately tested and available."
)

build = (
    f"0.15.0 build15 release compiled, packaged and signed successfully. "
    f"The accepted executable is {v['executable']['bytes']:,} bytes, SHA-256 "
    f"{v['executable']['sha256']}. APP015 retains {tests['passed']} passing tests "
    f"in {tests['suites']} suites, final-release GUI evidence, independent reviews, "
    "exact source/build snapshots and recursively verified prior/native evidence. "
    "Historical failures and limitations remain in their original records."
)
gui_status = (
    f"{gui['groups_passed']} final-release Rebase GUI groups passed; "
    f"{gui['package_files_unchanged']} QA package files remained unchanged. "
    "The independent review checks retained UI observations and identities; "
    "it does not replay the UI. Engine telemetry is not DAC capture or a Cubase comparison."
)
evidence = [record, v["gui"]["path"], tests["log"]["path"], v["build_log"]["path"]]
for key in ("independent_reviews", "independent_controls", "static_findings"):
    evidence += [row["path"] for row in v[key]]
evidence += [v[k]["path"] for k in (
    "source_manifest", "native_integrity", "historical_integrity",
    "recursive_integrity", "public_packaging")]

def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")

study_path = ROOT / "research/study.json"
study = json.loads(study_path.read_text())
app = study["application"]
assert app["version"] == "0.14.0"
app["validation_history"].append({key: copy.deepcopy(app[key]) for key in (
    "version", "build_executable_sha256", "implementation_test_count",
    "implementation_test_suites", "implementation_test_log",
    "implementation_test_log_sha256", "validation_record")})
app.update(version="0.15.0", implementation_test_count=tests["passed"],
    implementation_test_suites=tests["suites"], implementation_test_log=tests["log"]["path"],
    implementation_test_log_sha256=tests["log"]["sha256"],
    previous_validation_record=app["validation_record"], validation_record=record,
    implementation_checks="research/evidence/application/APP015",
    build_executable_sha256=v["executable"]["sha256"],
    build_status=build, gui_validation_status=gui_status)
app["implemented"].append(scope)
app["implementation_evidence"] += [p for p in evidence if p not in app["implementation_evidence"]]
app["native_placed_source_evidence_pins"] = v["static_findings"]
write(study_path, study)

coverage_path = ROOT / "research/coverage.json"
coverage = json.loads(coverage_path.read_text())
for domain in coverage["domains"]:
    if domain.get("id") == "project-media":
        domain["application_implementation"] = domain["application_implementation"].replace(
            "mode 1 and other unimplemented rate-conversion modes",
            "unimplemented rate-conversion branches and automatic backend selection")
old = coverage["application_iteration"]
assert old["id"] == "APP014"
coverage["previous_application_iterations"].append(copy.deepcopy(old))
coverage["application_iteration"] = dict(id="APP015", version="0.15.0",
    validation_record=record, gui_validation_status=gui_status,
    release_verification_status=build, swift_test_methods_passed=tests["passed"],
    test_suites=tests["suites"], test_log=tests["log"]["path"],
    test_log_sha256=tests["log"]["sha256"], implementation_evidence=evidence,
    scope=scope, build_executable_sha256=v["executable"]["sha256"])
write(coverage_path, coverage)

steering_path = ROOT / "research/rea-steering.json"
steering = json.loads(steering_path.read_text())
old = steering["iteration_status"]
assert old["iteration"] == "APP014"
steering["previous_iteration_status"].append(copy.deepcopy(old))
current = copy.deepcopy(old)
current.update(as_of=v["created_utc"], version="0.15.0", iteration="APP015",
    application="Rebase 0.15.0 native placed-source playback milestone",
    application_tests=dict(passed=tests["passed"], suites=tests["suites"],
        evidence=tests["log"]["path"], sha256=tests["log"]["sha256"],
        **{"class": "application implementation checks"}),
    implemented_scope=old["implemented_scope"] + [scope],
    evidence=evidence, validation_record=record,
    gui_validation_status=gui_status, release_verification_status=build,
    build_executable_sha256=v["executable"]["sha256"])
steering["iteration_status"] = current
steering["next_priorities"][0]["starting_evidence"] += [
    p for p in [record] + [r["path"] for r in v["static_findings"]]
    if p not in steering["next_priorities"][0]["starting_evidence"]]
steering["next_priorities"][0].update(
    id="native-placed-source-rate-accessor",
    question="How does the ordinary source accessor convert and seek placed, trimmed events at a differing output rate, and how are multiple event ranges and loop partitions selected?",
    action="Trace ordinary accessor construction flags0x25/policy1, gain/seek/read slots and rate/reset lifecycle from101d3eb24. Bind source offsets, filter history, preroll, output lengths and mapped partitions before composing the existing native mode0/1/2 kernels into nonzero source playback. Then recover complete channel inventories, overlap/priority/fades and loop mapping.",
    implementation_gate="APP015 source-derived nonzero placement uses an explicit source-rate builder and fresh resource state. Differing-rate placement needs native accessor state/seek proof and independent samples/counts across trim boundaries, EOF and rate changes. Keep ordinary project playback gated until every audible contributor and processing/routing state is supported or positively absent.")
write(steering_path, steering)

readme_path = ROOT / "README.md"
readme = readme_path.read_text()
start = readme.index("The current application checkpoint is ")
end = readme.index("\n\n", start)
paragraph = (
    f"The current application checkpoint is 0.15.0. Native source-rate audition now\n"
    f"plays supported saved nonzero starts, trimmed durations and media offsets,\n"
    f"using recovered clock, segment-builder and reader arithmetic. It passes\n"
    f"{tests['passed']} tests in {tests['suites']} suites and {gui['groups_passed']} bounded Rebase GUI groups.\n"
    f"Original-rate and mode0/1/2 converted audition remain available under their\n"
    f"existing contracts. Differing-rate placed events, complete channel/project\n"
    f"playback and Cubase runtime equivalence remain unresolved."
)

readme = readme[:start] + paragraph + readme[end:]
addition = (
    "Rebase 0.15 extends **Native timeline reader · original rate** to supported\n"
    "nonzero source events. Saved Start is interpreted through the containing track's\n"
    "preserved native clock; Length and Offset use the clip's type10 sample datum.\n"
    "The native builder snaps each coordinate separately before the reader applies\n"
    "its own distinct quantizer. Whole-frame trims and offsets are checked against\n"
    "the complete attached stereo PCM24 source. Leading silence is streamed, allowing\n"
    "absolute positions up to 24 hours without allocating a whole silent arrangement.\n\n"
    "The inspector exposes source start, duration and media offset. During audition,\n"
    "the timeline shows this ephemeral range; the frozen V4 import remains unchanged.\n"
    "The operation replays the original source clock even after the user explicitly\n"
    "edits application timing. It requires zero saved track delay and reconstructs\n"
    "fresh resource state without later host callback mutations. Its source-rate\n"
    "builder context is explicit, not inferred as the hosted default. Nonzero events\n"
    "at differing output rates remain gated pending native accessor seek/filter-state\n"
    "recovery; zero-origin mode0/1/2 conversion keeps its existing contracts.\n\n"
    "APP015 passes 258 tests in 40 suites, including 180 independent exact builder\n"
    "controls and seven source-derived placement/trim/offset cases around the original\n"
    "600-second tempo change. Eight final-release GUI groups cover placement, prefix\n"
    "silence, live output, seek/pause/end, source tampering, project barriers and all\n"
    "three converted audition modes. These use synthetic PCM and own-engine telemetry.\n"
    "The acceptance record is `research/evidence/application/APP015/application-validation.json`;\n"
    "full Cubase runtime equivalence remains unestablished.\n\n"
)
assert "Rebase 0.15 extends" not in readme
readme = readme.replace("Each imported project retains", addition + "Each imported project retains", 1)
readme_path.write_text(readme)
print(json.dumps({"updated": 4, "acceptance": record}))
