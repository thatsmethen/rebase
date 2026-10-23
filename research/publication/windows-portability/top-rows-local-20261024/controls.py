"""Authored receipt controls, not Windows execution. Run from repository root."""
import argparse
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import zlib

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
OUT = parser.parse_args().output
OUT.mkdir(parents=True, exist_ok=False)
ROOT = Path.cwd()
SCRIPT = ROOT / 'Application/scripts/build-windows-app.py'
spec = importlib.util.spec_from_file_location('gate', SCRIPT)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
EXPECTED = json.loads((ROOT / 'Application/Tests/Fixtures/SourceAudition/expected.json').read_bytes())
EXAMPLE = hashlib.sha256((ROOT / 'Application/Examples/Rebase Preview.rebaseproj/Project.json').read_bytes()).hexdigest()
BEFORE = 'b6b019148608b0081f78e163bb1c32a3d5ff0948'

def sha(data): return hashlib.sha256(data).hexdigest()
def rect(x, y, width, height): return dict(x=x, y=y, width=width, height=height)
def bounds(width=1264): return dict(outer_width=width+16,outer_height=850,client_width=width,client_height=811,dpi_x=1,dpi_y=1)
def png(path, width):
    def chunk(kind, data): return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,811,8,6,0,0,0))
        +chunk(b'IDAT',zlib.compress((b'\0'+b'\x28\x2a\x2c\xff'*width)*811))+chunk(b'IEND',b''))

def element(name, x, y, width, height, text=None, *, visible=True, tooltip=None, trimming='None', natural=None):
    box = rect(x,y,width,height) if visible else rect(0,0,0,0)
    metrics = dict(text_natural_width=None,text_natural_height=None,text_content_width=None,text_content_height=None,
                   text_fits_width=None,text_fits_height=None,text_trimming=None)
    if text is not None:
        nw = len(text)*4.5 if natural is None else natural
        nh = min(12,height) if height else 12
        metrics.update(text_natural_width=nw,text_natural_height=nh,text_content_width=box['width'],
            text_content_height=box['height'],text_fits_width=nw<=box['width']+.5,text_fits_height=nh<=box['height']+.5,text_trimming=trimming)
    return dict(name=name,**box,visible=visible,text=text,tooltip=tooltip,**metrics)

LONG_PROJECT = 'Authored long project name ' + 'with complete identity available from its tooltip ' * 6
LONG_EVENT = 'Authored long event name ' + 'with independent timing controls that remain visible ' * 5

def layout(width=1264, context='ordinary', limitation=False, long=False):
    project_name = LONG_PROJECT if long else 'Rebase Preview'
    event_name = LONG_EVENT if long else {'ordinary':'Opening beat','source':'Authored source 0','empty':'No event selected'}[context]
    kind = {'ordinary':'Selected event','source':'Retained source event','empty':'Event information'}[context]
    texts = ('0','5','0.000 s') if context=='ordinary' else ('—','—','—')
    toolbar_names = ['ExampleButton','OpenProjectButton','SaveProjectButton','UndoButton','RedoButton','SplitToolbarButton',
        'DeleteToolbarButton','SnapBox','Zoom','RulerModeBox','RowDensityBox','LeftZoneToggle','MixerZoneToggle','ExportButton']
    return dict(stack_height=107,client_width=width,client_height=811,
        bands=[element(n,0,y,width,h) for n,y,h in [('MenuBand',0,25),('ToolbarBand',25,30),('ProjectStatusBand',55,18),('EventInfoBand',73,34)]],
        toolbar_controls=[element(n,6+i*60,27,50,25) for i,n in enumerate(toolbar_names)],
        event_cells=[element(n,x,74,w,31) for n,x,w in [('EventNameCell',7,243),('EventStartCell',264,112),('EventEndCell',389,112),('EventOffsetCell',514,118)]],
        event_controls=[element('SelectionName',7,85,243,20,event_name,tooltip=event_name,trimming='CharacterEllipsis'),
            element('SelectionKind',7,74,243,11,kind),element('MoveBox',264,85,91,20,texts[0]),element('MoveButton',356,85,20,20),
            element('TrimBox',389,85,91,20,texts[1]),element('TrimButton',481,85,20,20),element('SourceOffsetText',514,85,118,20,texts[2]),
            element('EventStartLabel',264,74,112,11,'Start (s)'),element('EventEndLabel',389,74,112,11,'End (s)'),element('EventOffsetLabel',514,74,118,11,'Source offset (s)')],
        status_controls=[element('ProjectName',50,57,width-(480 if limitation else 280),14,project_name,tooltip=project_name,trimming='CharacterEllipsis'),
            element('ProjectInfo',width-220,57,210,14,'4 tracks · 48000 Hz · 20 seconds'),
            element('ProjectLimit',width-420,57,180,14,'Project playback unavailable',visible=limitation)])

