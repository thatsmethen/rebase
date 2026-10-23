#!/usr/bin/env python3
"""Prepare APP005 custody records after the release build and GUI checks finish.

Do not run snapshot while a source edit or release build is in progress.
snapshot --expected-executable-sha256 SHA --release-log APP005/LOG
         --gui-record APP005/GUI.json [--expected-version 0.5.0 --expected-build 5]
manifest --validation APP005/application-validation.json

Snapshot creates new final-source-snapshot/, final-build-snapshot/,
final-source-manifest.json, build-identity.json, validation-inputs.json and
codesign-verify.log. It never rebuilds, launches or modifies either application.
Manifest is a separate final operation after root authors validation. Every
destination is exclusive-create; existing evidence is never refreshed in place.
"""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import os
import plistlib
import re
import runpy
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
APP = ROOT / "Application/dist/Rebase.app"
helpers = runpy.run_path(str(HERE / "verify-gui-packages.py"))
read, sha, require, strict_json = (helpers[k] for k in ("read", "sha", "require", "strict_json"))


def at_root(path):
    path = Path(path)
    return path if path.is_absolute() else ROOT / path


def item(path, content=None):
    path = at_root(path)
    content = read(path) if content is None else content
    return {"path": str(path.relative_to(ROOT)), "bytes": len(content), "sha256": sha(content)}


def write_json(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False); stream.write("\n")


def source_paths():
    app = ROOT / "Application"
    paths = [app / name for name in ("Package.swift", "Package.resolved", "build-app.sh", "test-app.sh")]
    for name in ("Sources", "Tests"):
        for path in sorted((app / name).rglob("*")):
            require(not path.is_symlink(), "Source symlink is outside snapshot scope.")
            if path.is_file():
                require(path.suffix in (".swift", ".c", ".h"), "Unexpected source file: " + str(path))
                paths.append(path)
    return sorted(paths)


def bounded_evidence(path):
    path = at_root(path)
    require(path.is_relative_to(HERE), "Build/test/GUI inputs must be retained in APP005.")
    return path, read(path, limit=16_777_216)


