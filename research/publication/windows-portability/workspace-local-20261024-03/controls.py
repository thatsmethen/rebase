import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import zlib

import argparse
parser = argparse.ArgumentParser(description='Authored viewport and source-selection receipt controls; run from the repository root.')
parser.add_argument('--output', type=Path, required=True)
ROOT = Path.cwd()
OUT = parser.parse_args().output
OUT.mkdir(parents=True, exist_ok=False)
SCRIPT = ROOT / 'Application/scripts/build-windows-app.py'
spec = importlib.util.spec_from_file_location('windows_build', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
EXPECTED = json.loads((ROOT/'Application/Tests/Fixtures/SourceAudition/expected.json').read_bytes())

def png(path, width=1264, height=811):
    def chunk(name, data):
        return struct.pack('>I', len(data)) + name + data + struct.pack('>I', zlib.crc32(name + data))
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress((b'\0' + b'\x28\x2a\x2c\xff' * width) * height)) + chunk(b'IEND', b''))

for name in ('native-workspace-normal-visual.png', 'native-workspace-expanded-visual.png'):
    png(OUT / name)

def rect(x, y, width, height):
    return dict(x=x, y=y, width=width, height=height)

def state(name, rows=44, left=True, mixer=True, height=246):
    width = 978 if left else 1264
    x = 286 if left else 0
    timeline_height = 627 - height - 5 if mixer else 627
    return dict(name=name, state_sha256='a' * 64, revision=30, selected_track_id='authored-track', selected_clip_id='authored-clip',
                row_height=rows, left_visible=left, mixer_visible=mixer, left_width=286 if left else 0, horizontal_offset=0,
                selected_density_index=0 if rows==44 else 1,viewport_height=timeline_height-17,viewport_width=width-17,
                tracks_bottom=26+4*rows,extent_height=timeline_height-17,scrollable_height=0,vertical_offset=0,
                viewport=rect(x,126,width-17,timeline_height-17),
                timeline=rect(x,126,width,timeline_height), mixer=rect(x,126+timeline_height+5,width,height if mixer else 0),
                headers=[rect(x,152+i*rows,198,rows) for i in range(4)])

receipt = dict(initial_state_sha256='a'*64,
    input_evidence='UIA and injected routed keyboard events; no physical input',
    toolbar_controls=[dict(name=name,**rect(x,30,w,25)) for name,x,w in
                      (('RowDensityBox',700,88),('LeftZoneToggle',1100,50),('MixerZoneToggle',1160,60))],
    capture_safety=[dict(surface=name,capture_before=True,capture_after=True,layout_refused=True) for name in ('inspector','timeline','mixer')],
    screenshots=dict(normal='native-workspace-normal-visual.png', expanded='native-workspace-expanded-visual.png'),
    states=[state('compact'),state('normal',rows=68),state('left-hidden',left=False),state('panes-hidden',left=False,mixer=False),
            state('restored'),state('splitter-minimum',height=196),state('splitter-maximum',height=376),state('splitter-restored')],
    event_targets=[dict(row_height=r,event_width=80,event_height=h,move_x=20,trim_x=75,trim_width=10,move_hit=True,trim_hit=True)
                   for r,h in ((44,38),(68,58))],
    splitter=dict(minimum_height=196,maximum_height=376,minimum_actual=196,maximum_actual=376,arrangement_minimum_actual=246,
                  keyboard_focus_preserved=True, faders=[dict(zone_height=h,fader_height=f,value=0,tick_y=20,thumb_y=20)
                                                       for h,f in ((196,60),(376,240))]),
    source_only=dict(before_sha256='b'*64,after_sha256='b'*64,ordinary_actions_disabled=True,source_expanded=True,
                     auto_expand_input='Programmatic source-list SelectionChanged event through the shared session',
                     auto_expand=dict(before_selection_id=EXPECTED['eventID'],other_track_id='authored-empty-track',other_selection_id=None,
                        after_selection_id=EXPECTED['eventID'],source_sha256_before=EXPECTED['sourceSHA256'],source_sha256_after=EXPECTED['sourceSHA256'],
                        canonical_source_restored=True,derived_fixture=dict(kind='authored scratch project with one empty selection-control track',
                            original_manifest_sha256=EXPECTED['manifestSHA256'],derived_manifest_sha256='d'*64,original_track_count=1,
                            derived_track_count=2,retained_event_count=1,sidecars=[dict(path=path,original_sha256=EXPECTED[key],copied_sha256=EXPECTED[key])
                                for path,key in (('Compatibility/CPR/Original.cpr','sourceSHA256'),('Compatibility/CPR/ImportReport.json','reportSHA256'))]))))