def workspace(name, rows=44, left=True, mixer=True, lower=216):
    w=978 if left else 1264; x=286 if left else 0
    h=646-lower-5 if mixer else 646
    return dict(name=name,canvas_width=max(w-17,1006),viewport_width=w-17,row_height=rows,
        timeline=rect(x,107,w,h),mixer=rect(x,107+h+5,w,lower if mixer else 0),
        selected_track_id='authored-track',selected_clip_id='authored-clip',
        headers=[rect(x,133+i*rows,198,rows) for i in range(4)],
        divider_ends=[dict(x1=0,y1=26+(i+1)*rows,x2=max(w-17,1006),y2=26+(i+1)*rows) for i in range(4)])

def timing(name, context, limitation=False):
    l=layout(context=context,limitation=limitation)
    fields={v['name']:v for v in l['event_controls']}
    return dict(name=name,before_sha256='a'*64,after_sha256='a'*64,revision=1,
        selected_track_id='authored-track',selected_clip_id='authored-clip' if context=='ordinary' else EXPECTED['eventID'] if context=='source' else None,
        markers=dict(context=context,name=fields['SelectionName']['text'],kind=fields['SelectionKind']['text'],
            start=fields['MoveBox']['text'],end=fields['TrimBox']['text'],offset=fields['SourceOffsetText']['text'],
            editing_enabled=context=='ordinary',project_limitation_visible=limitation),layout=l)

captures=[]
for name,w in [('native-top-rows-long-names-visual.png',1264),('native-top-rows-wide-visual.png',1384)]:
    png(OUT/name,w)
    captures.append(dict(screenshot=name,png_sha256=sha((OUT/name).read_bytes()),window_bounds=bounds(w),layout=layout(w,long=True)))
long_layout=captures[0]['layout']
def long_text(group,name):
    value=next(v for v in long_layout[group] if v['name']==name)
    return {**{k:value[k] for k in ('text','tooltip','x','y','width','height')},'trimming':value['text_trimming'],'natural_width':value['text_natural_width']}

valid=dict(checks=sorted(gate.TOP_ROWS_CHECKS),window_bounds=bounds(),
    workspace=dict(states=[workspace('compact'),workspace('normal',rows=68),workspace('left-hidden',left=False),
        workspace('panes-hidden',left=False,mixer=False),workspace('restored'),workspace('splitter-minimum',lower=196),
        workspace('splitter-maximum',lower=376),workspace('splitter-restored')]),
    timeline_scroll={**{f'headers_{suffix}':[rect(286,133+i*44,198,44) for i in range(4)] for suffix in ('before','after')},
        **{f'ruler_header_{suffix}':rect(286,133,198,44) for suffix in ('before','after')},
        **{f'ruler_{suffix}':dict(text='Bars + Beats',**rect(306,113,177,20)) for suffix in ('before','after')}},
    top_rows=dict(layout=layout(context='empty'),states=[timing('startup-empty','empty'),timing('ordinary-zero','ordinary'),
        timing('retained-source','source',True),timing('empty-track','empty',True)],
        long_names=dict(project_name=LONG_PROJECT,event_name=LONG_EVENT,project_text=long_text('status_controls','ProjectName'),
            event_text=long_text('event_controls','SelectionName'),original_manifest_sha256=EXAMPLE,derived_manifest_sha256='d'*64),
        resize=dict(before_sha256='b'*64,after_sha256='b'*64,revision_before=30,revision_after=30,track_before='authored-track',
            track_after='authored-track',clip_before='authored-clip',clip_after='authored-clip',requested_outer_width=1400,
            outer_width_before=1280,outer_width_after=1400,wider_observed=True),captures=captures,
        input_evidence='UIA and injected routed keyboard events; no physical input'))
