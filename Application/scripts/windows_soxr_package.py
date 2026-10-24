"""Validate and package the pinned, dynamically replaceable public SoXR build.

This checks build evidence and exact bytes; it does not establish equivalence to
any proprietary library or independently reproduce the recorded Windows run.
"""
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import zipfile

SOURCE_VERSION = "0.1.3"
SOURCE_COMMIT = "945b592b70470e29f917f4de89b4281fbbd540c0"
MANIFEST_SHA256 = "faeba8d39aa6eb0c4117291be67a99c207f3e0027bd3f79c1184309eca27a66d"
ARTIFACTS = ("install/bin/soxr.dll", "install/lib/soxr.lib", "install/bin/rebase-soxr-probe.exe")
COMMANDS = ("compiler-version", "cmake-version", "configure", "build", "install", "probe-build", "probe")
OPTIONS = {"BUILD_SHARED_LIBS": "ON", "BUILD_TESTS": "OFF", "BUILD_EXAMPLES": "OFF",
           "WITH_OPENMP": "OFF", "WITH_LSR_BINDINGS": "OFF", "BUILD_LSR_TESTS": "OFF",
           "WITH_CR32": "ON", "WITH_CR64": "ON", "WITH_CR32S": "OFF", "WITH_CR64S": "OFF",
           "WITH_VR32": "OFF", "WITH_PFFFT": "OFF", "WITH_AVFFT": "OFF",
           "WITH_HI_PREC_CLOCK": "ON", "WITH_FLOAT_STD_PREC_CLOCK": "OFF",
           "WITH_DEV_TRACE": "OFF", "WITH_DEV_GPROF": "OFF"}
FEATURES = {key: int(OPTIONS[key] == "ON") for key in (
    "WITH_CR32", "WITH_CR64", "WITH_CR32S", "WITH_CR64S", "WITH_VR32", "WITH_PFFFT",
    "WITH_HI_PREC_CLOCK", "WITH_FLOAT_STD_PREC_CLOCK", "WITH_DEV_TRACE")}
FEATURES.update({"AVCODEC_FOUND": 0, "AVUTIL_FOUND": 0, "HAVE_BIGENDIAN": 0})
NOTICES = "ThirdPartyNotices/SoXR"


def _require(condition, message):
    if not condition:
        raise RuntimeError("SoXR dependency: " + message)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _entry(path, data):
    return {"path": path, "bytes": len(data), "sha256": _sha(data)}


def _relative(value):
    _require(isinstance(value, str) and value and "\\" not in value and ":" not in value,
             "unsafe relative path")
    path = PurePosixPath(value)
    _require(not path.is_absolute() and all(part not in ("", ".", "..") for part in value.split("/")),
             "unsafe relative path")
    return path


def _link(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _directory(path):
    path = Path(path).absolute()
    # Reject redirected ancestors as well as the selected directory itself.
    for current in reversed((path, *path.parents)):
        info = current.lstat()
        _require(not _link(info) and stat.S_ISDIR(info.st_mode), "directory is redirected or not a directory")
    return path


def _file(root, relative, limit=64 * 1024 * 1024):
    relative = _relative(relative)
    parent = root
    for part in relative.parts[:-1]:
        parent = _directory(parent / part)
    path = parent / relative.name
    info = path.lstat()
    _require(not _link(info) and stat.S_ISREG(info.st_mode), "file is redirected or not a regular file")
    _require(0 <= info.st_size <= limit, "file exceeds its bounded input size")
    data = path.read_bytes()
    _require(len(data) == info.st_size, "file size changed while reading")
    return data


def _json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, "duplicate JSON field")
            result[key] = value
        return result
    result = json.loads(data, object_pairs_hook=pairs,
                        parse_constant=lambda _: (_ for _ in ()).throw(RuntimeError("SoXR dependency: nonfinite JSON")))
    _require(isinstance(result, dict), "JSON root must be an object")
    return result


