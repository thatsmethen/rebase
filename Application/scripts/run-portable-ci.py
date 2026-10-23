#!/usr/bin/env python3
"""Run a bounded conformance lane and retain exit codes, logs, and JSON evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import stat
import subprocess
import struct
import sys
import time
import xml.etree.ElementTree as ET


def collect_test_results(xml_paths):
    if not xml_paths:
        raise RuntimeError("No test XML report was emitted")
    sources = []
    for path in xml_paths:
        cases = list(ET.parse(path).iter("testcase"))
        skipped = sum(case.find("skipped") is not None for case in cases)
        failures = sum(case.find("failure") is not None or case.find("error") is not None for case in cases)
        sources.append({"report": path.name, "count": len(cases), "executed": len(cases) - skipped,
                        "skipped": skipped, "failures": failures})
    result = {field: sum(source[field] for source in sources) for field in ("count", "executed", "skipped", "failures")}
    result["reports"] = sources
    if result["executed"] == 0 or result["failures"]:
        raise RuntimeError("Expected at least one executed passing test and no failures")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("c", "swift", "macos-app"))
    parser.add_argument("--configuration", choices=("Debug", "Release"), default="Debug")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--generator", default="Ninja")
    args = parser.parse_args()
    app = Path(__file__).resolve().parents[1]
    root = app.parent
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    build = out / "build"
    env = dict(os.environ)
    env.pop("REBASE_RESEARCH_ROOT", None)
    if args.kind == "swift":
        env["REBASE_PORTABLE_ONLY"] = "1"
    else:
        env.pop("REBASE_PORTABLE_ONLY", None)
    report = {
        "schema": "rebase.portable-ci.v1",
        "scope": "Authored portable component conformance; no desktop app parity or reference-runtime claim",
        "lane": args.kind, "configuration": args.configuration,
        "platform": platform.system(), "architecture": platform.machine(),
        "runner_image": {key: os.environ.get(key) for key in ("ImageOS", "ImageVersion")},
        "commit": os.environ.get("GITHUB_SHA"), "commands": [], "status": "failed",
    }
    resolved = app / "Package.resolved"
    original_resolution = resolved.read_bytes() if resolved.is_file() else None

    def clean(value):
        return value.replace(str(root), "<workspace>").replace(str(Path.home()), "<home>")

    def test_xml_paths():
        # SwiftPM uses a separate report for Swift Testing when XCTest is
        # enabled, even when this package has no XCTest cases. CLT-only runs
        # with XCTest disabled write the requested tests.xml directly.
        return [out / name for name in ("tests.xml", "tests-swift-testing.xml") if (out / name).is_file()]

    def sanitize_xml():
        for path in test_xml_paths():
            value = path.read_text(encoding="utf-8")
            value = value.replace(str(root), "&lt;workspace&gt;").replace(str(Path.home()), "&lt;home&gt;")
            path.write_text(value, encoding="utf-8")

    def run(command, name, cwd=app, expected_exit_codes=(0,)):
        start = time.monotonic()
        result = subprocess.run(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, errors="replace")
        output = clean(result.stdout)
        (out / f"{name}.log").write_text(output, encoding="utf-8")
        print(output, end="", flush=True)
        report["commands"].append({"name": name, "argv": [clean(str(x)) for x in command],
                                   "exit_code": result.returncode,
                                   "elapsed_seconds": round(time.monotonic() - start, 3),
                                   "log": f"{name}.log"})
        if result.returncode not in expected_exit_codes:
            raise RuntimeError(f"{name} exited with status {result.returncode}")
        return output

    try:
        run(["cmake", "--version"], "cmake-version")
        if args.kind == "c":
            run([sys.executable, str(app / "Tests/PortableDSP/generate_controls.py"), "--check"], "oracle-fixtures")
            run(["clang", "--version"], "compiler-version")
            run(["cmake", "-S", str(app), "-B", str(build), "-G", args.generator,
                 f"-DCMAKE_BUILD_TYPE={args.configuration}", "-DCMAKE_C_COMPILER=clang",
                 "-DREBASE_BUILD_SOXR=OFF"], "configure")
            run(["cmake", "--build", str(build), "--parallel", "2"], "build")
            run(["ctest", "--test-dir", str(build), "--output-on-failure",
                 "--output-junit", str(out / "tests.xml")], "ctest")
            executable = build / ("rebase_portable_dsp_tests.exe" if os.name == "nt" else "rebase_portable_dsp_tests")
            run([str(executable), "--json", str(out / "kernel-conformance.json")], "kernel-conformance")
            json.loads((out / "kernel-conformance.json").read_text())
        else:
            run(["swift", "--version"], "swift-version")
            if args.kind == "swift":
                command = ["swift", "test", "--scratch-path", str(build), "-c", args.configuration.lower(),
                           "--filter", "RebasePortableTests", "--xunit-output", str(out / "tests.xml")]
                if os.name == "nt" and args.configuration == "Release":
                    # Diagnostic hypothesis for the observed zero-test Release
                    # runner: retain discovery metadata without disabling -O.
                    # Production product builds below keep their normal link.
                    command += ["--disable-dead-strip"]
                    report["test_link_dead_strip_disabled"] = True
                if sys.platform == "darwin":
                    developer = run(["xcode-select", "-p"], "developer-directory").strip()
                    # Match test-app.sh only for a local Command Line Tools
                    # installation. Full-Xcode CI uses its ordinary toolchain.
                    if developer.endswith("/CommandLineTools"):
                        frameworks = developer + "/Library/Developer/Frameworks"
                        command += ["--disable-xctest", "--enable-swift-testing",
                                    "-Xswiftc", "-F", "-Xswiftc", frameworks,
                                    "-Xswiftc", "-Xfrontend", "-Xswiftc", "-disable-cross-import-overlays",
                                    "-Xswiftc", "-plugin-path", "-Xswiftc",
                                    developer + "/usr/lib/swift/host/plugins/testing",
                                    "-Xlinker", "-rpath", "-Xlinker", frameworks]
                        report["command_line_tools_testing_support"] = True
            else:
                if sys.platform != "darwin":
                    raise RuntimeError("The macos-app lane requires macOS")
                command = ["sh", "Tests/run-tests.sh", "--public", "-c", args.configuration.lower(),
                           "--xunit-output", str(out / "tests.xml")]
            run(command, "tests")
            if args.kind == "swift" and os.name == "nt" and args.configuration == "Release":
                run(["swift", "test", "list", "--scratch-path", str(build), "-c", "release",
                     "--skip-build", "--disable-dead-strip"], "test-discovery")
            if args.kind == "swift":
                configuration = args.configuration.lower()
                run(["swift", "build", "--scratch-path", str(build), "-c", configuration,
                     "--product", "rebase-inspect"], "inspector-build")
                bin_path = run(["swift", "build", "--scratch-path", str(build), "-c", configuration,
                                "--show-bin-path"], "inspector-path").strip().splitlines()[-1]
                # The command-output sanitizer is for retained evidence only;
                # reconstruct the actual path before executing our own CLI.
                bin_path = bin_path.replace("<workspace>", str(root)).replace("<home>", str(Path.home()))
                executable = Path(bin_path) / ("rebase-inspect.exe" if os.name == "nt" else "rebase-inspect")
                wav_path = out / "example-render.wav"
                if wav_path.exists() or wav_path.is_symlink():
                    raise RuntimeError("Use a fresh evidence directory for the example render")
                cli = json.loads(run([str(executable), "render", str(app / "Examples/Rebase Preview.rebaseproj"),
                                      str(wav_path)], "example-render"))
                if not stat.S_ISREG(wav_path.lstat().st_mode) or wav_path.is_symlink():
                    raise RuntimeError("Rendered WAV must be a regular file, not a symbolic link")
                wav = wav_path.read_bytes()
                run([str(executable), "render", str(app / "Examples/Rebase Preview.rebaseproj"),
                     str(wav_path)], "example-overwrite-refusal", expected_exit_codes=(1,))
                if (not stat.S_ISREG(wav_path.lstat().st_mode) or wav_path.is_symlink()
                        or wav_path.read_bytes() != wav):
                    raise RuntimeError("Refused repeat render must preserve the existing regular WAV byte for byte")
                if wav[:4] != b"RIFF" or wav[8:12] != b"WAVE" or struct.unpack_from("<I", wav, 4)[0] + 8 != len(wav):
                    raise RuntimeError("Rendered WAV has an invalid RIFF envelope")
                chunks = {}
                offset = 12
                while offset + 8 <= len(wav):
                    identifier, size = struct.unpack_from("<4sI", wav, offset)
                    start = offset + 8
                    if start + size > len(wav) or identifier in chunks:
                        raise RuntimeError("Rendered WAV has an invalid or duplicate chunk")
                    chunks[identifier] = wav[start:start+size]
                    offset = start + size + size % 2
                if offset != len(wav) or b"fmt " not in chunks or b"data" not in chunks:
                    raise RuntimeError("Rendered WAV is missing complete format or data chunks")
                format_tag, channels, sample_rate, _, block_align, bits = struct.unpack_from("<HHIIHH", chunks[b"fmt "])
                if format_tag != 3 or channels != 2 or sample_rate != 48000 or block_align != 8 or bits != 32:
                    raise RuntimeError("Expected stereo 48 kHz float32 WAV output")
                pcm = chunks[b"data"]
                if len(pcm) % block_align or len(pcm) // block_align != 960000:
                    raise RuntimeError("Expected a complete 20-second example render")
                render = {"schema": "rebase.portable-render.v1", "scope": "Authored example PCM conformance",
                          "platform": platform.system(), "architecture": platform.machine(),
                          "configuration": args.configuration, "commit": os.environ.get("GITHUB_SHA"),
                          "frames": len(pcm) // block_align, "channels": channels, "sample_rate": sample_rate,
                          "bits_per_sample": bits, "pcm_sha256": hashlib.sha256(pcm).hexdigest(),
                          "wav_sha256": hashlib.sha256(wav).hexdigest(), "wav_bytes": len(wav), "cli": cli,
                          "regular_file": True, "repeat_render_refused_without_modification": True}
                lock_path = app / "scripts/example-render-lock.json"
                lock = json.loads(lock_path.read_text())
                differences = [key for key in ("frames", "channels", "sample_rate", "bits_per_sample", "pcm_sha256", "wav_sha256")
                               if render[key] != lock[key]]
                render["expected_render_lock_sha256"] = hashlib.sha256(lock_path.read_bytes()).hexdigest()
                render["matches_predeclared_lock"] = not differences
                render["mismatched_fields"] = differences
                (out / "example-render.json").write_text(json.dumps(render, indent=2) + "\n", encoding="utf-8")
                if differences:
                    raise RuntimeError("Rendered example differs from its predeclared lock: " + ", ".join(differences))
                run(["swift", "build", "--scratch-path", str(build), "-c", configuration,
                     "--product", "rebase-session"], "session-build")
                session = Path(bin_path) / ("rebase-session.exe" if os.name == "nt" else "rebase-session")
                run([sys.executable, str(app / "scripts/check-session-protocol.py"),
                     "--helper", str(session), "--example", str(app / "Examples/Rebase Preview.rebaseproj"),
                     "--report", str(out / "session-protocol.json")], "session-protocol")
                session_result = json.loads((out / "session-protocol.json").read_text())
                if session_result.get("status") != "passed":
                    raise RuntimeError("Interactive session protocol checks did not pass")
                report["interactive_session_checks"] = len(session_result["checks"])
        sanitize_xml()
        report["tests"] = collect_test_results(test_xml_paths())
        report["status"] = "passed"
    except Exception as error:
        report["error"] = clean(str(error))
        print(report["error"], file=sys.stderr)
    finally:
        sanitize_xml()
        if args.kind == "swift" and original_resolution is not None:
            resolved.write_bytes(original_resolution)
            report["application_dependency_lock_preserved"] = True
        (out / "conformance.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
