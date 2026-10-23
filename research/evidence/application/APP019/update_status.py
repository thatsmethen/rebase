"""Advance live APP018 status only after APP019 final acceptance; preserve history.

This script is prepared separately from acceptance. All inputs and old status
documents are checked before writing the four live status files.
"""
from pathlib import Path
import copy
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BEFORE = ROOT / 'research/status-history/APP019-before'
BASELINE = {
    'README.md': '6238f593562754951cd35a584ac6a3937d19b617163d6b76c787590c37d55e34',
    'research/study.json': '349afc4fde3efe767e6af412e57861433a04d324754fbbfb4c312d33a0464fa3',
    'research/coverage.json': '5d081d86c72a232c9f862d3e35fd3d245a1d8d0a7078d132b1f722066cee72ac',
    'research/rea-steering.json': '7fa7fbe0f46340688f15f1a6cf15ea0341e9e4e9c0426f6a4527dc9e615d75d5',
}
EXECUTABLE_SHA = '1ebf6ad071aae23a79948350840963f17a96a7d6e8a9e5cba753f3ee408b60e2'
NATIVE_SHA = '1d4576dc2679e05206e4aecedf4c1bb695c5beb1a49ceafb689e098d1666cbda'


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
        assert sha(content) == digest, f'Live status is no longer the reviewed APP018 baseline: {relative}'
        assert (BEFORE / relative).read_bytes() == content, f'Historical snapshot mismatch: {relative}'
        old[relative] = content
    validation = load(HERE / 'application-validation.json')
    test = load(HERE / 'core-test-run.json')
    release = load(HERE / 'release-build.json')
    observed = load(HERE / 'gui-observations.json')
    independent = load(HERE / 'gui-independent-check.json')
    binary = release['executable']
    assert (validation['id'], validation['version'], validation['build']) == ('APP019', '0.19.0', 19)
    assert validation['full_fidelity_objective'] == 'incomplete'
    assert validation['target_executions'] == validation['cubase_runtime_comparisons'] == 0
    assert (test['tests'], test['suites']) == (287, 44)
    assert test['exit_code'] == 0 and test['source_unchanged'] and test['binaries_unchanged']
    assert (validation['tests']['passed'], validation['tests']['suites'], validation['source_entries']) == (287, 44, 271)
    check_record(validation['tests']['record'], HERE / 'core-test-run.json')
    check_record(test['log'], HERE / 'core-tests.log')
    check_record(validation['release_build'], HERE / 'release-build.json')
    assert release['exit_code'] == 0 and release['source_unchanged']
    assert binary['bytes'] == 5_077_056 and binary['sha256'] == EXECUTABLE_SHA
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

    record = 'research/evidence/application/APP019/application-validation.json'
    native = ['research/evidence/cubase-static/cpr-audio-events-001/project-audio-setup/finding.json']
    assert sha((ROOT / native[0]).read_bytes()) == NATIVE_SHA
    evidence = [record, 'research/evidence/application/APP019/core-test-run.json',
        'research/evidence/application/APP019/gui-observations.json',
        'research/evidence/application/APP019/gui-independent-check.json',
        'research/evidence/application/APP019/saved-project-clock-independent-review.json',
        'research/evidence/application/APP019/sealer-independent-review.json'] + native
    assert all((ROOT / path).is_file() for path in evidence)
    scope = (
        'Current CPR profile V5 decodes the explicit PArrangement-to-PArrangeSetup attachment and preserves '
        'raw Float32 base-rate and Double factor bits with source-object provenance. New imports use the '
        'saved rate only for an integral base from 10000 to 192000 Hz and exact +1 factor; missing, unknown '
        'or unsupported setup retains a labeled application default, never a native-rate claim. Frozen '
        'V1-V4 imports remain replayable without rewriting originals, reports or current projects. A separate '
        'saved-project-clock source-event mode freshly replays preserved setup and tempo independently of '
        'later Rebase rate or timing edits. Supplied-Rebase-clock and original-rate modes stay distinct; '
        'explicit mode 0/1/2 conversion is unchanged. The source accessor keeps its file rate and existing '
        'event, processing, provenance and full-capacity gates remain. This is bounded source-event audition, '
        'not complete native-track or project playback.')
    build = (f"Rebase 0.19.0 build 19 compiled, packaged and signed; executable {binary['bytes']} bytes, "
        f"SHA256 {binary['sha256']}. All {test['tests']} tests in {test['suites']} suites passed with "
        f"{validation['source_entries']} unchanged source entries and pre/post-identical preserved debug/test binaries. "
        'The final release has a separate immutable snapshot.')
    gui = (f"{len(names)} final-release GUI groups passed: {'; '.join(names)}. Independent review checked "
        f"{evidence_count} retained records; {package_files} QA package files stayed unchanged. Group scope and "
        'retained limitations are in the final observations. Engine telemetry is not DAC capture, Cubase '
        'execution or a reference-output comparison.')
    boundaries = [
        'Saved factor-one configuration does not establish effective hosted, engine or device rate; provider replacement, post-read callbacks and other factors remain separate.',
        'Native clamp fallback, other setup versions, unsupported datum/reference forms and nonfinite or fractional rate configurations are not admitted by the narrower saved-clock policy.',
        'Complete direct-track contributor coverage, event overlap/priority, fades, routing, mixer and automation semantics remain insufficient for ordinary native multi-event/project playback.',
        'Different source/output clocks can change speed, pitch and physical source consumption. No automatic resampler or missing-frame padding is inserted.',
        'Proprietary target executions and Cubase runtime comparisons remain zero; full product fidelity is incomplete.',
    ]
    milestone = dict(id='APP019', status='tested_packaged_application_milestone', version='0.19.0',
        validation_record=record, swift_test_methods_passed=287, test_suites=44,
        source_unchanged_during_full_suite=True, implementation=[scope], native_findings=native,
        gui_validation_status=gui, remaining_boundaries=boundaries)

    study = json.loads(old['research/study.json'])
    application = study['application']
    assert application['version'] == '0.18.0' and application['development_milestone']['id'] == 'APP018'
    application['validation_history'].append({key: copy.deepcopy(application[key]) for key in [
        'version', 'build_executable_sha256', 'implementation_test_count', 'implementation_test_suites',
        'implementation_test_log', 'implementation_test_log_sha256', 'validation_record']})
    application.setdefault('development_history', []).append(copy.deepcopy(application['development_milestone']))
    application['development_milestone'] = copy.deepcopy(milestone)
    application.update(version='0.19.0', implementation_test_count=287, implementation_test_suites=44,
        implementation_test_log=test['log']['path'], implementation_test_log_sha256=test['log']['sha256'],
        previous_validation_record=application['validation_record'], validation_record=record,
        implementation_checks='research/evidence/application/APP019', build_executable_sha256=binary['sha256'],
        build_status=build, gui_validation_status=gui,
        checkpoint_scope='Current packaged checkpoint APP019; earlier application/development records retain their original scope.',
        evidence_boundary=f"287 own-implementation tests and {len(names)} bounded final-release GUI groups; zero Cubase runtime comparisons and no complete-product conformance.")
    application['implemented'].append(scope)
    application['implementation_evidence'] = append_unique(application['implementation_evidence'], evidence)
    application['saved_project_audio_setup_status'] = scope

    coverage = json.loads(old['research/coverage.json'])
    assert coverage['application_iteration']['id'] == 'APP018' and coverage['development_milestone']['id'] == 'APP018'
    coverage['previous_application_iterations'].append(copy.deepcopy(coverage['application_iteration']))
    coverage.setdefault('previous_development_milestones', []).append(copy.deepcopy(coverage['development_milestone']))
    coverage['development_milestone'] = copy.deepcopy(milestone)
    coverage['application_iteration'] = dict(id='APP019', version='0.19.0', validation_record=record,
        swift_test_methods_passed=287, test_suites=44, test_log=test['log']['path'], test_log_sha256=test['log']['sha256'],
        scope=scope, implementation_evidence=evidence, build_executable_sha256=binary['sha256'],
        gui_validation_status=gui, release_verification_status=build)
    coverage['application_iteration_scope'] = 'APP019 current packaged checkpoint; earlier iteration/development records remain historical.'
    for domain in coverage['domains']:
        if domain['id'] == 'project-media':
            domain['saved_project_audio_setup_update'] = scope

    steering = json.loads(old['research/rea-steering.json'])
    assert steering['iteration_status']['iteration'] == 'APP018' and steering['development_milestone']['id'] == 'APP018'
    steering['previous_iteration_status'].append(copy.deepcopy(steering['iteration_status']))
    steering.setdefault('previous_development_milestones', []).append(copy.deepcopy(steering['development_milestone']))
    steering['development_milestone'] = copy.deepcopy(milestone)
    steering['iteration_status'].update(iteration='APP019', version='0.19.0',
        application='Rebase 0.19.0 saved project audio configuration and source-event playback milestone',
        as_of=validation['created_utc'], application_tests=dict(passed=287, suites=44,
            evidence=test['log']['path'], sha256=test['log']['sha256']),
        evidence=evidence, validation_record=record, gui_validation_status=gui,
        release_verification_status=build, build_executable_sha256=binary['sha256'])
    steering['iteration_status']['implemented_scope'].append(scope)
    steering['iteration_status_scope'] = 'APP019 current packaged checkpoint; full-product fidelity remains incomplete.'
    priority = steering['next_priorities'][0]
    priority.update(id='native-complete-direct-track-playback',
        question='How does a complete direct audio track enumerate all audible contributors and resolve overlaps, priority, fades and routing for multi-event playback?',
        action='Bind the counted source-track inventory to native contributor selection, overlap/priority, fade and routing consumers. Use independent source-backed multi-event and missing-contributor controls, including gaps, seeks, boundaries and rejection cases; enable ordinary track playback only when every audible contributor and required processing state is covered.',
        implementation_gate='APP019 recovers bounded saved factor-one audio configuration and retains event-only playback. A valid saved clock does not prove contributor completeness, mixer/routing state or effective hosted configuration. Preserve complete-source capacity checks and refuse unknown contributors rather than silently omit them.',
        historical_compatibility='Frozen V1-V5 reports and preserved originals remain replayable under their own profiles. Fresh inspection/audition must not rewrite historical reports or edited current projects.')
    priority['starting_evidence'] = append_unique(priority['starting_evidence'], evidence)
    host_priority = dict(id='native-host-rate-factors',
        question='When do provider replacement, post-read callbacks and nonunity audio-rate factors change the effective hosted clock relative to saved PArrangeSetup configuration?',
        starting_evidence=native + ['research/evidence/cubase-static/cpr-audio-events-001/builder-rate-provider/finding.json'],
        action='Trace concrete provider and post-read ownership before expanding the saved factor-one source interpretation. Keep saved base rate, effective provider rate and device rate distinct, with independent factor and fallback controls.',
        implementation_gate='Do not treat a persisted base-rate/factor record as proof of runtime provider or device state, and do not silently replace native clamp/factor branches with a generic rate assumption.')
    assert not any(value['id'] == host_priority['id'] for value in steering['next_priorities'])
    steering['next_priorities'].insert(1, host_priority)

    readme = old['README.md'].decode()
    start = readme.index('The latest packaged application is ')
    end = readme.index('\nAn active scientific investigation', start)
    paragraph = f'''The latest packaged application is **Rebase 0.19.0**. New CPR imports use the
saved project audio rate when the typed setup is supported. A separate saved-clock
audition mode also works with older imported packages, replaying their preserved
source independently of later Rebase rate or tempo edits. Historical reports and
current projects are not rewritten.

The admitted setup has an integral base rate of 10–192 kHz and a factor of exactly
+1. Raw rate/factor bits and object provenance remain available; unsupported or
missing setup never silently becomes a native rate. The supplied Rebase-clock,
original-rate and explicit mode 0/1/2 paths remain separate. Source readers retain
the file rate, and playback still rejects windows that exceed complete media.

All **287 tests in 44 suites** pass. Final acceptance records **{len(names)} bounded
GUI groups** and **{package_files} unchanged QA package files**. The signed release,
source and fixed test binaries have preserved identities.
See [APP019 validation](research/evidence/application/APP019/application-validation.json).

This recovers saved factor-one configuration, not an observed hosted or device
clock. Complete track contributors, overlaps, fades, routing and ordinary native
project playback remain unfinished. **Cubase runtime comparisons remain zero;
full reconstruction is not established.**
'''
    readme = readme[:start] + paragraph + readme[end:]
    prior_default = ('The 48 kHz default, unsupported-map 120 BPM default and any unrecovered 4/4\n'
                     'default remain explicit. No compatible CPR writing or Cubase roundtrip is claimed.')
    assert readme.count(prior_default) == 1
    readme = readme.replace(prior_default,
        'The 48 kHz application default remains explicit for historical profiles and\n'
        'new imports without an admitted saved setup; V5 otherwise uses the recovered\n'
        'base rate with factor +1. Unsupported-map 120 BPM and unrecovered 4/4 defaults\n'
        'remain explicit. No compatible CPR writing or Cubase roundtrip is claimed.')

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