valid = dict(checks=sorted(module.WORKSPACE_CHECKS), workspace=receipt,
             window_bounds=dict(outer_width=1280,outer_height=850,client_width=1264,client_height=811,dpi_x=1,dpi_y=1))
passed = []
failed = []

def run(name, update=None, expected=True):
    value = copy.deepcopy(valid)
    if update:
        update(value)
    try:
        module.require_workspace_layout(value, OUT, EXPECTED)
        accepted = True
    except RuntimeError:
        accepted = False
    except Exception as error:
        failed.append(dict(name=name,error=type(error).__name__ + ': ' + str(error)))
        return
    (passed if accepted == expected else failed).append(name)

def field(path, value):
    def change(data):
        for key in path[:-1]:
            data=data[key]
        data[path[-1]]=value
    return change

run('complete-authored-receipt-accepted')
cases = [
 ('missing-check',('checks',),[]), ('missing-workspace',('workspace',),{}),
 ('wrong-input-claim',('workspace','input_evidence'),'physical-input-tested'),
 ('missing-capture',('workspace','screenshots'),{}), ('invalid-state-hash',('workspace','initial_state_sha256'),'invalid'),
 ('missing-states',('workspace','states'),[]), ('duplicate-state',('workspace','states',7,'name'),'compact'),
 ('changed-project',('workspace','states',1,'state_sha256'),'c'*64), ('changed-revision',('workspace','states',1,'revision'),31),
 ('boolean-revision',('workspace','states',1,'revision'),True), ('changed-track',('workspace','states',1,'selected_track_id'),'other'),
 ('changed-clip',('workspace','states',1,'selected_clip_id'),'other'), ('wrong-density',('workspace','states',1,'row_height'),44),
 ('nan-density',('workspace','states',1,'row_height'),float('nan')), ('infinite-width',('workspace','states',1,'timeline','width'),float('inf')),
 ('wrong-left-extent',('workspace','states',2,'left_width'),286), ('wrong-left-visibility',('workspace','states',2,'left_visible'),True),
 ('scroll-not-preserved',('workspace','states',2,'horizontal_offset'),40), ('timeline-outside-client',('workspace','states',1,'timeline','width'),1300),
 ('empty-visible-timeline',('workspace','states',1,'timeline','height'),0), ('negative-mixer',('workspace','states',1,'mixer','height'),-2),
 ('mixer-not-below-timeline',('workspace','states',1,'mixer','y'),200), ('hidden-mixer-retains-height',('workspace','states',3,'mixer','height'),246),
 ('lost-left-space',('workspace','states',2,'timeline','width'),978), ('lost-lower-space',('workspace','states',3,'timeline','height'),376),
 ('missing-row',('workspace','states',1,'headers'),[]), ('wrong-row-pitch',('workspace','states',1,'headers',2,'y'),200),
 ('wrong-header-width',('workspace','states',1,'headers',1,'width'),160), ('bad-restoration',('workspace','states',4,'timeline','x'),280),
 ('missing-hit-targets',('workspace','event_targets'),[]), ('trim-outside-event',('workspace','event_targets',0,'trim_x'),90),
 ('move-in-trim-target',('workspace','event_targets',0,'move_x'),74), ('wrong-hit-height',('workspace','event_targets',0,'event_height'),44),
 ('failed-native-hit',('workspace','event_targets',0,'move_hit'),False), ('density-time-width-changed',('workspace','event_targets',1,'event_width'),85),
 ('wrong-split-minimum',('workspace','splitter','minimum_actual'),220), ('wrong-split-maximum',('workspace','splitter','maximum_actual'),300),
 ('lost-splitter-focus',('workspace','splitter','keyboard_focus_preserved'),False), ('missing-fader',('workspace','splitter','faders'),[]),
 ('fader-thumb-misaligned',('workspace','splitter','faders',1,'thumb_y'),35), ('fader-does-not-resize',('workspace','splitter','faders',1,'fader_height'),60),
 ('source-state-mutated',('workspace','source_only','after_sha256'),'c'*64), ('source-actions-enabled',('workspace','source_only','ordinary_actions_disabled'),False),
 ('source-hidden',('workspace','source_only','source_expanded'),False), ('wrong-capture-size',('window_bounds','client_width'),1200),
 ('missing-toolbar',('workspace','toolbar_controls'),[]), ('clipped-toolbar-control',('workspace','toolbar_controls',2,'x'),1250),
 ('overlapping-toolbar-controls',('workspace','toolbar_controls',2,'x'),1110), ('small-toolbar-target',('workspace','toolbar_controls',1,'height'),12),
 ('missing-capture-safety',('workspace','capture_safety'),[]), ('duplicate-capture-surface',('workspace','capture_safety',2,'surface'),'inspector'),
 ('inspector-capture-lost',('workspace','capture_safety',0,'capture_after'),False), ('layout-during-capture',('workspace','capture_safety',1,'layout_refused'),False),
 ('false-auto-expand-input-claim',('workspace','source_only','auto_expand_input'),'physical input'),
 ('rows-off-viewport',('workspace','states',0,'headers'),[rect(286,500+i*44,198,44) for i in range(4)]),
 ('headers-detached-from-timeline',('workspace','states',0,'headers'),[rect(500,152+i*44,198,44) for i in range(4)]),
 ('wrong-density-index',('workspace','states',1,'selected_density_index'),0),
 ('boolean-density-index',('workspace','states',1,'selected_density_index'),True),
 ('missing-viewport',('workspace','states',1,'viewport_height'),None),
 ('clipped-tracks-viewport',('workspace','states',1,'viewport_height'),297),
 ('wrong-tracks-bottom',('workspace','states',1,'tracks_bottom'),202),
 ('unnecessary-vertical-scroll',('workspace','states',1,'scrollable_height'),8),
 ('content-exceeds-viewport',('workspace','states',1,'extent_height'),367),
 ('content-smaller-than-viewport',('workspace','states',1,'extent_height'),350),
 ('vertical-offset-not-restored',('workspace','states',1,'vertical_offset'),5),
 ('viewport-wider-than-timeline',('workspace','states',1,'viewport_width'),1000),
 ('missing-measured-viewport',('workspace','states',1,'viewport'),{}),
 ('viewport-outside-client-content',('workspace','states',1,'viewport','x'),1300),
 ('viewport-width-not-measured-scalar',('workspace','states',1,'viewport','width'),950),
 ('native-centering-regression',('workspace','states',0,'headers'),[rect(290.5,156.5+i*44,198,44) for i in range(4)]),
 ('missing-source-transition',('workspace','source_only','auto_expand'),{}),
 ('unchanged-source-selection',('workspace','source_only','auto_expand','other_selection_id'),EXPECTED['eventID']),
 ('wrong-source-start',('workspace','source_only','auto_expand','before_selection_id'),'other'),
 ('wrong-source-restored',('workspace','source_only','auto_expand','after_selection_id'),'other'),
 ('missing-other-track',('workspace','source_only','auto_expand','other_track_id'),''),
 ('source-bytes-before-changed',('workspace','source_only','auto_expand','source_sha256_before'),'f'*64),
 ('source-bytes-after-changed',('workspace','source_only','auto_expand','source_sha256_after'),'f'*64),
 ('canonical-source-not-restored',('workspace','source_only','auto_expand','canonical_source_restored'),False),
 ('source-control-unidentified',('workspace','source_only','auto_expand','derived_fixture','kind'),'unknown'),
 ('original-manifest-not-locked',('workspace','source_only','auto_expand','derived_fixture','original_manifest_sha256'),'f'*64),
 ('derived-manifest-not-changed',('workspace','source_only','auto_expand','derived_fixture','derived_manifest_sha256'),EXPECTED['manifestSHA256']),
 ('derived-track-count-wrong',('workspace','source_only','auto_expand','derived_fixture','derived_track_count'),1),
 ('retained-events-changed',('workspace','source_only','auto_expand','derived_fixture','retained_event_count'),2),
 ('missing-sidecar-proof',('workspace','source_only','auto_expand','derived_fixture','sidecars'),[]),
 ('source-sidecar-changed',('workspace','source_only','auto_expand','derived_fixture','sidecars',0,'copied_sha256'),'f'*64),
 ('report-sidecar-changed',('workspace','source_only','auto_expand','derived_fixture','sidecars',1,'copied_sha256'),'f'*64),
]
for name,path,value in cases:
    run(name,field(path,value),False)

