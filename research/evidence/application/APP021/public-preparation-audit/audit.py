#!/usr/bin/env python3
"""Read-only inventory of a prepared share tree and every reachable Git blob.

Writes its report outside the inspected checkout. Heuristics identify material
for review; they do not establish publication rights or prove no secret exists.
"""
from pathlib import Path
from collections import defaultdict
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys

repo = Path(sys.argv[1])
output = Path(sys.argv[2])
archive = Path('/workspace/rebase')
def git(*args):
    return subprocess.check_output(['git', '-C', str(repo), *args])
def sha(data): return hashlib.sha256(data).hexdigest()
head_before = git('rev-parse', 'HEAD').decode().strip()
refs_before = git('show-ref').decode().splitlines()
commits = git('rev-list', '--all').decode().splitlines()
paths_by_blob = defaultdict(set)
historical_paths = set()
modes = defaultdict(set)
for commit in commits:
    for row in git('ls-tree', '-rz', '--full-tree', commit).split(b'\0'):
        if not row: continue
        metadata, path = row.split(b'\t', 1)
        mode, kind, oid = metadata.decode().split()
        path = path.decode()
        historical_paths.add(path)
        modes[mode].add(path)
        if kind == 'blob': paths_by_blob[oid].add(path)
oids = sorted(paths_by_blob)
batch = subprocess.run(['git', '-C', str(repo), 'cat-file', '--batch'],
    input=('\n'.join(oids) + '\n').encode(), stdout=subprocess.PIPE, check=True).stdout
blobs = {}
offset = 0
for oid in oids:
    end = batch.index(b'\n', offset)
    actual, kind, length = batch[offset:end].decode().split()
    assert actual == oid and kind == 'blob'
    offset = end + 1
    length = int(length)
    blobs[oid] = batch[offset:offset + length]
    offset += length + 1
assert offset == len(batch)

patterns = {
    'requested_names': re.compile(rb'cubase|steinberg', re.I),
    'native_disassembly_rows': re.compile(rb'^\s*(?:0x)?1[0-9a-f]{8}:?\s+(?:[0-9a-f]{2}\s+){4}', re.I | re.M),
    'native_payload_keys': re.compile(rb'"(?:original_word|bytes_hex|instruction_checks)"\s*:'),
    'private_key': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    'github_token': re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})\b'),
    'service_api_key': re.compile(rb'\b(?:sk-proj-|sk-svcacct-|sk-ant-|sk-)[A-Za-z0-9_-]{32,}\b|\bAIza[A-Za-z0-9_-]{30,}\b'),
    'credential_assignment': re.compile(rb'(?i)(?:api[_-]?key|access[_-]?token|client[_-]?secret)\s*[:=]\s*[\"\'][A-Za-z0-9_./+\-=]{16,}[\"\']'),
    'aws_access_key': re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'slack_token': re.compile(rb'\bxox[baprs]-[A-Za-z0-9-]{20,}\b'),
    'url_password': re.compile(rb'https?://[^\s/:]{1,80}:[^\s/@]{5,160}@'),
    'personal_absolute_path': re.compile(rb'/(?:Users|home)/[A-Za-z0-9_.-]+/'),
    'reference_research_paths': re.compile(rb'(?:research/(?:targets|evidence)|evidence/(?:cpr-static|application)|full-reference)'),
}
magic = {
    b'\xcf\xfa\xed\xfe': 'Mach-O', b'\xce\xfa\xed\xfe': 'Mach-O',
    b'\xfe\xed\xfa\xcf': 'Mach-O', b'\xfe\xed\xfa\xce': 'Mach-O',
    b'\xca\xfe\xba\xbe': 'fat-or-Java', b'\xca\xfe\xba\xbf': 'fat-Mach-O',
    b'\x7fELF': 'ELF', b'PK\x03\x04': 'ZIP', b'RIFF': 'RIFF', b'xar!': 'XAR',
}
def scan(items):
    hits = {name: [] for name in patterns}
    binary = []
    records = []
    for key, paths, data in items:
        decoded = True
        try: data.decode('utf-8')
        except UnicodeDecodeError: decoded = False
        recognized = next((label for prefix, label in magic.items() if data.startswith(prefix)), None)
        if recognized or not decoded or b'\0' in data:
            binary.append({'identity': key, 'paths': paths, 'bytes': len(data),
                'kind': recognized or 'non-UTF8-or-NUL'})
        for name, expression in patterns.items():
            matches = list(expression.finditer(data))
            if matches:
                hits[name].append({'identity': key, 'paths': paths, 'count': len(matches),
                    'lines': sorted(set(data[:m.start()].count(b'\n') + 1 for m in matches))})
        records.append({'identity': key, 'paths': paths, 'bytes': len(data), 'sha256': sha(data)})
    return {'files_or_blobs': records, 'hits': hits, 'binary_candidates': binary}
historical = scan((oid, sorted(paths_by_blob[oid]), blobs[oid]) for oid in oids)
current_names = sorted(set(x.decode() for x in git('ls-files', '-z', '--cached', '--others', '--exclude-standard').split(b'\0') if x))
current_items = []
missing = []
for name in current_names:
    path = repo / name
    if path.is_symlink(): current_items.append((name, [name], os.readlink(path).encode()))
    elif path.is_file(): current_items.append((name, [name], path.read_bytes()))
    else: missing.append(name)
current = scan(current_items)
commit_records = []
commit_hits = defaultdict(list)
for commit in commits:
    data = git('cat-file', 'commit', commit)
    commit_records.append({'oid': commit, 'bytes': len(data), 'sha256': sha(data)})
    for name, expression in patterns.items():
        if expression.search(data): commit_hits[name].append(commit)
