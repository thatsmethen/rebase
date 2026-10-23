#!/usr/bin/env python3
"""Build the authored WASAPI adapter and retain bounded, read-only CI evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import xml.etree.ElementTree as ET


def validate_test_xml(path):
    cases = list(ET.parse(path).iter("testcase"))
    skipped = sum(case.find("skipped") is not None for case in cases)
    failures = sum(case.find("failure") is not None or case.find("error") is not None for case in cases)
    if not cases or skipped == len(cases) or failures:
        raise ValueError("Expected executed lifecycle tests with no failures")
    if len(cases) != 1 or cases[0].get("name") != "native_audio_portable_lifecycle":
        raise ValueError("Expected only the portable lifecycle CTest case")
    return {"count": len(cases), "skipped": skipped, "failures": failures}


def validate_endpoint_probe(record, exit_code):
    if record.get("schema") != 1 or record.get("suite") != "windows-wasapi-native-probe":
        raise ValueError("Unexpected native endpoint probe schema")
    if record.get("wasapi_compiled") is not True:
        raise ValueError("Endpoint probe did not identify the compiled WASAPI adapter")
    for field in ("allow_audio", "playback_attempted", "playback_tested", "audible_output_measured"):
        if record.get(field) is not False:
            raise ValueError("CI must perform read-only endpoint discovery: " + field)
    expected = {0: ("endpoint-observed", 0), 77: ("unavailable-no-endpoint", 3)}
    if exit_code not in expected or (record.get("outcome"), record.get("result")) != expected[exit_code]:
        raise ValueError("Endpoint result and native exit code disagree")
    return "endpoint-observed" if exit_code == 0 else "unavailable-no-endpoint"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configuration", choices=("Debug", "Release"), default="Debug")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--generator", default="Ninja")
    parser.add_argument("--portable-lifecycle-only", action="store_true",
                        help="Validate the portable driver locally on a non-Windows host; no WASAPI build or endpoint probe")
    args = parser.parse_args()
    app = Path(__file__).resolve().parents[1]
    root = app.parent
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    build = out / "build"
    xml_path = out / "lifecycle.xml"
    env = dict(os.environ)
    env.pop("REBASE_RESEARCH_ROOT", None)
    report = {
        "schema": "rebase.windows-native-audio-ci.v1", "status": "failed",
        "scope": "Authored adapter compilation and portable lifecycle controls; endpoint discovery does not establish playback",
        "mode": "portable-lifecycle-only" if args.portable_lifecycle_only else "windows-native",
        "configuration": args.configuration, "platform": platform.system(), "architecture": platform.machine(),
        "commit": os.environ.get("GITHUB_SHA"),
        "runner_image": {key: os.environ.get(key) for key in ("ImageOS", "ImageVersion")},
        "commands": [], "native_library_built": False, "playback_tested": False,
        "audible_output_measured": False, "endpoint_probe": {"outcome": "not-run"},
    }
    replacements = []
    for value, label in ((str(root), "workspace"), (str(Path.home()), "home")):
        for variant in (value, value.replace("\\", "/"), value.replace("/", "\\")):
            replacements.append((variant, label))

    def clean(value, xml=False):
        for original, label in replacements:
            value = value.replace(original, "&lt;" + label + "&gt;" if xml else "<" + label + ">")
        return value

    def clean_record(value):
        if isinstance(value, str):
            return clean(value)
        if isinstance(value, dict):
            return {key: clean_record(item) for key, item in value.items()}
        if isinstance(value, list):
            return [clean_record(item) for item in value]
        return value

    def write_record(path, value):
        path.write_text(json.dumps(clean_record(value), indent=2) + "\n", encoding="utf-8")

    def sanitize_xml():
        if xml_path.is_file():
            xml_path.write_text(clean(xml_path.read_text(encoding="utf-8-sig"), xml=True), encoding="utf-8")

    def run(command, name, accepted=(0,), timeout=600):
        start = time.monotonic()
        row = {"name": name, "argv": [clean(str(value)) for value in command], "log": name + ".log"}
        report["commands"].append(row)
        try:
            result = subprocess.run(command, cwd=app, env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, errors="replace", timeout=timeout)
            output, code = result.stdout, result.returncode
        except subprocess.TimeoutExpired as error:
            output = error.stdout or ""
            if isinstance(output, bytes):
                output = output.decode("utf-8", errors="replace")
            code = None
            row["timed_out"] = True
        output = clean(output)
        (out / row["log"]).write_text(output, encoding="utf-8")
        print(output, end="", flush=True)
        row.update({"exit_code": code, "elapsed_seconds": round(time.monotonic() - start, 3)})
        if code not in accepted:
            raise RuntimeError(name + (" timed out" if code is None else f" exited with status {code}"))
        return code

    try:
        if args.portable_lifecycle_only:
            if os.name == "nt":
                raise RuntimeError("Use the full native lane on Windows")
        elif os.name != "nt" or platform.machine().lower() not in ("amd64", "x86_64"):
            raise RuntimeError("This lane requires native Windows x64; local portable mode must be explicit")
        if build.exists() or xml_path.exists() or (out / "endpoint-probe.json").exists():
            raise RuntimeError("Use a fresh evidence directory")
        compiler = "clang++" if args.portable_lifecycle_only else "clang-cl"
        run([compiler, "--version"], "compiler-version", timeout=30)
        run(["cmake", "--version"], "cmake-version", timeout=30)
        configure = ["cmake", "-S", str(app / "Windows/NativeAudio"), "-B", str(build),
                     "-G", args.generator, f"-DCMAKE_BUILD_TYPE={args.configuration}",
                     "-DCMAKE_CXX_COMPILER=" + compiler, "-DBUILD_TESTING=ON",
                     "-DREBASE_RUN_AUDIO_DEVICE_TESTS=OFF"]
        if not args.portable_lifecycle_only:
            configure.append("-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded$<$<CONFIG:Debug>:Debug>DLL")
        run(configure, "configure")
        run(["cmake", "--build", str(build), "--parallel", "2"], "build")
        run(["ctest", "--test-dir", str(build), "--output-on-failure", "--timeout", "30",
             "--output-junit", str(xml_path)], "lifecycle-ctest", timeout=60)
        sanitize_xml()
        report["tests"] = validate_test_xml(xml_path)
        suffix = ".exe" if os.name == "nt" else ""
        run([str(build / ("rebase_audio_lifecycle_tests" + suffix)), "--json", str(out / "lifecycle.json")],
            "lifecycle-controls", timeout=30)
        lifecycle = json.loads((out / "lifecycle.json").read_text(encoding="utf-8"))
        write_record(out / "lifecycle.json", lifecycle)
        if (lifecycle.get("suite") != "native-audio-portable-lifecycle" or
                type(lifecycle.get("checks")) is not int or lifecycle["checks"] <= 0 or
                lifecycle.get("failures") != 0 or lifecycle.get("playback_tested") is not False or
                lifecycle.get("wasapi_compiled") is not False):
            raise RuntimeError("Portable lifecycle control evidence is incomplete or failed")
        report["portable_lifecycle"] = lifecycle
        if args.portable_lifecycle_only:
            report["endpoint_probe"] = {"outcome": "not-run-non-windows-portable-mode"}
        else:
            files = [build / name for name in ("RebaseWindowsAudio.dll", "RebaseWindowsAudio.lib", "rebase_wasapi_probe.exe")]
            if not all(path.is_file() for path in files):
                raise RuntimeError("Expected native DLL, import library, and endpoint probe were not built")
            report["native_library_built"] = True
            report["build_products"] = [{"name": path.name, "bytes": path.stat().st_size,
                                         "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in files]
            report["endpoint_probe"] = {"outcome": "attempted", "playback_tested": False}
            code = run([str(build / "rebase_wasapi_probe.exe"), "--json", str(out / "endpoint-probe.json")],
                       "endpoint-probe", accepted=(0, 77), timeout=30)
            endpoint = json.loads((out / "endpoint-probe.json").read_text(encoding="utf-8"))
            write_record(out / "endpoint-probe.json", endpoint)
            outcome = validate_endpoint_probe(endpoint, code)
            report["endpoint_probe"] = {"outcome": outcome, "exit_code": code, "playback_tested": False}
        report["status"] = "passed"
    except Exception as error:
        if report["endpoint_probe"]["outcome"] == "attempted":
            report["endpoint_probe"] = {"outcome": "failed", "playback_tested": False,
                                        "exit_code": report["commands"][-1].get("exit_code")}
        report["error"] = clean(str(error))
        print(report["error"], file=sys.stderr)
    finally:
        try:
            sanitize_xml()
            for name in ("lifecycle.json", "endpoint-probe.json"):
                path = out / name
                if path.is_file():
                    write_record(path, json.loads(path.read_text(encoding="utf-8")))
        except Exception as error:
            report["status"] = "failed"
            report["artifact_sanitization_error"] = clean(str(error))
        write_record(out / "conformance.json", report)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
