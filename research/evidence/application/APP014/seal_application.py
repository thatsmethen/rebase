#!/usr/bin/env python3
"""Accept APP014 against frozen checks, then seal source/build/status custody.

Reuses the immutable APP012 file/signature/public-source verification routines.
No target code is executed. Every evidence output is exclusive.
"""
from pathlib import Path
import argparse
import datetime
import importlib.util
import json
import plistlib
import shutil

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
APP = ROOT / "Application/dist/Rebase.app"
INPUTS = OUT / "acceptance-inputs.json"
spec = importlib.util.spec_from_file_location(
    "app012_custody", OUT.parent / "APP012/seal_application.py")
custody = importlib.util.module_from_spec(spec)
spec.loader.exec_module(custody)
custody.OUT = OUT
record, matches, pinned = custody.record, custody.matches, custody.pinned
entries, write, verify = custody.entries, custody.write, custody.verify_manifest
SOURCE_DIRECTORIES = ("Sources", "Tests", "ThirdParty")
SOURCE_FILES = ("Package.swift", "Package.resolved", "build-app.sh", "test-app.sh")
REVIEW_PIN_KEYS = ("source_pins", "inputs", "reviewed_inputs",
                   "reviewed_sources", "reviewed_sources_and_evidence",
                   "source_and_evidence")


def application_source_entries():
    """The complete accepted source universe, excluding build output/caches."""
    paths = [ROOT / "Application" / name for name in SOURCE_FILES]
    for name in SOURCE_DIRECTORIES:
        paths.extend(entries(ROOT / "Application" / name))
    return sorted(paths)


def check_source_inventory(snapshot):
    current = {str(p.relative_to(ROOT / "Application")): p
               for p in application_source_entries()}
    saved = {str(p.relative_to(snapshot)): p for p in entries(snapshot)}
    assert current.keys() == saved.keys(), {
        "added_after_acceptance": sorted(current.keys() - saved.keys()),
        "missing_after_acceptance": sorted(saved.keys() - current.keys()),
    }
    for relative, path in current.items():
        assert matches(path, record(saved[relative])), relative
    return len(current)


def check_pinned_records(value):
    """Validate records already fixed by acceptance, including nested GUI rows."""
    checked = 0
    if isinstance(value, dict):
        if "path" in value and ("sha256" in value or "symlink" in value):
            assert matches(ROOT / value["path"], value), value["path"]
            checked += 1
        for child in value.values():
            checked += check_pinned_records(child)
    elif isinstance(value, list):
        for child in value:
            checked += check_pinned_records(child)
    return checked


