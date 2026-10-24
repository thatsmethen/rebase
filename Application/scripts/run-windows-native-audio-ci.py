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

from windows_soxr_package import validate_soxr_build


def validate_test_xml(path):
    cases = list(ET.parse(path).iter("testcase"))
    skipped = sum(case.find("skipped") is not None for case in cases)
    failures = sum(case.find("failure") is not None or case.find("error") is not None for case in cases)
    if not cases or skipped or failures:
        raise ValueError("Expected executed native portable tests with no skips or failures")
    if len(cases) != 2 or {case.get("name") for case in cases} != {
            "native_audio_portable_lifecycle", "native_audio_rate_conversion"}:
        raise ValueError("Expected the portable lifecycle and rate-conversion CTest cases")
    return {"count": len(cases), "skipped": skipped, "failures": failures}


def validate_rate_controls(record):
    if (type(record.get("schema")) is not int or record["schema"] != 1
            or record.get("suite") != "native-audio-rate-conversion"
            or type(record.get("checks")) is not int or record["checks"] <= 0
            or type(record.get("failures")) is not int or record["failures"] != 0
            or any(record.get(key) is not False for key in (
                "wasapi_compiled", "playback_tested", "audible_output_measured"))
            or record.get("soxr_version") != "libsoxr-0.1.3"):
        raise ValueError("Missing executed portable device-rate controls")
    profile = record.get("profile", {})
    if (type(profile.get("recipe")) is not int or profile["recipe"] != 6
            or type(profile.get("channels")) is not int or profile["channels"] != 2
            or type(profile.get("runtime_threads")) is not int or profile["runtime_threads"] != 1
            or profile.get("linear_phase") is not True or profile.get("implicit_os_conversion") is not False):
        raise ValueError("Device conversion profile is missing or changed")
    expected = {"identity-bits", "44100-to-48000", "48000-to-44100", "8000-to-192000",
                "192000-to-8000", "short-empty-downsample", "fractional-frame-count", "seek-phase-preserved",
                "pause-reset-drain", "allocation-failure", "converter-failure", "capacity-rejection",
                "environment-rejection", "zero-isolation-tail-drain"}
    cases = record.get("cases")
    if (not isinstance(cases, list) or len(cases) != len(expected)
            or any(not isinstance(case, dict) for case in cases)
            or {case.get("name") for case in cases} != expected
            or any(type(case.get("failures")) is not int or case["failures"] != 0 for case in cases)):
        raise ValueError("Required device conversion cases did not all pass")
    for case in cases:
        if any(type(case.get(key)) is not int or case[key] < 0 for key in (
                "source_rate", "endpoint_rate", "source_frames", "endpoint_frames")):
            raise ValueError("Invalid device conversion case measurements")
        if (not 8000 <= case["source_rate"] <= 192000 or not 8000 <= case["endpoint_rate"] <= 192000
                or not 0 < case["source_frames"] <= 32_000_000 or case["endpoint_frames"] > 32_000_000):
            raise ValueError("Device conversion case is outside the declared domain")
    indexed = {case["name"]: case for case in cases}
    for name, rates in {"44100-to-48000": (44100, 48000), "48000-to-44100": (48000, 44100),
                        "8000-to-192000": (8000, 192000), "192000-to-8000": (192000, 8000),
                        "fractional-frame-count": (44100, 48000)}.items():
        case = indexed[name]
        if (case["source_rate"], case["endpoint_rate"]) != rates or case["endpoint_frames"] != (
                case["source_frames"] * rates[1] + rates[0] // 2) // rates[0]:
            raise ValueError("Device conversion count/rate case disagrees with its declared input")
    identity = indexed["identity-bits"]
    if (identity["source_rate"] != identity["endpoint_rate"]
            or identity["source_frames"] != identity["endpoint_frames"]):
        raise ValueError("Identity control changed the sample clock or frame count")
    if any(indexed[name]["endpoint_frames"] != 0 for name in (
            "short-empty-downsample", "allocation-failure", "converter-failure", "capacity-rejection",
            "environment-rejection")):
        raise ValueError("A rejected conversion reported committed output")
    return record


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
                        help="Validate lifecycle and device-rate controls locally; no WASAPI build or endpoint probe")
    parser.add_argument("--soxr-library", type=Path,
                        help="Explicit public SoXR library for local portable controls; Windows builds its pinned source")
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
        "scope": "Authored adapter compilation, lifecycle and device-rate controls; endpoint discovery does not establish playback",
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
            if args.soxr_library is None or not args.soxr_library.is_file():
                raise RuntimeError("Local portable controls require an explicit public --soxr-library")
        elif os.name != "nt" or platform.machine().lower() not in ("amd64", "x86_64"):
            raise RuntimeError("This lane requires native Windows x64; local portable mode must be explicit")
        elif args.soxr_library is not None:
            raise RuntimeError("Windows must build and validate the pinned SoXR source")
        if build.exists() or xml_path.exists() or (out / "endpoint-probe.json").exists():
            raise RuntimeError("Use a fresh evidence directory")
        compiler = "clang++" if args.portable_lifecycle_only else "clang-cl"
        run([compiler, "--version"], "compiler-version", timeout=30)
        run(["cmake", "--version"], "cmake-version", timeout=30)
        if args.portable_lifecycle_only:
            library = args.soxr_library.resolve()
            report["soxr"] = {"scope": "Explicit local library; not a Windows binary qualification",
                              "library": clean(str(library)), "sha256": hashlib.sha256(library.read_bytes()).hexdigest()}
        else:
            soxr_out = out / "soxr"
            run([sys.executable, str(app / "scripts/build-windows-soxr.py"), "--output", str(soxr_out)],
                "build-pinned-soxr")
            report["soxr"] = validate_soxr_build(app, soxr_out, os.environ.get("GITHUB_SHA"))
            library = soxr_out / "install/lib/soxr.lib"
        configure = ["cmake", "-S", str(app / "Windows/NativeAudio"), "-B", str(build),
                     "-G", args.generator, f"-DCMAKE_BUILD_TYPE={args.configuration}",
                     "-DCMAKE_CXX_COMPILER=" + compiler, "-DBUILD_TESTING=ON",
                     "-DREBASE_RUN_AUDIO_DEVICE_TESTS=OFF", "-DREBASE_SOXR_LIBRARY=" + str(library)]
        if not args.portable_lifecycle_only:
            configure.append("-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded$<$<CONFIG:Debug>:Debug>DLL")
            configure.append("-DREBASE_SOXR_RUNTIME=" + str(soxr_out / "install/bin/soxr.dll"))
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
        run([str(build / ("rebase_audio_conversion_tests" + suffix)), "--json", str(out / "rate-conversion.json")],
            "rate-conversion-controls", timeout=60)
        rate_controls = json.loads((out / "rate-conversion.json").read_text(encoding="utf-8"))
        write_record(out / "rate-conversion.json", rate_controls)
        report["portable_rate_conversion"] = validate_rate_controls(rate_controls)
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
            for name in ("lifecycle.json", "rate-conversion.json", "endpoint-probe.json"):
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
