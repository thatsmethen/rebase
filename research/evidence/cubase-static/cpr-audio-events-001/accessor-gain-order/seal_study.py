"""Seal supplied-format accessor gain evidence; never promote it to hosted playback."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,subprocess
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
def pin(path):
    b=path.read_bytes();return dict(path=str(path.relative_to(ROOT)),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def write(name,d):
    with (HERE/name).open('x') as f:json.dump(d,f,indent=2);f.write('\n')
def verify():
    d=json.loads((HERE/'artifact-manifest.json').read_text())
    assert len({r['path'] for r in d['files']})==len(d['files'])
    for row in d['files']:assert pin(ROOT/row['path'])==row,row['path']
    print(json.dumps(dict(passed=True,files=len(d['files']),manifest=pin(HERE/'artifact-manifest.json'))))
def seal():
    assert not (HERE/'finding.json').exists() and not (HERE/'artifact-manifest.json').exists()
    subprocess.run(['python3',str(HERE/'verify_bindings.py')],check=True)
    verification=json.loads((HERE/'verification.json').read_text())
    imported=json.loads((HERE/'evidence-import.json').read_text())['structuredContent']['result']
    assert verification['passed'] and imported['imported']==6
    bindings=json.loads((HERE/'original-bindings.json').read_text())
    oracle=json.loads((HERE/'validation/gain-order-stage-oracle.json').read_text())
    controls=json.loads((HERE/'gain-controls.json').read_text())
    for output in controls['results']:assert output['result']['assertions']==117593 and output['result']['FP_rejections']==7
    finding=dict(id='CPR-ACCESSOR-GAIN-ORDER-001',schema_version=1,
        created_utc=datetime.now(timezone.utc).isoformat(),status='sealed_conditional_native_gain_composition',
        target=dict(image=pin(ROOT/'research/targets/derived/Cubase15-arm64'),version='15.0.30.287',architecture='arm64'),
        proprietary_target_executions=0,cubase_runtime_comparisons=0,
        native_custody=dict(**verification['totals'],reused_words=5459,jump_cells=3,dispatch_cells=2,
                            spans=14,canonical_records_imported=6,analysis_clients_closed=2,import_clients_closed=1),
        contracts=[
            dict(id='G1',claim='Both conversion fast paths return false for unequal source/output Float32 rates, reaching the generic order. For a Float32 destination, upsampling follows type conversion and destination-format gain; downsampling precedes those operations.',evidence='10032ddd0/10032f014 unequal-rate prefixes;100330cd4 fallback;1003306e4..8f0.'),
            dict(id='G2',claim='The generic destination32/kind2 gain stage is a separate Float32 multiply, scalar or vector, without clipping. The rate/source-format stage can precede gain; source PCM24 downsampling therefore performs its already-recovered signed24 roundtrip before this multiply.',evidence='1039346b8[3]→10032d4a4;10032d4b8..544; prior accessor-format-order finding.'),
            dict(id='G3',claim='The equal-rate interleaved Float32 fast path selects100333200 or1037c3b34. Both copy at gain1 and separately multiply at other gains; neither clamps samples.',evidence='103934718[3]→10032e538→10032e63c..670→10032e6dc..6f0; both fresh helper dossiers and original words.'),
            dict(id='G4',claim='The equal-rate interleaved PCM24 fast path passes actual gain to1003312c4 or1037d88d4. The former folds gain into2^-23 and the latter into2^-31 before multiplication by integer or integer<<8. For signed zero or finite |gain|>=2^-95, both scales remain normal/exact and the outputs equal exact PCM24 decode followed by one Float32 gain multiply. Smaller gains can distinguish these native paths.',evidence='103934718[2]→10032e4fc..534 and10032e6dc..6f0; prior decoder bodies; independent Fraction proof,3168 agreement vectors and709 below-bound discriminators.'),
            dict(id='G5',claim='Gain!=1 alone makes otherwise-matching accessor format require conversion. The gain setter only stores Float32 at+34. Each conversion read copies that gain into retained converter+28 and consumes the first-conversion flag; changing gain does not reset filter history or restore that flag.',evidence='primary vtable+160→100370538,+188→10036fb74;10036fc58..88,10036f060..0e4.'),
            dict(id='G6',claim='Changing the supplied accessor gain between calls affects newly admitted filter inputs on upsampling, and the current returned samples after downsampling. Event/segment gain is a separate owner and is not relocated into this accessor by this study.',evidence='Composition ofG1/G2/G5; integration state/sample checks belong to APP017.')
        ],
        candidate=dict(source=pin(HERE/'candidate/cpr_accessor_format.c'),header=pin(HERE/'candidate/cpr_accessor_format.h'),
            api='rb_cpr_accessor_gain_f32',domain='Signed finite normal-or-zero gain and sample/result values;1..32000000 samples; nearest arm64 FIZ/AH/FZ/DN disabled; complete-buffer preflight and transactional rejection. Restrictions are application policy.'),
        validation=dict(report=pin(HERE/'gain-controls.json'),oracle=pin(HERE/'validation/gain-order-stage-oracle.json'),
            counts=oracle['counts'],assertions_per_build=117593,builds=['optimized','UBSan'],FP_rejections_per_build=7,
            scope='Independent Fraction/IEEE stage expectations and execution of authored C only; retained resampler integration is separate.'),
        limits=[
            'Explicit interleaved stereo PCM24 or Float32 source and Float32 destination. Saved WAV metadata does not select a hosted backend, CPU helper, accessor gain owner or native layout.',
            'The equal-PCM24 bound is an application admission rule, not a native rejection. Below it scalar/SIMD pre-scale rounding can differ; actual selection is not guessed.',
            'Fresh REA dossiers decoded150 addresses of612 original words. Jump-table and5459 reused words are separately original-image verified; this is not complete native decompilation coverage.',
            'No other integer/Float64 output, channel mixing, byte swapping, full generic converter, automatic backend choice, dynamic rate change or postterminal continuation is implemented by this study.',
            'Own-kernel UBSan success covers the declared controls only. No proprietary code, reference playback, DAC capture or runtime differential test was executed.',
            'APP017 application integration and publication are separate. APP015 remains the latest accepted packaged GUI checkpoint.'
        ])
    write('finding.json',finding)
    paths={p for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='.DS_Store'}
    paths.update(ROOT/r['path'] for r in bindings['external_references']+bindings['reused_word_checks'])
    paths.update([ROOT/'research/targets/derived/Cubase15-arm64',ROOT/'research/evidence/cubase-static/cpr-map-clock-001/attributes/source_tools.py',ROOT/'research/evidence/application/APP010/native-rate-mode0-oracle.py',ROOT/'research/evidence/application/APP016/accessor-pcm24-oracle.py'])
    write('artifact-manifest.json',dict(id='CPR-ACCESSOR-GAIN-ORDER-001-MANIFEST',files=[pin(p) for p in sorted(paths)],scope='Local immutable custody; proprietary bytes/provider records/binaries stay local. Mutable application source paths excluded.'))
    verify()
if __name__=='__main__':
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--seal',action='store_true');g.add_argument('--verify',action='store_true')
    a=p.parse_args();seal() if a.seal else verify()
