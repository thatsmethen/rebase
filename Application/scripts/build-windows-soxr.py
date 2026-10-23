#!/usr/bin/env python3
"""Build pinned public SoXR on Windows x64 and execute a bounded DLL probe."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    app = Path(__file__).resolve().parents[1]
    source = app / "ThirdParty/soxr-0.1.3"
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    build, install = out / "build", out / "install"
    report = {"schema": "rebase.windows-soxr.v1", "status": "failed",
              "scope": "Independent public-source SoXR build; native reference equivalence unknown",
              "source_version": "0.1.3", "platform": platform.system(),
              "architecture": platform.machine(), "commit": os.environ.get("GITHUB_SHA"), "commands": []}

    def clean(value):
        return value.replace(str(app.parent), "<workspace>").replace(str(Path.home()), "<home>")

    def run(command, name):
        result = subprocess.run(command, cwd=app, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, errors="replace")
        output = clean(result.stdout)
        (out / f"{name}.log").write_text(output, encoding="utf-8")
        print(output, end="", flush=True)
        report["commands"].append({"name": name, "exit_code": result.returncode, "log": f"{name}.log"})
        if result.returncode:
            raise RuntimeError(f"{name} exited with status {result.returncode}")
        return output

    try:
        if os.name != "nt" or platform.machine().lower() not in ("amd64", "x86_64"):
            raise RuntimeError("This lane requires a native Windows x64 runner")
        manifest_path = app / "ThirdParty/soxr-source-manifest.json"
        manifest = json.loads(manifest_path.read_text())
        expected = {row["path"] for row in manifest["files"]}
        actual = {p.relative_to(source).as_posix() for p in source.rglob("*") if p.is_file() or p.is_symlink()}
        if actual != expected:
            raise RuntimeError("Pinned SoXR source entry set differs")
        for row in manifest["files"]:
            path = source / row["path"]
            if "symlink" in row:
                # Git for Windows can represent tracked symlinks as their exact
                # link-text blob. This wrapper is not part of compiled source.
                valid = ((path.is_symlink() and os.readlink(path) == row["symlink"])
                         or (path.is_file() and not path.is_symlink()
                             and path.read_bytes() == row["symlink"].encode("utf-8")))
            else:
                valid = path.is_file() and not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
            if not valid:
                raise RuntimeError("Pinned SoXR source mismatch: " + row["path"])
        report["source_manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        report["source_entries_verified"] = len(expected)
        report["symlink_policy"] = "Actual symlink or exact Git link-text blob; compiled source bytes remain exact"
        run(["clang", "--version"], "compiler-version")
        run(["cmake", "--version"], "cmake-version")
        options = {"BUILD_SHARED_LIBS": "ON", "BUILD_TESTS": "OFF", "BUILD_EXAMPLES": "OFF",
                   "WITH_OPENMP": "OFF", "WITH_LSR_BINDINGS": "OFF", "BUILD_LSR_TESTS": "OFF",
                   "WITH_CR32": "ON", "WITH_CR64": "ON", "WITH_CR32S": "OFF", "WITH_CR64S": "OFF",
                   "WITH_VR32": "OFF", "WITH_PFFFT": "OFF", "WITH_AVFFT": "OFF",
                   "WITH_HI_PREC_CLOCK": "ON", "WITH_FLOAT_STD_PREC_CLOCK": "OFF",
                   "WITH_DEV_TRACE": "OFF", "WITH_DEV_GPROF": "OFF"}
        report["options"] = options
        report["optimization"] = "-O3 -DNDEBUG; fast math disabled; FP contraction disabled"
        report["msvc_runtime"] = "MultiThreadedDLL (CMP0091 NEW)"
        report["windows_exports"] = "SOXR_DLL explicitly enabled for clang's GNU frontend"
        # Upstream adds Unix linker '-s' to Release; select another configuration
        # with the exact application optimization flags, without patching source.
        command = ["cmake", "-S", str(source), "-B", str(build), "-G", "Ninja",
                   "-DCMAKE_C_COMPILER=clang", "-DCMAKE_BUILD_TYPE=RelWithDebInfo",
                   "-DCMAKE_POLICY_DEFAULT_CMP0091=NEW", "-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreadedDLL",
                   "-DCMAKE_C_FLAGS=-fno-fast-math -ffp-contract=off -DSOXR_DLL",
                   "-DCMAKE_C_FLAGS_RELWITHDEBINFO=-O3 -DNDEBUG",
                   f"-DCMAKE_INSTALL_PREFIX={install}", "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON"]
        command += [f"-D{key}={value}" for key, value in options.items()]
        run(command, "configure")
        configured = (build / "soxr-config.h").read_text()
        macros = {key: int(value) for key, value in re.findall(r"^#define ([A-Z0-9_]+) ([01])$", configured, re.MULTILINE)}
        feature_macros = ("WITH_CR32", "WITH_CR64", "WITH_CR32S", "WITH_CR64S", "WITH_VR32",
                          "WITH_PFFFT", "WITH_HI_PREC_CLOCK", "WITH_FLOAT_STD_PREC_CLOCK", "WITH_DEV_TRACE")
        required_macros = {key: 1 if options[key] == "ON" else 0 for key in feature_macros}
        required_macros.update({"AVCODEC_FOUND": 0, "AVUTIL_FOUND": 0, "HAVE_BIGENDIAN": 0})
        if any(macros.get(key) != value for key, value in required_macros.items()):
            raise RuntimeError("Configured SoXR features differ from the requested profile")
        compile_commands = json.loads((build / "compile_commands.json").read_text())
        if not compile_commands or any("-fno-fast-math" not in row["command"] or "-ffp-contract=off" not in row["command"] for row in compile_commands):
            raise RuntimeError("Strict floating-point flags missing from SoXR compilation")
        if any("--dependent-lib=msvcrt" not in row["command"] for row in compile_commands):
            raise RuntimeError("Dynamic MSVC runtime selection missing from SoXR compilation")
        if any("-DSOXR_DLL" not in row["command"] for row in compile_commands):
            raise RuntimeError("Windows DLL exports missing from SoXR compilation")
        report["configured_features"] = macros
        report["compile_command_count"] = len(compile_commands)
        run(["cmake", "--build", str(build), "--parallel", "2"], "build")
        run(["cmake", "--install", str(build)], "install")
        dll = install / "bin/soxr.dll"
        library = install / "lib/soxr.lib"
        if not dll.is_file() or not library.is_file():
            raise RuntimeError("Expected SoXR DLL and import library were not installed")
        probe = install / "bin/rebase-soxr-probe.exe"
        # clang-cl /MD selects both compiler and linker dynamic-CRT behavior.
        # The GNU frontend's -fms-runtime-lib=dll alone leaves a conflicting
        # static default library in this standalone executable link.
        run(["clang-cl", "/clang:-std=c11", "/O2", "/MD", "/clang:-fno-fast-math",
             "/clang:-ffp-contract=off", "/DSOXR_DLL", "/I" + str(install / "include"),
             str(app / "scripts/windows-soxr-probe.c"), str(library), "/Fe:" + str(probe)], "probe-build")
        probe_result = json.loads(run([str(probe)], "probe"))
        if probe_result.get("status") != "passed":
            raise RuntimeError("SoXR probe did not report success")
        (out / "soxr-conformance.json").write_text(json.dumps(probe_result, indent=2) + "\n", encoding="utf-8")
        report["artifacts"] = [{"path": p.relative_to(out).as_posix(), "bytes": p.stat().st_size,
                                "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in (dll, library, probe)]
        report["status"] = "passed"
    except Exception as error:
        report["error"] = clean(str(error))
        print(report["error"], file=sys.stderr)
    finally:
        (out / "conformance.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
