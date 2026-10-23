"""Verify and prepare the official Ghidra release locally, without global setup."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import zipfile

ROOT = Path('/workspace/rebase')
ARCHIVE = ROOT / '.tools/ghidra-download/ghidra_12.1.4_PUBLIC_20260921.zip'
DEST = ROOT / '.tools/ghidra'
STAGING = ROOT / '.tools/ghidra-staging'
EVIDENCE = ROOT / 'research/evidence/tooling'
EXPECTED_SIZE = 569649598
EXPECTED_SHA256 = 'ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db'
DOWNLOAD_PID = 81410
DOWNLOAD_DEADLINE = ARCHIVE.stat().st_birthtime + 900

while ARCHIVE.stat().st_size != EXPECTED_SIZE:
    if time.time() >= DOWNLOAD_DEADLINE:
        try:
            os.kill(DOWNLOAD_PID, signal.SIGTERM)
        except ProcessLookupError:
            pass
        raise SystemExit('Download reached its overall 15-minute deadline; partial file retained.')
    try:
        os.kill(DOWNLOAD_PID, 0)
    except ProcessLookupError:
        raise SystemExit('Download exited before the expected byte count; partial file retained.')
    time.sleep(3)

digest = hashlib.sha256()
with ARCHIVE.open('rb') as stream:
    for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
        digest.update(chunk)
if digest.hexdigest() != EXPECTED_SHA256:
    raise SystemExit('Official archive SHA-256 mismatch; no extraction performed.')
print('Official archive size and SHA-256 verified.', flush=True)
if DEST.exists() or STAGING.exists():
    raise SystemExit('Refusing to overlay an existing Ghidra destination or staging tree.')
with zipfile.ZipFile(ARCHIVE) as archive:
    for name in archive.namelist():
        path = Path(name)
        if path.is_absolute() or '..' in path.parts:
            raise SystemExit('Unexpected archive path; refusing extraction.')
subprocess.run(['/usr/bin/unzip', '-q', str(ARCHIVE), '-d', str(STAGING)], check=True)
(STAGING / 'ghidra_12.1.4_PUBLIC').rename(DEST)
STAGING.rmdir()
print('Ghidra extracted to project-local destination.', flush=True)

source = DEST / 'Ghidra/Features/Decompiler/src/decompile/cpp'
command = ['/usr/bin/make', '-j4', 'ghidra_opt', 'ARCH_TYPE=-arch arm64', 'OSDIR=mac_arm_64']
with (EVIDENCE / 'ghidra-native-build.log').open('w') as log:
    built = subprocess.run(command, cwd=source, stdout=log, stderr=subprocess.STDOUT, timeout=600)
if built.returncode:
    raise SystemExit(f'Native build failed with code {built.returncode}; inspect retained build log.')
decompiler = DEST / 'Ghidra/Features/Decompiler/os/mac_arm_64/decompile'
decompiler.parent.mkdir(parents=True, exist_ok=True)
if decompiler.exists() or decompiler.is_symlink():
    raise SystemExit('Refusing to replace an existing native decompiler.')
subprocess.run(['/usr/bin/install', '-m', '755', str(source / 'ghidra_opt'), str(decompiler)], check=True)
report = {
    'status': 'installed-native-decompiler-built-provider-calibration-pending',
    'archive_source': 'https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_12.1.4_build/ghidra_12.1.4_PUBLIC_20260921.zip',
    'release_tag': 'Ghidra_12.1.4_build',
    'archive_size': ARCHIVE.stat().st_size,
    'archive_sha256': digest.hexdigest(),
    'installation': str(DEST),
    'java_home': '/Library/Java/JavaVirtualMachines/jdk-21.jdk/Contents/Home',
    'build_command': command,
    'native_decompiler': str(decompiler),
    'native_decompiler_sha256': hashlib.sha256(decompiler.read_bytes()).hexdigest(),
    'native_decompiler_file': subprocess.check_output(['/usr/bin/file', str(decompiler)], text=True).strip(),
    'official_build_docs': 'https://github.com/NationalSecurityAgency/ghidra/blob/Ghidra_12.1.4_build/GhidraDocs/GettingStarted.md#building-native-components',
    'official_makefile': 'https://github.com/NationalSecurityAgency/ghidra/blob/Ghidra_12.1.4_build/Ghidra/Features/Decompiler/src/decompile/cpp/Makefile',
    'provider_recipe': 'https://github.com/morluto/rea/blob/main/docs/installation.md#macos-arm64-native-decompiler',
    'scope': 'Tool installation only; no Cubase target behavior or equivalence established.'
}
(EVIDENCE / 'ghidra-install-report.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2), flush=True)
