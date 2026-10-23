#!/usr/bin/env python3
"""Assemble and exercise an unsigned Windows development package on Windows x64."""
import argparse
import hashlib
import json
import math
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


def require_window_visual(path, bounds=None):
    data = path.read_bytes()
    dimensions = struct.unpack_from(">II", data, 16) if len(data) >= 24 else (0, 0)
    if (len(data) < 1024 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR"
            or not all(0 < value <= 16_384 for value in dimensions)):
        raise RuntimeError("Missing or invalid WPF window visual")
    if bounds is not None:
        keys = ("outer_width", "outer_height", "client_width", "client_height", "dpi_x", "dpi_y")
        if any(type(bounds.get(key)) not in (int, float) or not math.isfinite(bounds[key]) or bounds[key] <= 0 for key in keys):
            raise RuntimeError("Missing finite client-window capture bounds")
        # The WPF capture deliberately renders logical client dimensions at 96 DPI;
        # reported host DPI describes the window, not a scaling of this PNG.
        if (dimensions != (math.ceil(bounds["client_width"]), math.ceil(bounds["client_height"]))
                or bounds["client_width"] > bounds["outer_width"] or bounds["client_height"] > bounds["outer_height"]):
            raise RuntimeError("Window PNG dimensions do not match its declared client capture")


def require_pinned_header_scroll(smoke):
    if smoke.get("timeline_scroll_screenshot") != "native-timeline-scroll-visual.png":
        raise RuntimeError("Missing scrolled timeline screenshot receipt")
    scroll = smoke.get("timeline_scroll", {})

    def number(value):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise RuntimeError("Invalid timeline scroll geometry")
        return value

    def point(value):
        return (number(value["x"]), number(value["y"]))

    if number(scroll.get("zoom_pixels_per_second")) != 100:
        raise RuntimeError("Timeline scroll was not checked at the declared zoom")
    delta = number(scroll.get("offset_after")) - number(scroll.get("offset_before"))
    before, after = scroll.get("headers_before", []), scroll.get("headers_after", [])
    if delta < 50 or len(before) != 4 or len(after) != 4:
        raise RuntimeError("Timeline scroll did not exercise all four track headers")
    if any(abs(a - b) > 0.5 for first, last in zip(before, after) for a, b in zip(point(first), point(last))):
        raise RuntimeError("Track headers moved during horizontal timeline scroll")
    first, last = point(scroll["event_before"]), point(scroll["event_after"])
    if abs(last[0] - first[0] + delta) > 0.5 or abs(last[1] - first[1]) > 0.5:
        raise RuntimeError("Timeline event geometry did not follow the measured scroll")


def require_cpr_review_layout(path, bounds, layout, minimum_error=False):
    require_window_visual(path, bounds)
    width, height = math.ceil(bounds["client_width"]), math.ceil(bounds["client_height"])
    if (type(layout.get("opaque_pixels")) is not int or type(layout.get("total_pixels")) is not int
            or layout["opaque_pixels"] != width * height or layout["total_pixels"] != width * height):
        raise RuntimeError("CPR review capture was not checked as fully opaque")
    viewport = layout.get("review_viewport_height")
    if type(viewport) not in (int, float) or not math.isfinite(viewport) or viewport < 40:
        raise RuntimeError("CPR review has no usable content viewport")
    controls = layout.get("footer_controls", [])
    if (len(controls) != 4 or {control.get("name") for control in controls} !=
            {"Previous", "Next", "Cancel", "Import Supported Data"}):
        raise RuntimeError("CPR review footer geometry is incomplete")
    for control in controls:
        if (any(type(control.get(key)) not in (int, float) or not math.isfinite(control[key])
                for key in ("x", "y", "width", "height"))
                or control["x"] < 0 or control["y"] < 0 or control["width"] <= 0 or control["height"] <= 0
                or control["x"] + control["width"] > bounds["client_width"] + 0.5
                or control["y"] + control["height"] > bounds["client_height"] + 0.5):
            raise RuntimeError("CPR review footer control lies outside the captured client")
    if minimum_error and (bounds["outer_width"] > 650.5 or bounds["outer_height"] > 480.5
                          or type(layout.get("error_characters")) is not int or layout["error_characters"] <= 0):
        raise RuntimeError("CPR review error layout was not checked at minimum window size")


