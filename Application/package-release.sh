#!/bin/sh
# Package an already built app. No rebuilding, signing or notarization occurs here.
set -eu
cd "$(dirname "$0")"
if [ "$#" -gt 1 ]; then
    printf 'Usage: %s [new-output-directory]\n' "$0" >&2
    exit 2
fi
python3 - "$PWD" "${1:-}" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import runpy
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

root = Path(sys.argv[1])
app = root / "dist/Rebase.app"
support = runpy.run_path(str(root / "release-support.py"))

def run(*args):
    return subprocess.check_output([str(arg) for arg in args], text=True).strip()

def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()

def inventory(directory):
    entries = {}
    for path in [directory, *sorted(directory.rglob("*"))]:
        item = {"mode": stat.S_IMODE(path.lstat().st_mode)}
        if path.is_symlink():
            item["symlink"] = os.readlink(path)
        elif path.is_file():
            item["sha256"] = digest(path)
        else:
            item["directory"] = True
        # Resource forks and Finder metadata must survive the archive round trip.
        attrs = {}
        for name, value in support["attributes"](path).items():
            if name in support["RESOURCE_ATTRIBUTES"]:
                attrs[name] = hashlib.sha256(value).hexdigest()
        if attrs:
            item["resource_attributes"] = attrs
        entries[path.relative_to(directory).as_posix()] = item
    return entries

with (app / "Contents/Info.plist").open("rb") as stream:
    info = plistlib.load(stream)
version = info["CFBundleShortVersionString"]
if not re.fullmatch(r"\d+\.\d+\.\d+", version):
    raise SystemExit("Expected a three-component release version")
if info.get("CFBundleIconFile") != "Rebase.icns" or info.get("LSMinimumSystemVersion") != "14.0":
    raise SystemExit("Unexpected icon or minimum macOS version")
if info.get("CFBundleIdentifier") != "org.rebaseproject.Rebase":
    raise SystemExit("Unexpected application identifier")
executable = app / "Contents/MacOS/Rebase"
library = app / "Contents/Frameworks/libsoxr.0.dylib"
for binary in (executable, library):
    if run("/usr/bin/lipo", "-archs", binary) != "arm64":
        raise SystemExit(f"Expected arm64 binary: {binary.name}")
required = (
    "Rebase.icns", "ThirdPartyNotices.txt", "ThirdParty/README.md",
    "ThirdParty/SOXR-NOTICES.txt", "ThirdParty/soxr-source-manifest.json",
    "ThirdParty/soxr-build-manifest.json", "ThirdParty/build-soxr.sh",
    "ThirdParty/soxr-0.1.3/LICENCE", "ThirdParty/soxr-0.1.3/COPYING.LGPL",
)
resources = app / "Contents/Resources"
for relative in required:
    if not (resources / relative).is_file():
        raise SystemExit(f"Missing bundled resource: {relative}")
if digest(resources / "Rebase.icns") != digest(root / "Assets/Rebase.icns"):
    raise SystemExit("Bundled icon does not match Assets/Rebase.icns")
for relative in ("SOXR-NOTICES.txt", "soxr-0.1.3/LICENCE", "soxr-0.1.3/COPYING.LGPL"):
    if (resources / "ThirdParty" / relative).read_bytes() != (root / "ThirdParty" / relative).read_bytes():
        raise SystemExit(f"Bundled third-party notice changed: {relative}")
