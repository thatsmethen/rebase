"""Publish APP014 status only after its application acceptance exists."""
from pathlib import Path
import copy
import json

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
v = json.loads((HERE / "application-validation.json").read_text())
assert v["id"] == "APP014" and v["version"] == "0.14.0"
record = "research/evidence/application/APP014/application-validation.json"
tests = v["tests"]
gui = json.loads((ROOT / v["gui"]["path"]).read_text())
scope = (
    "An explicit source-rate native timeline-reader audition now uses absolute "
    "frame windows, the recovered narrowed-reciprocal/FMA quantizer, segment "
    "intersection, prefix/gap silence and exact source seeks. Its direct stereo "
    "memory reads apply event gain once and run through the serial playback "
    "worker. It does not use the audition FIFO or a generic resampler. Real CPR "
    "admission retains the verified single zero-origin source-event contract. "
    "Synthetic placed/adjacent/gapped descriptors test the reader but do not "
    "establish nonzero CPR construction or full-project playback."
)
build = (
    f"0.14.0 build14 release compiled, packaged and signed successfully. "
    f"The accepted executable is {v['executable']['bytes']:,} bytes, SHA-256 "
    f"{v['executable']['sha256']}. APP014 retains {tests['passed']} passing tests "
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
assert app["version"] == "0.13.0"
app["validation_history"].append({key: copy.deepcopy(app[key]) for key in (
    "version", "build_executable_sha256", "implementation_test_count",
    "implementation_test_suites", "implementation_test_log",
    "implementation_test_log_sha256", "validation_record")})
app.update(version="0.14.0", implementation_test_count=tests["passed"],
    implementation_test_suites=tests["suites"], implementation_test_log=tests["log"]["path"],
    implementation_test_log_sha256=tests["log"]["sha256"],
    previous_validation_record=app["validation_record"], validation_record=record,
    implementation_checks="research/evidence/application/APP014",
    build_executable_sha256=v["executable"]["sha256"],
    build_status=build, gui_validation_status=gui_status)
app["implemented"].append(scope)
app["implementation_evidence"] += [p for p in evidence if p not in app["implementation_evidence"]]
app["native_timeline_reader_evidence_pins"] = v["static_findings"]
write(study_path, study)

coverage_path = ROOT / "research/coverage.json"
coverage = json.loads(coverage_path.read_text())
for domain in coverage["domains"]:
    if domain.get("id") == "project-media":
        domain["application_implementation"] = domain["application_implementation"].replace(
            "mode 1 and other unimplemented rate-conversion modes",
            "unimplemented rate-conversion branches and automatic backend selection")
old = coverage["application_iteration"]
assert old["id"] == "APP013"
coverage["previous_application_iterations"].append(copy.deepcopy(old))
coverage["application_iteration"] = dict(id="APP014", version="0.14.0",
    validation_record=record, gui_validation_status=gui_status,
    release_verification_status=build, swift_test_methods_passed=tests["passed"],
    test_suites=tests["suites"], test_log=tests["log"]["path"],
    test_log_sha256=tests["log"]["sha256"], implementation_evidence=evidence,
    scope=scope, build_executable_sha256=v["executable"]["sha256"])
write(coverage_path, coverage)

steering_path = ROOT / "research/rea-steering.json"
steering = json.loads(steering_path.read_text())
old = steering["iteration_status"]
assert old["iteration"] == "APP013"
steering["previous_iteration_status"].append(copy.deepcopy(old))
current = copy.deepcopy(old)
current.update(as_of=v["created_utc"], version="0.14.0", iteration="APP014",
    application="Rebase 0.14.0 native timeline reader milestone",
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
write(steering_path, steering)

readme_path = ROOT / "README.md"
readme = readme_path.read_text()
start = readme.index("The current application checkpoint is ")
end = readme.index("\n\n", start)
paragraph = (
    f"The current application checkpoint is 0.14.0. It adds an explicit native\n"
    f"timeline-reader audition with recovered absolute frame bounds and source\n"
    f"seeks. It passes {tests['passed']} tests in {tests['suites']} suites and "
    f"{gui['groups_passed']} bounded Rebase GUI\n"
    f"groups on the final release. Source-rate, mode0/1/2 audition and serial\n"
    f"worker refill remain available. Real CPR playback admission still requires\n"
    f"the verified zero-origin event; general placement, full-project playback\n"
    f"and Cubase runtime equivalence remain unresolved."
)
readme_path.write_text(readme[:start] + paragraph + readme[end:])
print(json.dumps({"updated": 4, "acceptance": record}))
