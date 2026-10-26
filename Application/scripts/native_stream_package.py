"""Bind the final staged native stream DLL to executed, source-bound CI evidence.

This is a read-only byte/export guard. It neither loads the DLL nor opens a
Windows endpoint. Authored tests replace only the PE inspector; production uses
pefile on the exact immutable byte string whose digest was checked.
"""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import stat


STREAM_EXPORTS = tuple('rb_audio_stream_' + name for name in
                       ('begin', 'submit', 'finish', 'play', 'pause', 'cancel', 'status'))
PRODUCTS = {'RebaseWindowsAudio.dll', 'RebaseWindowsAudio.lib', 'rebase_wasapi_probe.exe'}
COMMANDS = ('compiler-version', 'cmake-version', 'build-pinned-soxr', 'configure', 'build',
            'lifecycle-ctest', 'lifecycle-controls', 'rate-conversion-controls',
            'bounded-stream-controls', 'endpoint-probe')


def _require(condition, message):
    if not condition:
        raise ValueError('Native stream package: ' + message)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _redirected(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def _directory(path):
    path = Path(path).absolute()
    for part in reversed((path, *path.parents)):
        info = part.lstat()
        _require(stat.S_ISDIR(info.st_mode) and not _redirected(info), 'directory is redirected or irregular')
    return path


def _file(root, name, limit):
    parts = name.split('/')
    _require(all(part and part not in ('.', '..') and ':' not in part and '\\' not in part for part in parts),
             'invalid evidence path')
    parent = root
    for part in parts[:-1]:
        parent = _directory(parent / part)
    path = parent / parts[-1]
    before = path.lstat()
    _require(stat.S_ISREG(before.st_mode) and not _redirected(before), 'file is redirected or irregular')
    _require(0 <= before.st_size <= limit, 'input exceeds its bounded size')
    data = path.read_bytes()
    after = path.lstat()
    _require(not _redirected(after) and stat.S_ISREG(after.st_mode)
             and before.st_size == len(data) == after.st_size
             and before.st_mtime_ns == after.st_mtime_ns and before.st_ino == after.st_ino,
             'input changed during inspection')
    return data


def _json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, 'duplicate JSON field')
            result[key] = value
        return result
    def constant(_):
        raise ValueError('Native stream package: nonfinite JSON')
    value = json.loads(data, object_pairs_hook=pairs, parse_constant=constant)
    _require(isinstance(value, dict), 'JSON root is not an object')
    return value


