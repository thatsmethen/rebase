"""Validate pinned shared-library inputs and stage the portable Swift runtime.

The CPR mode-2 bridge keeps its existing profile; device adaptation has a
separate caller/profile. No identity substitute or ambient system library is
admitted by these CI/package helpers.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import struct

from windows_soxr_package import (FEATURES, SOURCE_COMMIT, SOURCE_VERSION,
                                  _directory, _file, _json, _source, validate_soxr_build)

MAC_UNITS = {'soxr.c', 'data-io.c', 'dbesi0.c', 'filter.c', 'fft4g64.c',
             'cr.c', 'cr32.c', 'fft4g32.c', 'cr64.c'}


def verify_windows(app, build, commit):
    receipt = validate_soxr_build(app, build, commit)
    build = _directory(build)
    dll = next(row for row in receipt['artifacts'] if row['path'] == 'install/bin/soxr.dll')
    return receipt, build / 'install/lib', build / dll['path'], dll['sha256']


def verify_macos(app, build, commit):
    app, build = _directory(app), _directory(build)
    manifest_bytes, source, _ = _source(app)
    if commit is not None and (not isinstance(commit, str) or re.fullmatch(r'[0-9a-f]{40}', commit) is None):
        raise RuntimeError('Portable SoXR application commit must be exact')
    manifest_bytes_build = _file(build, 'build-manifest.json')
    manifest = _json(manifest_bytes_build)
    expected_options = {'optimization': '-O3 -DNDEBUG', 'fast_math': False, 'fp_contract': 'off',
        'CR32': True, 'CR64': True, 'SIMD': False, 'VR32': False, 'PFFFT': False, 'AVFFT': False,
        'OpenMP': False, 'high_precision_clock': True, 'float_standard_precision_clock': False,
        'developer_trace': False, 'LSR_bindings': False}
    if (manifest.get('commit') != SOURCE_COMMIT or manifest.get('source_version') != SOURCE_VERSION
            or manifest.get('architecture') != 'arm64' or manifest.get('minimum_macos') != '14.0'
            or manifest.get('upstream_dylib_abi_version') != '0.1.2'
            or json.dumps(manifest.get('options'), sort_keys=True) != json.dumps(expected_options, sort_keys=True)):
        raise RuntimeError('Portable SoXR macOS build identity/profile differs')
    expected_source = [{**{key: value for key, value in row.items() if key != 'mode'},
                        'path': 'soxr-0.1.3/' + row['path']}
                       for row in _json(manifest_bytes)['files']]
    if manifest.get('source') != expected_source:
        raise RuntimeError('Portable SoXR recorded source differs from pinned identity')
    library = _file(build, 'install/lib/libsoxr.0.1.2.dylib')
    if (len(library) < 32 or library[:4] != b'\xcf\xfa\xed\xfe'
            or struct.unpack_from('<I', library, 4)[0] != 0x0100000c):
        raise RuntimeError('Portable SoXR library is not the expected arm64 Mach-O')
    compile_bytes = _file(build, 'cmake/compile_commands.json')
    header = _file(build, 'cmake/soxr-config.h')
    for key, data in [('library', library), ('compile_commands', compile_bytes), ('configured_header', header)]:
        row = manifest.get(key, {})
        if type(row.get('bytes')) is not int or row['bytes'] != len(data) or row.get('sha256') != hashlib.sha256(data).hexdigest():
            raise RuntimeError('Portable SoXR recorded artifact differs: ' + key)
    commands = json.loads(compile_bytes)
    if not isinstance(commands, list) or len(commands) != 9:
        raise RuntimeError('Portable SoXR compile profile differs')
    compiled = set()
    for row in commands:
        if not isinstance(row, dict) or not isinstance(row.get('command'), str) or not isinstance(row.get('file'), str):
            raise RuntimeError('Portable SoXR compile record is malformed')
        path = Path(row['file'])
        if path.parent != app / 'ThirdParty/soxr-0.1.3/src' or path.name not in MAC_UNITS or path.name in compiled:
            raise RuntimeError('Portable SoXR compile source differs')
        compiled.add(path.name)
        args = shlex.split(row['command'])
        if (any(flag not in args for flag in ('-fno-fast-math', '-ffp-contract=off', '-O3', '-DNDEBUG', str(path)))
                or any(flag in args for flag in ('-ffast-math', '-Ofast', '-ffp-contract=fast', '-ffp-contract=on'))
                or [x for x in args if re.fullmatch(r'-O[0-9sgz]', x)] != ['-O3']):
            raise RuntimeError('Portable SoXR compile flags differ')
    macros = {key: int(value) for key, value in re.findall(r'^#define ([A-Z0-9_]+) ([01])$', header.decode(), re.MULTILINE)}
    if any(macros.get(key) != value for key, value in FEATURES.items()):
        raise RuntimeError('Portable SoXR configured features differ')
    # Swift's embedded rpath resolves this ABI spelling. Verify the installed
    # alias itself, rather than accepting a different library at the same name.
    for name in ('libsoxr.0.dylib', 'libsoxr.dylib'):
        alias = build / 'install/lib' / name
        if not alias.is_symlink() or os.readlink(alias) not in (
                ('libsoxr.0.1.2.dylib',) if name == 'libsoxr.0.dylib' else ('libsoxr.0.dylib',)):
            raise RuntimeError('Portable SoXR library alias differs')
    receipt = {'schema': 'rebase.portable-soxr-dependency.v1', 'status': 'passed',
        'platform': 'Darwin', 'architecture': 'arm64', 'application_commit': commit,
        'source_version': SOURCE_VERSION, 'source_commit': SOURCE_COMMIT,
        'source_manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
        'source_entries_verified': len(source), 'options': expected_options,
        'library_sha256': hashlib.sha256(library).hexdigest(), 'library_bytes': len(library),
        'compile_commands_sha256': hashlib.sha256(compile_bytes).hexdigest(),
        'build_manifest_sha256': hashlib.sha256(manifest_bytes_build).hexdigest(),
        'configured_header_sha256': hashlib.sha256(header).hexdigest(),
        'scope': 'Pinned public SoXR build; reference-library equivalence unknown'}
    return receipt, build / 'install/lib'


def stage_windows_runtime(runtime, destination, expected_sha256):
    """Copy exact validated DLL bytes beside tests/helper; never replace others."""
    runtime = Path(runtime).absolute()
    data = _file(_directory(runtime.parent), runtime.name)
    if (not isinstance(expected_sha256, str) or re.fullmatch(r'[0-9a-f]{64}', expected_sha256) is None
            or hashlib.sha256(data).hexdigest() != expected_sha256):
        raise RuntimeError('Portable SoXR runtime changed before staging')
    destination = Path(destination).absolute()
    destination.mkdir(parents=True, exist_ok=True)
    destination = _directory(destination)
    target = destination / 'soxr.dll'
    if os.path.lexists(target):
        if _file(destination, 'soxr.dll') != data:
            raise RuntimeError('Portable SoXR runtime destination already contains different bytes')
    else:
        with target.open('xb') as stream:
            stream.write(data)
    if _file(destination, 'soxr.dll') != data:
        raise RuntimeError('Portable SoXR staged runtime changed')
    return {'name': 'soxr.dll', 'bytes': len(data), 'sha256': expected_sha256,
            'location': 'beside portable Swift test and helper executables'}