passed=[];failed=[]
def field(path,value):
    def update(data):
        for key in path[:-1]:data=data[key]
        data[path[-1]]=value
    return update
def run(name,update=None,expected=False):
    value=copy.deepcopy(valid)
    if update:update(value)
    try:gate.require_top_rows(value,OUT,EXAMPLE,EXPECTED);accepted=True
    except RuntimeError:accepted=False
    except Exception as error:failed.append(dict(name=name,error=type(error).__name__));return
    (passed if accepted==expected else failed).append(name)

run('complete-authored-top-row-receipt-accepted',expected=True)
cases=[
 ('missing-native-label',('checks',),[]),('duplicate-native-label',('checks',),sorted(gate.TOP_ROWS_CHECKS)*2),
 ('missing-top-row-receipt',('top_rows',),None),('false-physical-input-claim',('top_rows','input_evidence'),'physical input'),
 ('stack-is-old126',('top_rows','layout','stack_height'),126),('wrong-client-width',('top_rows','layout','client_width'),1000),
 ('missing-band',('top_rows','layout','bands'),[]),('duplicate-band',('top_rows','layout','bands',1,'name'),'MenuBand'),
 ('gapped-bands',('top_rows','layout','bands',2,'y'),60),('taller-toolbar',('top_rows','layout','bands',1,'height'),34),
 ('toolbar-outside-band',('top_rows','layout','toolbar_controls',1,'y'),40),('toolbar-overlap',('top_rows','layout','toolbar_controls',1,'x'),8),
 ('missing-toolbar-control',('top_rows','layout','toolbar_controls'),[]),('toolbar-hidden',('top_rows','layout','toolbar_controls',1,'visible'),False),
 ('toolbar-hit-area-shrunk',('top_rows','layout','toolbar_controls',1,'height'),18),('zoom-hit-area-shrunk',('top_rows','layout','toolbar_controls',8,'height'),5),
 ('missing-event-cell',('top_rows','layout','event_cells'),[]),('overlapping-event-cells',('top_rows','layout','event_cells',1,'x'),200),
 ('event-control-outside-cell',('top_rows','layout','event_controls',2,'x'),100),('overlapping-event-controls',('top_rows','layout','event_controls',3,'x'),270),
 ('event-control-outside-band',('top_rows','layout','event_controls',2,'y'),105),('event-target-shrunk',('top_rows','layout','event_controls',3,'width'),10),
 ('text-nan',('top_rows','layout','event_controls',2,'text_natural_width'),float('nan')),
 ('text-height-clipped',('top_rows','layout','event_controls',2,'text_natural_height'),30),
 ('numeric-width-clipped',('top_rows','layout','event_controls',2,'text_natural_width'),100),
 ('lying-width-fit-flag',('top_rows','layout','event_controls',2,'text_fits_width'),False),
 ('lying-height-fit-flag',('top_rows','layout','event_controls',2,'text_fits_height'),False),
 ('numeric-content-outside-field',('top_rows','layout','event_controls',2,'text_content_width'),100),
 ('empty-visible-text',('top_rows','layout','event_controls',0,'text'),''),
 ('nontext-with-metrics',('top_rows','layout','toolbar_controls',0,'text_natural_width'),10),
 ('missing-status-control',('top_rows','layout','status_controls'),[]),('hidden-limit-keeps-width',('top_rows','layout','status_controls',2,'width'),180),
 ('status-overlap',('top_rows','layout','status_controls',1,'x'),100),('project-name-hidden',('top_rows','layout','status_controls',0,'visible'),False),
 ('workspace-missing',('workspace',),None),('workspace-state-missing',('workspace','states'),[]),
 ('saved-height-not-returned',('workspace','states',0,'timeline','height'),406),('mixer-absorbs-returned-height',('workspace','states',0,'mixer','height'),235),
 ('old-workspace-origin',('workspace','states',0,'timeline','y'),126),('canvas-smaller-than-viewport',('workspace','states',3,'canvas_width'),1006),
 ('divider-ends-early',('workspace','states',3,'divider_ends',2,'x2'),1006),('divider-diagonal',('workspace','states',0,'divider_ends',1,'y2'),110),
 ('duplicate-divider-baseline',('workspace','states',0,'divider_ends',2,'y1'),114),('missing-divider',('workspace','states',0,'divider_ends'),[]),
 ('nan-divider',('workspace','states',0,'divider_ends',0,'x2'),float('nan')),('missing-ruler',('timeline_scroll','ruler_after'),{}),
 ('wrong-ruler-text',('timeline_scroll','ruler_after','text'),'Seconds'),('scrolled-ruler',('timeline_scroll','ruler_after','x'),406),
 ('clipped-ruler',('timeline_scroll','ruler_after','width'),200),('ruler-outside-header',('timeline_scroll','ruler_after','y'),140),
 ('missing-client-ruler-header',('timeline_scroll','ruler_header_before'),{}),('wrong-ruler-header-width',('timeline_scroll','ruler_header_before','width'),300),
 ('infinite-ruler',('timeline_scroll','ruler_after','y'),float('inf')),('missing-timing-state',('top_rows','states'),[]),
 ('duplicated-timing-state',('top_rows','states',3,'name'),'startup-empty'),('changed-timing-session',('top_rows','states',2,'after_sha256'),'f'*64),
 ('boolean-revision',('top_rows','states',0,'revision'),True),('wrong-source-context',('top_rows','states',2,'markers','context'),'ordinary'),
 ('source-timing-enabled',('top_rows','states',2,'markers','editing_enabled'),True),('source-limitation-hidden',('top_rows','states',2,'markers','project_limitation_visible'),False),
 ('source-limitation-misleading-text',('top_rows','states',2,'layout','status_controls',2,'text'),'Project playback available'),
 ('rendered-timing-differs',('top_rows','states',2,'layout','event_controls',2,'text'),'0'),
 ('source-selected-id-differs',('top_rows','states',2,'selected_clip_id'),'different-source'),
 ('empty-selection-has-clip',('top_rows','states',0,'selected_clip_id'),'unexpected-clip'),
 ('ordinary-selection-lost',('top_rows','states',1,'selected_clip_id'),None),
 ('long-name-baseline-unbound',('top_rows','long_names','original_manifest_sha256'),'c'*64),
 ('long-name-derived-unchanged',('top_rows','long_names','derived_manifest_sha256'),EXAMPLE),
 ('long-name-tooltip-incomplete',('top_rows','long_names','event_text','tooltip'),'short'),
 ('long-name-not-overflowed',('top_rows','long_names','event_text','natural_width'),100),
 ('long-name-no-ellipsis',('top_rows','long_names','project_text','trimming'),'None'),
 ('long-name-bounds-unbound',('top_rows','long_names','event_text','x'),8),
 ('long-name-measurement-unbound',('top_rows','long_names','event_text','natural_width'),9999),
 ('capture-missing',('top_rows','captures'),[]),('capture-duplicate',('top_rows','captures',1,'screenshot'),'native-top-rows-long-names-visual.png'),
 ('capture-hash-unbound',('top_rows','captures',0,'png_sha256'),'c'*64),('capture-bounds-unbound',('top_rows','captures',1,'window_bounds','client_width'),1300),
 ('capture-title-differs',('top_rows','captures',0,'layout','event_controls',0,'text'),'short'),
 ('long-title-displaces-timing',('top_rows','captures',0,'layout','event_controls',2,'text'),'—'),
 ('capture-text-ellipsis-missing',('top_rows','captures',0,'layout','event_controls',0,'text_trimming'),'None'),
 ('capture-text-tooltip-missing',('top_rows','captures',0,'layout','event_controls',0,'tooltip'),None),
 ('resize-state-changed',('top_rows','resize','after_sha256'),'c'*64),('resize-revision-changed',('top_rows','resize','revision_after'),31),
 ('resize-track-changed',('top_rows','resize','track_after'),'other'),('resize-clip-changed',('top_rows','resize','clip_after'),'other'),
 ('resize-boolean-revision',('top_rows','resize','revision_before'),True),('resize-request-not-made',('top_rows','resize','requested_outer_width'),1280),
 ('resize-claim-false',('top_rows','resize','wider_observed'),False),('resize-width-unbound',('top_rows','resize','outer_width_after'),1300),
 ('restored-bounds-lost',('window_bounds','outer_width'),1400),('nan-resize',('top_rows','resize','outer_width_after'),float('nan')),
]
for name,path,value in cases:run(name,field(path,value))

