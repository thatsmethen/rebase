#!/bin/sh
# Copy only release inputs into a fresh neutral workspace, then build there.
set -eu
cd "$(dirname "$0")"
if [ "$#" -gt 1 ]; then
    printf 'Usage: %s [new-neutral-workspace]\n' "$0" >&2
    exit 2
fi
WORKSPACE=${1:-/private/tmp/rebase-release-build}
python3 - "$PWD" "$WORKSPACE" <<'PY'
from pathlib import Path
import re
import shutil
import sys

source = Path(sys.argv[1])
workspace = Path(sys.argv[2]).resolve()
if workspace.parent != Path('/private/tmp') or not re.fullmatch(r'rebase-release-build(?:-[a-z0-9-]+)?', workspace.name):
    raise SystemExit('Use /private/tmp/rebase-release-build or that path with a lowercase neutral suffix')
if workspace.exists():
    raise SystemExit('Release workspace already exists; choose a fresh neutral suffix')
required = ('Sources', 'Tests/RebaseCoreTests', 'ThirdParty', 'Assets', 'Package.swift', 'Package.resolved',
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
printf 'Neutral release bundle: %s/Application/dist/Rebase.app\n' "$WORKSPACE"
