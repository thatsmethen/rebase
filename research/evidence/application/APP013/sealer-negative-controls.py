"""Exercise APP013 integrity guards with disposable, self-authored files."""
from pathlib import Path
import hashlib
import importlib.util
import json
import tempfile

HERE = Path(__file__).resolve().parent
source = HERE / "seal_application.py"
spec = importlib.util.spec_from_file_location("app013_custody_controls", source)
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)
controls = []


def rejects(name, action):
    try:
        action()
    except AssertionError:
        controls.append({"name": name, "rejected": True})
        return
    raise AssertionError("Guard accepted mutation: " + name)


with tempfile.TemporaryDirectory(prefix="rebase-app013-integrity-") as directory:
    root = Path(directory)
    s.ROOT = root
    s.custody.ROOT = root
    app, snapshot = root / "Application", root / "snapshot"
    for name in s.SOURCE_DIRECTORIES:
        (app / name).mkdir(parents=True)
        (snapshot / name).mkdir(parents=True)
        (app / name / "fixture.txt").write_text(name)
        (snapshot / name / "fixture.txt").write_text(name)
    for name in s.SOURCE_FILES:
        (app / name).write_text(name)
        (snapshot / name).write_text(name)
    assert s.check_source_inventory(snapshot) == 7
    controls.append({"name": "matching_complete_source_inventory", "passed": True})
    added = app / "Sources/added-after-acceptance.swift"
    added.write_text("new source")
    rejects("source_added_after_acceptance", lambda: s.check_source_inventory(snapshot))
    added.unlink()
    existing = app / "Sources/fixture.txt"
    existing.write_text("changed")
    rejects("existing_source_changed", lambda: s.check_source_inventory(snapshot))
    existing.write_text("Sources")
    retained = s.record(existing)
    existing.write_text("changed again")
    rejects("nested_acceptance_record_changed",
            lambda: s.check_pinned_records({"nested": [{"input": retained}]}))
    existing.write_text("Sources")
    assert s.check_pinned_records({"nested": [{"input": retained}]}) == 1
    controls.append({"name": "matching_nested_acceptance_record", "passed": True})

    child = root / "child"
    outer = root / "outer"
    child.mkdir()
    outer.mkdir()
    original = child / "file.txt"
    original.write_text("accepted native evidence")
    child_manifest = child / "artifact-manifest.json"
    child_manifest.write_text(json.dumps({"files": [s.record(original)]}))
    link = outer / "native-final-integrity.json"
    link.write_text(json.dumps({"native": {"manifest": s.record(child_manifest)}}))
    outer_manifest = outer / "artifact-manifest.json"
    outer_manifest.write_text(json.dumps({"files": [s.record(link)]}))
    result = s.recursive_integrity([(outer_manifest, root, 1)])
    assert len(result["manifests"]) == 2
    controls.append({"name": "recursive_manifest_chain", "passed": True})
    original.write_text("post-acceptance native change")
    rejects("transitive_native_file_changed",
            lambda: s.recursive_integrity([(outer_manifest, root, 1)]))

    # A preserved old identity is allowed only by a pinned explicit mapping.
    preserved = child / "old-snapshot.txt"
    preserved.write_text("accepted native evidence")
    old_row = json.loads(child_manifest.read_text())["files"][0]
    substitution = {"original_manifest_entry": old_row,
                    "preserved_bytes": s.record(preserved)}
    link.write_text(json.dumps({"native": {
        "manifest": s.record(child_manifest),
        "superseded_application_files": [substitution]}}))
    outer_manifest.write_text(json.dumps({"files": [s.record(link)]}))
    result = s.recursive_integrity([(outer_manifest, root, 1)])
    child_result = next(x for x in result["manifests"]
                        if x["manifest"]["path"] == "child/artifact-manifest.json")
    assert child_result["unchanged_at_original_path"] == 0
    assert len(child_result["explicit_preserved_substitutions"]) == 1
    controls.append({"name": "explicit_identical_preserved_snapshot", "passed": True})
    preserved.write_text("wrong recovery")
    rejects("preserved_substitution_bytes_changed",
            lambda: s.recursive_integrity([(outer_manifest, root, 1)]))
    preserved.write_text("accepted native evidence")
    link.write_text("changed linking record")
    rejects("linking_integrity_record_changed",
            lambda: s.recursive_integrity([(outer_manifest, root, 1)]))

result = {
    "scope": "Synthetic integrity-instrument controls; no application/target execution.",
    "passed": True, "controls": controls,
    "script": {"path": str(source.relative_to(HERE.parents[3])),
               "sha256": hashlib.sha256(source.read_bytes()).hexdigest()},
}
with (HERE / "sealer-negative-controls.json").open("x") as stream:
    stream.write(json.dumps(result, indent=2) + "\n")
print(json.dumps({"passed": True, "controls": len(controls)}))