def _same_json(left, right):
    return json.dumps(left, sort_keys=True, separators=(",", ":"), allow_nan=False) == json.dumps(right, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _native_gate():
    specification = importlib.util.spec_from_file_location(
        'rebase_native_stream_package_ci', Path(__file__).with_name('run-windows-native-audio-ci.py'))
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _inspect_pe(data):
    import pefile  # Pinned packaging dependency; no fallback inspector in production.
    with pefile.PE(data=data, fast_load=True) as image:
        image.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT']])
        symbols = []
        for symbol in getattr(getattr(image, 'DIRECTORY_ENTRY_EXPORT', None), 'symbols', []):
            if symbol.name is None:
                continue
            executable = any(section.Characteristics & 0x20000000
                             and section.VirtualAddress <= symbol.address < section.VirtualAddress +
                             max(section.Misc_VirtualSize, section.SizeOfRawData)
                             for section in image.sections)
            symbols.append({'name': symbol.name.decode('ascii'), 'rva': symbol.address,
                            'forwarder': None if symbol.forwarder is None else symbol.forwarder.decode('ascii'),
                            'executable': bool(executable)})
        return {'machine': image.FILE_HEADER.Machine, 'magic': image.OPTIONAL_HEADER.Magic,
                'is_dll': bool(image.FILE_HEADER.Characteristics & 0x2000), 'exports': symbols}


def _require_exports(record):
    _require(isinstance(record, dict) and type(record.get('machine')) is int and record['machine'] == 0x8664
             and type(record.get('magic')) is int and record['magic'] == 0x20b and record.get('is_dll') is True,
             'staged product is not an x64 PE32+ DLL')
    rows = record.get('exports')
    _require(isinstance(rows, list) and 0 < len(rows) <= 4096, 'missing or oversized export table')
    names = {}
    for row in rows:
        _require(isinstance(row, dict) and isinstance(row.get('name'), str) and row['name']
                 and row['name'].isascii() and row['name'] not in names, 'duplicate or invalid named export')
        names[row['name']] = row
    for name in STREAM_EXPORTS:
        row = names.get(name)
        _require(row is not None and type(row.get('rva')) is int and row['rva'] > 0
                 and 'forwarder' in row and row['forwarder'] is None and row.get('executable') is True,
                 'required stream export is absent, forwarded, or not executable: ' + name)
    return list(STREAM_EXPORTS)


def validate_native_stream_package(stage: Path, native_evidence: Path, expected_commit: str):
    """Check final staged bytes after publish; return a path-free summary.

    No file is created or modified, no DLL is loaded, and expected_commit must
    identify one exact source commit. Source identity is claimed by the passed
    native CI record and bound here to its actual build product bytes.
    """
    _require(isinstance(expected_commit, str) and re.fullmatch('[0-9a-f]{40}', expected_commit),
             'expected source commit must be a full lowercase SHA')
    stage, evidence = _directory(stage), _directory(native_evidence)
    report_bytes = _file(evidence, 'conformance.json', 1024 * 1024)
    report = _json(report_bytes)
    for field, value in {'schema': 'rebase.windows-native-audio-ci.v1', 'status': 'passed',
                         'configuration': 'Release', 'mode': 'windows-native', 'platform': 'Windows',
                         'commit': expected_commit, 'native_library_built': True,
                         'playback_tested': False, 'audible_output_measured': False}.items():
        _require(type(report.get(field)) is type(value) and report[field] == value,
                 'native build identity/outcome differs: ' + field)
    _require(isinstance(report.get('architecture'), str)
             and report['architecture'].lower() in ('amd64', 'x86_64'), 'native build is not Windows x64')
    _require('error' not in report and 'artifact_sanitization_error' not in report,
             'native report retains a failure')
    commands = report.get('commands')
    _require(isinstance(commands, list) and len(commands) == len(COMMANDS), 'native command sequence incomplete')
    for command, name in zip(commands, COMMANDS):
        _require(isinstance(command, dict) and command.get('name') == name
                 and command.get('log') == name + '.log' and type(command.get('exit_code')) is int
                 and command['exit_code'] in ((0, 77) if name == 'endpoint-probe' else (0,))
                 and command.get('timed_out') is not True, 'native command failed or changed: ' + name)
        _file(evidence, name + '.log', 16 * 1024 * 1024)  # Successful compilers may be silent.
    gate = _native_gate()
    xml = _file(evidence, 'lifecycle.xml', 2 * 1024 * 1024)
    tests = gate.validate_test_xml(io.BytesIO(xml))
    _require(isinstance(report.get('tests'), dict) and set(report['tests']) == set(tests)
             and all(type(report['tests'][key]) is int and report['tests'][key] == value for key, value in tests.items()),
             'reported native test counts differ from executed XML')
    stream_bytes = _file(evidence, 'bounded-stream.json', 1024 * 1024)
    stream = _json(stream_bytes)
    gate.validate_stream_controls(stream)
    embedded = report.get('portable_bounded_stream')
    _require(isinstance(embedded, dict) and _same_json(embedded, stream), 'embedded bounded-stream receipt differs')
    gate.validate_stream_controls(embedded)
    _require(_same_json(_json(_file(evidence, 'bounded-stream-controls.log', 1024 * 1024)), stream),
             'bounded-stream receipt differs from executed output')
    endpoint = _json(_file(evidence, 'endpoint-probe.json', 1024 * 1024))
    _require(type(endpoint.get('schema')) is int and type(endpoint.get('result')) is int, 'endpoint receipt scalar types differ')
    code = commands[-1]['exit_code']
    outcome = gate.validate_endpoint_probe(endpoint, code)
    _require(_same_json(report.get('endpoint_probe'), {'outcome': outcome, 'exit_code': code, 'playback_tested': False}),
             'endpoint summary differs from read-only probe')
    products = report.get('build_products')
    _require(isinstance(products, list) and len(products) == len(PRODUCTS), 'native build products incomplete')
    indexed = {}
    for product in products:
        _require(isinstance(product, dict) and product.get('name') in PRODUCTS and product['name'] not in indexed
                 and type(product.get('bytes')) is int and product['bytes'] > 0
                 and isinstance(product.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', product['sha256']),
                 'invalid or duplicate native product identity')
        indexed[product['name']] = product
    _require(set(indexed) == PRODUCTS, 'native build product set differs')
    dll_name = 'RebaseWindowsAudio.dll'
    product = indexed[dll_name]
    built = _file(evidence, 'build/' + dll_name, 64 * 1024 * 1024)
    staged = _file(stage, dll_name, 64 * 1024 * 1024)
    _require(len(staged) == len(built) == product['bytes'] and staged == built and _sha(staged) == product['sha256'],
             'final staged native DLL differs from the executed build product')
    exports = _require_exports(_inspect_pe(staged))
    return {'schema': 'rebase.native-stream-package.v1', 'status': 'passed', 'commit': expected_commit,
            'configuration': 'Release', 'native_dll': {'name': dll_name, 'bytes': len(staged), 'sha256': _sha(staged)},
            'required_exports': exports, 'native_tests': tests,
            'native_report_sha256': _sha(report_bytes), 'bounded_stream_report_sha256': _sha(stream_bytes),
            'ctest_xml_sha256': _sha(xml), 'dll_loaded_by_guard': False, 'physical_playback_tested': False}