def truthful_unavailable(data):
    state=data['top_rows']['states'][2]
    state['markers']['start']='0';state['layout']['event_controls'][2]['text']='0'
run('source-zero-rejected-even-with-matching-rendered-text',truthful_unavailable)
def clipped_numeric(data):
    control=data['top_rows']['layout']['event_controls'][2]
    control.update(text_natural_width=100,text_fits_width=False,tooltip=control['text'],text_trimming='CharacterEllipsis')
run('numeric-clipping-rejected-even-with-tooltip',clipped_numeric)
def clipped_limitation(data):
    control=data['top_rows']['states'][2]['layout']['status_controls'][2]
    control.update(text_natural_width=300,text_fits_width=False,tooltip=control['text'],text_trimming='CharacterEllipsis')
run('playback-limitation-must-fit-without-ellipsis',clipped_limitation)
def old_outer_coordinates(data):
    for suffix in ('before','after'):
        for header in data['timeline_scroll']['headers_'+suffix]:header['x']+=8;header['y']+=31
run('client-ruler-ignores-legacy-window-coordinate-points',old_outer_coordinates,expected=True)
def constrained(data):
    last=data['top_rows']['captures'][1]
    last['layout']=copy.deepcopy(data['top_rows']['captures'][0]['layout'])
    last['window_bounds']=bounds()
    last['png_sha256']=sha((OUT/'native-top-rows-long-names-visual.png').read_bytes())
    data['top_rows']['resize'].update(outer_width_after=1280,wider_observed=False)
