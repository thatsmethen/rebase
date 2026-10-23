#!/usr/bin/env python3
"""Accept APP012 after independent GUI review, then seal after final status docs.

Requires explicit frozen acceptance-inputs.json (test/build/binary/native pins).
All evidence writes are exclusive. Does not execute app, tests or vendor code.
Read-only codesign/otool checks inspect the independently built application.
"""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import os
import plistlib
import re
import shutil
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
APP = ROOT / "Application/dist/Rebase.app"
INPUTS = OUT / "acceptance-inputs.json"
PRIOR_SHA = "ff197a663e3095918e114d2ca307ff11e63274079a57c9ea0f827f11089ed22e"
PUBLIC_MANIFEST_SHA = "c6b872975ccb94cf6ec3832ed74f5b10805ab77b7ae6304bad5315e2fa80c3b2"
PUBLIC_FINDING_SHA = "b1a89c059919631331be61bea29940fb39d7a0cf38fd0d685b29d2279e2d8965"
PUBLIC_LIBRARY_SHA = "c614df97b2c3f3881fa694efc73a6d5152fe0288ac9396adb6bd7c8c8e5f895a"


def entries(directory):
    return [p for p in sorted(directory.rglob("*"))
            if (p.is_file() or p.is_symlink()) and p.name != ".DS_Store"
            and "__pycache__" not in p.parts]


def record(path):
    before = path.lstat()
    result = {"path": str(path.relative_to(ROOT))}
    if stat.S_ISLNK(before.st_mode):
        result["symlink"] = os.readlink(path)
    else:
        assert stat.S_ISREG(before.st_mode), path
        data = path.read_bytes()
        result.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    after = path.lstat()
    fields = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    assert fields(before) == fields(after), f"Changed while reading: {path}"
    return result


def matches(path, expected):
    actual = record(path)
    keys = ("symlink",) if "symlink" in expected else ("bytes", "sha256")
    return all(actual.get(k) == expected[k] for k in keys)


def pinned(path, sha):
    result = record(path)
    assert result["sha256"] == sha, path
    return result


def write(name, value):
    path = OUT / name
    with path.open("x") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")
    return record(path)


def require_new(names):
    for name in names:
        assert not os.path.lexists(OUT / name), f"Refusing overwrite: {name}"


def verify_manifest(path, base=ROOT, expected_count=None):
    rows = json.loads(path.read_text())["files"]
    assert len({r["path"] for r in rows}) == len(rows), path
    if expected_count is not None:
        assert len(rows) == expected_count, path
    for row in rows:
        assert matches(base / row["path"], row), row["path"]
    return {"manifest": record(path), "files_checked": len(rows),
            "all_original_entries_verified": True}


def command(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT).strip()


