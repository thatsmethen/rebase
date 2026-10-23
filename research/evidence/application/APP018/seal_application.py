#!/usr/bin/env python3
"""Record APP018 only after fixed-binary tests, final GUI and native custody pass.

No application/target execution or build occurs here. Codesign/otool are read-only.
Historical helpers and evidence are immutable. All output writes are exclusive.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import importlib.util
import json
import os
import plistlib
import re
import shutil
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
APP = ROOT / 'Application/dist/Rebase.app'
BUNDLE = HERE / 'final-build-snapshot/Rebase.app'
SOURCE = HERE / 'final-source-snapshot'
HELPERS = {
    'APP015/seal_application.py': 'b0b259952dc55147600a25b82934fca043b9c1265706662fb8037c92b7c5d102',
    'APP012/seal_application.py': 'b356f42d2b9bd3a707f4071ec412423166035b505102326066cefd84efd6c343',
}
for relative, sha in HELPERS.items():
    assert hashlib.sha256((HERE.parent / relative).read_bytes()).hexdigest() == sha, relative
spec = importlib.util.spec_from_file_location('app018_prior_custody', HERE.parent / 'APP015/seal_application.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
c.REVIEW_PIN_KEYS += ('input_pins', 'evidence_pins')
CAPTURE_SHA = 'dbe98d14e927735e44cecc80c70d368a881550d4d2ec69552110220167a3bb98'
PRIOR_SHA = '2e941f49312d41223fafcf2d314ad49cf59679aea1dc2f8d909b754e192f5292'
DOCUMENTATION_SHA = '4065e5da3bced53d7539bd2abcd7ece22cda7097bbe12cb5a5f557a6a2c7054c'
NATIVE = {
    'builder-rate-provider': ('f6448e5a71e2110f70246febd2d66c6b7965f97ff23bc9e9075a6abf3c4bc121', '64fa01bc5de7b90c623507d4ae0eb52e5122c6f5bb2b0e24b5e4160b2ea894f3', 376),
    'prepared-stream-rate': ('510aa3182cd3179b2b2e6c8d1dcd76cb40dfe36625e224281c0ff93ff39df9be', '8de873442af33b9f768d48b7cea8d31c4f2dc1b1c7528bf93e47ce547f9628d1', 303),
    'channel-rate-reconciliation': ('95258c04e8174d326e284dff5710a49ddd813ca099965e62f9e7dbab9be2c3a5', 'ebebedc2afafb3f5af440bb54e15e4cea02cf64c40a089933a16e82d90e17aa3', 362),
    'file-backend-format': ('3a240eed17d150a0d798731abc873e195559fd97c636580e2a836ec1b8b58f44', '55bdc6dd4822a39e4fd73f3b852d2d34ec8721b2a702730c823c9368ee72e0d1', 279),
}
REVIEWS = ('project-clock-independent-review.json', 'project-clock-native-review.json')
STATUS = ('README.md', 'research/study.json', 'research/coverage.json', 'research/rea-steering.json')


def load(path):
    return json.loads(path.read_text())


def require_new(names):
    for name in names:
        assert not os.path.lexists(HERE / name), f'Refusing overwrite: {name}'


def write(name, data):
    with (HERE / name).open('x') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
    return c.record(HERE / name)


def same_content(a, b):
    return c.identity_matches(a, b)


def assert_record_at(row, path):
    assert row['path'] == str(path.relative_to(ROOT)), row
    assert c.matches(path, row), row


def source_matches_capture():
    before = load(HERE / 'test-source-before.json')['files']
    after = load(HERE / 'test-source-after.json')['files']
    assert len({r['path'] for r in before}) == len(before)
    assert before == after
    assert before == [c.record(p) for p in c.application_source_entries()]
    return len(before)


def tests_and_release():
    capture = c.pinned(HERE / 'capture_validation.py', CAPTURE_SHA)
    build = load(HERE / 'test-build.json')
    assert build['command'] == ['sh', 'Application/test-app.sh', '--list-tests']
    assert build['exit_code'] == 0
    assert_record_at(build['log'], HERE / 'test-build.log')
    assert 'Build complete!' in (HERE / 'test-build.log').read_text()
    test = load(HERE / 'core-test-run.json')
    assert test['command'] == ['sh', 'Application/test-app.sh', '--skip-build']
    assert test['exit_code'] == 0 and test['source_unchanged'] is True and test['binaries_unchanged'] is True
    assert test['tests'] == 280 and test['suites'] == 43
    assert_record_at(test['log'], HERE / 'core-tests.log')
    assert re.findall(r'Test run with (\d+) tests in (\d+) suites passed', (HERE / 'core-tests.log').read_text()) == [('280', '43')]
    assert_record_at(test['before'], HERE / 'test-source-before.json')
    assert_record_at(test['after'], HERE / 'test-source-after.json')
    run = load(HERE / 'core-tests.json')
    assert all(test[key] == value for key, value in run.items())
    debug = ROOT / 'Application/.build-tests/arm64-apple-macosx/debug'
    original = [debug / 'Rebase', debug / 'RebasePackageTests.xctest/Contents/MacOS/RebasePackageTests']
    fixed = test['fixed_binaries']
    assert len(fixed) == 2
    for row, path in zip(fixed, original):
        assert row['observed_original_path'] == str(path.relative_to(ROOT))
        saved = HERE / 'test-build-snapshot' / path.name
        assert_record_at(row['snapshot'], saved)
        assert same_content(c.record(path), row['snapshot']), path
    assert {p.name for p in c.entries(HERE / 'test-build-snapshot')} == {p.name for p in original}
    c.check_pinned_records(test)
    release = load(HERE / 'release-build.json')
    assert release['command'] == ['sh', 'Application/build-app.sh'] and release['exit_code'] == 0
    assert release['source_unchanged'] is True
    assert_record_at(release['log'], HERE / 'final-build-release.log')
    assert_record_at(release['source_inventory'], HERE / 'test-source-before.json')
    assert_record_at(release['executable'], BUNDLE / 'Contents/MacOS/Rebase')
    raw = load(HERE / 'final-build-release.json')
    assert all(release[key] == value for key, value in raw.items())
    assert 'Build complete!' in (HERE / 'final-build-release.log').read_text()
    c.check_pinned_records(release)
    return dict(capture_script=capture, test_build=c.record(HERE / 'test-build.json'),
                record=c.record(HERE / 'core-test-run.json'), passed=280, suites=43,
                log=test['log'], fixed_binaries=[r['snapshot'] for r in fixed],
                source_files=source_matches_capture()), release


def bundle_matches_release(release):
    for bundle in (APP, BUNDLE):
        info = plistlib.loads((bundle / 'Contents/Info.plist').read_bytes())
        assert info['CFBundleShortVersionString'] == '0.18.0' and info['CFBundleVersion'] == '18'
        assert same_content(c.record(bundle / 'Contents/MacOS/Rebase'), release['executable'])
    current = {str(p.relative_to(APP)): p for p in c.entries(APP)}
    saved = {str(p.relative_to(BUNDLE)): p for p in c.entries(BUNDLE)}
    assert current.keys() == saved.keys()
    for name, path in current.items():
        assert same_content(c.record(path), c.record(saved[name])), name
    previous_app = c.custody.APP
    try:
        # Package/signature/rpath checks operate on immutable copied bytes.
        c.custody.APP = BUNDLE
        packaging = c.custody.packaging()
    finally:
        c.custody.APP = previous_app
    return len(current), packaging


def native_integrity():
    assert set(NATIVE) == {'builder-rate-provider', 'prepared-stream-rate', 'channel-rate-reconciliation', 'file-backend-format'}
    prior = HERE.parent / 'APP017/artifact-manifest.json'
    c.pinned(prior, PRIOR_SHA)
    roots = [(prior, ROOT, 296)]
    studies = []
    for name, (finding, manifest, count) in NATIVE.items():
        assert finding and manifest and isinstance(count, int) and count > 0, f'Unsealed study: {name}'
        directory = ROOT / 'research/evidence/cubase-static/cpr-audio-events-001' / name
        fr = c.pinned(directory / 'finding.json', finding)
        mr = c.pinned(directory / 'artifact-manifest.json', manifest)
        studies.append(dict(name=name, finding=fr, manifest=mr, files=count))
        roots.append((directory / 'artifact-manifest.json', ROOT, count))
    doc = c.pinned(ROOT / 'research/evidence/cubase-documentation/project-rate-001/finding.json', DOCUMENTATION_SHA)
    c.check_pinned_records(load(ROOT / doc['path']))
    return studies, doc, c.recursive_integrity(roots)


def reviews():
    result = []
    for name in REVIEWS:
        value = load(HERE / name)
        assert value['status'] == 'passed' or value['status'].startswith('no open actionable defect')
        assert not value.get('open_actionable_defects') and not value.get('findings')
        direct = c.check_review_pins(value)
        total = c.check_pinned_records(value)
        assert total >= direct > 0
        result.append(dict(record=c.record(HERE / name), pinned_inputs_checked=total))
    return result


def package_inputs():
    packages, records, count = set(), [], 0
    for name in ('gui-inputs.json', 'gui-capacity-inputs.json'):
        value = load(HERE / name)
        rows = value['files']
        assert rows and len({row['path'] for row in rows}) == len(rows)
        roots = set()
        for row in rows:
            path = ROOT / row['path']
            assert path.is_relative_to(HERE)
            candidates = [p for p in path.parents if p.suffix == '.rebaseproj' and p.is_relative_to(HERE)]
            assert len(candidates) == 1
            roots.add(candidates[0])
            assert c.matches(path, row)
        assert len(roots) == 1
        package = roots.pop()
        assert package not in packages
        packages.add(package)
        assert {str(p.relative_to(ROOT)) for p in c.entries(package)} == {row['path'] for row in rows}
        c.check_pinned_records(value)
        count += len(rows)
        records.append(c.record(HERE / name))
    return dict(packages=len(packages), files=count, baselines=records)


def group_name(group):
    return group.get('name', group.get('id'))


def gui_records(release):
    observed = load(HERE / 'gui-observations.json')
    assert observed['final_release'] is True
    assert_record_at(observed['executable'], BUNDLE / 'Contents/MacOS/Rebase')
    assert same_content(observed['executable'], release['executable'])
    c.check_pinned_records(observed)
    independent = load(HERE / 'gui-independent-check.json')
    assert independent['status'] == 'passed'
    binary = independent['release']['binary']
    assert binary['path'] in {str((BUNDLE / 'Contents/MacOS/Rebase').relative_to(ROOT)), str((APP / 'Contents/MacOS/Rebase').relative_to(ROOT))}
    assert same_content(binary, release['executable'])
    assert independent['tests']['passed'] == 280 and independent['tests']['suites'] == 43
    assert_record_at(independent['tests']['log'], HERE / 'core-tests.log')
    expected = independent['expected_group_names']
    assert expected and len(set(expected)) == len(expected)
    assert sorted(group_name(g) for g in independent['groups']) == sorted(expected)
    assert sorted(group_name(g) for g in observed['groups']) == sorted(expected)
    assert observed['groups_passed'] == len(expected)
    for group in observed['groups']:
        assert group.get('result', group.get('status', 'passed')) == 'passed'
    evidence = independent['gui_evidence']
    assert evidence and len({r['path'] for r in evidence}) == len(evidence)
    for row in evidence:
        assert (ROOT / row['path']).is_relative_to(HERE)
        assert c.matches(ROOT / row['path'], row)
    for group in independent['groups']:
        assert group['files'] and group['observations']
        for name in group['files']:
            assert any(r['path'] == str((HERE / name).relative_to(ROOT)) for r in evidence), name
    c.check_pinned_records(independent)
    packages = package_inputs()
    assert observed['package_files_unchanged'] == packages['files']
    # A prior binary observation is preserved honestly, never matched to the
    # final mutable dist path or reclassified as a final-release observation.
    initial = load(HERE / 'gui-release-build.json')
    initial_binary = HERE / 'gui-initial-build-snapshot/Rebase.app/Contents/MacOS/Rebase'
    assert same_content(c.record(initial_binary), initial)
    return dict(observations=c.record(HERE / 'gui-observations.json'),
                independent_review=c.record(HERE / 'gui-independent-check.json'),
                groups=len(expected), evidence_records=len(evidence), packages=packages,
                superseded_initial_observation=dict(record=c.record(HERE / 'gui-release-build.json'),
                    executable=c.record(initial_binary), status='superseded initial GUI build; not final acceptance'))


def preflight():
    tests, release = tests_and_release()
    bundle_count, packaging = bundle_matches_release(release)
    reviewed = reviews()
    studies, documentation, integrity = native_integrity()
    gui = gui_records(release)
    return dict(tests=tests, release=release, bundle_entries=bundle_count, packaging=packaging,
                reviews=reviewed, studies=studies, documentation=documentation, integrity=integrity, gui=gui)


def record():
    require_new(['application-validation.json', 'final-source-snapshot', 'final-source-manifest.json',
                 'recursive-integrity.json', 'public-backend-packaging.json'])
    data = preflight()
    # All scientific/test/GUI inputs have passed before any acceptance output.
    SOURCE.mkdir()
    for name in c.SOURCE_DIRECTORIES:
        shutil.copytree(ROOT / 'Application' / name, SOURCE / name, symlinks=True)
    for name in c.SOURCE_FILES:
        shutil.copy2(ROOT / 'Application' / name, SOURCE / name)
    assert c.check_source_inventory(SOURCE) == data['tests']['source_files']
    source_manifest = write('final-source-manifest.json', dict(files=[c.record(p) for p in c.entries(SOURCE)]))
    # Avoid mutable build/application paths as long-term packaging identities.
    data['packaging']['source_manifest'] = c.record(SOURCE / 'ThirdParty/soxr-source-manifest.json')
    packaging = write('public-backend-packaging.json', data['packaging'])
    integrity = write('recursive-integrity.json', data['integrity'])
    value = dict(id='APP018', created_utc=datetime.now(timezone.utc).isoformat(),
        version='0.18.0', build=18, status='explicit_project_clock_source_audition_integrated_and_checked',
        full_fidelity_objective='incomplete', target_executions=0, cubase_runtime_comparisons=0,
        executable=data['release']['executable'], public_library=c.record(BUNDLE / 'Contents/Frameworks/libsoxr.0.dylib'),
        source_manifest=source_manifest, source_entries=data['tests']['source_files'],
        build_inventory_entries=data['bundle_entries'], tests=data['tests'],
        release_build=c.record(HERE / 'release-build.json'), build_log=data['release']['log'],
        gui=data['gui'], independent_reviews=data['reviews'], native_studies=data['studies'],
        documentation=data['documentation'], recursive_integrity=integrity, public_packaging=packaging,
        acceptance_script=c.record(Path(__file__)), helper_inputs=[c.record(HERE.parent / p) for p in HELPERS],
        implemented=[
            'Explicit native direct-reader source-event mode uses supplied integral Rebase project rate and factor1 for builder/reader coordinates while retaining source-rate accessor ownership.',
            'Saved scalar duration/offset and preserved-source native Start clock are replayed separately; no source-rate rewrite, automatic resampling or CPR schema migration occurs.',
            'Separately quantized raw seek/read extent must fit the complete verified source. Positive-short source reads are rejected rather than padded.',
            'Existing selected-event boundaries, immutable source proof, native reader/accessor lifetime and separate event gain remain enforced.'],
        limits=[
            'The supplied project clock is application context, not recovered saved CPR rate or proof of the effective hosted provider/device state.',
            'Ordinary-path admission is conditional on inactive scrub/appropriate channel state and eligible fresh direct source. Prepared/cache/warp/group replacements remain separate.',
            'Different source/output clocks can change speed, pitch and physical source-time consumption. No transparent conformer is silently inserted.',
            'Own engine telemetry and GUI observations are not DAC capture, native callback equivalence or Cubase runtime output.',
            'Full-project MIDI/plugin/routing/mixer/automation behavior, arbitrary nested events and complete product fidelity remain unestablished.'])
    print(json.dumps(write('application-validation.json', value)))


def publication_check():
    publication = load(HERE / 'publication-review.json')
    assert str(publication['status']).startswith('passed')
    assert c.check_review_pins(publication) > 0
    assert c.check_pinned_records(publication) > 0
    found = set()
    def visit(value):
        if isinstance(value, dict):
            if 'path' in value and 'sha256' in value:
                found.add(value['path'])
            for item in value.values(): visit(item)
        elif isinstance(value, list):
            for item in value: visit(item)
    visit(publication)
    assert set(STATUS).issubset(found), 'Final status files must be publication-pinned'
    return c.record(HERE / 'publication-review.json')


def seal():
    require_new(['final-status-snapshot', 'seal-integrity.json', 'artifact-manifest.json', 'final-integrity.json'])
    validation = load(HERE / 'application-validation.json')
    c.check_pinned_records(validation)
    assert_record_at(validation['acceptance_script'], Path(__file__))
    fresh = preflight()
    assert validation['tests'] == fresh['tests'] and validation['gui'] == fresh['gui']
    assert validation['native_studies'] == fresh['studies']
    assert validation['independent_reviews'] == fresh['reviews']
    assert validation['documentation'] == fresh['documentation']
    assert validation['executable'] == fresh['release']['executable']
    c.verify(HERE / 'final-source-manifest.json')
    assert c.check_source_inventory(SOURCE) == validation['source_entries']
    publication = publication_check()
    status = HERE / 'final-status-snapshot'
    status.mkdir()
    for relative in STATUS:
        destination = status / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
        assert c.matches(destination, c.record(ROOT / relative))
    write('seal-integrity.json', dict(recursive_integrity=fresh['integrity'],
        publication_review=publication, validation=c.record(HERE / 'application-validation.json'),
        source_entries=validation['source_entries'], bundle_entries=fresh['bundle_entries'],
        scope='Acceptance-pinned source, fixed test binaries, bundle, GUI, native/prior history and published statuses rechecked.'))
    manifest = write('artifact-manifest.json', dict(id='APP018',
        scope='Immutable local source/build/status and static/test/GUI custody. Private native/proprietary artifacts are not thereby authorized for publication.',
        files=[c.record(p) for p in c.entries(HERE)]))
    checked = c.verify(HERE / 'artifact-manifest.json')
    print(json.dumps(write('final-integrity.json', dict(manifest=manifest,
        validation=c.record(HERE / 'application-validation.json'), sealed=True,
        files_verified=checked['files_checked']))))


def verify():
    final = load(HERE / 'final-integrity.json')
    assert final['sealed'] is True
    assert_record_at(final['manifest'], HERE / 'artifact-manifest.json')
    assert_record_at(final['validation'], HERE / 'application-validation.json')
    checked = c.verify(HERE / 'artifact-manifest.json')
    assert checked['files_checked'] == final['files_verified']
    rows = load(HERE / 'artifact-manifest.json')['files']
    excluded = {HERE / 'artifact-manifest.json', HERE / 'final-integrity.json'}
    assert [c.record(p) for p in c.entries(HERE) if p not in excluded] == rows
    # Archived verification deliberately does not require later mutable source,
    # debug builds or dist/ to equal this historical release.
    _, _, recursive = native_integrity()
    print(json.dumps(dict(passed=True, local=checked, recursive=recursive)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    for option in ('record', 'seal', 'verify', 'preflight'):
        group.add_argument('--' + option, action='store_true')
    args = parser.parse_args()
    if args.record: record()
    elif args.seal: seal()
    elif args.verify: verify()
    else:
        value = preflight()
        print(json.dumps(dict(passed=True, source_entries=value['tests']['source_files'],
            tests=value['tests']['passed'], suites=value['tests']['suites'],
            gui_groups=value['gui']['groups'], recursive=value['integrity'])))
