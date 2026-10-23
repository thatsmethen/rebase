"""Disposable controls of APP015 custody, never acceptance or historical writes."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
source = HERE / "seal_application.py"
spec = importlib.util.spec_from_file_location("app015_sealer_controls", source)
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)
controls = []


def rejects(name, action):
    try:
        action()
    except AssertionError:
        controls.append(dict(name=name, rejected=True))
        return
    raise AssertionError("Mutation was not rejected: " + name)


def passed(name):
    controls.append(dict(name=name, passed=True))


def save(path, value):
    path.write_text(json.dumps(value) + "\n")


with tempfile.TemporaryDirectory(prefix="rebase-app015-custody-") as directory:
    root = Path(directory)
    s.ROOT = root
    s.custody.ROOT = root
    app, snapshot = root / "Application", root / "snapshot"
    for name in s.SOURCE_DIRECTORIES:
        for tree in [app, snapshot]:
            (tree / name).mkdir(parents=True)
            (tree / name / "fixture.txt").write_text(name)
    for name in s.SOURCE_FILES:
        (app / name).write_text(name)
        (snapshot / name).write_text(name)
    assert s.check_source_inventory(snapshot) == 7
    passed("matching_exact_source_inventory")
    added = app / "Sources/added.swift"
    added.write_text("added")
    rejects("source_inventory_addition", lambda: s.check_source_inventory(snapshot))
    added.unlink()
    existing = app / "Sources/fixture.txt"
    existing.unlink()
    rejects("source_inventory_removal", lambda: s.check_source_inventory(snapshot))
    existing.write_text("Sources")
    existing.write_text("changed")
    rejects("source_inventory_changed_bytes", lambda: s.check_source_inventory(snapshot))
    existing.write_text("Sources")
    link, saved_link = app / "Sources/link", snapshot / "Sources/link"
    link.symlink_to("fixture.txt"); saved_link.symlink_to("fixture.txt")
    assert s.check_source_inventory(snapshot) == 8
    passed("matching_symlink_identity")
    link.unlink(); link.symlink_to("../Tests/fixture.txt")
    rejects("source_symlink_target_changed", lambda: s.check_source_inventory(snapshot))
    link.unlink(); saved_link.unlink()

    row = s.record(existing)
    short = {k: v for k, v in row.items() if k != "bytes"}
    assert s.check_pinned_records({"nested": [{"input": short}]}) == 1
    passed("hash_only_nested_pin_without_size")
    bad = dict(short, sha256="0" * 64)
    rejects("hash_only_nested_wrong_sha", lambda: s.check_pinned_records(bad))
    rejects("wrong_optional_size", lambda: s.check_pinned_records(dict(row, bytes=row["bytes"] + 1)))
    existing.write_text("updated")
    rejects("nested_source_change", lambda: s.check_pinned_records({"nested": [row]}))
    existing.write_text("Sources")

    evidence = root / "research-evidence.txt"
    evidence.write_text("reviewed evidence")
    for key in s.REVIEW_PIN_KEYS:
        records = [s.record(existing), s.record(evidence)]
        records[1].pop("bytes")
        assert s.check_review_pins({key: records}) == 2
        passed("matching_review_key_" + key)
        existing.write_text("source change")
        rejects("review_source_change_" + key, lambda: s.check_review_pins({key: records}))
        existing.write_text("Sources")
        evidence.write_text("evidence change")
        rejects("review_evidence_change_" + key, lambda: s.check_review_pins({key: records}))
        evidence.write_text("reviewed evidence")

    child, outer = root / "child", root / "outer"
    child.mkdir(); outer.mkdir()
    original = child / "data.txt"
    original.write_text("accepted native input")
    child_manifest = child / "artifact-manifest.json"
    child_row = s.record(original)
    save(child_manifest, {"files": [child_row]})
    integrity = outer / "native-final-integrity.json"
    manifest_pin = s.record(child_manifest)
    manifest_pin.pop("bytes")
    save(integrity, {"native": {"manifest": manifest_pin}})
    parent = outer / "artifact-manifest.json"
    save(parent, {"files": [s.record(integrity)]})
    result = s.recursive_integrity([(parent, root, 1)])
    assert len(result["manifests"]) == 2
    passed("recursive_hash_only_manifest_reference")
    bad_manifest_pin = dict(manifest_pin, sha256="0"*64)
    save(integrity, {"native": {"manifest": bad_manifest_pin}})
    save(parent, {"files": [s.record(integrity)]})
    rejects("recursive_manifest_reference_wrong_sha", lambda: s.recursive_integrity([(parent, root, 1)]))
    save(integrity, {"native": {"manifest": manifest_pin}})
    save(parent, {"files": [s.record(integrity)]})
    original.write_text("changed native input")
    rejects("transitive_native_input_mutation", lambda: s.recursive_integrity([(parent, root, 1)]))
    original.write_text("accepted native input")
    save(child_manifest, {"files": [{"path": "child/data.txt"}]})
    rejects("digestless_manifest_entry", lambda: s.recursive_integrity([(child_manifest, root, 1)]))
    save(child_manifest, {"files": [{"path": "child/data.txt", "bytes": child_row["bytes"]}]})
    rejects("size_only_manifest_entry", lambda: s.recursive_integrity([(child_manifest, root, 1)]))
    save(child_manifest, {"files": [dict(child_row, sha256="z"*64)]})
    rejects("nonhex_digest_entry", lambda: s.recursive_integrity([(child_manifest, root, 1)]))
    save(child_manifest, {"files": [child_row, child_row]})
    rejects("duplicate_manifest_path", lambda: s.recursive_integrity([(child_manifest, root, 2)]))
    save(child_manifest, {"files": [child_row]})
    rejects("wrong_manifest_file_count", lambda: s.recursive_integrity([(child_manifest, root, 2)]))

    external = s.record(evidence)
    external.pop("bytes")
    save(child_manifest, {"files": [child_row], "external_references": [external]})
    manifest_pin = s.record(child_manifest); manifest_pin.pop("bytes")
    save(integrity, {"native": {"manifest": manifest_pin}})
    save(parent, {"files": [s.record(integrity)]})
    result = s.recursive_integrity([(parent, root, 1)])
    assert sum(x["external_references_checked"] for x in result["manifests"]) == 1
    passed("transitive_hash_only_external_reference")
    evidence.write_text("external modification")
    rejects("transitive_external_reference_changed", lambda: s.recursive_integrity([(parent, root, 1)]))
    evidence.write_text("reviewed evidence")
    save(child_manifest, {"files": [child_row], "external_references": [dict(external, sha256="0"*64)]})
    rejects("native_external_reference_wrong_sha", lambda: s.recursive_integrity([(child_manifest, root, 1)]))

    # Old superseded test bytes are accepted only through a pinned identical
    # preserved snapshot, never described as unchanged at the former live path.
    save(child_manifest, {"files": [child_row]})
    preserved = child / "old-snapshot.txt"
    preserved.write_text("accepted native input")
    original.write_text("new live source")
    substitution = {"original_manifest_entry": child_row, "preserved_bytes": s.record(preserved)}
    save(integrity, {"native": {"manifest": s.record(child_manifest), "superseded_application_files": [substitution]}})
    save(parent, {"files": [s.record(integrity)]})
    result = s.recursive_integrity([(parent, root, 1)])
    child_result = next(x for x in result["manifests"] if x["manifest"]["path"] == "child/artifact-manifest.json")
    assert child_result["unchanged_at_original_path"] == 0
    assert len(child_result["explicit_preserved_substitutions"]) == 1
    passed("identical_explicit_preserved_substitution")
    preserved.write_text("wrong bytes")
    rejects("preserved_substitution_changed", lambda: s.recursive_integrity([(parent, root, 1)]))
    preserved.write_text("accepted native input")
    integrity.write_text("modified link")
    rejects("linking_integrity_record_changed", lambda: s.recursive_integrity([(parent, root, 1)]))

root = HERE.parents[3]
def pin(path):
    data = path.read_bytes()
    return dict(path=str(path.relative_to(root)), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
result = dict(schema_version=1, passed=True,
    scope="Disposable authored custody-instrument controls. No app/target execution, acceptance, status sealing or historical edits.",
    sealer=pin(source), generator=pin(Path(__file__)), controls=controls,
    passed_controls=len(controls), negative_controls=sum(x.get("rejected",False) for x in controls))
with (HERE / "sealer-negative-controls-final.json").open("x") as output:
    json.dump(result,output,indent=2);output.write("\n")
print(json.dumps(dict(passed=True,controls=len(controls),negative_controls=result["negative_controls"])))