def packaging():
    """Bind nested dynamic library, source, licenses, signatures and rpaths."""
    third = ROOT / "Application/ThirdParty"
    packaged = APP / "Contents/Resources/ThirdParty"
    source_manifest = json.loads((third / "soxr-source-manifest.json").read_text())
    assert source_manifest["commit"] == "945b592b70470e29f917f4de89b4281fbbd540c0"
    assert len(source_manifest["files"]) == 138
    for row in source_manifest["files"]:
        assert matches(third / "soxr-0.1.3" / row["path"], row), row["path"]
    source_set = {str(p.relative_to(third)) for p in entries(third)}
    packaged_set = {str(p.relative_to(packaged)) for p in entries(packaged)}
    assert packaged_set == source_set | {"soxr-build-manifest.json"}
    for relative in source_set:
        assert matches(packaged / relative, record(third / relative)), relative
    for name in ["soxr-0.1.3/LICENCE", "soxr-0.1.3/COPYING.LGPL",
                 "soxr-0.1.3/src/fft4g.c", "soxr-0.1.3/src/pffft.c",
                 "SOXR-NOTICES.txt", "README.md", "build-soxr.sh"]:
        assert (packaged / name).is_file(), name
    notice = APP / "Contents/Resources/ThirdPartyNotices.txt"
    assert (third / "SOXR-NOTICES.txt").read_bytes() in notice.read_bytes()
    library = APP / "Contents/Frameworks/libsoxr.0.dylib"
    lib_record = pinned(library, PUBLIC_LIBRARY_SHA)
    build = json.loads((packaged / "soxr-build-manifest.json").read_text())
    assert build["library"]["sha256"] == PUBLIC_LIBRARY_SHA
    assert build["source_version"] == "0.1.3" and build["minimum_macos"] == "14.0"
    assert build["architecture"] == "arm64"
    assert build["options"]["SIMD"] is False and build["options"]["OpenMP"] is False
    assert build["options"]["fp_contract"] == "off"
    binary = APP / "Contents/MacOS/Rebase"
    exe_loads = command("otool", "-L", str(binary))
    lib_loads = command("otool", "-L", str(library))
    exe_commands = command("otool", "-l", str(binary))
    lib_commands = command("otool", "-l", str(library))
    rpaths = re.findall(r"cmd LC_RPATH\s+cmdsize \d+\s+path (.*?) \(offset", exe_commands)
    assert "@executable_path/../Frameworks" in rpaths
    assert all(p in {"@executable_path/../Frameworks", "@loader_path"} or p.startswith("/usr/lib/")
               for p in rpaths), rpaths
    assert "@rpath/libsoxr.0.dylib" in exe_loads and "@rpath/libsoxr.0.dylib" in lib_loads
    exe_dependencies = [line.strip().split(" (", 1)[0] for line in exe_loads.splitlines()[1:]]
    assert all(p == "@rpath/libsoxr.0.dylib" or
               p.startswith(("/usr/lib/", "/System/Library/")) for p in exe_dependencies)
    dependencies = [line.strip().split(" (", 1)[0] for line in lib_loads.splitlines()[1:]]
    assert dependencies == ["@rpath/libsoxr.0.dylib", "/usr/lib/libSystem.B.dylib"]
    assert re.search(r"\bminos 14\.0\b", lib_commands), "Unexpected public library deployment target"
    exe_signature = command("codesign", "--verify", "--strict", str(APP))
    lib_signature = command("codesign", "--verify", "--strict", str(library))
    return {"library": lib_record, "source_entries_packaged": len(source_set),
            "upstream_entries": 138, "source_manifest": record(third / "soxr-source-manifest.json"),
            "packaged_build_manifest": record(packaged / "soxr-build-manifest.json"),
            "notices": record(notice), "all_source_and_license_entries_match": True,
            "rpaths": rpaths, "executable_dependencies": exe_loads,
            "library_dependencies": lib_loads, "library_load_commands": lib_commands,
            "codesign_app_result": exe_signature, "codesign_library_result": lib_signature,
            "scope": "Static packaging/signature checks; public backend only, no vendor execution."}


