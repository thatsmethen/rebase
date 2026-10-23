"""Seal conditional format evidence without asserting a hosted source format."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,shutil,subprocess
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
APP=ROOT/'research/evidence/application/APP016'

def pin(path):
    raw=path.read_bytes()
    return dict(path=str(path.relative_to(ROOT)),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
def write(name,value):
    with (HERE/name).open('x') as f:json.dump(value,f,indent=2);f.write('\n')
def verify():
    d=json.loads((HERE/'artifact-manifest.json').read_text())
    assert len({x['path'] for x in d['files']})==len(d['files'])
    for row in d['files']:assert pin(ROOT/row['path'])==row,row['path']
    print(json.dumps(dict(passed=True,files=len(d['files']),manifest=pin(HERE/'artifact-manifest.json'))))
def seal():
    assert not (HERE/'finding.json').exists() and not (HERE/'artifact-manifest.json').exists()
    subprocess.run(['python3',str(HERE/'verify_bindings.py')],check=True)
    copies=[]
    paths=[]
    for name in ['accessor-pcm24-oracle.py','accessor-pcm24-oracle-v2.json',
                 'accessor-pcm24-oracle.json','accessor-pcm24-oracle-generator-v1.py',
                 'check-accessor-pcm24.py','accessor-pcm24-controls.json']:
        paths.append(APP/name)
    paths += [p for p in (APP/'accessor-pcm24-controls').rglob('*') if p.is_file()]
    for p in paths:
        dst=HERE/'validation'/p.relative_to(APP)
        dst.parent.mkdir(parents=True,exist_ok=True)
        assert not dst.exists()
        shutil.copyfile(p,dst)
        copies.append(dict(original=pin(p),snapshot=pin(dst)))
    write('validation-snapshots.json',dict(copies=copies))
    v=json.loads((HERE/'verification.json').read_text())
    imported=json.loads((HERE/'evidence-import.json').read_text())['structuredContent']['result']
    assert imported['imported']==6 and v['passed']
    controls=json.loads((HERE/'validation/accessor-pcm24-controls.json').read_text())
    assert controls['status']=='passed'
    for row in controls['reviewed_sources']:assert pin(ROOT/row['path'])==row
    finding={
        'id':'CPR-ACCESSOR-FORMAT-ORDER-001','schema_version':1,
        'created_utc':datetime.now(timezone.utc).isoformat(),
        'status':'sealed_conditional_native_format_composition',
        'target':dict(image=pin(ROOT/'research/targets/derived/Cubase15-arm64'),version='15.0.30.287',architecture='arm64'),
        'proprietary_target_executions':0,'cubase_runtime_comparisons':0,
        'native_custody':dict(**v['totals'],reused_words=1191,original_jump_cells=3,
                              canonical_records_imported=6,analysis_clients_closed=1,import_clients_closed=1),
        'contracts':[
            dict(id='FO1',claim='General conversion applies rate conversion before type/channel/gain changes for source rate above output rate. For source rate below output rate it generally applies type/channel/gain first; destination24 with non24 source is a separate early-rate exception.',evidence='1003306f0..774 and100330778..8ec; caller100330cd4 falls through after fast-path failure for unequal rates.'),
            dict(id='FO2',claim='Source24 rate conversion enters10032646c via original table103934638[2]. It decodes packed24 with unity gain into Float32, invokes10030a534, then quantizes each returned value back to packed24 before later format conversion.',evidence='10032646c..5c4; source-format flagw4=1 from100330764.'),
            dict(id='FO3',claim='Quantization separately multiplies Float32 by2^23, clamps at signed24 endpoints, truncates then rounds the residual to nearest-even using binary64 comparison. Negative zero becomes integer zero. This intermediate stage can change samples relative to direct Float32 resampling.',evidence='100326528..5c4; positive threshold0x4afffffe=8388607, negative threshold0xcb000000=-8388608; exacthalf compares odd truncated integer.'),
            dict(id='FO4',claim='The subsequent24-kind1 to32-kind2 stage selects1003312c4 or1037d88d4 with gain1. Their signed24 integer decode and power-of-two scaling are exact. Original tables103934640[2] and103934680[3] bind this branch.',evidence='100326da8..de0→10032725c..290→100327960..978; fresh decoder dossiers and original-image tables.'),
            dict(id='FO5',claim='The candidate implements only the packed24 intermediate quantize/decode stage; the app must bind actual selected-backend format and processing order before selecting it.',evidence='candidate/cpr_accessor_format.c and original-bindings.json')
        ],
        'candidate':dict(source=pin(HERE/'candidate/cpr_accessor_format.c'),header=pin(HERE/'candidate/cpr_accessor_format.h'),api='rb_cpr_accessor_pcm24_roundtrip',domain='Finite normal-or-zero Float32; scaled values finite; nearest arm64 FIZ/AH/FZ/DN disabled; transactional rejection;1..32000000 samples. Defensive restrictions are application policy.'),
        'validation':dict(report=pin(HERE/'validation/accessor-pcm24-controls.json'),oracle=pin(HERE/'validation/accessor-pcm24-oracle-v2.json'),vectors=681,accepted=606,rejected=75,assertions_per_build=3124,builds=['optimized','UBSan'],gain_order_noncommutation_controls=1264,scope='Independent Fraction/IEEE expectations and own candidate execution only.'),
        'limits':[
            'A WAV extension or saved PCM24 description does not prove the current selected backend descriptor. No concrete hosted format or project/output rate is inferred here.',
            'REA raw-slice metadata intervals omit external context. Three dossiers decoded250 instruction addresses of2314 original words; original tables and1191 reused words were checked separately. This is not complete decompilation coverage.',
            'No complete generic converter, channel/layout path, allocator address order, resampler choice, backend availability, lifetime, EOF or nonunity gain composition is established by this study.',
            'The first oracle version lost intermediate signed-zero metadata. It and its generator are retained; corrected v2 leaves all final output/admission expectations unchanged.',
            'App integration and release acceptance are separate APP016 work; this seal does not assert a new GUI release.'
        ]}
    write('finding.json',finding)
    paths={p for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    bindings=json.loads((HERE/'original-bindings.json').read_text())
    paths.update(ROOT/x['path'] for x in bindings['external_references'])
    paths.update([ROOT/'research/targets/derived/Cubase15-arm64',ROOT/'research/evidence/cubase-static/cpr-map-clock-001/attributes/source_tools.py',ROOT/'research/evidence/application/APP010/native-rate-mode0-oracle.py'])
    write('artifact-manifest.json',dict(id='CPR-ACCESSOR-FORMAT-ORDER-001-MANIFEST',files=[pin(p) for p in sorted(paths)],scope='Local immutable custody; proprietary bytes and provider dumps remain local. Mutable Application paths excluded.'))
    verify()

if __name__=='__main__':
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--seal',action='store_true');g.add_argument('--verify',action='store_true')
    a=p.parse_args();seal() if a.seal else verify()
