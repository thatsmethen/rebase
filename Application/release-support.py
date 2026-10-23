#!/usr/bin/env python3
"""Local release metadata checks; uses the macOS xattr tool, not Linux-only APIs."""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys

RESOURCE_ATTRIBUTES = frozenset(("com.apple.ResourceFork", "com.apple.FinderInfo"))
# macOS may retain/recreate this attribute even when xattr reports successful
# deletion. It is tolerated on local files, never encoded in the release ZIP.
SYSTEM_ATTRIBUTES = frozenset(("com.apple.provenance",))

def paths(directory):
    return [directory, *sorted(directory.rglob("*"))]

def attributes(path):
    names = subprocess.check_output(["/usr/bin/xattr", "-s", str(path)], text=True).splitlines()
    return {name: bytes.fromhex(subprocess.check_output(
        ["/usr/bin/xattr", "-p", "-s", "-x", name, str(path)], text=True)) for name in names}

def metadata_inventory(directory):
    return {path.relative_to(directory).as_posix(): {
        name: hashlib.sha256(value).hexdigest() for name, value in attributes(path).items()
    } for path in paths(directory)}

def clean_metadata(directory):
    for path in paths(directory):
        for name in attributes(path):
            if name not in RESOURCE_ATTRIBUTES | SYSTEM_ATTRIBUTES:
                subprocess.run(["/usr/bin/xattr", "-d", "-s", name, str(path)], check=True)

def audit_metadata(directory):
    for path in paths(directory):
        if set(attributes(path)) - RESOURCE_ATTRIBUTES - SYSTEM_ATTRIBUTES:
            raise SystemExit(f"Unexpected extended metadata: {path.relative_to(directory)}")

def audit_paths(directory):
    # Optional local-only denylist: one private identifier per line. Its path and
    # contents never become a release artifact or diagnostic message.
    marker_path = os.environ.get("REBASE_RELEASE_PRIVATE_MARKERS")
    markers = [line.strip().lower() for line in Path(marker_path).read_bytes().splitlines() if line.strip()] if marker_path else []
    home_paths = re.compile(rb"/(?:Users|home)/[^/\x00\s]+|/(?:private/)?var/folders/")
    for path in paths(directory):
        values = [os.fsencode(path.relative_to(directory)), *attributes(path).values()]
        if path.is_symlink():
            values.append(os.fsencode(os.readlink(path)))
        elif path.is_file():
            values.append(path.read_bytes())
        for value in values:
            encodings = (value, value.replace(b"\x00", b""))
            if any(home_paths.search(encoded) or any(marker in encoded.lower() for marker in markers)
                   for encoded in encodings):
                raise SystemExit(f"Private path or identifier in release entry: {path.relative_to(directory)}")

if __name__ == "__main__":
    command, directory = sys.argv[1], Path(sys.argv[2])
    if command == "clean":
        clean_metadata(directory)
    elif command != "audit":
        raise SystemExit("Usage: release-support.py clean|audit APP")
    audit_metadata(directory)
    audit_paths(directory)