def recursive_integrity(manifests):
    """Follow pinned native/prior manifest references through integrity records.

    The one old test-source supersession is accepted only when a pinned
    integrity record explicitly maps the original hash to identical preserved
    bytes. The record is not rewritten and its old live path is not called
    unchanged. Relative-path manifest conventions are explicit, not guessed.
    """
    relative_bases = {
        "research/evidence/cubase-static/cpr-audio-events-001/rate-selection/artifact-manifest.json",
        "research/evidence/application/APP003/artifact-manifest.json",
    }
    visited, active, overrides, cache = {}, set(), {}, {}

    def cached_matches(path, expected):
        stat = path.lstat()
        stamp = (stat.st_dev, stat.st_ino, stat.st_mode, stat.st_size,
                 stat.st_mtime_ns, stat.st_ctime_ns)
        previous = cache.get(path)
        if previous is None or previous[0] != stamp:
            previous = (stamp, record(path))
            cache[path] = previous
        actual = previous[1]
        keys = ("symlink",) if "symlink" in expected else ("bytes", "sha256")
        assert all(actual.get(k) == expected[k] for k in keys), str(path)

    def integrity_links(value):
        if isinstance(value, dict):
            link = value.get("manifest")
            if isinstance(link, dict) and "path" in link and "sha256" in link:
                manifest = ROOT / link["path"]
                cached_matches(manifest, link)
                substitutions = overrides.setdefault(manifest, {})
                for substitution in value.get("superseded_application_files", []):
                    original = substitution["original_manifest_entry"]
                    preserved = substitution["preserved_bytes"]
                    assert original["bytes"] == preserved["bytes"]
                    assert original["sha256"] == preserved["sha256"]
                    cached_matches(ROOT / preserved["path"], preserved)
                    key = (original["path"], original["sha256"])
                    assert key not in substitutions or substitutions[key] == preserved
                    substitutions[key] = preserved
                visit(manifest)
            for child in value.values():
                integrity_links(child)
        elif isinstance(value, list):
            for child in value:
                integrity_links(child)

    def visit(path, base=None, expected_count=None):
        relative = str(path.relative_to(ROOT))
        if path in visited:
            if expected_count is not None:
                assert visited[path]["files_checked"] == expected_count
            return
        assert path not in active, f"Manifest cycle: {relative}"
        active.add(path)
        data = json.loads(path.read_text())
        rows = data["files"]
        assert len({row["path"] for row in rows}) == len(rows), relative
        if expected_count is not None:
            assert len(rows) == expected_count, relative
        if base is None:
            base = path.parent if relative in relative_bases else ROOT
        saved, direct = [], 0
        for row in rows:
            candidate = base / row["path"]
            replacement = overrides.get(path, {}).get((row["path"], row.get("sha256")))
            if replacement is not None:
                cached_matches(ROOT / replacement["path"], replacement)
                saved.append({"original": row, "preserved": replacement})
            else:
                cached_matches(candidate, row)
                direct += 1
        # Only recurse after each linking record itself matches the parent.
        for row in rows:
            candidate = base / row["path"]
            if candidate.name.endswith("integrity.json"):
                integrity_links(json.loads(candidate.read_text()))
            elif candidate.name == "artifact-manifest.json":
                visit(candidate)
        active.remove(path)
        visited[path] = {
            "manifest": record(path), "files_checked": len(rows),
            "unchanged_at_original_path": direct,
            "explicit_preserved_substitutions": saved,
        }

    for path, base, count in manifests:
        visit(path, base, count)
    return {"scope": "Recursive manifest custody, not semantic/runtime revalidation.",
            "manifests": [visited[p] for p in sorted(visited)],
            "unique_file_identities_read": len(cache)}


def configured_integrity(config):
    prior = OUT.parent / "APP013/artifact-manifest.json"
    pinned(prior, "df83d2260ac460e39988f2869b9af51eeac7b27611e18ea76cc5563e66ee9660")
    roots = [(prior, ROOT, 506)]
    for study in config["native_studies"]:
        directory = ROOT / study["directory"]
        pinned(directory / "finding.json", study["finding_sha256"])
        pinned(directory / "artifact-manifest.json", study["manifest_sha256"])
        manifest = json.loads((directory / "artifact-manifest.json").read_text())
        check_pinned_records(manifest.get("external_references", []))
        roots.append((directory / "artifact-manifest.json",
                      directory if study.get("study_relative") else ROOT,
                      study["files"]))
    return recursive_integrity(roots)