def _pe(data, dll):
    _require(len(data) >= 64 and data[:2] == b"MZ", "invalid Windows image")
    offset = struct.unpack_from("<I", data, 60)[0]
    _require(offset >= 64 and offset <= len(data) - 24 and data[offset:offset + 4] == b"PE\0\0",
             "truncated Windows image")
    machine, sections = struct.unpack_from("<HH", data, offset + 4)
    optional_size, flags = struct.unpack_from("<HH", data, offset + 20)
    _require(machine == 0x8664 and sections > 0 and optional_size >= 112
             and offset + 24 + optional_size + sections * 40 <= len(data)
             and struct.unpack_from("<H", data, offset + 24)[0] == 0x20b
             and bool(flags & 0x2000) == dll, "image is not the expected x64 PE32+ product")


def _source(app):
    manifest_bytes = _file(app, "ThirdParty/soxr-source-manifest.json", 1024 * 1024)
    _require(_sha(manifest_bytes) == MANIFEST_SHA256, "source manifest differs from pinned identity")
    manifest = _json(manifest_bytes)
    _require(manifest.get("tag") == SOURCE_VERSION and manifest.get("commit") == SOURCE_COMMIT,
             "source version/commit differs")
    rows = manifest.get("files")
    _require(isinstance(rows, list) and len(rows) == 138, "incomplete source manifest")
    source = _directory(app / "ThirdParty" / ("soxr-" + SOURCE_VERSION))
    names = [str(_relative(row["path"])) for row in rows]
    _require(len(set(name.casefold() for name in names)) == len(names), "duplicate source path")
    actual = set()
    for parent, dirs, files in os.walk(source, followlinks=False):
        for name in dirs:
            _directory(Path(parent) / name)
        actual.update((Path(parent) / name).relative_to(source).as_posix() for name in files)
    _require(actual == set(names), "source file entry set differs")
    files, links = {}, []
    for row in rows:
        name = row["path"]
        if "symlink" in row:
            target = row["symlink"]
            _relative(target)
            path = source / name
            _directory(path.parent)
            if path.is_symlink():
                _require(os.readlink(path) == target, "source symbolic link target differs")
                data = target.encode("utf-8")
            else:
                data = _file(source, name)
                _require(data == target.encode("utf-8"), "source link-text differs")
            links.append({"path": name, "target": target, "representation": "regular link-text"})
        else:
            data = _file(source, name, 16 * 1024 * 1024)
            _require(len(data) == row["bytes"] and _sha(data) == row["sha256"], "source bytes differ: " + name)
        files[name] = data
    return manifest_bytes, files, links


