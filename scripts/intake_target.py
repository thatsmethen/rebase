#!/usr/bin/env python3
"""Read-only macOS .app inventory. Output contains metadata and hashes, not code."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import shutil
import stat
import subprocess
import sys
import tempfile

TOOL_VERSION = "1.0.0"
CHUNK_SIZE = 1024 * 1024
IDENTITY_FIELDS = {
    "name": "CFBundleName",
    "display_name": "CFBundleDisplayName",
    "version": "CFBundleShortVersionString",
    "build": "CFBundleVersion",
    "bundle_identifier": "CFBundleIdentifier",
    "executable": "CFBundleExecutable",
}


class IntakeError(Exception):
    """Input cannot produce a trustworthy inventory."""


def signature(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


def unchanged(before, after, path):
    if signature(before) != signature(after):
        raise IntakeError(f"Changed during intake: {path}")


def open_directory(name, parent_fd=None):
    before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if not stat.S_ISDIR(before.st_mode):
        raise IntakeError(f"Expected a real directory, not a symlink: {name}")
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                 dir_fd=parent_fd)
    try:
        unchanged(before, os.fstat(fd), name)
    except BaseException:
        os.close(fd)
        raise
    return fd


def read_regular(parent_fd, name, relative, capture=False, file_tool=None):
    before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode):
        raise IntakeError(f"Expected a regular file, not a symlink: {relative}")
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                 dir_fd=parent_fd)
    data, digest, inspection = bytearray(), hashlib.sha256(), None
    size = 0
    try:
        unchanged(before, os.fstat(fd), relative)
        while True:
            chunk = os.read(fd, CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
            if capture:
                data.extend(chunk)
        if file_tool:
            os.lseek(fd, 0, os.SEEK_SET)
            result = subprocess.run(
                [file_tool, "-b", "-L", "--", f"/dev/fd/{fd}"],
                pass_fds=(fd,), capture_output=True, text=True, timeout=30,
                check=False,
            )
            inspection = {"tool": file_tool, "arguments": ["-b", "-L"],
                          "input": relative, "returncode": result.returncode,
                          "stdout": result.stdout, "stderr": result.stderr}
            if result.returncode:
                raise IntakeError(f"file inspection failed: {relative}")
        unchanged(before, os.fstat(fd), relative)
        unchanged(before, os.stat(name, dir_fd=parent_fd,
                                  follow_symlinks=False), relative)
        if size != before.st_size:
            raise IntakeError(f"Read size changed: {relative}")
    finally:
        os.close(fd)
    return {"path": relative, "size": size, "sha256": digest.hexdigest()}, bytes(data), inspection


def metadata_from_plist(data, edition_key):
    try:
        info = plistlib.loads(data)
    except Exception as exc:
        raise IntakeError(f"Malformed Contents/Info.plist: {exc}") from exc
    if not isinstance(info, dict):
        raise IntakeError("Contents/Info.plist must contain a dictionary")
    fields = {**IDENTITY_FIELDS}
    if edition_key:
        fields["edition"] = edition_key
    metadata = {}
    for label, key in fields.items():
        value = info.get(key)
        if value is not None and not isinstance(value, str):
            raise IntakeError(f"Info.plist field {key} must be a string when present")
        metadata[label] = value
    metadata.setdefault("edition", None)
    metadata["edition_key"] = edition_key
    executable = metadata["executable"]
    if (not executable or executable in (".", "..") or
            any(char in executable for char in ("/", "\\", "\x00"))):
        raise IntakeError("CFBundleExecutable must be a nonempty filename within Contents/MacOS")
    return metadata


def inventory(app, edition_key=None, inspect_file=False):
    file_tool = shutil.which("file") if inspect_file else None
    if inspect_file and not file_tool:
        raise IntakeError("Requested file inspection, but the file tool is unavailable")
    root_fd = open_directory(str(app))
    files, symlinks, directories = [], [], []
    inspection = None
    try:
        root_before = os.fstat(root_fd)
        contents_fd = open_directory("Contents", root_fd)
        try:
            plist_record, data, _ = read_regular(
                contents_fd, "Info.plist", "Contents/Info.plist", capture=True)
            metadata = metadata_from_plist(data, edition_key)
            macos_fd = open_directory("MacOS", contents_fd)
            try:
                main_stat = os.stat(metadata["executable"], dir_fd=macos_fd,
                                    follow_symlinks=False)
                if not stat.S_ISREG(main_stat.st_mode):
                    raise IntakeError("Declared executable must be a regular file, not a symlink")
            finally:
                os.close(macos_fd)
        finally:
            os.close(contents_fd)
        main_path = "Contents/MacOS/" + metadata["executable"]

        def walk(fd, prefix=""):
            nonlocal inspection
            before = os.fstat(fd)
            for name in sorted(os.listdir(fd)):
                relative = prefix + name
                entry = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISLNK(entry.st_mode):
                    target = os.readlink(name, dir_fd=fd)
                    unchanged(entry, os.stat(name, dir_fd=fd,
                                            follow_symlinks=False), relative)
                    symlinks.append({"path": relative, "target": target})
                elif stat.S_ISDIR(entry.st_mode):
                    child_fd = open_directory(name, fd)
                    try:
                        unchanged(entry, os.fstat(child_fd), relative)
                        directories.append(relative)
                        walk(child_fd, relative + "/")
                        unchanged(entry, os.stat(name, dir_fd=fd,
                                                follow_symlinks=False), relative)
                    finally:
                        os.close(child_fd)
                elif stat.S_ISREG(entry.st_mode):
                    record, _, inspected = read_regular(
                        fd, name, relative, file_tool=file_tool if relative == main_path else None)
                    unchanged(entry, os.stat(name, dir_fd=fd,
                                            follow_symlinks=False), relative)
                    files.append(record)
                    if inspected is not None:
                        inspection = inspected
                else:
                    raise IntakeError(f"Unsupported special file: {relative}")
            unchanged(before, os.fstat(fd), prefix or ".")

        walk(root_fd)
        unchanged(root_before, os.fstat(root_fd), str(app))
        unchanged(root_before, os.stat(app, follow_symlinks=False), str(app))
        records = {record["path"]: record for record in files}
        if records.get(plist_record["path"]) != plist_record:
            raise IntakeError("Contents/Info.plist changed after metadata was read")
        if main_path not in records:
            raise IntakeError("Declared executable was not inventoried as a regular file")
        manifest = {
            "schema_version": 1, "tool": "intake_target.py", "tool_version": TOOL_VERSION,
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "host": {"system": platform.system(), "release": platform.release(),
                     "machine": platform.machine(), "python": platform.python_version()},
            "bundle_path": str(app), "metadata": metadata,
            "main_executable": records[main_path], "files": files,
            "symlinks": symlinks, "directories": directories,
            "file_inspection": "file-inspection.json" if inspection is not None else None,
        }
        return manifest, inspection
    finally:
        os.close(root_fd)


def write_new_output(out, manifest, inspection):
    # Reserve exclusively; publish each complete JSON by a no-overwrite hard link.
    out.mkdir(mode=0o700)
    created = []
    try:
        outputs = [("manifest.json", manifest)]
        if inspection is not None:
            outputs.insert(0, ("file-inspection.json", inspection))
        for name, value in outputs:
            fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=out)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(value, stream, indent=2, ensure_ascii=True, allow_nan=False)
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                destination = out / name
                os.link(temporary, destination)
                created.append(destination)
            finally:
                os.unlink(temporary)
    except BaseException:
        for path in created:
            path.unlink()
        out.rmdir()
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", type=Path, help="Explicit path to the .app bundle")
    parser.add_argument("--out", required=True, type=Path, help="New directory outside the bundle")
    parser.add_argument("--edition-key", help="Exact Info.plist key for edition; otherwise unresolved")
    parser.add_argument("--inspect-file", action="store_true", help="Capture optional file(1) output")
    parser.add_argument("--version", action="version", version=TOOL_VERSION)
    args = parser.parse_args(argv)
    try:
        app = Path(os.path.abspath(args.app.expanduser()))
        out = Path(os.path.abspath(args.out.expanduser()))
        if app.suffix.lower() != ".app":
            raise IntakeError("Input must explicitly name an .app bundle")
        if app.is_symlink():
            raise IntakeError("The .app bundle itself must not be a symlink")
        # Resolve the supplied parent, but never resolve the bundle entry itself.
        # Its final component is opened with O_NOFOLLOW below, including on races.
        app = app.parent.resolve(strict=True) / app.name
        if os.path.lexists(out):
            raise IntakeError(f"Output already exists: {out}")
        out = out.parent.resolve(strict=True) / out.name
        if out == app or app in out.parents:
            raise IntakeError("Output must be outside the source bundle")
        manifest, inspection = inventory(app, args.edition_key, args.inspect_file)
        write_new_output(out, manifest, inspection)
    except (IntakeError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Intake failed: {exc}", file=sys.stderr)
        return 1
    print(out / "manifest.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