def accept():
    custody.require_new(["application-validation.json", "gui-observations.json",
        "historical-final-integrity.json", "native-final-integrity.json",
        "public-backend-packaging.json", "recursive-acceptance-integrity.json", "final-source-snapshot",
        "final-source-manifest.json", "final-build-snapshot"])
    config = json.loads(INPUTS.read_text())
    tests = config["tests"]
    test = ROOT / tests["path"]
    pinned(test, tests["sha256"])
    assert f"Test run with {tests['passed']} tests in {tests['suites']} suites passed" in test.read_text()
    assert tests["passed"] > 238 and tests["suites"] > 36
    build = ROOT / config["build_log"]["path"]
    pinned(build, config["build_log"]["sha256"])
    assert "Build complete!" in build.read_text()
    info = plistlib.loads((APP / "Contents/Info.plist").read_bytes())
    assert info["CFBundleShortVersionString"] == "0.14.0"
    assert info["CFBundleVersion"] == "14"
    binary = pinned(APP / "Contents/MacOS/Rebase", config["executable_sha256"])
    gui_binary = json.loads((OUT / "gui-release-build.json").read_text())
    assert all(gui_binary[k] == binary[k] for k in ("path", "bytes", "sha256"))
    packaging = custody.packaging()
    gui = json.loads((OUT / "gui-independent-check.json").read_text())
    assert gui["status"] == "passed"
    assert gui["release"]["binary"] == binary
    assert gui["tests"]["log"] == record(test)
    assert gui["tests"]["passed"] == tests["passed"] and gui["tests"]["suites"] == tests["suites"]
    expected = gui["expected_group_names"]
    assert expected and len(set(expected)) == len(expected)
    assert sorted(g["name"] for g in gui["groups"]) == sorted(expected)
    for row in gui["gui_evidence"]:
        assert matches(ROOT / row["path"], row), row["path"]
    for group in gui["groups"]:
        assert group["files"] and group["observations"]
        assert all(any(r["path"] == str((OUT / name).relative_to(ROOT))
                       for r in gui["gui_evidence"]) for name in group["files"])
    package_files = 0
    baseline = json.loads((OUT / "gui-package-baselines.json").read_text())
    assert len(baseline["controls"]) == 1
    for control in baseline["controls"]:
        package = ROOT / control["copy"]
        assert {str(p.relative_to(package)) for p in entries(package)} == {r["path"] for r in control["files"]}
        for row in control["files"]:
            assert matches(package / row["path"], row), row["path"]
            package_files += 1
    assert package_files == 5
    prior = OUT.parent / "APP013/artifact-manifest.json"
    pinned(prior, "df83d2260ac460e39988f2869b9af51eeac7b27611e18ea76cc5563e66ee9660")
    historical = {"APP013": verify(prior, expected_count=506)}
    native = {}
    for study in config["native_studies"]:
        directory = ROOT / study["directory"]
        pinned(directory / "finding.json", study["finding_sha256"])
        pinned(directory / "artifact-manifest.json", study["manifest_sha256"])
        native[directory.name] = verify(directory / "artifact-manifest.json",
            base=directory if study.get("study_relative") else ROOT,
            expected_count=study["files"])
    assert set(native) == {"timeline-reader", "timeline-provider"}
    reviews = config["reviews"] + [str((OUT / "gui-independent-check.json").relative_to(ROOT))]
    for path in reviews:
        review = json.loads((ROOT / path).read_text())
        for key in REVIEW_PIN_KEYS:
            for row in review.get(key, []):
                if row["path"].startswith("Application/"):
                    assert matches(ROOT / row["path"], row), row["path"]
    recursive = configured_integrity(config)
    # All inputs are checked before acceptance outputs are published.
    historical_record = write("historical-final-integrity.json", historical)
    native_record = write("native-final-integrity.json", native)
    packaging_record = write("public-backend-packaging.json", packaging)
    recursive_record = write("recursive-acceptance-integrity.json", recursive)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    gui_record = write("gui-observations.json", {
        "id": "APP014-GUI", "created_utc": now, "groups_passed": len(gui["groups"]),
        "executable": binary, "groups": gui["groups"], "records": gui["gui_evidence"],
        "package_files_unchanged": package_files,
        "scope": "Own application and synthetic PCM; engine telemetry is not DAC or Cubase output."})
    source = OUT / "final-source-snapshot"
    source.mkdir()
    for directory in SOURCE_DIRECTORIES:
        shutil.copytree(ROOT / "Application" / directory, source / directory, symlinks=True)
    for name in SOURCE_FILES:
        shutil.copy2(ROOT / "Application" / name, source / name)
    check_source_inventory(source)
    source_record = write("final-source-manifest.json", {"files": [record(p) for p in entries(source)]})
    bundle = OUT / "final-build-snapshot/Rebase.app"
    shutil.copytree(APP, bundle, symlinks=True)
    pinned(bundle / "Contents/MacOS/Rebase", binary["sha256"])
    validation = write("application-validation.json", {
        "id": "APP014", "created_utc": now, "version": "0.14.0", "build": 14,
        "status": "native_absolute_timeline_reader_integrated_and_checked",
        "full_fidelity_objective": "incomplete", "cubase_runtime_comparisons": 0, "target_executions": 0,
        "acceptance_inputs": record(INPUTS), "executable": record(bundle / "Contents/MacOS/Rebase"),
        "public_library": record(bundle / "Contents/Frameworks/libsoxr.0.dylib"),
        "source_manifest": source_record,
        "tests": {"passed": tests["passed"], "suites": tests["suites"], "log": record(test)},
        "build_log": record(build), "gui": gui_record,
        "independent_reviews": [record(ROOT / p) for p in reviews],
        "independent_controls": [record(ROOT / p) for p in config["controls"]],
        "static_findings": [record(ROOT / p["directory"] / "finding.json") for p in config["native_studies"]],
        "native_integrity": native_record, "historical_integrity": historical_record,
        "recursive_integrity": recursive_record,
        "public_packaging": packaging_record, "implemented": config["implemented"],
        "limits": config["limits"], "retained_corrections": config["retained_corrections"],
        "next": config["next"]})
    print(json.dumps({"validation": validation, "gui_groups": len(gui["groups"]),
                      "package_files": package_files, "source_entries": len(entries(source))}))


