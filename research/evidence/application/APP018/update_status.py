"""Advance live status after APP018 application validation; preserve old checkpoints."""
from pathlib import Path
import copy,json
ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
v=json.loads((HERE/'application-validation.json').read_text())
assert v['id']=='APP018' and v['version']=='0.18.0'
t=json.loads((HERE/'core-test-run.json').read_text());g=json.loads((HERE/'gui-observations.json').read_text())
binary=json.loads((HERE/'release-build.json').read_text())['executable']
assert (t['tests'],t['suites'],g['groups_passed'])==(280,43,6)
record='research/evidence/application/APP018/application-validation.json'
native=['research/evidence/cubase-static/cpr-audio-events-001/'+n+'/finding.json' for n in
        ['builder-rate-provider','prepared-stream-rate','channel-rate-reconciliation','file-backend-format']]
docs='research/evidence/cubase-documentation/project-rate-001/finding.json'
evidence=[record,'research/evidence/application/APP018/core-test-run.json',
          'research/evidence/application/APP018/gui-observations.json',
          'research/evidence/application/APP018/gui-independent-check.json',
          'research/evidence/application/APP018/project-clock-independent-review.json',
          'research/evidence/application/APP018/project-clock-native-review.json',docs]+native
scope=('Explicit native project-clock audition now plays supported placed/trimmed stereo PCM24 CPR events '
       'at the supplied Rebase clock while the retained source accessor stays at the file rate. Raw source '
       'frames are not resampled; saved clip-datum duration/offset and original tempo-clock start remain '
       'distinct from builder/reader frame coordinates. Differing clocks therefore change speed/pitch '
       'and raw seek/count. Full source capacity is required; positive-short-read windows are rejected '
       'before scheduling. Integral8k-192k rates, common builder/reader rate and factor1 are explicit '
       'application context, not recovered CPR project/device state. Old original-rate and explicit '
       'mode0/1/2 conversion paths remain separate. Ordinary whole-project playback remains gated.')
build=(f"Rebase0.18.0 build18 compiled, packaged and signed; executable {binary['bytes']} bytes, "
       f"SHA256 {binary['sha256']}. All280 tests in43 suites passed with268 unchanged source entries "
       'and pre/post-identical preserved debug/test binaries. Final release has a separate immutable snapshot.')
gui=('Six final-build GUI groups passed: admission, prefix/output, pause/resume, seek/end, exit/project guard, '
     'and capacity rejection/original-rate admission. Eight QA package files unchanged. Transient UI routing '
     'timeouts were retained and recovered. Engine peaks are not DAC measurements or Cubase comparisons.')
milestone=dict(id='APP018',status='tested_packaged_application_milestone',version='0.18.0',validation_record=record,
    swift_test_methods_passed=280,test_suites=43,source_unchanged_during_full_suite=True,
    implementation=[scope],native_findings=native,documentation=docs,gui_validation_status=gui,
    remaining_boundaries=['Saved project audio configuration is not yet decoded; timeline clock is supplied explicitly.',
        'Arbitrary prepared providers, host rate factors, live registry/backend selection, source-format changes, short-read/EOF recovery, scrub and processed/group streams are not fully implemented.',
        'Multiple native tracks/events, overlap/priority, fades, routing, mixer, automation and complete-project fidelity remain incomplete.',
        'Proprietary target executions and Cubase runtime comparisons remain zero.'])
def write(p,d):p.write_text(json.dumps(d,indent=2,ensure_ascii=False)+'\n')
p=ROOT/'research/study.json';d=json.loads(p.read_text());a=d['application'];assert a['version']=='0.15.0'
a['validation_history'].append({k:copy.deepcopy(a[k]) for k in ['version','build_executable_sha256',
    'implementation_test_count','implementation_test_suites','implementation_test_log','implementation_test_log_sha256','validation_record']})
a.setdefault('development_history',[]).append(a['development_milestone']);a['development_milestone']=milestone
a.update(version='0.18.0',implementation_test_count=280,implementation_test_suites=43,
    implementation_test_log=t['log']['path'],implementation_test_log_sha256=t['log']['sha256'],
    previous_validation_record=a['validation_record'],validation_record=record,
    implementation_checks='research/evidence/application/APP018',build_executable_sha256=binary['sha256'],
    build_status=build,gui_validation_status=gui,checkpoint_scope='Current packaged checkpoint APP018; historical records retain their original scope.',
    evidence_boundary='280 own-implementation tests and six bounded GUI groups; no Cubase runtime comparisons or complete-product conformance.')
