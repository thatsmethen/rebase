"""Advance live APP019 status only after APP020 final acceptance; preserve history.

This script is prepared separately from acceptance. All inputs and old status
documents are checked before writing the four live status files.
"""
from pathlib import Path
import copy
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BEFORE = ROOT / 'research/status-history/APP020-before'
BASELINE = {
    'README.md': '7131a641d008609be9e8db9871094b89719369817c8078d62cdb3fa5506adeb6',
    'research/study.json': 'dde5d9df0d9ae895d08ee040ba660a30e1913d3bd02ed2815d04321a20831e00',
    'research/coverage.json': 'e368c43bf9a0c82e4fd82eb0d732ca859a9ebb803dbfe9412bc719f1c7d7c0db',
    'research/rea-steering.json': '35b70172df2d2754a3d45163cb257d197e91ce487120b888eb0bc9d4b88b302b',
}
EXECUTABLE_SHA = 'e4073f77dc5296362256ad388dd176ef6f3ffc33843a89f9c5b149f76f59e528'
NATIVE_SHA = 'd77daf2de0721ed483e554e0f3f1004cbb6127361072c1c32767c38fa3c1bff5'


def load(path):
    return json.loads(path.read_text())


def sha(content):
    return hashlib.sha256(content).hexdigest()


def check_record(row, path):
    assert row['path'] == str(path.relative_to(ROOT)), row
    content = path.read_bytes()
    assert row['sha256'] == sha(content), row
    assert 'bytes' not in row or row['bytes'] == len(content), row


def append_unique(values, additions):
    return values + [item for item in additions if item not in values]