def snapshot(args):
    names = ["final-source-snapshot", "final-build-snapshot", "final-source-manifest.json",
             "build-identity.json", "validation-inputs.json", "codesign-verify.log"]
    require(all(not os.path.lexists(HERE / name) for name in names), "Refusing existing final snapshot destinations.")
    release_path, release = bounded_evidence(args.release_log)
    gui_path, gui = bounded_evidence(args.gui_record)
    strict_json(gui)  # Pin user-visible root observations, without manufacturing their interpretation.
    test_path, test = bounded_evidence(HERE / "core-tests-final.log")
    require(re.findall(rb"Test run with (\d+) tests in (\d+) suites passed after", test) == [(b"108", b"16")], "Unexpected accepted test log.")
    require(not re.search(rb"error:|Test .* failed|recorded an issue", test), "Test failure diagnostic found.")
    require(b"Build complete!" in release and b"Built " + str(APP).encode() in release
            and b"error:" not in release, "Release log does not show completed app packaging.")
    executable = APP / "Contents/MacOS/Rebase"
    plist_path = APP / "Contents/Info.plist"
    binary = read(executable); plist_bytes = read(plist_path); info = plistlib.loads(plist_bytes)
    require(sha(binary) == args.expected_executable_sha256, "Binary changed or does not match root's expected release identity.")
    require(info["CFBundleShortVersionString"] == args.expected_version and info["CFBundleVersion"] == args.expected_build
            and info["CFBundleExecutable"] == "Rebase", "Unexpected release plist identity.")
    files = {path: read(path) for path in source_paths()}
    bundle = []
    for path in sorted(APP.rglob("*")):
        require(not path.is_symlink(), "Bundle symlink is outside this local build snapshot scope.")
        if path.is_file():
            bundle.append(item(path))
    sign = subprocess.run(["/usr/bin/codesign", "--verify", "--strict", str(APP)], capture_output=True)
    require(sign.returncode == 0, "Strict local signature verification failed: " + sign.stderr.decode(errors="replace"))
    signature_log = sign.stdout + sign.stderr
    # Freshly verify all read inputs after the potentially longer signature check.
    for path, content in list(files.items()) + [(executable, binary), (plist_path, plist_bytes),
                                               (release_path, release), (gui_path, gui), (test_path, test)]:
        require(read(path) == content, "Input changed during snapshot: " + str(path))
    require(source_paths() == sorted(files), "Source inventory changed during snapshot.")
    for record in bundle:
        require(item(record["path"]) == record, "App bundle changed during snapshot.")
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    staging = Path(tempfile.mkdtemp(prefix=".final-snapshot-", dir=HERE))
    try:
        source_manifest = {"scope": "Application source/tests captured after root-confirmed final release build; original target source excluded.",
                           "created_utc": timestamp, "files": [item(path, data) for path, data in files.items()]}
        for path, data in files.items():
            destination = staging / "final-source-snapshot" / path.relative_to(ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as stream: stream.write(data)
        for path, data in [(executable, binary), (plist_path, plist_bytes)]:
            destination = staging / "final-build-snapshot" / path.relative_to(APP)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as stream: stream.write(data)
        write_json(staging / "final-source-manifest.json", source_manifest)
        with (staging / "codesign-verify.log").open("xb") as stream: stream.write(signature_log)
        identity = {"created_utc": timestamp, "version": args.expected_version, "build": args.expected_build,
                    "executable_sha256": sha(binary), "executable_bytes": len(binary), "info_plist_sha256": sha(plist_bytes),
                    "source_manifest_sha256": sha((staging / "final-source-manifest.json").read_bytes()),
                    "release_log": item(release_path, release), "codesign_strict_exit": sign.returncode,
                    "codesign_log_sha256": sha(signature_log), "bundle_files": bundle,
                    "snapshot_helper_sha256": sha(Path(__file__).read_bytes()),
                    "limits": "Local build/signature custody. No notarization, target execution or source-to-binary reproducibility assertion."}
        write_json(staging / "build-identity.json", identity)
        inputs = {"id": "APP005-VALIDATION-INPUTS", "created_utc": timestamp,
                  "build_identity_sha256": sha((staging / "build-identity.json").read_bytes()),
                  "tests": {"passed": 108, "suites": 16, "evidence": item(test_path, test), "classification": "Retained self-authored app test log; no rerun by snapshot."},
                  "gui_observations": item(gui_path, gui),
                  "existing_checks": [item(HERE / name) for name in ("resumed-integrity.json", "native-map-independent-check.json",
                       "converted-copy-independent-check.json", "converted-exchange-independent-check.json")],
                  "reference_runtime_comparisons": 0,
                  "limits": ["This is a manifest input record, not an approval or generated application-validation verdict.",
                             "Root must explicitly report current native host callback gate and all unresolved scope in application-validation.json.",
                             "GUI observations are pinned, not independently replayed or interpreted by this helper."]}
        write_json(staging / "validation-inputs.json", inputs)
        for name in names:
            require(not os.path.lexists(HERE / name), "Destination appeared during snapshot.")
            os.rename(staging / name, HERE / name)
    finally:
        shutil.rmtree(staging)
    print(json.dumps({"created": names, "source_files": len(files), "executable_sha256": sha(binary)}, indent=2))


def manifest(args):
    destination = HERE / "artifact-manifest.json"
    require(not os.path.lexists(destination), "Refusing to replace an artifact manifest.")
    validation_path = at_root(args.validation)
    require(validation_path == HERE / "application-validation.json", "Expected root-authored APP005 application-validation.json.")
    strict_json(read(validation_path))
    require((HERE / "build-identity.json").is_file() and (HERE / "final-source-manifest.json").is_file(), "Final snapshot is not present.")
    files = []
    for path in sorted(HERE.rglob("*")):
        require(not path.is_symlink(), "Symlink in evidence inventory.")
        require(not any(part.startswith(".final-snapshot-") for part in path.parts), "Snapshot staging is still present.")
        if path.is_file(): files.append(item(path))
    record = {"id": "APP005-artifacts", "at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "scope": "Retained application build/test/review/GUI/package evidence and source/binary snapshots; manifest excludes itself. No reference runtime conformance implied.",
              "files": files}
    write_json(destination, record)
    print(json.dumps({"manifest": str(destination), "files": len(files), "sha256": sha(destination.read_bytes())}))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("snapshot")
    for name in ("expected-executable-sha256", "release-log", "gui-record"):
        command.add_argument("--" + name, required=True)
    command.add_argument("--expected-version", default="0.5.0")
    command.add_argument("--expected-build", default="5")
    commands.add_parser("manifest").add_argument("--validation", required=True)
    args = parser.parse_args()
    (snapshot if args.command == "snapshot" else manifest)(args)


if __name__ == "__main__": main()
