#!/usr/bin/env python3
"""Independent downloaded candidate verification; no personal values are emitted."""
import collections
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile

from audit_context import load, decode
CONTEXT = load()
ROOT, COMMIT, EVIDENCE, BASE = CONTEXT.root, CONTEXT.commit, CONTEXT.evidence, CONTEXT.output
AUDIT = BASE / 'zip-audit'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def source(relative):
    return CONTEXT.source(relative)

def main():
    archive = CONTEXT.archive
    build = decode((EVIDENCE/'application-build.json').read_text())
    assert build['status'] == 'passed' and build['commit'] == COMMIT
    observed = {'name': archive.name, 'bytes': archive.stat().st_size, 'sha256': sha(archive.read_bytes())}
    assert observed == build['package'], 'Downloaded ZIP identity differs from CI'
    audit = decode((AUDIT/'audit.json').read_text())
    assert not audit['blockers'] and audit['commit'] == COMMIT
    assert audit['zip_sha256'] == observed['sha256']
    assert audit['crc_verified'] and audit['manifest_exact_coverage'] and audit['manifest_all_hashes_match']
    expected = decode(source('Application/Tests/Fixtures/SourceAudition/expected.json'))
    fixture_hashes = {expected[k] for k in ('sourceSHA256','mediaSHA256','outputSHA256','manifestSHA256','reportSHA256')}
    fixture_paths = CONTEXT.paths('Application/Tests/Fixtures/SourceAudition', 'Application/Tests/Fixtures/SourceAuditionModes', 'Application/Tests/Fixtures/SourceStreamTimelines')
    assert any('/SourceStreamTimelines/' in path for path in fixture_paths), 'Committed long stream fixtures missing'
    fixture_hashes.update(sha(source(path)) for path in fixture_paths)
    CONTEXT.bind_gates()
    from structure_window_gate import require_structure_fixture, GENERATOR_FILES
    # Source-relative validators are materialized from the exact audited commit.
    # The independent authored fixture is accepted only if its generator hashes
    # and every byte match the retained actual Windows fixture lock.
    generated, generated_hash, generated_files = require_structure_fixture(CONTEXT.output/'structure-fixture-verification-view',
        {name:sha(source('Application/Tests/SharedCPRAudioTests/'+name)) for name in GENERATOR_FILES})
    assert (EVIDENCE/'structure-fixture-lock.json').read_bytes() == (CONTEXT.structure_fixture/'expected.json').read_bytes()
    fixture_hashes.update(generated_files.values())
    records=[]
    with zipfile.ZipFile(archive) as package:
        reserved={'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}
        for name in package.namelist():
            assert all(part and part not in ('.','..') and part[-1] not in ' .'
                       and part.split('.')[0].upper() not in reserved and not any(ord(char)<32 or char in '<>"|?*' for char in part)
                       for part in name.split('/')), 'Unsafe Windows archive component'
        manifest = decode(package.read('Rebase/package-manifest.json'))
        manifest_files={item['path']:item for item in manifest['files']}
        modules=decode((EVIDENCE/'loaded-modules.json').read_text())
        for group in ('process','helper'):
            assert modules[group]
            for module in modules[group]:
                location=module['location']
                assert location.startswith(('application/','windows/')), 'Unexpected runtime module origin'
                if location.startswith('application/'):
                    assert module['sha256']==manifest_files[location.removeprefix('application/')]['sha256'], 'Loaded module differs from download'
        assert not any(item['sha256'] in fixture_hashes for item in manifest['files']), 'Source test fixture bytes are shipped'
        assert not any('SourceAudition' in name or 'SourceStreamTimelines' in name or 'AuthoredSource.rebaseproj' in name or name.endswith('/SelectedSource.wav') for name in package.namelist()), 'Source fixture path is shipped'
        for name in package.namelist():
            if name.startswith('Rebase/Examples/'):
                path=name.removeprefix('Rebase/')
                data=package.read(name)
                assert data == source('Application/'+path), 'Bundled example differs from committed source'
                records.append({'path':path,'bytes':len(data),'sha256':sha(data)})
        assert len(records) == 7
        assert not any(part.endswith('.rebaseproj') and part != 'Rebase Preview.rebaseproj'
                       for name in package.namelist() for part in name.split('/')), 'Generated smoke project shipped'
        assert not any(name.endswith('/invalid-import-control.wav') for name in package.namelist()), 'Invalid audio smoke path shipped'
        assert not any(row['sha256'] == sha(b'Authored invalid audio control') for row in manifest['files']), 'Invalid audio smoke input shipped'
        manifest_sha=sha(package.read('Rebase/package-manifest.json'))
    baseline=decode(CONTEXT.path_baseline_audit.read_bytes())
    baseline_hashes={item['path']:item['sha256'] for item in baseline['files']}
    known_shapes={item['redacted_structure'] for record in decode(CONTEXT.path_baseline_review.read_bytes()) for item in record['redacted_path_shapes']}
    pattern=re.compile(r'(?:[A-Za-z]:[\\/]a[\\/]rebase[\\/]rebase|[A-Za-z]:[\\/]Users[\\/][^\s\x00"<>]{1,160}|/(?:Users|home)/[^/\s\x00"<>]{1,100})',re.I)
    reviews=[]
    with zipfile.ZipFile(archive) as package:
        for item in audit['reviews']:
            data=package.read(item['path'])
            offset=int(item['encoding'][-1]) if item['encoding'].startswith('utf-16le-offset-') else None
            text=data[offset:].decode('utf-16le','ignore') if offset is not None else data.decode('utf-8','ignore')
            classes=collections.Counter()
            for match in pattern.finditer(text):
                raw=match.group()
                normalized=re.sub(r'([A-Za-z]:[\\/]Users[\\/])[^\\/]+',r'\1<redacted-profile>',raw,flags=re.I)
                assert normalized in known_shapes, 'New source-path shape needs private review'
                if re.match(r'[A-Za-z]:[\\/]a[\\/]rebase[\\/]rebase$',raw,re.I):
                    category='github_hosted_checkout'
                elif '\\AppData\\Local\\Programs\\Swift\\' in normalized:
                    category='github_hosted_runner_profile'
                else:
                    assert item['path'] in ('Rebase/swiftCore.dll','Rebase/swift_StringProcessing.dll')
                    assert sha(data) == baseline_hashes[item['path']], 'Upstream runtime changed; review embedded profile again'
                    category='upstream_runtime_embedded_profile'
                classes[category]+=1
            assert sum(classes.values()) == item['occurrences']
            reviews.append({'file':item['path'].removeprefix('Rebase/'),'classification_counts':dict(classes)})
    result={'schema':'rebase.downloaded-example-source-verification.v1','source_commit':COMMIT,
            'all_source_bytes_match':True,'files':records,'source_fixture_shipped':False,
            'source_fixture_committed_files_checked':len(fixture_paths),'source_fixture_hashes_checked':len(fixture_hashes)}
    CONTEXT.write_once(AUDIT/'example-source-verification.json', (json.dumps(result,indent=2)+'\n').encode())
    summary={'archive':observed,'archive_matches_ci_receipt':True,'source_commit':COMMIT,
             'file_count':audit['file_count'],'uncompressed_bytes':audit['uncompressed_bytes'],
             'crc_verified':True,'safe_unique_relative_archive_paths':True,
             'manifest':{'sha256':manifest_sha,'covered_file_count':audit['file_count']-1,'exact_coverage':True,'all_file_sizes_and_sha256_match':True},
             'source_example_files_verified':len(records),'source_fixture_shipped':False,
             'app_local_loaded_modules_match_download':True,
             'reviewed_source_path_records':reviews,'privacy_blocker_records':0}
    CONTEXT.write_once(AUDIT/'download-summary.json', (json.dumps(summary,indent=2)+'\n').encode())
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