def seal():
    custody.require_new(["final-status-snapshot", "artifact-manifest.json", "final-integrity.json",
                         "seal-revalidation.json"])
    validation = json.loads((OUT / "application-validation.json").read_text())
    assert matches(INPUTS, validation["acceptance_inputs"])
    acceptance_records_checked = check_pinned_records(validation)
    gui = json.loads((ROOT / validation["gui"]["path"]).read_text())
    gui_records_checked = check_pinned_records(gui)
    config = json.loads(INPUTS.read_text())
    for reference in validation["independent_reviews"]:
        review = json.loads((ROOT / reference["path"]).read_text())
        for key in REVIEW_PIN_KEYS:
            for row in review.get(key, []):
                if row["path"].startswith("Application/"):
                    assert matches(ROOT / row["path"], row), row["path"]
    verify(OUT / "final-source-manifest.json")
    source = OUT / "final-source-snapshot"
    source_count = check_source_inventory(source)
    pinned(APP / "Contents/MacOS/Rebase", validation["executable"]["sha256"])
    custody.packaging()
    saved_bundle = OUT / "final-build-snapshot/Rebase.app"
    current_bundle = {str(p.relative_to(APP)): p for p in entries(APP)}
    accepted_bundle = {str(p.relative_to(saved_bundle)): p for p in entries(saved_bundle)}
    assert current_bundle.keys() == accepted_bundle.keys()
    for relative, path in current_bundle.items():
        assert matches(path, record(accepted_bundle[relative])), relative
    recursive = configured_integrity(config)
    write("seal-revalidation.json", {
        "acceptance_records_checked": acceptance_records_checked,
        "gui_records_checked": gui_records_checked,
        "source_inventory_entries": source_count,
        "build_inventory_entries": len(current_bundle),
        "recursive_integrity": recursive,
        "scope": "Acceptance-pinned bytes, exact current source/build inventories and recursive historical/native custody rechecked before status sealing.",
    })
    status = OUT / "final-status-snapshot"
    for name in ("README.md", "research/study.json", "research/coverage.json", "research/rea-steering.json"):
        target = status / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    manifest = write("artifact-manifest.json", {
        "id": "APP014", "scope": "Local source/build/status snapshots, controls, GUI/custody and retained failures.",
        "files": [record(p) for p in entries(OUT)]})
    checked = verify(OUT / "artifact-manifest.json")
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