def accept():
    require_new(["application-validation.json", "gui-observations.json",
                 "historical-final-integrity.json", "native-final-integrity.json",
                 "public-backend-packaging.json", "final-source-snapshot",
                 "final-source-manifest.json", "final-build-snapshot"])
    config = json.loads(INPUTS.read_text())
    assert config["tests"]["passed"] == 212 and config["tests"]["suites"] == 31
    test = ROOT / config["tests"]["path"]
    pinned(test, config["tests"]["sha256"])
    assert "Test run with 212 tests in 31 suites passed" in test.read_text()
    build_log = ROOT / config["build_log"]["path"]
    pinned(build_log, config["build_log"]["sha256"])
    assert "Build complete!" in build_log.read_text()
    info = plistlib.loads((APP / "Contents/Info.plist").read_bytes())
    assert info["CFBundleShortVersionString"] == "0.12.0" and info["CFBundleVersion"] == "12"
    binary = pinned(APP / "Contents/MacOS/Rebase", config["executable_sha256"])
    observed = json.loads((OUT / "gui-release-build.json").read_text())
    assert all(observed[k] == binary[k] for k in ("path", "bytes", "sha256"))
    package_check = packaging()

    independent = json.loads((OUT / "gui-independent-check.json").read_text())
    assert independent["status"] == "passed"
    groups = independent["groups"]
    expected = independent["expected_group_names"]
    assert expected and len(expected) == len(set(expected))
    assert sorted(g["name"] for g in groups) == sorted(expected)
    assert independent["release"]["binary"] == binary
    assert independent["tests"]["log"] == record(test)
    assert independent["tests"]["passed"] == 212 and independent["tests"]["suites"] == 31
    for row in independent["gui_evidence"]:
        assert matches(ROOT / row["path"], row), row["path"]
    for group in groups:
        assert group["files"] and group["observations"]
        assert all(any(r["path"] == str((OUT / name).relative_to(ROOT))
                       for r in independent["gui_evidence"]) for name in group["files"])
    baseline = json.loads((OUT / "gui-package-baselines.json").read_text())
    assert len(baseline["controls"]) == 3
    package_files = 0
    for control in baseline["controls"]:
        package = ROOT / control["copy"]
        assert {str(p.relative_to(package)) for p in entries(package)} == {
            row["path"] for row in control["files"]}
        for row in control["files"]:
            assert matches(package / row["path"], row), row["path"]
            package_files += 1
    assert package_files == 15
    prior = ROOT / "research/evidence/application/APP011/artifact-manifest.json"
    pinned(prior, PRIOR_SHA)
    historical = {"APP011": verify_manifest(prior, expected_count=181)}
    public = OUT / "soxr-public-build"
    pinned(public / "finding.json", PUBLIC_FINDING_SHA)
    pinned(public / "artifact-manifest.json", PUBLIC_MANIFEST_SHA)
    native = {"public_soxr_build": verify_manifest(public / "artifact-manifest.json", expected_count=19)}
    for pin in config["native_studies"]:
        directory = ROOT / pin["directory"]
        pinned(directory / "finding.json", pin["finding_sha256"])
        pinned(directory / "artifact-manifest.json", pin["manifest_sha256"])
        native[directory.name] = verify_manifest(directory / "artifact-manifest.json",
            base=directory if pin.get("study_relative") else ROOT, expected_count=pin["files"])
    assert "rate-mode2" in native
    reviews = config["reviews"] + ["research/evidence/application/APP012/gui-independent-check.json"]
    for name in reviews:
        review = json.loads((ROOT / name).read_text())
        for row in (review.get("source_pins", []) + review.get("inputs", [])
                    + review.get("reviewed_sources_and_evidence", [])):
            if row["path"].startswith("Application/"):
                assert matches(ROOT / row["path"], row), row["path"]

    # All identity, GUI, custody and packaging predicates pass before publication.
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    historical_record = write("historical-final-integrity.json", historical)
    native_record = write("native-final-integrity.json", native)
    packaging_record = write("public-backend-packaging.json", package_check)
    gui_record = write("gui-observations.json", {
        "id": "APP012-GUI", "created_utc": now, "groups_passed": len(groups),
        "executable": binary, "public_library": package_check["library"],
        "groups": [{"id": g["name"], "result": "passed", "observation": g["observations"],
                    "records": [record(OUT / n) for n in g["files"]]} for g in groups],
        "package_files_unchanged": package_files,
        "scope": "Own application with synthetic PCM; engine telemetry is not DAC or Cubase output."})
    source = OUT / "final-source-snapshot"
    source.mkdir()
    for directory in ["Sources", "Tests", "ThirdParty"]:
        shutil.copytree(ROOT / "Application" / directory, source / directory, symlinks=True)
    for name in ["Package.swift", "Package.resolved", "build-app.sh", "test-app.sh"]:
        shutil.copy2(ROOT / "Application" / name, source / name)
    for p in entries(source):
        assert matches(ROOT / "Application" / p.relative_to(source), record(p))
    source_record = write("final-source-manifest.json", {
        "scope": "Application sources/tests plus complete public SoXR source, licenses and build scripts; symlinks preserved.",
        "files": [record(p) for p in entries(source)]})
    bundle = OUT / "final-build-snapshot/Rebase.app"
    shutil.copytree(APP, bundle, symlinks=True)
    pinned(bundle / "Contents/MacOS/Rebase", binary["sha256"])
    pinned(bundle / "Contents/Frameworks/libsoxr.0.dylib", PUBLIC_LIBRARY_SHA)
    validation = write("application-validation.json", {
        "id": "APP012", "created_utc": now, "version": "0.12.0", "build": 12,
        "status": "explicit_public_soxr_native_wrapper_source_audition_integrated_and_checked",
        "full_fidelity_objective": "incomplete", "cubase_runtime_comparisons": 0, "target_executions": 0,
        "acceptance_inputs": record(INPUTS),
        "executable": record(bundle / "Contents/MacOS/Rebase"),
        "public_library": record(bundle / "Contents/Frameworks/libsoxr.0.dylib"),
        "source_manifest": source_record,
        "tests": {"passed": 212, "suites": 31, "log": record(test),
                  "scope": "Application regression, instruction-derived wrapper and independent public-library controls; no vendor samples."},
        "build_log": record(build_log), "gui": gui_record,
        "independent_reviews": [record(ROOT / p) for p in reviews],
        "independent_controls": [record(ROOT / p) for p in config["controls"]],
        "static_findings": [record(ROOT / p["directory"] / "finding.json") for p in config["native_studies"]],
        "public_build": record(public / "finding.json"), "public_packaging": packaging_record,
        "native_integrity": native_record, "historical_integrity": historical_record,
        "implemented": [
            "Explicit public-SoXR mode2 option reconstructs the successful Float32 native wrapper using io0, quality6/flags0 VHQ and runtime0.",
            "Native-style initial padding/discard, requested/produced distinction, retained buffers, compaction, drift accounting and one terminal extension/NULL drain are represented separately from the public library.",
            "Each cursor owns fresh backend state. Count planning and playback use the same 8192-input/final-positive policy; reset/preroll seeks retain the crossing suffix.",
            "Separate Float32 event gain follows conversion, then the existing stereo transfer and four-buffer AVAudioEngine queue.",
            "Complete pinned public source/licenses/build scripts and replaceable dynamic library are packaged; ordinary project barriers and frozen CPR provenance remain intact."],
        "limits": [
            "The public scalar CR32/CR64 build is not proven equivalent to Cubase's bundled modifications, FP/SIMD/compiler configuration or runtime output.",
            "This is an explicit mode2 choice, not automatic native availability selection; mode1 fallback samples are not implemented.",
            "One eligible zero-origin source event only. General placement, track/mixer/routing/automation, plugin processing and full CPR playback remain incomplete.",
            "Resident PCM, 8192-input partitions, serialized ring transfer, main-actor refill, AVAudioEngine queue and seek preroll are application policies.",
            "Independent wrapper controls using the same public backend validate the reconstructed wrapper, not vendor-library sample equivalence.",
            "No DAC capture, device-rate equivalence or Cubase runtime comparison follows from these checks."],
        "retained_corrections": config.get("retained_corrections", []),
        "next": "Trace the remaining live callback binding and mode1 fallback, and use future authorized reference samples to challenge public-build equivalence."})
    print(json.dumps({"validation": validation, "groups": len(groups),
                      "package_files": package_files, "source_entries": len(entries(source))}))