wide=(OUT/'native-top-rows-wide-visual.png').read_bytes()
(OUT/'native-top-rows-wide-visual.png').write_bytes((OUT/'native-top-rows-long-names-visual.png').read_bytes())
try:run('truthfully-constrained-resize-accepted',constrained,expected=True)
finally:(OUT/'native-top-rows-wide-visual.png').write_bytes(wide)

protected=('require_window_visual','require_pinned_header_scroll','require_cpr_review_layout','require_musical_ruler',
    'require_workspace_layout','require_timeline_viewport','require_source_selection_control','validate_modules','copy_example')
baseline=subprocess.check_output(['git','show',BEFORE+':Application/scripts/build-windows-app.py'],cwd=ROOT,text=True)
def functions(source):return {node.name:ast.dump(node,include_attributes=False) for node in ast.parse(source).body if isinstance(node,ast.FunctionDef)}
old,new=functions(baseline),functions(SCRIPT.read_text())
for name in protected:(passed if old[name]==new[name] else failed).append('preserved-existing-'+name)
result=dict(schema='rebase.authored-top-row-gate-controls.v1',status='passed' if not failed else 'failed',
    passed=len(passed),failures=failed,checks=passed,gate_script_sha256=sha(SCRIPT.read_bytes()),baseline_commit=BEFORE,
    example_manifest_sha256=EXAMPLE,expected_source_sha256=EXPECTED['sourceSHA256'],
    boundary='Authored JSON receipts and generated solid-color PNGs exercise validation gates only; no Windows UI, executable, physical input, reference fidelity or audio output was measured.')
(OUT/'gate-controls.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(status=result['status'],passed=len(passed),failures=failed,receipt_sha256=sha((OUT/'gate-controls.json').read_bytes()))))
raise SystemExit(bool(failed))
