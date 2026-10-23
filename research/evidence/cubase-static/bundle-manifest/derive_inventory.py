#!/usr/bin/env python3
"""Reproduce a metadata-only inventory; do not execute or copy target content."""
import base64
import collections
import csv
import hashlib
import json
import pathlib
import plistlib
import stat
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[4]
OUT = pathlib.Path(__file__).resolve().parent
SOURCE = ROOT / 'research/targets/downloads/partial-components-01'
CONTENTS = SOURCE / 'components/Cubase 15.app/Contents'
MANIFEST = CONTENTS / '_CodeSignature/CodeResources'
LEDGER = SOURCE / 'components.json'
EXPECTED = 'c7b8e3234e2efefb0c7aa2ddf815d413c69ac710460b6908ccdcfdf655ac2c8e'

def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()

def write_json(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

def convert(value):
    if isinstance(value, bytes):
        return {'data_hex': value.hex(), 'data_bytes': len(value)}
    if isinstance(value, dict):
        return {k: convert(v) for k, v in value.items()}
    if isinstance(value, list):
        return [convert(v) for v in value]
    return value

def rea_decode(value):
    if isinstance(value, dict) and value.get('$plist_type') == 'data':
        return base64.b64decode(value['base64'])
    if isinstance(value, dict):
        return {k: rea_decode(v) for k, v in value.items()}
    if isinstance(value, list):
        return [rea_decode(v) for v in value]
    return value

def safe_relative(name):
    p = pathlib.PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts:
        raise ValueError('Unsafe relative path: ' + name)
    return p

def classify(name):
    parts = safe_relative(name).parts
    if any(p.endswith('.framework') for p in parts):
        return 'frameworks'
    if any(p.endswith('.lproj') for p in parts):
        return 'localization'
    if parts[0] == 'VST3':
        return 'bundled_plugins'
    if parts[0] == 'Components':
        return 'other_components'
    if parts[0] in ('scripts', 'midiremote_factory_scripts'):
        return 'scripts_and_control_definitions'
    if parts[0] == 'MacOS':
        return 'nested_native_libraries'
    if parts[0] == 'Externals':
        return 'external_libraries'
    return 'resources_and_presets'

manifest_bytes = MANIFEST.read_bytes()
ledger_bytes = LEDGER.read_bytes()
assert sha256_bytes(manifest_bytes) == EXPECTED
manifest = plistlib.loads(manifest_bytes)
ledger = json.loads(ledger_bytes)
rea_file = OUT / 'code-resources-plist.json'
rea = json.loads(rea_file.read_text())
assert rea['operation'] == 'inspect_plist'
assert pathlib.Path(rea['parameters']['path']) == MANIFEST
assert rea_decode(rea['normalized_result']['value']) == manifest

records = {}
recovered = []
prefix = 'Cubase 15.app/Contents/'
for record in ledger['complete_records']:
    if not record['path'].startswith(prefix):
        continue
    name = record['path'][len(prefix):]
    safe_relative(name)
    records[name] = record
    if not record['regular_file_written']:
        continue
    path = CONTENTS / name
    for parent in path.parents:
        if parent == CONTENTS:
            break
        assert not parent.is_symlink(), str(parent)
    info = path.lstat()
    assert stat.S_ISREG(info.st_mode), name
    h256, h1 = hashlib.sha256(), hashlib.sha1()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h256.update(chunk)
            h1.update(chunk)
    recovered.append({
        'relative_to_contents': name,
        'bytes': info.st_size,
        'sha256': h256.hexdigest(),
        'sha1': h1.hexdigest(),
        'independently_recovered_and_hashed': True,
        'ledger_declared_bytes': record['declared_bytes'],
        'ledger_sha256': record['sha256'],
        'ledger_size_match': info.st_size == record['declared_bytes'],
        'ledger_sha256_match': h256.hexdigest() == record['sha256'],
        'declared_by_code_resources': name in manifest['files2'] or name in manifest['files'],
    })
recovered_by_path = {r['relative_to_contents']: r for r in recovered}
all_paths = sorted(set(manifest['files']) | set(manifest['files2']))
entries = []
partial_path = ledger['partial_record']['path'].removeprefix(prefix)
for name in all_paths:
    safe_relative(name)
    declarations = {table: manifest[table][name] for table in ('files', 'files2') if name in manifest[table]}
    r = recovered_by_path.get(name)
    checks = []
    for table, d in declarations.items():
        d = {'hash': d} if isinstance(d, bytes) else d
        for field, algorithm in (('hash', 'sha1'), ('hash2', 'sha256')):
            if field in d:
                expected = d[field].hex()
                actual = r[algorithm] if r else None
                checks.append({'table': table, 'field': field, 'algorithm': algorithm,
                               'declared_digest': expected, 'observed_digest': actual,
                               'status': ('match' if actual == expected else 'mismatch') if r else 'not_acquired'})
        if 'cdhash' in d:
            checks.append({'table': table, 'field': 'cdhash', 'declared_cdhash': d['cdhash'].hex(),
                           'status': 'not_compared', 'reason': 'CodeDirectory hash is not a whole-file SHA-256.'})
    entries.append({
        'relative_to_contents': name,
        'declared_by_code_resources': True,
        'declarations': convert(declarations),
        'primary_category': classify(name),
        'top_level': name.split('/')[0],
        'independently_recovered_and_hashed': r is not None,
        'acquisition_status': 'complete_regular_file_rehashed' if r else ('partial_record_not_promoted' if name == partial_path else 'not_in_complete_written_records'),
        'recovered_metadata': r,
        'resource_hash_comparisons': checks,
    })

def grouped(prefix, depth):
    buckets = collections.defaultdict(list)
    for entry in entries:
        name = entry['relative_to_contents']
        if name.startswith(prefix):
            buckets['/'.join(name.split('/')[:depth])].append(entry)
    return [{'relative_group_path': key, 'declared_path_count': len(items),
             'complete_regular_files_rehashed': sum(e['independently_recovered_and_hashed'] for e in items)}
            for key, items in sorted(buckets.items())]

comparisons = [c for e in entries for c in e['resource_hash_comparisons']]
summary = {
    'generated_at_utc': datetime.now(timezone.utc).isoformat(),
    'claim_scope': 'Static manifest declarations and independently rehashed recovered files; not a complete bundle inventory or sealed-bundle verification.',
    'source': {'path_relative_to_project': str(MANIFEST.relative_to(ROOT)), 'bytes': len(manifest_bytes), 'sha256': EXPECTED},
    'recovery_ledger': {'path_relative_to_project': str(LEDGER.relative_to(ROOT)), 'sha256': sha256_bytes(ledger_bytes),
                        'complete_cpio_records': len(ledger['complete_records']),
                        'written_regular_files': len(recovered),
                        'other_complete_records': sum(not r['regular_file_written'] for r in ledger['complete_records']),
                        'all_written_file_sizes_and_hashes_match_ledger': all(r['ledger_size_match'] and r['ledger_sha256_match'] for r in recovered),
                        'source_stream_complete': ledger['gzip_stream_complete'],
                        'cpio_trailer_seen': ledger['cpio_trailer_seen'],
                        'partial_record': ledger['partial_record'], 'stop_reason': ledger['stop_reason']},
    'rea': {'evidence_id': rea['evidence_id'], 'operation': rea['operation'], 'provider': rea['provider'],
            'record_sha256': sha256_bytes(rea_file.read_bytes()),
            'caution': 'REA subject digest identifies the Mach-O anchor, not CodeResources. The manifest digest is recorded separately above.',
            'parameter_path_identifies_manifest': True, 'decoded_value_equals_python_plistlib': True,
            'limitations': rea['limitations'], 'initial_app_target_error': 'Missing app Info.plist; retained in code-resources-plist-incomplete-app-error.json.'},
    'declaration_counts': {'files': len(manifest['files']), 'files2': len(manifest['files2']),
                           'distinct_paths': len(entries), 'intersection': len(set(manifest['files']) & set(manifest['files2'])),
                           'files2_schema_counts': dict(collections.Counter(','.join(sorted(v)) for v in manifest['files2'].values()))},
    'primary_category_definition': 'Exclusive precedence: .framework path, .lproj path, VST3 root, Components root, scripts/midiremote roots, MacOS root, Externals root, remaining resources/presets. Top-level counts and group counts are separate views of the same declarations, not additive totals.',
    'primary_categories': dict(sorted(collections.Counter(e['primary_category'] for e in entries).items())),
    'top_level_path_counts': dict(sorted(collections.Counter(e['top_level'] for e in entries).items())),
    'coverage': {'declared_paths_independently_rehashed': sum(e['independently_recovered_and_hashed'] for e in entries),
                 'declared_paths_without_complete_recovered_file': sum(not e['independently_recovered_and_hashed'] for e in entries),
                 'resource_hash_comparison_statuses': dict(collections.Counter(c['status'] for c in comparisons)),
                 'comparison_count_note': 'Counts compare individual table entries and may count a path twice because files and files2 overlap. The 52 matches are 52 distinct recovered paths in this collection.',
                 'recovered_regular_files_not_explicitly_declared': [r['relative_to_contents'] for r in recovered if not r['declared_by_code_resources']],
                 'resource_hash_match_does_not_authenticate_manifest': True},
    'bundled_plugin_groups': grouped('VST3/', 2),
    'component_groups': grouped('Components/', 2),
    'preset_groups': grouped('presets/', 2),
    'framework_instances': sorted(set(name[:name.index('.framework') + len('.framework')] for name in all_paths if '.framework/' in name)),
    'localization_groups': sorted(set('/'.join(name.split('/')[:i+1]) for name in all_paths for i, part in enumerate(name.split('/')) if part.endswith('.lproj'))),
    'rules': convert({k: manifest[k] for k in ('rules', 'rules2')}),
    'limitations': [
        'The app Info.plist is absent and extraction is incomplete; no complete app or whole-DMG digest is available.',
        'CodeResources is recovered metadata, not independently authenticated as the sealed outer application. Self-consistent file hashes cannot authenticate their source manifest.',
        'A declaration is not proof of file acquisition, availability in a licensed edition, a public API, or observable feature behavior.',
        'The files and files2 tables overlap. Rules can omit items; explicit declaration counts are not an exhaustive expected filesystem count.',
        'Nested cdhash declarations are not raw file digests. Their designated requirements were preserved, not evaluated in this inventory.',
        'Bundle-name counts do not equal plug-in class counts; a bundle can contain many classes. No scripts, plug-ins, app code, or media were executed.',
        'Only metadata was produced; no target art, screenshots, or UI assets were copied or displayed by this inventory task.'
    ],
    'candidate_research_questions': [
        {'priority': 1, 'question': 'What exact contracts are documented by the recovered ModScripter module metadata, documentation and six script examples, and which edge cases can be translated into original, independent test vectors?',
         'evidence_status': 'Several complete files acquired and rehashed; this inventory does not inspect their content or claim host execution semantics.',
         'paths': ['VST3/ModScripter.vst3/Contents/Resources/moduleinfo.json', 'VST3/ModScripter.vst3/Contents/Resources/doc.html', 'VST3/ModScripter.vst3/Contents/Resources/scripts/']},
        {'priority': 2, 'question': 'Once obtained, do MIDI Remote API declarations distinguish stable documented controller contracts from implementation-specific behavior?',
         'evidence_status': 'Declared paths only; none acquired in this recovery ledger.',
         'paths': ['midiremote_factory_scripts/.api/v1/midiremote_api_v1.d.ts', 'midiremote_factory_scripts/.api/v1/midiremote_api_v1.js', 'midiremote_factory_scripts/Public/examplecompany/']},
        {'priority': 3, 'question': 'Once obtained, can logical editor, input transformer, and key-command presets support explicit format hypotheses and malformed-input boundaries?',
         'evidence_status': 'Declared paths only; no format or runtime interpretation inferred.',
         'paths': ['presets/Project Logical Editor/', 'presets/Logical Edit/', 'presets/Input Transformer/', 'presets/KeyCommands/']},
        {'priority': 4, 'question': 'Which import/export and media transformations cross separable component boundaries and need independent round-trip experiments after complete acquisition?',
         'evidence_status': 'Named component declarations only; names are prioritization hints, not confirmed behavior.',
         'paths': ['Components/DAWproject.bundle/', 'Components/AAFfilter.bundle/', 'Components/omffilter.bundle/', 'Components/audiocodecs/']}
    ],
}
assert sha256_bytes(MANIFEST.read_bytes()) == EXPECTED
assert LEDGER.read_bytes() == ledger_bytes, 'Recovery ledger changed during collection'
write_json('path-inventory.json', {'path_base': 'Cubase 15.app/Contents', 'entries': entries})
write_json('recovered-file-metadata.json', {'path_base': 'Cubase 15.app/Contents', 'files': recovered})
write_json('findings.json', summary)
with (OUT / 'path-inventory.csv').open('w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['relative_to_contents', 'category', 'declared_by_code_resources', 'independently_recovered_and_hashed', 'acquisition_status'])
    w.writerows([e['relative_to_contents'], e['primary_category'], True, e['independently_recovered_and_hashed'], e['acquisition_status']] for e in entries)
print(json.dumps({k: summary[k] for k in ('declaration_counts', 'primary_categories', 'coverage')}, indent=2))