def seal():
    require_new(["final-status-snapshot", "artifact-manifest.json", "final-integrity.json"])
    validation = json.loads((OUT / "application-validation.json").read_text())
    assert matches(INPUTS, validation["acceptance_inputs"])
    verify_manifest(OUT / "final-source-manifest.json")
    source = OUT / "final-source-snapshot"
    for path in entries(source):
        assert matches(ROOT / "Application" / path.relative_to(source), record(path))
    pinned(APP / "Contents/MacOS/Rebase", validation["executable"]["sha256"])
    packaging()
    status = OUT / "final-status-snapshot"
    status.mkdir()
    for name in ["README.md", "research/study.json", "research/coverage.json", "research/rea-steering.json"]:
        target = status / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    manifest = write("artifact-manifest.json", {
        "id": "APP012", "scope": "Local source/build/status snapshots, public library source/licenses, controls, GUI/custody and retained failures.",
        "files": [record(p) for p in entries(OUT)]})
    checked = verify_manifest(OUT / "artifact-manifest.json")
    write("final-integrity.json", {"manifest": manifest,
        "validation": record(OUT / "application-validation.json"), "sealed": True,
        "files_verified": checked["files_checked"]})
    print(json.dumps(manifest))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--accept", action="store_true")
    mode.add_argument("--seal", action="store_true")
    args = parser.parse_args()
    seal() if args.seal else accept()
