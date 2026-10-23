#!/bin/sh
# Stage only release inputs inside this checkout, then build with path remapping.
set -eu
cd "$(dirname "$0")"
if [ "$#" -gt 1 ]; then
    printf 'Usage: %s [new-local-build-directory]\n' "$0" >&2
    exit 2
fi
REPOSITORY=$(cd .. && pwd -P)
WORKSPACE=${1:-"$REPOSITORY/.local/builds/macos/release"}
python3 - "$PWD" "$WORKSPACE" <<'PY'
from pathlib import Path
import re
import shutil
import sys

source = Path(sys.argv[1])
workspace = Path(sys.argv[2]).resolve()
if workspace.parent != (source.parent / '.local' / 'builds' / 'macos') or not re.fullmatch(r'release(?:-[a-z0-9-]+)?', workspace.name):
    raise SystemExit("Use this checkout's .local/builds/macos/release directory, optionally with a lowercase suffix")
if workspace.exists():
    raise SystemExit('Release staging directory already exists; choose a fresh lowercase suffix')
required = ('Sources', 'Tests', 'ThirdParty', 'Assets', 'Examples', 'Package.swift', 'Package.resolved',
            'build-app.sh', 'package-release.sh', 'release-support.py',
            'export-build-manifest.py', 'INSTALL.md')
for name in required:
    if not (source / name).exists():
        raise SystemExit(f'Missing release input: {name}')
target = workspace / 'Application'
target.mkdir(parents=True)
for name in required:
    item = source / name
    if item.is_dir():
        shutil.copytree(item, target / name, copy_function=shutil.copy, symlinks=True)
    else:
        shutil.copy(item, target / name)
print(f'Prepared {target}')
PY
WORKSPACE=$(cd "$WORKSPACE" && pwd -P)
mkdir -p "$WORKSPACE/tmp" "$WORKSPACE/cache/clang" "$WORKSPACE/cache/swift"
export TMPDIR="$WORKSPACE/tmp/"
export CLANG_MODULE_CACHE_PATH="$WORKSPACE/cache/clang"
export SWIFTPM_MODULECACHE_OVERRIDE="$WORKSPACE/cache/swift"
sh "$WORKSPACE/Application/build-app.sh"
printf 'Local release bundle: %s/Application/dist/Rebase.app\n' "$WORKSPACE"
