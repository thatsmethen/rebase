#!/usr/bin/env python3
"""Compile/run only the isolated GUI input helper after APP021 capture freezes.

Does not invoke SwiftPM, rebuild application/test objects, launch the GUI or
execute any proprietary component. Existing capture and input identities are
checked before and after both the helper compile and package preparation.
"""
from datetime import datetime, timezone
import argparse
import importlib.util
import json
from pathlib import Path
import plistlib
import re
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
DEBUG = ROOT/"Application/.build-tests/arm64-apple-macosx/debug"
spec = importlib.util.spec_from_file_location("prior_gui_custody", HERE.parent/"APP015/seal_application.py")
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def load(path): return json.loads(path.read_text())


def write(path, value):
    with path.open("x") as f: json.dump(value, f, indent=2); f.write("\n")
    return c.record(path)


def run(name, command):
    clock = time.monotonic()
    with (HERE/(name+".log")).open("x") as log:
        result = subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    value = dict(command=command,exit_code=result.returncode,elapsed_seconds=time.monotonic()-clock,
                 log=c.record(HERE/(name+".log")))
    write(HERE/(name+".json"), value)
    return value


def check_capture():
    before = load(HERE/"test-source-before.json")["files"]
    assert before == load(HERE/"test-source-after.json")["files"]
    assert before == [c.record(p) for p in c.application_source_entries()]
    test = load(HERE/"core-test-run.json"); release = load(HERE/"release-build.json")
    assert test["exit_code"] == 0 and test["tests"] > 301 and test["suites"] > 47
    assert test["source_unchanged"] is True and test["binaries_unchanged"] is True
    assert release["exit_code"] == 0 and release["source_unchanged"] is True
    c.check_pinned_records(test); c.check_pinned_records(release)
    for row in test["fixed_binaries"]:
        assert c.matches(ROOT/row["observed_original_path"],row["snapshot"])
    assert c.matches(ROOT/"Application/dist/Rebase.app/Contents/MacOS/Rebase",release["executable"])
    assert plistlib.loads((ROOT/"Application/dist/Rebase.app/Contents/Info.plist").read_bytes())["CFBundleShortVersionString"] == "0.21.0"
    return dict(source_inventory=c.record(HERE/"test-source-before.json"),
                test_record=c.record(HERE/"core-test-run.json"),release_record=c.record(HERE/"release-build.json"),
                source_files=len(before),tests=test["tests"],suites=test["suites"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute",action="store_true",help="Explicitly compile and run the helper after authorization")
    parser.add_argument("--attempt",required=True,help="Fresh two-digit attempt ID; failed attempts are preserved")
    args = parser.parse_args()
    assert args.execute and re.fullmatch(r"[0-9]{2}",args.attempt)
    capture = check_capture()
    label = "gui-helper-"+args.attempt
    work = HERE/"gui-package-helper-build"/args.attempt
    outputs = [HERE/(label+s) for s in ["-inputs.json","-compile.log","-compile.json",
        "-compile-integrity.json","-run.log","-run.json","-run-integrity.json","-preparation.json"]]
    outputs += [HERE/"gui-inputs.json",work]
    packages = [HERE/(name+".rebaseproj") for name in ["Nested Overlap QA","Covered Anchor QA",
        "Signed Priority QA","Saved32 Overlap QA"]]
    assert all(not p.exists() for p in outputs+packages), "Refusing existing output or package"
    work.mkdir(parents=True)
    cache = work/"module-cache"; cache.mkdir()
    helper = HERE/"prepare_gui_packages.swift"
    compiler = subprocess.check_output(["xcrun","--find","swiftc"],text=True).strip()
    sdk = subprocess.check_output(["xcrun","--show-sdk-path"],text=True).strip()
    modules = ["RebaseAmbiDSP","RebaseCore","RebaseDSP","RebaseSoXR","RebaseTimingDSP","ZIPFoundation"]
    objects = sorted(p for name in modules for p in (DEBUG/(name+".build")).glob("*.o"))
    assert all(any(p.parent.name == name+".build" for p in objects) for name in modules)
    command = [compiler,"-swift-version","5","-target","arm64-apple-macosx14.0","-sdk",sdk,
        "-module-name","APP021GUIInputHelper","-module-cache-path",str(cache),
        "-I",str(DEBUG/"Modules"),"-Xfrontend","-disable-cross-import-overlays",
        "-F","/Library/Developer/CommandLineTools/Library/Developer/Frameworks"]
    maps = []
    for name in ["RebaseAmbiDSP","RebaseDSP","RebaseTimingDSP","RebaseSoXR"]:
        include = ROOT/"Application/Sources"/name/"include"
        modulemap = include/"module.modulemap" if name == "RebaseTimingDSP" else DEBUG/(name+".build")/"module.modulemap"
        assert modulemap.is_file(); maps.append(modulemap)
        command += ["-Xcc","-fmodule-map-file="+str(modulemap),"-Xcc","-I","-Xcc",str(include)]
    library = ROOT/"Application/.build-soxr/install/lib"
    executable = work/"prepare-gui-packages"
    command += [str(helper),*[str(p) for p in objects],"-L",str(library),"-lsoxr",
        "-Xlinker","-rpath","-Xlinker",str(library),"-o",str(executable)]
    controls = HERE/"overlap-controls-01"
    input_paths = sorted(set([Path(__file__),helper,DEBUG/"description.json",*maps,*objects,
        *[p for p in (DEBUG/"Modules").iterdir() if p.is_file()],
        *[p for p in library.iterdir() if p.is_file() or p.is_symlink()],
        *[p for p in controls.iterdir() if p.is_file()]]))
    inputs = [c.record(p) for p in input_paths]
    input_record = write(HERE/(label+"-inputs.json"),dict(created_utc=datetime.now(timezone.utc).isoformat(),
        scope="Frozen own-application objects linked into a separate helper; no shared rebuild or target execution.",
        capture=capture,files=inputs,compile_command=command,object_count=len(objects),
        compiler_version=subprocess.check_output([compiler,"--version"],text=True)))

    def unchanged():
        assert [c.record(p) for p in input_paths] == inputs, "Helper inputs changed"
        assert check_capture() == capture, "Frozen capture changed"

    compile_result = run(label+"-compile",command)
    unchanged()
    write(HERE/(label+"-compile-integrity.json"),dict(inputs=input_record,
        source_and_compiled_inputs_unchanged=True,capture=capture,exit_code=compile_result["exit_code"]))
    assert compile_result["exit_code"] == 0, "Helper compile failed; preserved attempt"
    helper_record = c.record(executable)
    result = run(label+"-run",[str(executable),str(ROOT)])
    unchanged(); assert c.record(executable) == helper_record
    write(HERE/(label+"-run-integrity.json"),dict(inputs=input_record,helper=helper_record,
        source_and_compiled_inputs_unchanged=True,capture=capture,exit_code=result["exit_code"]))
    assert result["exit_code"] == 0, "Helper run failed; preserve partial packages and attempt"
    observed = load(HERE/(label+"-run.log"))
    assert len(observed["packages"]) == 4 and observed["target_executed"] is False
    assert observed["gui_import_observed"] is False and observed["transport_started"] is False
    assert [row["package"] for row in observed["packages"]] == [p.name for p in packages]
    files = []
    for package, row in zip(packages,observed["packages"]):
        actual = [c.record(p) for p in c.entries(package)]
        assert actual == row["files"] and len(actual) == 5
        files += actual
    baseline = write(HERE/"gui-inputs.json",dict(basis="Saved synthetic packages prepared through frozen compiled public APIs. No GUI import is claimed. Subsequent audition must not alter these files.",files=files))
    prepared = write(HERE/(label+"-preparation.json"),dict(status="prepared",inputs=input_record,
        compilation=c.record(HERE/(label+"-compile.json")),run=c.record(HERE/(label+"-run.json")),
        helper=helper_record,gui_inputs=baseline,source_and_compiled_inputs_unchanged=True,
        target_executed=False,gui_import_observed=False,native_validity_established=False,packages=observed["packages"]))
    print(json.dumps(prepared))


if __name__ == "__main__": main()