identities = git('log', '--all', '--format=%an <%ae>|%cn <%ce>').decode().splitlines()
identity_summary = [{'identity_sha256': sha(value.encode()), 'commit_count': identities.count(value),
    'uses_noreply_email': 'noreply' in value.lower()} for value in sorted(set(identities))]

license_paths = [
    'Application/ThirdParty/SOXR-NOTICES.txt',
    'Application/ThirdParty/soxr-0.1.3/LICENCE',
    'Application/ThirdParty/soxr-0.1.3/COPYING.LGPL',
    'Application/ThirdParty/soxr-0.1.3/lsr-tests/COPYING',
    'Application/ThirdParty/soxr-0.1.3/src/fft4g.c',
    'Application/ThirdParty/soxr-0.1.3/src/pffft.c',
    'Application/ThirdParty/soxr-0.1.3/src/pffft.h',
]
licenses = []
for name in license_paths:
    original = (archive / name).read_bytes()
    now = (repo / name).read_bytes()
    historical_versions = [(oid, data) for oid, data in blobs.items() if name in paths_by_blob[oid]]
    licenses.append({'path': name, 'current_sha256': sha(now), 'archive_sha256': sha(original),
        'current_matches_archive': now == original, 'historical_version_count': len(historical_versions),
        'all_historical_versions_match_archive': all(data == original for _, data in historical_versions)})
manifest = json.loads((repo / 'Application/ThirdParty/soxr-source-manifest.json').read_text())
source_mismatches = []
for row in manifest['files']:
    path = repo / 'Application/ThirdParty/soxr-0.1.3' / row['path']
    if 'sha256' in row and (not path.is_file() or sha(path.read_bytes()) != row['sha256']):
        source_mismatches.append(row['path'])
    if 'symlink' in row and (not path.is_symlink() or os.readlink(path) != row['symlink']):
        source_mismatches.append(row['path'])
expected_soxr = {row['path'] for row in manifest['files']}
actual_soxr = {str(p.relative_to(repo / 'Application/ThirdParty/soxr-0.1.3'))
    for p in (repo / 'Application/ThirdParty/soxr-0.1.3').rglob('*') if p.is_file() or p.is_symlink()}

changed_current = []
for name, paths, data in current_items:
    path = repo / name
    after = os.readlink(path).encode() if path.is_symlink() else path.read_bytes() if path.is_file() else None
    if data != after: changed_current.append(name)
current_names_after = sorted(set(x.decode() for x in git('ls-files', '-z', '--cached', '--others', '--exclude-standard').split(b'\0') if x))
head_after = git('rev-parse', 'HEAD').decode().strip()
refs_after = git('show-ref').decode().splitlines()
result = {
    'kind': 'read-only technical publication inventory; not legal certification',
    'generated_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'repository': str(repo), 'head_before': head_before, 'head_after': head_after,
    'refs_before': refs_before, 'refs_after': refs_after,
    'history_stable_during_audit': head_before == head_after and refs_before == refs_after,
    'commit_count': len(commits), 'historical_path_count': len(historical_paths),
    'historical_paths': sorted(historical_paths), 'historical': historical,
    'requested_name_path_hits': sorted(name for name in historical_paths | set(current_names) if patterns['requested_names'].search(name.encode())),
    'historical_non_application_paths': sorted(name for name in historical_paths if not name.startswith('Application/') and name not in ['README.md', '.gitignore']),
    'current_non_application_paths': sorted(name for name in current_names if not name.startswith('Application/') and name not in ['README.md', '.gitignore']),
    'artifact_extension_paths': sorted(name for name in historical_paths | set(current_names) if Path(name).suffix.lower() in ['.cpr', '.wav', '.aiff', '.flac', '.dmg', '.pkg', '.dylib', '.so', '.a', '.zip', '.gz', '.bundle', '.png', '.jpg']),
    'current_working_snapshot_stable': not changed_current and current_names == current_names_after,
    'current_working_files_changed_during_audit': changed_current,
    'current_path_count': len(current_items), 'current_missing_tracked_paths': missing, 'current': current,
    'commit_records': commit_records, 'commit_pattern_hits': dict(commit_hits),
    'commit_identity_summary': identity_summary,
    'required_notices_and_notice_source_comparison': licenses,
    'soxr_source_manifest_file_count': len(manifest['files']),
    'soxr_source_mismatches': source_mismatches,
    'soxr_unmanifested_paths': sorted(actual_soxr - expected_soxr),
    'path_mode_counts': {k: len(v) for k, v in modes.items()},
    'fsck_unreachable_output': git('fsck', '--no-reflogs', '--unreachable', '--no-progress').decode().splitlines(),
    'limits': [
        'Current working files may still be edited by the preparation agent; this is not a final frozen-tree audit.',
        'Known credential pattern absence is heuristic, not a proof that no possible secret exists.',
        'Static interoperability implementations and mathematical constants retain their research provenance.',
        'Neutral names cannot prevent indexing of a public repository or establish publication rights.',
        'Old copies previously pushed to a remote are outside this local reachable-object inventory.'
    ]
}
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({'output': str(output), 'sha256': sha(output.read_bytes()),
    'commits': len(commits), 'historical_blobs': len(blobs), 'current_files': len(current_items),
    'history_hit_counts': {k: len(v) for k, v in historical['hits'].items()},
    'current_hit_counts': {k: len(v) for k, v in current['hits'].items()},
    'binary_candidates': len(historical['binary_candidates']) + len(current['binary_candidates']),
    'notices_match': all(x['current_matches_archive'] and x['all_historical_versions_match_archive'] for x in licenses),
    'soxr_source_mismatches': len(source_mismatches)}))