a['implemented'].append(scope);a['implementation_evidence'] += [e for e in evidence if e not in a['implementation_evidence']]
a['native_project_clock_status']=scope;write(p,d)
p=ROOT/'research/coverage.json';d=json.loads(p.read_text());d['previous_application_iterations'].append(d['application_iteration'])
d.setdefault('previous_development_milestones',[]).append(d['development_milestone']);d['development_milestone']=milestone
d['application_iteration']=dict(id='APP018',version='0.18.0',validation_record=record,
    swift_test_methods_passed=280,test_suites=43,test_log=t['log']['path'],test_log_sha256=t['log']['sha256'],
    scope=scope,implementation_evidence=evidence,build_executable_sha256=binary['sha256'],
    gui_validation_status=gui,release_verification_status=build)
d['application_iteration_scope']='APP018 current packaged checkpoint; earlier iteration/development records remain historical.'
for domain in d['domains']:
    if domain['id']=='project-media':domain['native_project_clock_update']=scope
write(p,d)
p=ROOT/'research/rea-steering.json';d=json.loads(p.read_text());d['previous_iteration_status'].append(copy.deepcopy(d['iteration_status']))
d.setdefault('previous_development_milestones',[]).append(d['development_milestone']);d['development_milestone']=milestone
d['iteration_status'].update(iteration='APP018',version='0.18.0',application='Rebase0.18.0 supplied project-clock playback milestone',
    as_of=v['created_utc'],application_tests=dict(passed=280,suites=43,evidence=t['log']['path'],sha256=t['log']['sha256']),
    evidence=evidence,validation_record=record,gui_validation_status=gui,release_verification_status=build,
    build_executable_sha256=binary['sha256'])
d['iteration_status']['implemented_scope'].append(scope)
d['iteration_status_scope']='APP018 current packaged checkpoint; full-product fidelity remains incomplete.'
priority=d['next_priorities'][0]
priority.update(id='native-project-config-and-channel-inventory',
    question='How is saved PArrangement audio configuration restored, and how does a complete direct audio track enumerate and resolve event windows, overlaps and fades?',
    action='Trace configuration archive setters from the concrete PArrangement owner, then bind complete direct-track event inventories to the recovered reader. Use independent imported-CPR controls for sample-rate selection, multiple windows, priority and boundaries; integrate supported results into project playback only with complete contributor coverage.',
    implementation_gate='APP018 admits an explicit integral factor1 application clock and fresh direct-event state. Do not silently infer original project rate, enable incomplete native tracks, or fabricate source samples on short reads. Bind actual configured clock, audible contributors and processing/routing state first.')
priority['starting_evidence'] += [e for e in evidence if e not in priority['starting_evidence']]
d['rate_hypothesis_revision']='The earlier search for universal transparent source/project conformance was too broad: Cubase15 documentation explicitly permits wrong-speed/pitch playback when media remains unconverted. Ordinary direct accessors inherit source rate; scrub mapping and conditional prepared-provider requests are separate paths.'
write(p,d)
p=ROOT/'README.md';s=p.read_text();start=s.index('The latest packaged GUI checkpoint is ');end=s.index('\nAn active scientific investigation',start)
s=s[:start]+'''The latest packaged application is **Rebase 0.18.0**. The new native project-clock
mode plays supported placed and trimmed CPR events at the supplied Rebase rate,
keeping the source accessor at its file rate. Saved timing, frame coordinates and
source reads stay distinct; differing clocks change speed and pitch. Windows
that exceed complete source capacity are rejected before playback.

All **280 tests in 43 suites** and **six bounded GUI checks** pass. Tests cover
raw sample identity in both rate directions, mixed-rate descriptors, placement,
offsets, gaps, gain, seeks and short-read boundaries. The final signed build and
test executables have preserved identities; eight GUI project files stayed unchanged.
See [APP018 validation](research/evidence/application/APP018/application-validation.json).

REA now binds the builder's PArrangement rate provider, distinguishes inactive
scrub playback from interpolation, traces conditional prepared-provider rate
requests, and identifies the built-in WAV metadata path. The original CPR project
rate and complete channel context remain unresolved: this mode explicitly uses
Rebase's supplied integral clock with factor1. Whole-project playback, native
mixing/routing and Cubase runtime equivalence remain incomplete. Existing
original-rate and explicit mode0/1/2 conversion paths remain available separately.
The earlier APP017 retained accessor gain/state work is included in this build.

The change also corrects the earlier assumption of universal automatic rate
conformance. Cubase documents altered speed/pitch for unconverted mismatched-rate
files; import-time conversion is optional.
[Cubase15 media import documentation](https://www.steinberg.help/r/cubase-pro/15.0/en/cubase_nuendo/topics/pool/pool_media_importing_c.html).
''' +s[end:]
s=s.replace('Nonzero events\nat differing output rates remain gated pending native accessor seek/filter-state\nrecovery; zero-origin mode0/1/2 conversion keeps its existing contracts.',
    'At APP015, nonzero events at differing output rates remained gated. APP018 adds\nexplicit unconverted project-clock playback; zero-origin mode0/1/2 conversion\nkeeps its separate contracts.')
p.write_text(s)