example_manifest = json.loads((resources / "Examples/example.json").read_text())
example_root = resources / "Examples" / example_manifest["project"]
for item in example_manifest["files"]:
    relative = Path(item["path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise SystemExit("Unsafe bundled example path")
    path = example_root / relative
    if not path.is_file() or path.stat().st_size != item["bytes"] or digest(path) != item["sha256"]:
        raise SystemExit(f"Bundled example differs from manifest: {relative}")
for path in (root / "Examples").rglob("*"):
    if path.is_file() and path.read_bytes() != (resources / "Examples" / path.relative_to(root / "Examples")).read_bytes():
        raise SystemExit("Bundled example differs from release source inputs")
zip_license = (root / ".build/checkouts/ZIPFoundation/LICENSE").read_bytes()
if zip_license not in (resources / "ThirdPartyNotices.txt").read_bytes():
    raise SystemExit("Bundled notices do not contain the complete ZIPFoundation license")
run("/usr/bin/codesign", "--verify", "--strict", "--deep", app)
support["audit_paths"](app)
before = inventory(app)
before_metadata = support["metadata_inventory"](app)
if any("resource_attributes" in item for item in before.values()):
    raise SystemExit("This file-only release format cannot preserve resource forks or FinderInfo")
output = (Path(sys.argv[2]).expanduser() if sys.argv[2] else root / "dist/releases" / version).resolve()
if output == app.resolve() or app.resolve() in output.parents:
    raise SystemExit("Release output must be outside the source application bundle")
if output.exists():
    raise SystemExit(f"Refusing to replace existing release directory: {output}")
output.parent.mkdir(parents=True, exist_ok=True)

with tempfile.TemporaryDirectory(prefix=".rebase-release-", dir=output.parent) as work_name:
    work = Path(work_name)
    delivery = work / "delivery"
    delivery.mkdir()
    archive = delivery / f"Rebase-{version}-macos-arm64.zip"
    staged_app = work / "staged/Rebase.app"
    # Copy bytes/modes/symlinks, not host metadata or ACLs. The OS may add its own
    # local provenance attribute; the explicit ZIP writer below never exports it.
    shutil.copytree(app, staged_app, copy_function=shutil.copy, symlinks=True)
    support["clean_metadata"](staged_app)
    support["audit_metadata"](staged_app)
    support["audit_paths"](staged_app)
    if inventory(staged_app) != before:
        raise SystemExit("Staging changed app contents, modes or resource attributes")
    run("/usr/bin/codesign", "--verify", "--strict", "--deep", staged_app)
    # Stable order/timestamps; files, modes and symlink targets only. No AppleDouble,
    # xattrs, ACLs, ownership fields or host-created metadata enter this archive.
    # Reproducibility assumes identical app bytes and the same Python/zlib version.
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as target:
        for path in [staged_app, *sorted(staged_app.rglob("*"))]:
            mode = path.lstat().st_mode
            name = path.relative_to(staged_app.parent).as_posix()
            if path.is_symlink():
                payload = os.fsencode(os.readlink(path))
            elif path.is_file():
                payload = path.read_bytes()
            elif path.is_dir():
                name += "/"
                payload = b""
            else:
                raise SystemExit(f"Unsupported release file type: {name}")
            entry = zipfile.ZipInfo(name, date_time=(2000, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = (mode << 16) | (0x10 if path.is_dir() else 0)
            entry.compress_type = zipfile.ZIP_DEFLATED
            target.writestr(entry, payload, compresslevel=9)
    with zipfile.ZipFile(archive) as packed:
        if packed.comment or any(entry.extra or entry.comment for entry in packed.infolist()):
            raise SystemExit("Archive contains unexpected extra fields or comments")
    restored = work / "restored"
    run("/usr/bin/ditto", "-x", "-k", "--rsrc", "--extattr", archive, restored)
    restored_app = restored / "Rebase.app"
    support["audit_metadata"](restored_app)
    support["audit_paths"](restored_app)
    if inventory(restored_app) != before:
        raise SystemExit("Archive round trip changed app contents, modes or resource attributes")
    run("/usr/bin/codesign", "--verify", "--strict", "--deep", restored_app)
    if inventory(app) != before or support["metadata_inventory"](app) != before_metadata:
        raise SystemExit("Source app changed during packaging")
    archive_hash = digest(archive)
    (delivery / "SHA256SUMS").write_text(f"{archive_hash}  {archive.name}\n")
    shutil.copyfile(root / "INSTALL.md", delivery / "INSTALL.md")
    record = {
        "version": version, "build": info["CFBundleVersion"], "architecture": "arm64",
        "minimum_macos": "14.0", "signature_verified_after_extraction": True,
        "notarization_performed": False, "source_bundle_unchanged": True,
        "metadata_policy": "File bytes, Unix modes and symlink targets only; no xattrs, ACLs, AppleDouble, ZIP extra fields, ownership fields or comments",
        "archive": {"name": archive.name, "bytes": archive.stat().st_size, "sha256": archive_hash},
        "executable_sha256": digest(executable), "icon_sha256": digest(resources / "Rebase.icns"),
        "bundle_entries": len(before), "third_party_notices_sha256": digest(resources / "ThirdPartyNotices.txt"),
        "zip_timestamps_utc": "2000-01-01T00:00:00Z",
        "example": {"project": example_manifest["project"], "files": len(example_manifest["files"]), "manifest_sha256": digest(resources / "Examples/example.json")},
    }
    (delivery / "release-manifest.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    delivery.rename(output)
print(json.dumps({"output": str(output), **record}, indent=2, sort_keys=True))
PY
