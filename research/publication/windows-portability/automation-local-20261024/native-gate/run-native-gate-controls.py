#!/usr/bin/env python3
"""Authored acceptance-gate controls. NO native UI, playback or render execution.

The PNGs are generated flat colours with real headers/CRC, not screenshots.
The representative receipt uses the current WPF emission shape and authored
example point data solely to exercise the packaging validator.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import struct
import sys
import zlib

# Publication derivative: require fresh ignored output instead of writing beside
# this frozen harness. Validation assertions and authored controls are unchanged.
sys.dont_write_bytecode = True
parser = argparse.ArgumentParser()
parser.add_argument('--root', type=Path, default=Path.cwd())
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
ROOT = args.root.resolve()
OUTPUT = args.output.resolve()
OUTPUT.mkdir(parents=True, exist_ok=False)
GATE = ROOT / 'Application/scripts/windows_automation_gate.py'
spec = importlib.util.spec_from_file_location('automation_gate_under_test', GATE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
EXAMPLE_PATH = ROOT / 'Application/Examples/Rebase Preview.rebaseproj/Project.json'
LOCK_PATH = ROOT / 'Application/scripts/example-render-lock.json'
example = json.loads(EXAMPLE_PATH.read_text())
lock = json.loads(LOCK_PATH.read_text())
ARTIFACTS = OUTPUT / 'authored-gate-artifacts'
ARTIFACTS.mkdir(exist_ok=True)

def digest(data): return hashlib.sha256(data).hexdigest()
def identity(text): return digest(text.encode())
def png(width, height, colour):
    def chunk(kind, data): return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    pixels = (b'\0' + bytes(colour) * width) * height
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(pixels, 9)) + chunk(b'IEND', b''))

def rect(name, x, y, width, height): return dict(name=name, x=x, y=y, width=width, height=height)
controls = [rect('parameter',14,40,110,30), rect('read',130,40,200,30), rect('curve',14,82,636,160),
    rect('points',14,250,374,160), rect('time',398,268,118,26), rect('value',522,268,118,26),
    rect('interpolation',398,316,252,30), rect('add',400,350,66,26), rect('update',470,350,66,26),
    rect('delete',540,350,66,26), rect('reset',400,382,240,26), rect('undo',435,480,60,28),
    rect('redo',497,480,60,28), rect('close',559,480,76,28)]
track = example['tracks'][1]
authored = next(lane for lane in track['automation'] if lane['parameter'] == 'gainDB')
phase_names = ['original','opening','after_edit','read_off','after_undo_restored','pan','curve','after_close']
revisions = [20,20,21,22,24,27,28,32]
phase_states = [('base','volume-base','pan-base'), ('base','volume-base','pan-base'),
    ('edited','volume-edit','pan-base'), ('read-off','volume-off','pan-base'), ('base','volume-base','pan-base'),
    ('pan','volume-base','pan-edit'), ('curve','volume-base','pan-curve'), ('curve','volume-base','pan-curve')]
phases = [dict(name=name, revision=revision, track_id=track['id'], clip_id=None,
               project_sha256=identity(state[0]), volume_sha256=identity(state[1]), pan_sha256=identity(state[2]))
          for name,revision,state in zip(phase_names,revisions,phase_states)]
captures=[]
original_images={}
for index,name in enumerate(sorted(gate.CAPTURE_NAMES)):
    data=png(664,522,(20+index,30+index,40+index,255))
    original_images[name]=data
    (ARTIFACTS/name).write_bytes(data)
    points=copy.deepcopy(authored['points'])
    if name=='native-automation-read-off-visual.png': points[1].update(value=-4,interpolation='step')
    def position(time,value): return dict(x=48+time/20*574,y=12+120-(value+96)/120*120)
    vertices=[position(0,points[0]['value'])]
    for i,point in enumerate(points):
        if i and points[i-1]['interpolation']=='step': vertices.append(position(point['time'],points[i-1]['value']))
        vertices.append(position(point['time'],point['value']))
    vertices.append(position(20,points[-1]['value']))
    captures.append(dict(file=name,sha256=digest(data),frame_excluded=True,
        bounds=dict(width_dip=664,height_dip=522,outer_width_dip=680,outer_height_dip=560,
                    dpi_scale_x=1,dpi_scale_y=1,pixel_width=664,pixel_height=522),controls=copy.deepcopy(controls),
        parameter='gainDB',read_enabled=name!='native-automation-read-off-visual.png',point_count=5,curve_duration=20,
        curve_plot=dict(x=48,y=12,width=574,height=120),curve_vertices=vertices,points=points,
        message='Enter a finite time and value.' if name=='native-automation-invalid-visual.png' else ''))
record={key:True for key in gate.WINDOW_GATES}
record.update(original_render_sha256=lock['wav_sha256'],restored_render_sha256=lock['wav_sha256'],edited_render_sha256=identity('authored-edited-render'),
    phases=phases,captures=captures,playback_invalidation_tested=False,physical_input_tested=False,native_frame_visual_tested=False,
    input_evidence='AUTHORED GATE CONTROL. No Windows execution; generated flat-colour PNGs are not screenshots.')
baseline=dict(checks=sorted(gate.WINDOW_CHECKS),automation=record)
results=[]

def check(name, change=lambda data:None, rejects=True, image=None):
    payload=copy.deepcopy(baseline)
    try:
        change(payload)
        if image: image(payload)
        try: gate.require_automation_window(payload,ARTIFACTS,example,lock)
        except RuntimeError as error:
            if not rejects: raise
            results.append(dict(name=name,expected='reject',outcome='rejected',reason=str(error)))
        else:
            if rejects: raise AssertionError('Gate accepted authored negative control: '+name)
            results.append(dict(name=name,expected='accept',outcome='accepted'))
    finally:
        for filename,data in original_images.items(): (ARTIFACTS/filename).write_bytes(data)

def set_record(key,value): return lambda data:data['automation'].__setitem__(key,value)
def phase(index,key,value): return lambda data:data['automation']['phases'][index].__setitem__(key,value)
def capture(key,value): return lambda data:data['automation']['captures'][0].__setitem__(key,value)
def bound(key,value): return lambda data:data['automation']['captures'][0]['bounds'].__setitem__(key,value)
def control(index,key,value): return lambda data:data['automation']['captures'][0]['controls'][index].__setitem__(key,value)
def point(index,key,value): return lambda data:data['automation']['captures'][0]['points'][index].__setitem__(key,value)
check('representative-lowercase-native-receipt',rejects=False)
for key in gate.WINDOW_GATES: check('missing-success-'+key,set_record(key,False))
for key in ('playback_invalidation_tested','physical_input_tested','native_frame_visual_tested'):
    check('unsupported-evidence-claim-'+key,set_record(key,True))
check('missing-native-check',lambda data:data['checks'].pop())
for key in ('original_render_sha256','restored_render_sha256'):
    check('wrong-lock-'+key,set_record(key,identity('wrong render')))
check('edited-render-unchanged',set_record('edited_render_sha256',lock['wav_sha256']))
check('edited-render-hash-malformed',set_record('edited_render_sha256','A'*64))
check('missing-phase',lambda data:data['automation']['phases'].pop())
check('phase-name-mismatch',phase(2,'name','unknown'))
check('phase-revision-bool',phase(2,'revision',True))
check('phase-revision-stationary',phase(2,'revision',20))
check('opening-revision-changed',phase(1,'revision',21))
check('phase-selection-changed',phase(3,'clip_id','unexpected-clip'))
check('phase-track-changed',phase(3,'track_id',example['tracks'][0]['id']))
check('phase-hash-malformed',phase(2,'volume_sha256','not-a-hash'))
check('opening-project-mutated',phase(1,'project_sha256',identity('different')))
check('undo-volume-not-restored',phase(4,'volume_sha256',identity('different')))
check('close-project-mutated',phase(7,'project_sha256',identity('different')))
check('volume-edit-mutated-pan',phase(2,'pan_sha256',identity('different')))
check('pan-edit-mutated-volume',phase(5,'volume_sha256',identity('different')))
check('pan-edit-did-not-change',phase(5,'pan_sha256',phases[0]['pan_sha256']))
check('curve-insertion-did-not-change',phase(6,'pan_sha256',phases[5]['pan_sha256']))
check('missing-capture',lambda data:data['automation']['captures'].pop())
check('duplicate-capture',lambda data:data['automation']['captures'].__setitem__(1,copy.deepcopy(data['automation']['captures'][0])))
check('image-hash-mismatch',capture('sha256',identity('wrong pixels')))
check('native-caption-claim',capture('frame_excluded',False))
check('pixel-width-mismatch',bound('pixel_width',663))
check('pixel-height-mismatch',bound('pixel_height',521))
check('pixel-dpi-mismatch',bound('dpi_scale_x',1.25))
check('zero-dpi',bound('dpi_scale_y',0))
check('nonfinite-dpi',bound('dpi_scale_x',math.nan))
check('bool-client-width',bound('width_dip',True))
check('larger-than-minimum-outer',bound('outer_width_dip',841))
check('client-exceeds-outer',bound('outer_width_dip',600))
check('missing-control',lambda data:data['automation']['captures'][0]['controls'].pop())
check('duplicate-control-name',control(0,'name','read'))
check('control-overflow-right',control(0,'x',650))
check('control-overflow-bottom',control(13,'y',510))
check('control-negative-origin',control(0,'x',-2))
check('control-zero-width',control(0,'width',0))
check('control-nonfinite',control(0,'width',math.inf))
check('list-unusable-height',control(3,'height',139))
check('plot-outside-curve',lambda data:data['automation']['captures'][0]['curve_plot'].__setitem__('x',120))
check('plot-unusable-height',lambda data:data['automation']['captures'][0]['curve_plot'].__setitem__('height',79))
check('wrong-parameter',capture('parameter','pan'))
check('wrong-point-count',capture('point_count',4))
check('missing-point',lambda data:data['automation']['captures'][0]['points'].pop())
check('wrong-duration',capture('curve_duration',21))
check('pascalcase-points',lambda data:data['automation']['captures'][0].__setitem__('points',[{key[0].upper()+key[1:]:value for key,value in p.items()} for p in data['automation']['captures'][0]['points']]))
check('bad-point-identity',point(0,'id','bad'))
check('duplicate-point-identity',point(1,'id',authored['points'][0]['id']))
check('duplicate-time',point(1,'time',0))
check('negative-time',point(0,'time',-1))
check('point-after-extent',point(4,'time',21))
check('nonfinite-value',point(0,'value',math.nan))
check('bool-value',point(0,'value',False))
check('out-of-range-value',point(0,'value',25))
check('unsupported-interpolation',point(0,'interpolation','bezier'))
check('authored-point-drift',point(0,'value',-11))
check('missing-curve-endpoint',lambda data:data['automation']['captures'][0]['curve_vertices'].pop())
check('wrong-curve-coordinate',lambda data:data['automation']['captures'][0]['curve_vertices'][1].__setitem__('x',90))
check('nonfinite-curve-coordinate',lambda data:data['automation']['captures'][0]['curve_vertices'][1].__setitem__('y',math.inf))
check('missing-hold-transition',lambda data:next(c for c in data['automation']['captures'] if not c['read_enabled'])['curve_vertices'].pop(3))
check('wrong-read-state',capture('read_enabled',False))
check('invalid-error-not-visible',lambda data:next(c for c in data['automation']['captures'] if 'invalid' in c['file']).__setitem__('message',''))

def altered_image(payload,data):
    current=payload['automation']['captures'][0]
    (ARTIFACTS/current['file']).write_bytes(data)
    current['sha256']=digest(data)
check('invalid-png-signature-with-matching-hash',image=lambda payload:altered_image(payload,b'notpng00'+original_images[captures[0]['file']][8:]))
check('truncated-png-header-with-matching-hash',image=lambda payload:altered_image(payload,b'\x89PNG\r\n\x1a\n'+b'x'*20))
check('wrong-ihdr-dimensions-with-matching-hash',image=lambda payload:altered_image(payload,png(665,522,(20,30,40,255))))

def high_dpi(payload):
    for current in payload['automation']['captures']:
        data=png(830,653,(21,31,41,255)); (ARTIFACTS/current['file']).write_bytes(data)
        current['sha256']=digest(data)
        current['bounds'].update(dpi_scale_x=1.25,dpi_scale_y=1.25,pixel_width=830,pixel_height=653)
check('valid-125-percent-dpi-round-up',rejects=False,image=high_dpi)

(ARTIFACTS/'authored-smoke.json').write_text(json.dumps(baseline,indent=2)+'\n')
receipt=dict(schema=1,evidence_class='authored-packaging-gate-controls',native_windows_executed=False,wpf_runtime_tested=False,
    playback_tested=False,images_are_screenshots=False,checks=len(results),accepted=sum(r['outcome']=='accepted' for r in results),
    rejected=sum(r['outcome']=='rejected' for r in results),failures=0,results=results,
    source_hashes={str(path.relative_to(ROOT)):digest(path.read_bytes()) for path in (GATE,EXAMPLE_PATH,LOCK_PATH,Path(__file__))},
    limits=['PNG gate checks signature, IHDR geometry and recorded SHA-256; this control does not establish full image decode or native visibility.',
            'Individual control containment is checked; sibling overlap requires native image review.',
            'Receipt booleans/hashes are authored test data, not execution evidence.'])
(OUTPUT/'gate-controls.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({key:receipt[key] for key in ('evidence_class','checks','accepted','rejected','failures','native_windows_executed')}))