# The general viewport invariant must accept legitimate scrolling for tracks
# taller than the viewport. The eight native smoke states separately require
# their four authored rows to fit.
tall=state('tall',rows=68)
tall.update(viewport_height=200,extent_height=298,scrollable_height=98,vertical_offset=50)
tall['viewport']['height']=200
try:
    module.require_timeline_viewport(tall,require_tracks_fit=False)
    passed.append('legitimate-tall-timeline-scroll-accepted')
except Exception as error:
    failed.append(dict(name='legitimate-tall-timeline-scroll-accepted',error=type(error).__name__))
try:
    module.require_timeline_viewport(tall,require_tracks_fit=True)
    failed.append('required-fit-rejects-tall-timeline')
except RuntimeError:
    passed.append('required-fit-rejects-tall-timeline')
empty=state('empty')
empty.update(headers=[],tracks_bottom=26)
try:
    module.require_timeline_viewport(empty)
    passed.append('empty-project-viewport-accepted')
except Exception as error:
    failed.append(dict(name='empty-project-viewport-accepted',error=type(error).__name__))

baseline = subprocess.check_output(['git','show','HEAD:Application/scripts/build-windows-app.py'],cwd=ROOT,text=True)
current = SCRIPT.read_text()
existing = ('require_window_visual','require_pinned_header_scroll','require_cpr_review_layout','require_musical_ruler','validate_modules','copy_example')
def functions(source):
    return {node.name:ast.dump(node,include_attributes=False) for node in ast.parse(source).body if isinstance(node,ast.FunctionDef)}
before,after=functions(baseline),functions(current)
unchanged={name:before[name]==after[name] for name in existing}
if not all(unchanged.values()):
    failed.append('prior-gate-function-changed')
report=dict(schema=1,suite='authored-workspace-receipt-gate-controls',outcome='passed' if not failed else 'failed',
            evidence='Local authored receipt and generated PNG controls; no Windows runtime or visual claim.',
            passed=len(passed),checks=passed,failures=failed,prior_gate_functions_unchanged=unchanged,
            script_sha256=hashlib.sha256(SCRIPT.read_bytes()).hexdigest())
(OUT/'viewport-source-controls.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ('outcome','passed','failures','prior_gate_functions_unchanged','script_sha256')}))
raise SystemExit(bool(failed))
