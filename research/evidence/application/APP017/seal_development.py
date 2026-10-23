"""Seal a tested development milestone; do not promote a packaged GUI release."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,importlib.util,json,re,shutil
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
spec=importlib.util.spec_from_file_location('prior_custody',HERE.parent/'APP015/seal_application.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
# Extend only this loaded instance; historical APP015 code remains immutable.
c.REVIEW_PIN_KEYS += ('input_pins',)
NATIVE={
    'accessor-gain-order':('111dc72c995faca34ed2750f55b4565dc9a973cb42de69b73f18db0802b4214d','f9f1124b0022857a91758e52f8cc7adf05578246fa9e5e11c163918ef5a8aed8',81),
    'processed-stream-rate':('b05b974e7d121bb78cbc496ca1669fd8da023b0430430dc0ec34fa6ad93f067a','d6ef99f4d68fd725ac5a9fd7338d19e16b21a013b4ce7b6c97261dcdac7494f1',521),
    'channel-rate-context':('456e462f8dbc13075ca3074ccd929654e0b856a8d61d236f05adc513e2286be6','8d87f2d1b9d79e7225509bd0e6587da96216944b30d4719a439f3bd4edd110bf',436),
}
REVIEWS=['accessor-gain-independent-review.json','reference-rate-independent-review.json',
         'processed-rate-independent-review.json','channel-rate-independent-review.json',
         'sealer-independent-review.json']

def write(name,value):
    with (HERE/name).open('x') as f:json.dump(value,f,indent=2);f.write('\n')
    return c.record(HERE/name)
def source_matches_test():
    rows=json.loads((HERE/'test-source-before.json').read_text())['files']
    current=[c.record(p) for p in c.application_source_entries()]
    assert current==rows
    assert json.loads((HERE/'test-source-after.json').read_text())['files']==rows
    return len(rows)
def verified_test_record():
    test=json.loads((HERE/'core-test-run.json').read_text())
    assert test['exit_code']==0 and test['source_unchanged'] and test['tests']==271 and test['suites']==42
    c.check_pinned_records(test)
    assert test['command']==['sh','Application/test-app.sh']
    assert test['log']['path']==str((HERE/'core-tests-first.log').relative_to(ROOT))
    passed=re.findall(r'Test run with (\d+) tests in (\d+) suites passed',
                      (HERE/'core-tests-first.log').read_text())
    assert passed==[('271','42')], passed
    return test
def native_integrity():
    prior=HERE.parent/'APP016/artifact-manifest.json'
    c.pinned(prior,'3a60466015219fe29390addc31eb5530471fd0fe1ba64db4fceb7a50017669f5')
    roots=[(prior,ROOT,315)]
    assert 'channel-rate-context' in NATIVE, 'Require sealed channel study before recording'
    studies=[]
    for name,(finding,manifest,count) in NATIVE.items():
        d=ROOT/'research/evidence/cubase-static/cpr-audio-events-001'/name
        fr=c.record(d/'finding.json');mr=c.pinned(d/'artifact-manifest.json',manifest)
        if finding:assert fr['sha256']==finding
        studies.append(dict(name=name,finding=fr,manifest=mr))
        roots.append((d/'artifact-manifest.json',ROOT,count))
    return studies,c.recursive_integrity(roots)
def reviews():
    result=[]
    for name in REVIEWS:
        d=json.loads((HERE/name).read_text())
        pins=c.check_review_pins(d)
        assert c.check_pinned_records(d) >= pins
        assert pins > 0, name
        result.append(dict(record=c.record(HERE/name),pins_verified=pins))
    return result
def record():
    for name in ['final-source-snapshot','test-build-snapshot','development-validation.json',
                 'final-source-manifest.json','record-native-integrity.json']:
        assert not (HERE/name).exists(),name
    source_count=source_matches_test()
    verified_test_record()
    reviewed=reviews();studies,integrity=native_integrity()
    native_record=write('record-native-integrity.json',integrity)
    snap=HERE/'final-source-snapshot';snap.mkdir()
    for name in c.SOURCE_DIRECTORIES:
        shutil.copytree(ROOT/'Application'/name,snap/name,symlinks=True)
    for name in c.SOURCE_FILES:shutil.copy2(ROOT/'Application'/name,snap/name)
    assert c.check_source_inventory(snap)==source_count
    source_manifest=write('final-source-manifest.json',dict(files=[c.record(p) for p in c.entries(snap)]))
    debug=ROOT/'Application/.build-tests/arm64-apple-macosx/debug/Rebase'
    before=c.record(debug)
    build=HERE/'test-build-snapshot';build.mkdir()
    shutil.copyfile(debug,build/'Rebase')
    assert c.record(debug)==before and c.record(build/'Rebase')['sha256']==before['sha256']
    # The existing bundle is still the accepted APP015 executable. Retain its
    # immutable prior snapshot as evidence, not a mutable dist/ manifest pin.
    previous=HERE.parent/'APP015/final-build-snapshot/Rebase.app/Contents/MacOS/Rebase'
    old=c.pinned(previous,'65d0704e0897752c235d48e66ce96443f9f4b0a6c9366916efa5be2796d2fd41')
    assert c.record(ROOT/'Application/dist/Rebase.app/Contents/MacOS/Rebase')['sha256']==old['sha256']
    validation=dict(id='APP017-DEVELOPMENT',created_utc=datetime.now(timezone.utc).isoformat(),
        status='tested_development_milestone',source_files=source_count,
        tests=c.record(HERE/'core-test-run.json'),source_snapshot=source_manifest,
        post_test_debug_executable_observation=dict(record=c.record(build/'Rebase'),
            observed_utc=datetime.now(timezone.utc).isoformat(),
            provenance='Copied from the local debug build directory after testing. The test capture did not hash the executable; this identity is not cryptographically bound to the test invocation or its link step.'),
        latest_packaged_GUI_checkpoint=dict(version='0.15.0',validation=c.record(HERE.parent/'APP015/application-validation.json'),executable=old),
        native_studies=studies,native_integrity=native_record,independent_reviews=reviewed,
        implementation=['Mutable supplied accessor gain preserves first-read state, cursor and retained mode1/mode2 history across gain changes and seeks.',
                        'Float32 gain precedes upsampling and follows source-format downsampling, including the conditional PCM24 intermediate roundtrip.',
                        'Equal-rate Float32 and bounded PCM24 gain reproduce the recovered fast-path arithmetic; finite normal-or-zero, unclipped results and transactional preflight are explicit application bounds.',
                        'Existing equal-rate timeline accessor ownership and separate event/segment gain remain intact.'],
        validation_scope=['271 tests in 42 suites passed with identical before/after source inventories and a successful incremental build. The earlier focused gain run records Linking Rebase; the later debug executable snapshot is a separate observation.',
                          'Six new gain tests compare 48 retained-state reads and 16,540 independently predicted Float32 sample words.',
                          'Standalone optimized and UBSan candidate controls each pass 117,593 assertions; 3,168 equal-PCM24 vectors and 96 stage-order vectors discriminate arithmetic and quantization.'],
        limitations=['No new packaged GUI release or new GUI observation in APP017. APP015 remains the last accepted bundle.',
                     'Differing-rate placed timeline playback remains gated: selected stream/reference rate, timeline reader multiplier and engine rate are distinct recovered owners; actual reconciliation is not yet bound.',
                     'Nonunity accessor gain, source format and rates are explicit supplied context. Selected backend and gain-owner binding, dynamic rate changes, transient I/O and postterminal continuation remain outside this implementation.',
                     'Group reference is the first collected event, not automatically the originally requested event. Collection ordering, cached membership and short-count behavior need separate recovery.',
                     'The immutable memory backend does not reproduce file I/O. Mode1 expected samples share host libm primitives; mode2 expected samples share the pinned public SoXR backend, with independent wrapper/state arithmetic.',
                     'Proprietary target executions and Cubase runtime comparisons remain zero; full product fidelity is incomplete.'])
    print(json.dumps(write('development-validation.json',validation)))
def seal():
    for name in ['final-status-snapshot','seal-integrity.json','artifact-manifest.json','final-integrity.json']:
        assert not (HERE/name).exists(),name
    source_matches_test();verified_test_record();c.check_source_inventory(HERE/'final-source-snapshot');reviews()
    validation=json.loads((HERE/'development-validation.json').read_text())
    assert c.check_pinned_records(validation) > 0
    c.verify(HERE/'final-source-manifest.json')
    studies,integrity=native_integrity()
    write('seal-integrity.json',integrity)
    # Publication review is written after all substantive findings/status.
    publication=json.loads((HERE/'publication-review.json').read_text())
    assert c.check_review_pins(publication) > 0
    snapshot=HERE/'final-status-snapshot';snapshot.mkdir()
    for p in ['README.md','research/study.json','research/coverage.json','research/rea-steering.json']:
        shutil.copyfile(ROOT/p,snapshot/Path(p).name)
    paths=c.entries(HERE)
    assert not any(p.name=='artifact-manifest.json' for p in paths)
    manifest=write('artifact-manifest.json',dict(id='APP017-DEVELOPMENT-MANIFEST',
        scope='Immutable local development evidence. Includes private logs/snapshots by identity; no assertion all entries are published.',files=[c.record(p) for p in paths]))
    result=c.verify(HERE/'artifact-manifest.json')
    print(json.dumps(write('final-integrity.json',dict(manifest=manifest,verified=result['files_checked'],sealed=True,
        validation=c.record(HERE/'development-validation.json'),scope='Development source/test custody, not a new GUI release.'))))
def verify():
    print(json.dumps(c.verify(HERE/'artifact-manifest.json')))
if __name__=='__main__':
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--record',action='store_true');g.add_argument('--seal',action='store_true');g.add_argument('--verify',action='store_true')
    a=p.parse_args();record() if a.record else seal() if a.seal else verify()
