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

from windows_automation_gate import require_automation_protocol
from portable_soxr import verify_windows, verify_macos, stage_windows_runtime
from cpr_audition_gate import require_cpr_audition
from source_stream_gate import require_receipt as require_source_stream


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
    parser.add_argument("--soxr-build", type=Path,
                        help="Reuse an explicitly validated pinned SoXR build; otherwise build it in this lane")
    args = parser.parse_args()
    app = Path(__file__).resolve().parents[1]
    root = app.parent
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    build = out / "build"
    env = dict(os.environ)
    env.pop("REBASE_RESEARCH_ROOT", None)
    env.pop("REBASE_SOXR_ALLOW_MODIFIED_SOURCE", None)
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
                run([sys.executable, str(app / "scripts/test_portable_soxr.py"),
                     "--output", str(out / "portable-soxr-controls")], "portable-soxr-controls")
                controls = json.loads((out / "portable-soxr-controls/observation.json").read_text())
                if (controls.get("status") != "passed" or controls.get("failures") != 0
                        or controls.get("errors") != 0 or type(controls.get("tests")) is not int
                        or controls["tests"] - controls.get("skipped", 0) <= 0):
                    raise RuntimeError("Portable SoXR dependency controls did not execute successfully")
                report["soxr_dependency_controls"] = controls
                dependency = args.soxr_build.resolve() if args.soxr_build else out / "soxr"
                if os.name == "nt":
                    if args.soxr_build is None:
                        run([sys.executable, str(app / "scripts/build-windows-soxr.py"),
                             "--output", str(dependency)], "soxr-build")
                    dependency_receipt, library_dir, runtime, runtime_digest = verify_windows(
                        app, dependency, env.get("GITHUB_SHA"))
                elif sys.platform == "darwin":
                    if args.soxr_build is None:
                        env["REBASE_SOXR_BUILD_DIR"] = str(dependency)
                        run(["sh", "ThirdParty/build-soxr.sh"], "soxr-build")
                    dependency_receipt, library_dir = verify_macos(app, dependency, env.get("GITHUB_SHA"))
                else:
                    raise RuntimeError("Portable SoXR CI currently qualifies Windows x64 and macOS arm64 only")
                env["REBASE_SOXR_LIBRARY_DIR"] = str(library_dir)
                report["cpr_mode2_dependency"] = dependency_receipt
                (out / "soxr-dependency.json").write_text(json.dumps(dependency_receipt, indent=2) + "\n", encoding="utf-8")
                if os.name == "nt":
                    # Test DLLs and runner executables share SwiftPM's actual
                    # product directory. Stage before swift test can launch it.
                    path_text = run(["swift", "build", "--scratch-path", str(build),
                                     "-c", args.configuration.lower(), "--show-bin-path"], "test-products-path")
                    product_directory = Path(path_text.strip().splitlines()[-1]
                        .replace("<workspace>", str(root)).replace("<home>", str(Path.home())))
                    report["cpr_mode2_runtime"] = stage_windows_runtime(runtime, product_directory, runtime_digest)
                command = ["swift", "test", "--scratch-path", str(build), "-c", args.configuration.lower(),
                           "--filter", "RebasePortableTests", "--xunit-output", str(out / "tests.xml")]
                if os.name == "nt" and args.configuration == "Release":
                    # Swift Build generates an empty public test-anchor call
                    # to load the test DLL. Prevent cross-module elimination
                    # of that call while retaining -O within every module.
                    # NOREF alone did not restore discovery. Production
                    # products below keep their normal compiler/link flags.
                    command += ["--disable-dead-strip", "-Xlinker", "/OPT:NOREF",
                                "-Xswiftc", "-disable-cmo", "--verbose"]
                    report["test_link_dead_strip_disabled"] = True
                    report["test_linker_options"] = ["/OPT:NOREF"]
                    report["test_compiler_options"] = ["-disable-cmo"]
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
                # Keep generated entrypoints and PE evidence even if discovery
                # is empty, without uploading build trees or test binaries.
                sources = []
                for name in ("test_anchor.swift", "test_entry_point.swift"):
                    for path in sorted(build.rglob(name)):
                        sources.append({"path": str(path.relative_to(build)),
                                        "source": clean(path.read_text(encoding="utf-8"))})
                (out / "test-generated-sources.json").write_text(
                    json.dumps(sources, indent=2) + "\n", encoding="utf-8")
                for name in ("RebasePortableTests.dll", "RebasePortableTests-test-runner.exe"):
                    paths = list(build.rglob(name))
                    if len(paths) != 1:
                        raise RuntimeError("Expected exactly one test product: " + name)
                    run(["dumpbin", "/headers", "/imports", str(paths[0])], "test-pe-" + name)
                run(["swift", "test", "list", "--scratch-path", str(build), "-c", "release",
                     "--skip-build", "--disable-dead-strip", "-Xlinker", "/OPT:NOREF",
                     "-Xswiftc", "-disable-cmo"], "test-discovery")
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
                fixture = app / "Tests/Fixtures/SourceAudition"
                source_lock = fixture / "expected.json"
                expected_source = json.loads(source_lock.read_text(encoding="utf-8"))
                run([sys.executable, str(app / "scripts/check-session-protocol.py"),
                     "--helper", str(session), "--example", str(app / "Examples/Rebase Preview.rebaseproj"),
                     "--report", str(out / "session-protocol.json"),
                     "--source-project", str(fixture / "AuthoredSource.rebaseproj"),
                     "--source-media", str(fixture / "SelectedSource.wav"),
                     "--source-lock", str(source_lock)], "session-protocol")
                session_result = json.loads((out / "session-protocol.json").read_text())
                if (session_result.get("status") != "passed" or session_result.get("source_journey_tested") is not True
                        or session_result.get("waveform", {}).get("clips_checked") != 11
                        or session_result.get("source", {}).get("playback_tested") is not False
                        or session_result.get("ruler", {}).get("read_only") is not True
                        or session_result.get("ruler", {}).get("stale_revision_rejected") is not True
                        or session_result.get("ruler", {}).get("first_bar_seconds") != [0, 2.5, 5, 7.5]
                        or session_result.get("ruler", {}).get("first_quarter_seconds") != [0, 0.625, 1.25, 1.875, 2.5]
                        or any(session_result.get("source", {}).get(key) != expected_source[key]
                               for key in ("sourceSHA256", "mediaSHA256", "outputSHA256", "pcmSHA256", "frames", "sampleRate", "channels"))):
                    raise RuntimeError("Interactive session protocol checks did not pass")
                report["interactive_session_checks"] = len(session_result["checks"])
                report["source_journey_tested"] = True
                report["source_control"] = {**session_result["source"],
                                            "expected_lock_sha256": hashlib.sha256(source_lock.read_bytes()).hexdigest()}
                report["waveform_control"] = session_result["waveform"]
                report["ruler_control"] = session_result["ruler"]
                imported = session_result.get("cpr_import", {})
                required_import_controls = (
                    "tested", "review_read_only", "review_bounded", "cancellation_preserves_state",
                    "superseded_review_rejected", "stale_revision_rejected", "changed_source_rejected",
                    "explicit_partial_required", "dirty_replacement_guarded", "existing_destination_preserved",
                    "import_published", "exact_source_and_report_preserved", "save_reopen_preserves_baseline",
                    "historical_read_only", "tampered_report_rejected", "tampered_source_rejected")
                if (any(imported.get(key) is not True for key in required_import_controls)
                        or imported.get("sourceSHA256") != expected_source["sourceSHA256"]
                        or imported.get("reportSHA256") != expected_source["reportSHA256"]):
                    raise RuntimeError("Reviewed CPR import protocol checks did not pass")
                report["cpr_import_control"] = imported
                require_automation_protocol(session_result,
                    json.loads((app / "Examples/Rebase Preview.rebaseproj/Project.json").read_text(encoding="utf-8")), lock)
                report["automation_control"] = session_result["automation"]
                modes_fixture = app / "Tests/Fixtures/SourceAuditionModes"
                modes_lock = modes_fixture / "expected.json"
                modes_result_path = out / "cpr-audition-modes.json"
                run([sys.executable, str(app / "scripts/check-cpr-audition-modes.py"),
                     "--helper", str(session), "--fixtures", str(modes_fixture),
                     "--report", str(modes_result_path)], "cpr-audition-modes")
                report["cpr_audition_control"] = require_cpr_audition(
                    json.loads(modes_result_path.read_text()), json.loads(modes_lock.read_text()),
                    hashlib.sha256(modes_lock.read_bytes()).hexdigest(),
                    hashlib.sha256(session.read_bytes()).hexdigest())
                report["cpr_audition_control"]["receipt_sha256"] = hashlib.sha256(modes_result_path.read_bytes()).hexdigest()
                run([sys.executable, str(app / "scripts/test_cpr_audition_gate.py"),
                     "--receipt", str(modes_result_path), "--fixture", str(modes_lock),
                     "--output", str(out / "cpr-audition-gate-controls")], "cpr-audition-gate-controls")
                mode_controls = json.loads((out / "cpr-audition-gate-controls/observation.json").read_text())
                if (mode_controls.get("status") != "passed" or mode_controls.get("failures") != 0
                        or mode_controls.get("errors") != 0 or type(mode_controls.get("tests")) is not int
                        or mode_controls["tests"] <= 0 or mode_controls.get("skipped") != 0):
                    raise RuntimeError("CPR audition receipt rejection controls did not execute successfully")
                report["cpr_audition_gate_controls"] = mode_controls
                long_fixture = app / "Tests/Fixtures/SourceStreamTimelines"
                stream_result_path = out / "source-stream.json"
                run([sys.executable, str(app / "scripts/check-source-stream.py"),
                     "--helper", str(session), "--fixtures", str(modes_fixture),
                     "--long-fixtures", str(long_fixture), "--report", str(stream_result_path)], "source-stream")
                report["source_stream_control"] = require_source_stream(
                    json.loads(stream_result_path.read_text()), json.loads(modes_lock.read_text()),
                    json.loads((long_fixture / "expected.json").read_text()),
                    hashlib.sha256(modes_lock.read_bytes()).hexdigest(),
                    hashlib.sha256((long_fixture / "expected.json").read_bytes()).hexdigest(),
                    hashlib.sha256(session.read_bytes()).hexdigest(), json.loads(modes_result_path.read_text()))
                report["source_stream_control"]["receipt_sha256"] = hashlib.sha256(stream_result_path.read_bytes()).hexdigest()
                run([sys.executable, "-m", "unittest", "discover", "-s", str(app / "scripts"),
                     "-p", "test_source_stream_gate.py"], "source-stream-gate-controls")
                run([sys.executable, str(app / "scripts/test_source_stream_receipt.py"),
                     "--receipt", str(stream_result_path), "--short-fixture", str(modes_lock),
                     "--long-fixture", str(long_fixture / "expected.json"), "--snapshot-receipt", str(modes_result_path),
                     "--output", str(out / "source-stream-receipt-controls")], "source-stream-receipt-controls")
                stream_controls = json.loads((out / "source-stream-receipt-controls/observation.json").read_text())
                if (stream_controls.get("status") != "passed" or stream_controls.get("tests") != 36
                        or stream_controls.get("failures") != 0 or stream_controls.get("errors") != 0
                        or stream_controls.get("skipped") != 0):
                    raise RuntimeError("Source stream receipt rejection controls did not execute successfully")
                report["source_stream_gate_controls"] = stream_controls
                if os.name == "nt":
                    # Verify execution/build steps did not replace the DLL.
                    report["cpr_mode2_runtime"] = stage_windows_runtime(runtime, product_directory, runtime_digest)
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