def _validate(app, native_soxr_output, expected_commit):
    _require(expected_commit is None or isinstance(expected_commit, str)
             and re.fullmatch(r"[0-9a-f]{40}", expected_commit), "invalid expected application commit")
    app, output = _directory(app), _directory(native_soxr_output)
    manifest_bytes, source, links = _source(app)
    report_bytes = _file(output, "conformance.json", 1024 * 1024)
    report = _json(report_bytes)
    _require(report.get("schema") == "rebase.windows-soxr.v1" and report.get("status") == "passed",
             "Windows build did not pass")
    _require(report.get("platform") == "Windows" and report.get("architecture", "").lower() in ("amd64", "x86_64"),
             "build is not Windows x64")
    _require("commit" in report and report["commit"] == expected_commit, "application commit mismatch")
    _require(report.get("source_version") == SOURCE_VERSION
             and report.get("source_manifest_sha256") == MANIFEST_SHA256
             and type(report.get("source_entries_verified")) is int and report["source_entries_verified"] == len(source),
             "build source identity differs")
    _require(report.get("options") == OPTIONS, "build options differ from pinned profile")
    _require(report.get("optimization") == "-O3 -DNDEBUG; fast math disabled; FP contraction disabled"
             and report.get("msvc_runtime") == "MultiThreadedDLL (CMP0091 NEW)"
             and report.get("windows_exports") == "SOXR_DLL explicitly enabled for clang's GNU frontend",
             "compiler/runtime profile differs")
    features = report.get("configured_features")
    _require(isinstance(features, dict) and all(type(features.get(k)) is int and features[k] == v for k, v in FEATURES.items()),
             "configured features differ")
    _require(type(report.get("compile_command_count")) is int and report["compile_command_count"] == 9,
             "incomplete compiled source count")
    commands = report.get("commands")
    _require(isinstance(commands, list) and len(commands) == len(COMMANDS), "incomplete build commands")
    logs = {}
    for command, name in zip(commands, COMMANDS):
        _require(isinstance(command, dict) and command.get("name") == name
                 and type(command.get("exit_code")) is int and command["exit_code"] == 0
                 and command.get("log") == name + ".log", "failed or changed build command")
        logs[name] = _file(output, name + ".log", 16 * 1024 * 1024)
        _require(bool(logs[name].strip()), "empty build log")
    probe_bytes = _file(output, "soxr-conformance.json", 1024 * 1024)
    probe = _json(probe_bytes)
    _require(_json(logs["probe"]) == probe, "probe report differs from executed output")
    for key, expected in {"schema": "rebase.soxr-plumbing.v1", "status": "passed", "source_rate": 48000,
                          "output_rate": 44100, "channels": 2, "input_frames": 4800, "output_frames": 4410,
                          "finite": True}.items():
        _require(type(probe.get(key)) is type(expected) and probe[key] == expected, "plumbing result differs: " + key)
    for name in ("peak", "energy", "maximum_channel_error"):
        _require(type(probe.get(name)) in (int, float) and math.isfinite(probe[name]), "invalid plumbing measurement")
    _require(0 < probe["peak"] <= 2 and probe["energy"] > 0 and 0 <= probe["maximum_channel_error"] < 1e-6,
             "plumbing measurement outside admitted profile")
    rows = report.get("artifacts")
    _require(isinstance(rows, list) and len(rows) == len(ARTIFACTS), "incomplete build artifacts")
    artifacts = {}
    for row in rows:
        _require(isinstance(row, dict), "invalid artifact record")
        name = str(_relative(row.get("path")))
        _require(name in ARTIFACTS and name not in artifacts, "unexpected or duplicate artifact")
        data = _file(output, name)
        _require(type(row.get("bytes")) is int and row["bytes"] == len(data)
                 and row.get("sha256") == _sha(data), "artifact bytes differ: " + name)
        if name.endswith(".lib"):
            _require(data.startswith(b"!<arch>\n") and len(data) > 68, "truncated import library")
        else:
            _pe(data, name.endswith(".dll"))
        artifacts[name] = data
    receipt = {"schema": "rebase.windows-soxr-dependency.v1", "status": "passed",
               "scope": "Pinned public SoXR build bytes; no reference-library equivalence claim",
               "source_version": SOURCE_VERSION, "source_commit": SOURCE_COMMIT,
               "source_manifest_sha256": MANIFEST_SHA256, "source_entries_verified": len(source),
               "application_commit": expected_commit, "build_report_sha256": _sha(report_bytes),
               "plumbing_report_sha256": _sha(probe_bytes),
               "artifacts": [_entry(name, artifacts[name]) for name in ARTIFACTS]}
    return receipt, artifacts, source, links, manifest_bytes, app


def validate_soxr_build(app, native_soxr_output, expected_commit):
    """Validate exact native Windows build/source bytes; return a path-free receipt.

    expected_commit=None only accepts an explicitly local report whose commit is
    also null. It is never a wildcard. No files are created by this function.
    """
    return _validate(app, native_soxr_output, expected_commit)[0]