def require_musical_ruler(smoke):
    ruler = smoke.get("musical_ruler", {})
    numeric = ("tempo", "duration", "pixels_per_second", "bar_two_seconds", "first_label_x", "second_label_x")
    if (type(ruler.get("revision")) is not int or ruler["revision"] <= 0
            or any(type(ruler.get(key)) not in (int, float) or not math.isfinite(ruler[key]) for key in numeric)):
        raise RuntimeError("Missing finite musical ruler geometry and revision")
    if (ruler["tempo"] != 96 or ruler["duration"] != 24 or ruler["pixels_per_second"] != 32
            or ruler["bar_two_seconds"] != 2.5 or ruler["first_label_x"] < 0
            or abs(ruler["second_label_x"] - ruler["first_label_x"] - 2.5 * ruler["pixels_per_second"]) > 0.5):
        raise RuntimeError("Musical ruler labels do not match the authored 96 BPM example")


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
        fixture = app / "Tests/Fixtures/SourceAudition"
        source_project = fixture / "AuthoredSource.rebaseproj"
        source_media = fixture / "SelectedSource.wav"
        source_lock = fixture / "expected.json"
        if (not source_project.is_dir() or not source_media.is_file() or not source_lock.is_file()
                or any(inside(path, stage) for path in (source_project, source_media, source_lock))):
            raise RuntimeError("The external authored source fixture is unavailable")
        expected_source = json.loads(source_lock.read_text(encoding="utf-8"))
        fixture_bytes = {path.relative_to(fixture).as_posix(): digest(path)
                         for path in fixture.rglob("*") if path.is_file()}
        run([sys.executable, str(app / "scripts/check-session-protocol.py"), "--helper", str(stage / "rebase-session.exe"),
             "--example", str(example), "--report", str(evidence / "packaged-session-protocol.json"),
             "--source-project", str(source_project), "--source-media", str(source_media), "--source-lock", str(source_lock)],
            "packaged-session-protocol", restricted, timeout=600, cwd=stage)
        session = json.loads((evidence / "packaged-session-protocol.json").read_text(encoding="utf-8"))
        if (session.get("status") != "passed" or session.get("source_journey_tested") is not True
                or session.get("waveform", {}).get("clips_checked") != 11
                or session.get("source", {}).get("playback_tested") is not False
                or session.get("ruler", {}).get("read_only") is not True
                or session.get("ruler", {}).get("stale_revision_rejected") is not True
                or session.get("ruler", {}).get("first_bar_seconds") != [0, 2.5, 5, 7.5]
                or session.get("ruler", {}).get("first_quarter_seconds") != [0, 0.625, 1.25, 1.875, 2.5]
                or any(session.get("source", {}).get(key) != expected_source[key]
                       for key in ("sourceSHA256", "mediaSHA256", "outputSHA256", "pcmSHA256", "frames", "sampleRate", "channels"))):
            raise RuntimeError("Packaged session protocol did not pass")
        imported = session.get("cpr_import", {})
        required_import_controls = (
            "tested", "review_read_only", "review_bounded", "cancellation_preserves_state",
            "superseded_review_rejected", "stale_revision_rejected", "changed_source_rejected",
            "explicit_partial_required", "dirty_replacement_guarded", "existing_destination_preserved",
            "import_published", "exact_source_and_report_preserved", "save_reopen_preserves_baseline",
            "historical_read_only", "tampered_report_rejected", "tampered_source_rejected")
        if (any(imported.get(key) is not True for key in required_import_controls)
                or imported.get("sourceSHA256") != expected_source["sourceSHA256"]
                or imported.get("reportSHA256") != expected_source["reportSHA256"]):
            raise RuntimeError("Packaged CPR import protocol checks did not pass")
        smoke_path = evidence / "wpf-smoke.json"
        run([str(stage / "Rebase.exe"), "--smoke", "--smoke-json", str(smoke_path),
             "--smoke-source-project", str(source_project), "--smoke-source-media", str(source_media)],
            "packaged-window-smoke", restricted, timeout=240, cwd=stage)
        smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
        if (smoke.get("suite") != "windows-wpf-shared-session-smoke" or smoke.get("outcome") != "passed"
                or smoke.get("stage") != "completed" or smoke.get("playback_tested") is not False
                or smoke.get("audible_output_measured") is not False or not smoke.get("checks")):
            raise RuntimeError("Window smoke receipt is incomplete")
        required_checks = {"real-waveforms-visible", "four-track-rows-fit", "source-package-copy", "source-event-ui-selection",
                           "source-media-ui-attachment", "source-attachment-undo", "source-attachment-redo",
                           "source-export-ui-verified", "source-provenance-matches", "source-window-visual-artifact",
                           "snap-control-fits-toolbar", "timeline-horizontal-scroll-performed", "track-headers-stay-anchored",
                           "timeline-events-scroll", "timeline-scroll-visual-artifact", "inspector-volume-shared-edit",
                           "inspector-volume-undo", "inspector-volume-redo", "inspector-focus-restored",
                           "inspector-pan-shared-edit", "inspector-mute-shared-edit", "inspector-solo-shared-edit",
                           "source-selection-labels", "mixer-mute-shared-edit", "track-solo-shared-edit",
                           "mixer-volume-shared-edit-and-undo",
                           "musical-ruler-shared-96bpm", "musical-ruler-seconds-toggle",
                           "selection-synchronized-across-panes", "channel-strip-bottom-aligned", "channel-volume-shared-edit", "channel-volume-undo",
                           "channel-pan-shared-edit", "channel-mute-shared-edit", "fader-scale-matches-value",
                           "mixer-numeric-volume-commit", "mixer-numeric-volume-invalid-preserved", "mixer-numeric-volume-cancel",
                           "numeric-event-enter-and-undo", "numeric-event-cancel", "numeric-event-invalid-preserved",
                           "numeric-trim-enter-and-undo", "numeric-tempo-enter-and-undo", "numeric-seek-and-cancel",
                           "cpr-review-window-visible", "cpr-review-all-pages-accessible", "cpr-review-cancel-preserves-session",
                           "cpr-changed-source-rejected", "cpr-dirty-cancel-preserves-session",
                           "cpr-destination-cancel-preserves-review", "cpr-import-supported-data", "cpr-import-source-preserved",
                           "cpr-historical-report-readonly", "cpr-review-visual-artifact",
                           "cpr-review-footer-visible", "cpr-review-capture-opaque", "cpr-review-minimum-error-layout"}
        if (smoke.get("source_journey_tested") is not True or not required_checks.issubset(smoke["checks"])
                or smoke.get("source_screenshot") != "native-source-visual.png"
                or smoke.get("source_output_sha256") != expected_source["outputSHA256"]
                or smoke.get("source_sha256") != expected_source["sourceSHA256"]
                or smoke.get("media_sha256") != expected_source["mediaSHA256"]):
            raise RuntimeError("Source-event or waveform window checks are incomplete")
        alignment = smoke.get("channel_alignment", {})
        if (any(type(alignment.get(key)) not in (int, float) or not math.isfinite(alignment[key]) for key in ("selected_nameplate_bottom", "mixer_nameplate_bottom")) or
                abs(alignment["selected_nameplate_bottom"] - alignment["mixer_nameplate_bottom"]) > 6):
            raise RuntimeError("Selected Channel strip is not aligned with the lower console")
        scale = smoke.get("fader_scale", [])
        if (len(scale) != 6 or {(entry.get("selected_channel"), entry.get("value")) for entry in scale} !=
                {(side, value) for side in (False, True) for value in (-96, 0, 24)} or
                any(type(entry.get(key)) not in (int, float) or not math.isfinite(entry[key]) for entry in scale for key in ("tick_y", "thumb_y")) or
                any(abs(entry["tick_y"] - entry["thumb_y"]) > 0.5 for entry in scale)):
            raise RuntimeError("Fader scale does not match observed native thumb geometry")
        require_pinned_header_scroll(smoke)
        require_musical_ruler(smoke)
        modules = {"process": validate_modules(smoke.pop("process_modules", None), stage, windows,
                                               {"rebase.exe", "coreclr.dll", "rebasewindowsaudio.dll"}),
                   "helper": validate_modules(smoke.pop("helper_modules", None), stage, windows,
                                              {"rebase-session.exe", "swiftcore.dll"})}
        write(evidence / "loaded-modules.json", modules)
        write(smoke_path, smoke)
        bounds = smoke.get("window_bounds", {})
        require_window_visual(evidence / "native-app-visual.png", bounds)
        require_window_visual(evidence / "native-source-visual.png", bounds)
        require_window_visual(evidence / "native-timeline-scroll-visual.png", bounds)
        cpr_review = smoke.get("cpr_review", {})
        if (any(cpr_review.get(key) is not True for key in (
                "reviewed", "cancelled_without_changes", "changed_source_rejected", "dirty_guard",
                "destination_cancel_preserved_review", "imported", "historical_read_only", "vertical_scroll_checked"))
                or cpr_review.get("preserved_source_sha256") != expected_source["sourceSHA256"]
                or cpr_review.get("native_file_pickers_tested") is not False
                or cpr_review.get("physical_input_tested") is not False
                or cpr_review.get("native_frame_visual_tested") is not False
                or cpr_review.get("review_screenshot") != "native-cpr-review-visual.png"
                or type(cpr_review.get("pages_checked")) is not int or cpr_review["pages_checked"] < 1
                or type(cpr_review.get("items_checked")) is not int or cpr_review["items_checked"] < 1):
            raise RuntimeError("Reviewed CPR import window checks are incomplete")
        require_cpr_review_layout(evidence / "native-cpr-review-visual.png", cpr_review.get("window_bounds", {}),
                                  cpr_review.get("capture_layout", {}))
        if cpr_review.get("minimum_error_screenshot") != "native-cpr-review-minimum-error-visual.png":
            raise RuntimeError("Missing minimum-size CPR error capture")
        require_cpr_review_layout(evidence / "native-cpr-review-minimum-error-visual.png", cpr_review.get("minimum_error_bounds", {}),
                                  cpr_review.get("minimum_error_layout", {}), minimum_error=True)
        # Recheck all bundled source bytes after both complete user journeys.
        example_manifest = json.loads((stage / "Examples/example.json").read_text(encoding="utf-8"))
        if any(digest(example / item["path"]) != item["sha256"] for item in example_manifest["files"]):
            raise RuntimeError("A package check changed the bundled example")
        if fixture_bytes != {path.relative_to(fixture).as_posix(): digest(path)
                             for path in fixture.rglob("*") if path.is_file()}:
            raise RuntimeError("A package check changed the authored source fixture")
        # Keep this mandatory gate after window diagnostics, before any downloadable ZIP.
        # An application smoke pass cannot turn a failed/empty Release suite into success.
        run([sys.executable, str(app / "scripts/run-portable-ci.py"), "swift", "--configuration", "Release",
             "--output", str(evidence / "shared")], "shared-release-conformance", timeout=900)
        files = [{"path": path.relative_to(stage).as_posix(), "bytes": path.stat().st_size, "sha256": digest(path)}
                 for path in sorted(stage.rglob("*")) if path.is_file()]
        fixture_payload_hashes = {expected_source[key] for key in
                                  ("sourceSHA256", "mediaSHA256", "manifestSHA256", "reportSHA256", "outputSHA256")}
        if any(item["sha256"] in fixture_payload_hashes for item in files):
            raise RuntimeError("A source-audition test payload was copied into the application package")
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
        report.update(source_journey_tested=True, source_fixture_shipped=False, real_waveform_checks_passed=True)
        report["pinned_track_headers_scroll_checked"] = True
        report["musical_ruler_placement_checked"] = True
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