def main():
    old = {}
    for relative, digest in BASELINE.items():
        content = (ROOT / relative).read_bytes()
        assert sha(content) == digest, f'Live status is no longer the reviewed APP019 baseline: {relative}'
        assert (BEFORE / relative).read_bytes() == content, f'Historical snapshot mismatch: {relative}'
        old[relative] = content
    validation = load(HERE / 'application-validation.json')
    test = load(HERE / 'core-test-run.json')
    release = load(HERE / 'release-build.json')
    observed = load(HERE / 'gui-observations.json')
    independent = load(HERE / 'gui-independent-check.json')
    binary = release['executable']
    assert (validation['id'], validation['version'], validation['build']) == ('APP020', '0.20.0', 20)
    assert validation['full_fidelity_objective'] == 'incomplete'
    assert validation['target_executions'] == validation['cubase_runtime_comparisons'] == 0
    assert (test['tests'], test['suites']) == (301, 47)
    assert test['exit_code'] == 0 and test['source_unchanged'] and test['binaries_unchanged']
    assert (validation['tests']['passed'], validation['tests']['suites'], validation['source_entries']) == (301, 47, 277)
    check_record(validation['tests']['record'], HERE / 'core-test-run.json')
    check_record(test['log'], HERE / 'core-tests.log')
    check_record(validation['release_build'], HERE / 'release-build.json')
    assert release['exit_code'] == 0 and release['source_unchanged']
    assert binary['bytes'] == 5_229_008 and binary['sha256'] == EXECUTABLE_SHA
    check_record(binary, HERE / 'final-build-snapshot/Rebase.app/Contents/MacOS/Rebase')
    assert validation['executable'] == binary and observed['executable'] == binary
    assert observed['final_release'] is True and independent['status'] == 'passed'
    check_record(validation['gui']['observations'], HERE / 'gui-observations.json')
    check_record(validation['gui']['independent_review'], HERE / 'gui-independent-check.json')
    names = [group.get('name', group.get('id')) for group in observed['groups']]
    assert names and all(isinstance(name, str) and name for name in names)
    assert len(names) == len(set(names)) and sorted(names) == sorted(independent['expected_group_names'])
    assert len(names) == observed['groups_passed'] == validation['gui']['groups']
    assert all(group.get('result', group.get('status', 'passed')) == 'passed' for group in observed['groups'])
    package_files = observed['package_files_unchanged']
    assert package_files == validation['gui']['packages']['files'] and package_files > 0
    evidence_count = validation['gui']['evidence_records']
    assert evidence_count == len(independent['gui_evidence'])

    record = 'research/evidence/application/APP020/application-validation.json'
    native = ['research/evidence/cubase-static/cpr-audio-events-001/track-contributors/finding.json']
    assert sha((ROOT / native[0]).read_bytes()) == NATIVE_SHA
    evidence = [record, 'research/evidence/application/APP020/core-test-run.json',
        'research/evidence/application/APP020/gui-observations.json',
        'research/evidence/application/APP020/gui-independent-check.json',
        'research/evidence/application/APP020/track-contributors-independent-review.json',
        'research/evidence/application/APP020/track-application-independent-review.json',
        'research/evidence/application/APP020/sealer-independent-review.json'] + native
    assert all((ROOT / path).is_file() for path in evidence)
    scope = (
        'Fresh counted contributor inventory is separate from frozen V1-V5 recovery and retains every '
        'visited child identity, serialized order and ownership. Complete chronological disjoint source-track '
        'audition now requires every counted child of one direct audio track to be a supported original '
        'event, still retained on its imported track, with matching source proof and attached media. '
        'Unknown, nested, duplicate, missing, removed or extra contributors reject the whole operation. '
        'Native canonical ranges and reader windows must already be chronological and nonoverlapping; '
        'the app never sorts an arbitrary source order into admission. A shared immutable saved CPR clock '
        'drives all events while each accessor retains its file rate, exact source offsets and event gain. '
        'The fresh root mode0/filter/attribute context is explicit reconstruction policy, not recovered '
        'hosted state. All media hashes, full source capacity and aggregate sample budget are checked '
        'before transport installation. Gaps, boundary seeks and live transport use the existing direct '
        'timeline reader. Editable project playback remains guarded; original CPRs, historical reports '
        'and project files are not rewritten by inspection/audition.')
    build = (f"Rebase 0.20.0 build 20 compiled, packaged and signed; executable {binary['bytes']} bytes, "
        f"SHA256 {binary['sha256']}. All {test['tests']} tests in {test['suites']} suites passed with "
        f"{validation['source_entries']} unchanged source entries and pre/post-identical preserved debug/test binaries. "
        'The final release has a separate immutable snapshot.')
    gui = (f"{len(names)} final-release GUI groups passed: {'; '.join(names)}. Independent review checked "
        f"{evidence_count} retained records; {package_files} QA package files stayed unchanged. Group scope and "
        'retained limitations are in the final observations. Engine telemetry is not DAC capture, Cubase '
        'execution or a reference-output comparison.')
    boundaries = [
        'Complete counted source membership is not complete channel or project acoustic fidelity; routing, inserts, sends, automation, mixer gains and other project contributors remain unresolved.',
        'Unsorted or overlapping events, priority/split normalization, explicit fades, effective automatic fades and nested containers remain outside admission.',
        'Fresh root mode0, flags, attributes and nil external predicate are explicit reconstruction conditions; saved source state does not establish hosted callbacks, provider mutation, effective engine or device rate.',
        'Multi-event symbolic fixtures have self-authored minimal ancillary bodies and validate app parsing/sample composition, not native-valid CPR restoration or Cubase output.',
        'Different saved/source clocks retain raw frame consumption and can change speed and pitch. No automatic resampler or missing-frame padding is inserted.',
        'Proprietary target executions and Cubase runtime comparisons remain zero; full product fidelity is incomplete.',
    ]
    milestone = dict(id='APP020', status='tested_packaged_application_milestone', version='0.20.0',
        validation_record=record, swift_test_methods_passed=301, test_suites=47,
        source_unchanged_during_full_suite=True, implementation=[scope], native_findings=native,
        gui_validation_status=gui, remaining_boundaries=boundaries)

    study = json.loads(old['research/study.json'])
    application = study['application']
    assert application['version'] == '0.19.0' and application['development_milestone']['id'] == 'APP019'
    application['validation_history'].append({key: copy.deepcopy(application[key]) for key in [
        'version', 'build_executable_sha256', 'implementation_test_count', 'implementation_test_suites',
        'implementation_test_log', 'implementation_test_log_sha256', 'validation_record']})
    application.setdefault('development_history', []).append(copy.deepcopy(application['development_milestone']))
    application['development_milestone'] = copy.deepcopy(milestone)
    application.update(version='0.20.0', implementation_test_count=301, implementation_test_suites=47,
        implementation_test_log=test['log']['path'], implementation_test_log_sha256=test['log']['sha256'],
        previous_validation_record=application['validation_record'], validation_record=record,
        implementation_checks='research/evidence/application/APP020', build_executable_sha256=binary['sha256'],
        build_status=build, gui_validation_status=gui,
        checkpoint_scope='Current packaged checkpoint APP020; earlier application/development records retain their original scope.',
        evidence_boundary=f"301 own-implementation tests and {len(names)} bounded final-release GUI groups; zero Cubase runtime comparisons and no complete-product conformance.")
    application['implemented'].append(scope)
    application['implementation_evidence'] = append_unique(application['implementation_evidence'], evidence)
    application['complete_track_source_audition_status'] = scope

    coverage = json.loads(old['research/coverage.json'])
    assert coverage['application_iteration']['id'] == 'APP019' and coverage['development_milestone']['id'] == 'APP019'
    coverage['previous_application_iterations'].append(copy.deepcopy(coverage['application_iteration']))
    coverage.setdefault('previous_development_milestones', []).append(copy.deepcopy(coverage['development_milestone']))
    coverage['development_milestone'] = copy.deepcopy(milestone)
    coverage['application_iteration'] = dict(id='APP020', version='0.20.0', validation_record=record,
        swift_test_methods_passed=301, test_suites=47, test_log=test['log']['path'], test_log_sha256=test['log']['sha256'],
        scope=scope, implementation_evidence=evidence, build_executable_sha256=binary['sha256'],
        gui_validation_status=gui, release_verification_status=build)
    coverage['application_iteration_scope'] = 'APP020 current packaged checkpoint; earlier iteration/development records remain historical.'
    for domain in coverage['domains']:
        if domain['id'] == 'project-media':
            domain['complete_track_source_audition_update'] = scope

    steering = json.loads(old['research/rea-steering.json'])
    assert steering['iteration_status']['iteration'] == 'APP019' and steering['development_milestone']['id'] == 'APP019'
    steering['previous_iteration_status'].append(copy.deepcopy(steering['iteration_status']))
    steering.setdefault('previous_development_milestones', []).append(copy.deepcopy(steering['development_milestone']))
    steering['development_milestone'] = copy.deepcopy(milestone)
    steering['iteration_status'].update(iteration='APP020', version='0.20.0',
        application='Rebase 0.20.0 complete chronological disjoint source-track audition milestone',
        as_of=validation['created_utc'], application_tests=dict(passed=301, suites=47,
            evidence=test['log']['path'], sha256=test['log']['sha256']),
        evidence=evidence, validation_record=record, gui_validation_status=gui,
        release_verification_status=build, build_executable_sha256=binary['sha256'])
    steering['iteration_status']['implemented_scope'].append(scope)
    steering['iteration_status_scope'] = 'APP020 current packaged checkpoint; full-product fidelity remains incomplete.'
    priority = steering['next_priorities'][0]
    assert priority['id'] == 'native-complete-direct-track-playback'
    priority.update(id='native-track-overlap-priority-fades',
        question='How do native overlap priority, split/reinsert normalization, explicit fades and automatic fades extend complete counted source-track playback beyond chronological disjoint events?',
        action='Trace concrete collector/normalizer and fade consumers with original instruction ownership and independent boundary controls. Preserve counted membership and order, then implement the recovered overlap/tie/split and fade rules in the app with per-sample composition checks. Continue toward hosted channel/routing and complete project playback rather than treating source audition as completion.',
        implementation_gate='APP020 admits every supported contributor on one direct chronological disjoint source track under an explicit fresh root mode0 context. Do not promote that condition to restored hosted filtering or channel/mixer equivalence. Preserve exact native arithmetic, complete media capacity and rejection of any unaccounted contributor.',
        historical_compatibility='Frozen V1-V5 reports and preserved originals remain replayable under their own profiles. Fresh inventory, inspection and audition must not rewrite historical reports or edited current projects.')
    priority['starting_evidence'] = append_unique(priority['starting_evidence'], evidence)
    # Existing host-factor and differing-rate priorities remain active and unchanged.

    readme = old['README.md'].decode()
    start = readme.index('The latest packaged application is ')
    end = readme.index('\nAn active scientific investigation', start)
    paragraph = f'''The latest packaged application is **Rebase 0.20.0**. Complete source-track
audition now includes every supported event on a direct audio track, in its saved
order, with gaps and exact source offsets. It uses the saved CPR clock while each
file keeps its own rate. Every counted contributor and media binding must pass;
unknown, missing, removed or overlapping contributors cannot silently disappear.

The admitted track has chronological, disjoint ranges, supported plain events
and no active fades. A fresh default filtering context is explicitly reconstructed;
live Cubase state is not restored. Project effects, mixer, routing and automation
remain outside this source audition. Historical reports and current projects are
not rewritten, and ordinary project playback remains guarded.

All **301 tests in 47 suites** pass. Final acceptance records **{len(names)} bounded
GUI groups** and **{package_files} unchanged QA package files**. The signed release,
source and fixed test binaries have preserved identities.
See [APP020 validation](research/evidence/application/APP020/application-validation.json).

The multi-event controls test app parsing and exact sample composition; their
minimal ancillary objects are not proved native-valid CPR data. Overlap priority,
fades, hosted filtering, channel routing and full project playback remain unfinished.
**Cubase runtime comparisons remain zero; full reconstruction is not established.**
'''
    readme = readme[:start] + paragraph + readme[end:]

    prepared = {'README.md': readme.encode()}
    for relative, document in [('research/study.json', study), ('research/coverage.json', coverage),
                               ('research/rea-steering.json', steering)]:
        prepared[relative] = (json.dumps(document, indent=2, ensure_ascii=False) + '\n').encode()
    for relative in BASELINE:
        assert (ROOT / relative).read_bytes() == old[relative]
        assert (BEFORE / relative).read_bytes() == old[relative]
    for relative, content in prepared.items():
        (ROOT / relative).write_bytes(content)
    print(json.dumps(dict(updated=[dict(path=path, bytes=len(value), sha256=sha(value))
                                  for path, value in prepared.items()], gui_groups=len(names),
                          package_files_unchanged=package_files)))


if __name__ == '__main__':
    main()