def _archive(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    return buffer.getvalue()


def stage_soxr(app, native_soxr_output, stage, expected_commit):
    """Stage a new replaceable DLL and complete public source/notices, no links.

    Existing dependency destinations are refused. The caller must treat any
    exception as a failed package; partial writes are retained for diagnosis.
    """
    receipt, artifacts, source, links, manifest_bytes, app = _validate(app, native_soxr_output, expected_commit)
    stage = _directory(stage)
    _require(not os.path.lexists(stage / "soxr.dll") and not os.path.lexists(stage / NOTICES),
             "dependency destination already exists")
    parent = stage / "ThirdPartyNotices"
    if os.path.lexists(parent):
        _directory(parent)
    rebuild = _file(app, "scripts/build-windows-soxr.py", 1024 * 1024)
    probe = _file(app, "scripts/windows-soxr-probe.c", 1024 * 1024)
    contents = {"soxr-" + SOURCE_VERSION + "/" + name: data for name, data in source.items()}
    contents.update({"soxr-source-manifest.json": manifest_bytes,
                     "rebuild/build-windows-soxr.py": rebuild, "rebuild/windows-soxr-probe.c": probe})
    archive = _archive(contents)
    coordinate = expected_commit or "local build (no application commit was supplied)"
    notes = ("Public SoXR 0.1.3 dependency\n\n"
             "This application dynamically loads the app-local soxr.dll, built from public SoXR source. "
             "It is not a proprietary reference library; sample equivalence to that library is unknown.\n"
             "Upstream source commit: " + SOURCE_COMMIT + "\n"
             "Application source commit: " + coordinate + "\n"
             "Source manifest SHA-256: " + MANIFEST_SHA256 + "\n\n"
             "The complete source is in soxr-0.1.3-source.zip. Its single symbolic-link entry "
             "inst-check-soxr-lsr is stored as an ordinary UTF-8 file containing inst-check-soxr; "
             "no symbolic links are installed. The manifest records the original link.\n\n"
             "Rebuild on Windows x64 from the canonical Rebase repository at the application commit above. "
             "With clang/clang-cl and the Visual Studio x64 dynamic CRT environment, Python, "
             "CMake 3.31.6 and Ninja 1.11.1.4 installed, run:\n"
             "  python Application/scripts/build-windows-soxr.py --output <new-build-directory>\n"
             "The archive includes the exact build script and probe under rebuild/. If rebuilding outside "
             "that repository, place those two files in Application/scripts/, the manifest in "
             "Application/ThirdParty/, and the extracted soxr-0.1.3 directory in Application/ThirdParty/.\n"
             "The resulting install/bin/soxr.dll and install/lib/soxr.lib are the runtime and import library. "
             "For an unmodified dependency, preserve the manifest pin; for modified-library development, "
             "update the local source verification to cover the intended source changes. The script's "
             "manifest check deliberately rejects unrecorded source edits.\n\n"
             "To replace the library, close Rebase and replace soxr.dll beside Rebase.exe with a compatible "
             "Windows x64 DLL exposing the same SoXR C API and compatible dynamic CRT. The application "
             "does not require a signature or embedded digest for the replacement DLL. Keep a backup; "
             "build receipts describe the distributed DLL, not a later replacement.\n"
             "COPYING.LGPL, LICENCE and AUTHORS are exact upstream notices. See those notices for terms.\n")
    packaged = {"soxr.dll": artifacts[ARTIFACTS[0]], NOTICES + "/soxr-0.1.3-source.zip": archive,
                NOTICES + "/soxr-source-manifest.json": manifest_bytes,
                NOTICES + "/REBUILD-AND-REPLACE.txt": notes.encode("utf-8")}
    for name in ("COPYING.LGPL", "LICENCE", "AUTHORS"):
        packaged[NOTICES + "/" + name] = source[name]
    parent.mkdir(exist_ok=True)
    (stage / NOTICES).mkdir()
    for name, data in packaged.items():
        path = stage / name
        with path.open("xb") as stream:
            stream.write(data)
        _require(_file(stage, name) == data, "staged bytes changed")
    receipt.update({"runtime_path": "soxr.dll", "notices_directory": NOTICES,
                    "packaged_files": [_entry(name, data) for name, data in sorted(packaged.items())],
                    "source_archive": {"path": NOTICES + "/soxr-0.1.3-source.zip", "sha256": _sha(archive),
                                       "entry_count": len(contents), "source_entries": len(source),
                                       "symlink_entries": links}})
    return receipt
