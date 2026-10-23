#!/usr/bin/env python3
"""Assemble and exercise an unsigned Windows development package on Windows x64."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys
import time
import urllib.request
import zipfile

SDK = "10.0.402"
DOTNET_RUNTIME = "10.0.13"
SWIFT = "6.4.1"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inside(path, root):
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def inspect_pe(path):
    import pefile
    with pefile.PE(str(path), fast_load=True) as pe:
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY[name] for name in
                                 ("IMAGE_DIRECTORY_ENTRY_IMPORT", "IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT")])
        clr = pe.OPTIONAL_HEADER.DATA_DIRECTORY[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_COM_DESCRIPTOR"]]
        flags = struct.unpack("<I", pe.get_data(clr.VirtualAddress + 16, 4))[0] if clr.VirtualAddress else 0
        if pe.FILE_HEADER.Machine != 0x8664 and not (pe.FILE_HEADER.Machine == 0x14c and flags & 1 and not flags & 2):
            raise RuntimeError("Package contains a non-x64 native image: " + path.name)
        imports = sorted({entry.dll.decode("ascii").lower() for kind in
                          ("DIRECTORY_ENTRY_IMPORT", "DIRECTORY_ENTRY_DELAY_IMPORT")
                          for entry in getattr(pe, kind, [])})
        if any(Path(name).name != name or ":" in name or "\\" in name for name in imports):
            raise RuntimeError("PE import contains a path")
        return imports


def runtime_index(directories):
    found = {}
    for directory in directories:
        for path in sorted(directory.rglob("*.dll")):
            key = path.name.lower()
            if key in found and digest(found[key]) != digest(path):
                raise RuntimeError("Ambiguous runtime dependency: " + path.name)
            found[key] = path
    return found


def assemble_dependencies(stage, swift_runtime, vc_runtime, system):
    # Only the pinned runtime component and VS redistributable CRT are sources.
    # Installed compiler tools and arbitrary PATH entries are never copied.
    swift = runtime_index([swift_runtime])
    vc = runtime_index(vc_runtime)
    sources = {**swift, **vc}
    copied, records = [], []
    for name, path in sources.items():
        # ICU loads data/components dynamically. Include its pinned runtime DLLs.
        if "icu" in name:
            shutil.copyfile(path, stage / path.name)
            copied.append({"name": path.name, "source": "swift-runtime-" + SWIFT})
    pending = sorted(p for p in stage.rglob("*") if p.suffix.lower() in (".dll", ".exe"))
    visited = set()
    while pending:
        path = pending.pop(0)
        key = str(path.relative_to(stage)).lower()
        if key in visited:
            continue
        visited.add(key)
        local = {p.name.lower(): p for p in stage.glob("*") if p.is_file()}
        imports = inspect_pe(path)
        resolved = []
        for name in imports:
            if name in local:
                origin = "application"
            elif name in sources:
                source = sources[name]
                target = stage / source.name
                shutil.copyfile(source, target)
                pending.append(target)
                origin = "visual-cpp-runtime" if name in vc else "swift-runtime-" + SWIFT
                copied.append({"name": source.name, "source": origin})
            elif name.startswith(("api-ms-", "ext-ms-")):
                origin = "windows-api-contract"
            elif name.startswith(("msvcp1", "msvcr1", "vcruntime", "concrt", "vcomp", "swift", "foundation", "dispatch")):
                raise RuntimeError("Required app-local runtime is missing: " + name)
            elif (system / name).is_file():
                origin = "windows-system"
            else:
                raise RuntimeError("Unresolved PE dependency: " + name + " from " + path.name)
            resolved.append({"name": name, "source": origin})
        records.append({"path": path.relative_to(stage).as_posix(), "imports": resolved})
    return {"copied": copied, "images": records}


def validate_modules(modules, stage, windows, required):
    if not isinstance(modules, list) or not modules:
        raise RuntimeError("Missing actual process module evidence")
    result = []
    names = set()
    for module in modules:
        path = Path(module["path"])
        if path.name.lower() != module["name"].lower() or not path.is_file():
            raise RuntimeError("Invalid process module evidence")
        if inside(path, stage):
            location = "application/" + path.resolve().relative_to(stage.resolve()).as_posix()
            names.add(path.name.lower())
        elif inside(path, windows):
            location = "windows/" + path.name
        else:
            raise RuntimeError("Process loaded a module outside the package and Windows: " + path.name)
        result.append({"name": path.name, "location": location, "sha256": digest(path)})
    if not set(required).issubset(names):
        raise RuntimeError("Required runtime was not observed loading from the application folder")
    return result


def copy_example(app, stage):
    manifest = json.loads((app / "Examples/example.json").read_text(encoding="utf-8"))
    target = stage / "Examples" / manifest["project"]
    for item in manifest["files"]:
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts or ":" in item["path"] or "\\" in item["path"]:
            raise RuntimeError("Invalid bundled example path")
        source = app / "Examples" / manifest["project"] / relative
        if source.is_symlink() or source.stat().st_size != item["bytes"] or digest(source) != item["sha256"]:
            raise RuntimeError("Authored example bytes do not match their manifest")
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    for name in ("README.md", "example.json"):
        shutil.copyfile(app / "Examples" / name, stage / "Examples" / name)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    app = Path(__file__).resolve().parents[1]
    root = app.parent
    out = args.output.resolve()
    if out.exists():
        raise SystemExit("Use a new output directory")
    evidence = out / "evidence"
    evidence.mkdir(parents=True)
    stage = out / "package/Rebase"
    stage.mkdir(parents=True)
    env = dict(os.environ)
    env.update(REBASE_PORTABLE_ONLY="1", DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1")
    env.pop("REBASE_RESEARCH_ROOT", None)
    resolved = app / "Package.resolved"
    original_resolved = resolved.read_bytes() if resolved.exists() else None
    report = {"schema": "rebase.windows-application-build.v1", "status": "failed",
              "commit": env.get("GITHUB_SHA"), "development_build": True, "signed": False,
              "playback_tested": False, "audible_output_measured": False, "commands": [],
              "toolchain": {"dotnet_sdk": SDK, "dotnet_runtime": DOTNET_RUNTIME, "swift": SWIFT},
              "runner_image": {key: os.environ.get(key) for key in ("ImageOS", "ImageVersion")}}
    replacements = []
    for path, label in ((root, "workspace"), (Path.home(), "home"), (out, "build-output")):
        for value in (str(path), str(path).replace("\\", "/"), str(path).replace("/", "\\")):
            replacements.append((value, "<" + label + ">"))

    def clean(value):
        if isinstance(value, str):
            for original, replacement in replacements:
                value = value.replace(original, replacement)
        elif isinstance(value, dict):
            value = {key: clean(item) for key, item in value.items()}
        elif isinstance(value, list):
            value = [clean(item) for item in value]
        return value

    def write(path, record):
        path.write_text(json.dumps(clean(record), indent=2) + "\n", encoding="utf-8")

    def run(command, name, custom_env=None, timeout=600, cwd=app):
        record = {"name": name, "argv": clean([str(item) for item in command])}
        report["commands"].append(record)
        started = time.monotonic()
        try:
            process = subprocess.run(command, cwd=cwd, env=custom_env or env, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, errors="replace", timeout=timeout)
            output, code = process.stdout, process.returncode
        except subprocess.TimeoutExpired as error:
            output, code = error.stdout or b"", None
            if isinstance(output, bytes):
                output = output.decode("utf-8", errors="replace")
        record.update(exit_code=code, elapsed_seconds=round(time.monotonic() - started, 3))
        (evidence / (name + ".log")).write_text(clean(output), encoding="utf-8")
        print(clean(output), end="", flush=True)
        if code != 0:
            raise RuntimeError(name + (" timed out" if code is None else " failed with exit " + str(code)))
        return output

    try:
        if os.name != "nt" or platform.machine().lower() not in ("amd64", "x86_64"):
            raise RuntimeError("Packaging requires actual Windows x64")
        if run(["dotnet", "--version"], "dotnet-version", timeout=30).strip() != SDK:
            raise RuntimeError("Unexpected .NET SDK")
        if "Swift version " + SWIFT not in run(["swift", "--version"], "swift-version", timeout=30):
            raise RuntimeError("Unexpected Swift toolchain")
        controls = run(["dotnet", "run", "--project", str(app / "Windows/RebaseWindows/Tests/RebaseWindows.Controls.csproj"),
                        "-c", "Release"], "host-controls")
        controls = json.loads(controls.strip().splitlines()[-1])
        if (controls.get("suite") != "windows-host-portable-controls" or controls.get("failures") != 0
                or type(controls.get("checks")) is not int or controls["checks"] <= 0):
            raise RuntimeError("Missing executed host controls")
        write(evidence / "host-controls.json", controls)
        run([sys.executable, str(app / "scripts/run-windows-native-audio-ci.py"), "--configuration", "Release",
             "--output", str(evidence / "native")], "native-audio-conformance")
        shutil.copyfile(evidence / "native/build/RebaseWindowsAudio.dll", stage / "RebaseWindowsAudio.dll")
        run(["dotnet", "publish", str(app / "Windows/RebaseWindows/RebaseWindows.csproj"), "-c", "Release",
             "-r", "win-x64", "--self-contained", "true", "-p:PublishTrimmed=false", "-p:PublishSingleFile=false",
             "-p:DebugType=None", "-p:DebugSymbols=false", "-p:ContinuousIntegrationBuild=true",
             "-p:PathMap=" + str(root) + "=/_/Rebase",
             "-p:RuntimeFrameworkVersion=" + DOTNET_RUNTIME, "-o", str(stage)], "publish-wpf")
        runtime_options = json.loads((stage / "Rebase.runtimeconfig.json").read_text(encoding="utf-8"))["runtimeOptions"]
        included = {item["name"]: item["version"] for item in runtime_options.get("includedFrameworks", [])}
        if (included.get("Microsoft.NETCore.App") != DOTNET_RUNTIME
                or included.get("Microsoft.WindowsDesktop.App") != DOTNET_RUNTIME):
            raise RuntimeError("Published desktop runtime is not the pinned self-contained version")
        scratch = out / "session-build"
        run(["swift", "build", "--scratch-path", str(scratch), "-c", "release", "--product", "rebase-session",
             "-Xswiftc", "-file-prefix-map", "-Xswiftc", str(root) + "=/_/Rebase",
             "-Xswiftc", "-debug-prefix-map", "-Xswiftc", str(root) + "=/_/Rebase",
             "-Xcc", "-ffile-prefix-map=" + str(root) + "=/_/Rebase"], "build-session")
        bin_path = Path(run(["swift", "build", "--scratch-path", str(scratch), "-c", "release", "--show-bin-path"],
                            "session-bin-path", timeout=60).strip().splitlines()[-1])
        shutil.copyfile(bin_path / "rebase-session.exe", stage / "rebase-session.exe")
        swiftc = Path(shutil.which("swiftc") or "missing").resolve()
        candidates = [parent / "Runtimes" / SWIFT / "usr/bin" for parent in swiftc.parents]
        candidates = [path for path in candidates if path.is_dir()]
        if len(candidates) != 1:
            raise RuntimeError("Cannot identify the pinned Swift runtime component")
        vc_root = Path(os.environ.get("VCToolsRedistDir", "missing"))
        vc_dirs = list((vc_root / "x64").glob("Microsoft.*.CRT"))
        if not vc_dirs:
            raise RuntimeError("Visual C++ x64 redistribution directory is unavailable")
        windows = Path(os.environ["SystemRoot"])
        closure = assemble_dependencies(stage, candidates[0], vc_dirs, windows / "System32")
        write(evidence / "pe-dependency-closure.json", closure)
        example = copy_example(app, stage)
        licenses = stage / "ThirdPartyNotices"
        licenses.mkdir()
        license_sources = json.loads((app / "scripts/windows-runtime-license-sources.json").read_text(encoding="utf-8"))
        for source in license_sources:
            with urllib.request.urlopen(source["url"], timeout=60) as response:
                content = response.read(2_000_001)
            if hashlib.sha256(content).hexdigest() != source["sha256"]:
                raise RuntimeError("Pinned runtime notice changed: " + source["name"])
            (licenses / source["name"]).write_bytes(content)
        write(licenses / "sources.json", license_sources)
        (licenses / "Visual-Cpp-Runtime.txt").write_text(
            "The package includes Microsoft Visual C++ runtime DLLs from the x64 redistributable component.\n"
            "Microsoft runtime terms: https://visualstudio.microsoft.com/license-terms/\n", encoding="utf-8")
        (stage / "README.txt").write_text(
            "Rebase for Windows — unsigned development build\n\n"
            "Extract this entire folder before running Rebase.exe. Keep the DLLs and helper beside it.\n"
            "The authored example opens as a separate editable copy. Its audio permission is in Examples/README.md.\n"
            "This preview supports a bounded set of shared project editing and rendering workflows.\n"
            "Recording, plugins, native CPR playback and general device-rate adaptation are not integrated.\n"
            "CI window checks do not establish audio-device playback or complete application parity.\n"
            "Source and development notes: https://github.com/thatsmethen/rebase"
            "\n", encoding="utf-8")
        if any(stage.rglob("*.pdb")):
            raise RuntimeError("Development package must not include PDB/debug path records")
        # Exclude the installed Swift/.NET/VS search paths while testing these exact files.
        restricted = dict(env)
        for key in list(restricted):
            if key.upper().startswith(("SWIFT", "DOTNET_ROOT", "COREHOST", "COMPLUS_", "_NT_")):
                del restricted[key]
        restricted.update(PATH=os.pathsep.join((str(stage), str(windows / "System32"), str(windows))),
                          DOTNET_MULTILEVEL_LOOKUP="0")
        run([sys.executable, str(app / "scripts/check-session-protocol.py"), "--helper", str(stage / "rebase-session.exe"),
             "--example", str(example), "--report", str(evidence / "packaged-session-protocol.json")],
            "packaged-session-protocol", restricted, timeout=600, cwd=stage)
        session = json.loads((evidence / "packaged-session-protocol.json").read_text(encoding="utf-8"))
        if session.get("status") != "passed":
            raise RuntimeError("Packaged session protocol did not pass")
        smoke_path = evidence / "wpf-smoke.json"
        run([str(stage / "Rebase.exe"), "--smoke", "--smoke-json", str(smoke_path)],
            "packaged-window-smoke", restricted, timeout=180, cwd=stage)
        smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
        if (smoke.get("suite") != "windows-wpf-shared-session-smoke" or smoke.get("outcome") != "passed"
                or smoke.get("stage") != "completed" or smoke.get("playback_tested") is not False
                or smoke.get("audible_output_measured") is not False or not smoke.get("checks")):
            raise RuntimeError("Window smoke receipt is incomplete")
        modules = {"process": validate_modules(smoke.pop("process_modules", None), stage, windows,
                                               {"rebase.exe", "coreclr.dll", "rebasewindowsaudio.dll"}),
                   "helper": validate_modules(smoke.pop("helper_modules", None), stage, windows,
                                              {"rebase-session.exe", "swiftcore.dll"})}
        write(evidence / "loaded-modules.json", modules)
        write(smoke_path, smoke)
        png = evidence / "native-app-visual.png"
        if png.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n" or png.stat().st_size < 1024:
            raise RuntimeError("Missing WPF window visual")
        # Recheck all bundled source bytes after both complete user journeys.
        example_manifest = json.loads((stage / "Examples/example.json").read_text(encoding="utf-8"))
        if any(digest(example / item["path"]) != item["sha256"] for item in example_manifest["files"]):
            raise RuntimeError("A package check changed the bundled example")
        # Keep this mandatory gate after window diagnostics, before any downloadable ZIP.
        # An application smoke pass cannot turn a failed/empty Release suite into success.
        run([sys.executable, str(app / "scripts/run-portable-ci.py"), "swift", "--configuration", "Release",
             "--output", str(evidence / "shared")], "shared-release-conformance", timeout=900)
        files = [{"path": path.relative_to(stage).as_posix(), "bytes": path.stat().st_size, "sha256": digest(path)}
                 for path in sorted(stage.rglob("*")) if path.is_file()]
        if any(path.is_symlink() for path in stage.rglob("*")):
            raise RuntimeError("Package contains a symbolic link")
        write(stage / "package-manifest.json", {"schema": "rebase.windows-package.v1", "commit": env.get("GITHUB_SHA"),
                                               "toolchain": report["toolchain"], "files": files})
        download = out / "download"
        download.mkdir()
        revision = env.get("GITHUB_SHA", "local")[:12]
        archive = download / ("Rebase-Windows-x64-development-" + revision + ".zip")
        with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
            for path in sorted(stage.rglob("*")):
                if path.is_file():
                    bundle.write(path, "Rebase/" + path.relative_to(stage).as_posix())
        with zipfile.ZipFile(archive) as bundle:
            if bundle.testzip() is not None:
                raise RuntimeError("Archive CRC verification failed")
        report.update(status="passed", package={"name": archive.name, "bytes": archive.stat().st_size,
                                                "sha256": digest(archive)}, window_smoke_tested=True,
                      dialogs_tested=False, dependency_closure_checked=True, app_local_modules_observed=True)
    except Exception as error:
        report["error"] = clean(str(error))
        print(report["error"], file=sys.stderr)
        # A partial/failed package must never be mistaken for the checked download.
        shutil.rmtree(out / "download", ignore_errors=True)
    finally:
        if original_resolved is not None:
            resolved.write_bytes(original_resolved)
        # Raw module receipts are checked above, then paths are removed from public evidence.
        smoke_path = evidence / "wpf-smoke.json"
        if smoke_path.exists():
            try:
                smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
                for key in ("process_modules", "helper_modules"):
                    if key in smoke:
                        smoke[key] = [{"name": item.get("name")} for item in smoke[key]]
                write(smoke_path, smoke)
            except Exception:
                smoke_path.unlink()
        write(evidence / "application-build.json", report)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
