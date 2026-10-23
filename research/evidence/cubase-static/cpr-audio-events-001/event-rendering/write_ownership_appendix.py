"""Append the bounded MRoot ownership result without altering earlier reports."""
from pathlib import Path
import hashlib, json, sys

h=Path(__file__).resolve().parent
r=h.parents[4]
sys.path.insert(0,str(r/'research/evidence/cubase-static/cpr-map-clock-001/attributes'))
import source_tools as s
def ref(path):
    p=r/path
    return dict(path=path,sha256=hashlib.sha256(p.read_bytes()).hexdigest())

cells=[]
for name,table,slots in [
    ('MRoot',0x104671208,{0x220:0x101701318,0x250:0x10171752c,0x258:0x10171759c}),
    ('MAudioTrackEvent',0x10444a208,{0x220:0x10174a2c4,0x258:0x10174a698,0x618:0x1001fcf1c}),
    ('MTrackList',0x104678ea8,{0x68:0x1016e9058,0xf0:0x101758eec,0x140:0x101758ee8}),
    ('MListNode',0x104670218,{0x68:0x1016e9058,0xf0:0x1017154a0,0x140:0x101715cf8}),
    ('MTrackList iterator',0x104679050,{0xd0:0x101715bac,0xd8:0x101715bbc}),
    ('MListNode iterator',0x1046703b8,{0xd0:0x101715bac,0xd8:0x101715bbc}),
]:
    for slot,expected in slots.items():
        v=s.region(table+slot,8)
        target=int.from_bytes(bytes.fromhex(v['bytes_hex']),'little')
        assert target==expected
        v.update(receiver=name,table=hex(table),slot=hex(slot),target=hex(target))
        cells.append(v)
spans=[]
for name,a,end in [
    ('MEvent reader passes decoded data node to concrete +250',0x10170185c,0x1017018a4),
    ('MRoot reader stores source MAutoFadeSetting at +c0',0x1017223c4,0x1017223f8),
    ('MRoot post-read invokes its +220 with itself as second argument',0x1017225c8,0x1017225dc),
    ('MRoot +250 attaches own data node at +58',0x10171752c,0x10171759c),
    ('common event +220 forwards root to own data node +140',0x101701328,0x101701360),
    ('MAudioTrackEvent +220 retains supplied root and tails to common method',0x10174a2c4,0x10174a348),
    ('MTrackList +140 forwards to MListNode root setter',0x101758ee8,0x101758eec),
    ('MListNode root setter invokes base before additional collections',0x101715d0c,0x101715d24),
    ('base data node writes owner root and requests mode2 traversal',0x1016e8ed4,0x1016e8f18),
    ('base data node forwards unchanged root to every iterated child +220',0x1016e8f18,0x1016e8f54),
    ('iterator constructor clears filter pointer',0x1016c137c,0x1016c13a4),
    ('concrete iterator begins at list+b0, skips refresh for mode2',0x101716480,0x1017164ac),
    ('concrete iterator done and next slots',0x101715bac,0x101715c20),
    ('selected data node owner lookup',0x101700eb4,0x101700f14),
    ('auto-fade local setting or root fallback',0x1001f7554,0x1001f7598),
    ('root auto-fade setting getter',0x101720d58,0x101720d60),
]:
    v=s.region(a,end-a);v['meaning']=name;spans.append(v)
linkage=dict(source_sha256='dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb',
    scope='Only the explicit concrete virtual cells and original instruction ranges used for ownership; candidate table overreads are not used.',
    cells=cells,instruction_spans=spans,target_execution=False)
(h/'ownership-linkage.json').write_text(json.dumps(linkage,indent=2)+'\n')

base='research/evidence/cubase-static/cpr-audio-events-001/'
finding=dict(id='CPR-EVENT-ROOT-OWNERSHIP-001',status='bounded static ownership receiver closed',
    source_sha256=linkage['source_sha256'],target_execution=False,runtime_comparisons=0,
    conclusion='The normal successful MRoot restoration path propagates that exact root pointer through concrete MTrackList/MListNode children into the audio track data node. With a null local auto-fade setting, the track getter therefore selects the MAutoFadeSetting at that root +0xc0. The +0x250 attachment alone was insufficient: the decisive step is MRoot post-read +0x220(root, root).',
    contract=[
        dict(id='O1',claim='MEvent reader1017017a0 passes a successfully read data node to receiver+250 at101701884..890. For actual MRoot table104671208, +250 is10171752c: it stores root+58, retains the node and links the owning event via1016e9a30. This is not itself a list+30 write.',functions=['0x1017017a0','0x10171752c','0x1016e9a30']),
        dict(id='O2',claim='MRoot reader101722120 stores the decoded MAutoFadeSetting at root+c0, and later1017225c8..5d8 calls root+220 with x0=root and x1=root. Concrete root+220 is101701318. It obtains its own data node via+258 (root+58) and calls that node+140 with the same x1 root.',functions=['0x101722120','0x101701318','0x10171759c']),
        dict(id='O3',claim='Concrete MTrackList+140 is101758ee8, a tail branch to101715cf8. MListNode+140 is101715cf8 directly. Unless the stored owner already equals the argument, this calls1016e8e80;1016e8eec writes the supplied root to node+30. Fresh old-owner nil cleanup +68 has no external callback: concrete1016e9058 takes its nil-owner branch and only clears node+90.',functions=['0x101758ee8','0x101715cf8','0x1016e8e80','0x1016e9058']),
        dict(id='O4',claim='1016e8e80 requests concrete node+f0 iterator with mode2, then calls child+220(child,sameRoot) until iterator+d0 is true. Both concrete iterator families initialize filter+20=nil and current+30=node+b0; mode2 skips +158 refresh. +d0 tests current==nil; +d8 returns current then advances to current+10. Thus this is direct counted-child traversal, not a class-name search or arbitrary root inference.',functions=['0x101758eec','0x1017154a0','0x101716448','0x1016c137c','0x101715bac','0x101715bbc']),
        dict(id='O5',claim='Concrete MAudioTrackEvent+220 is10174a2c4. On normal return from its preliminary branches it tail-calls101701318 with the original track and root arguments. Its own +258 is10174a698 loading track+58, so its data node receives the same root through +140. Extra auxiliary collections are traversed separately; this claim does not require assigning them an invented source role.',functions=['0x10174a2c4','0x101701318','0x10174a698']),
        dict(id='O6',claim='1001f7554 returns track+170 when nonnull. Only when local setting is null does track+618→1001fcf1c→101700eb4 obtain the own data node (+258 preferred, +280 fallback) and load node+30. If that root is nonnull,101720d58 returns root+c0. This binds the inherited fallback receiver to the same restored MRoot, subject to the successful normal path and no later replacement.',functions=['0x1001f7554','0x1001fcf1c','0x101700eb4','0x101720d58']),
    ],
    applicability=['Actual known MRoot, MTrackList/MListNode and MAudioTrackEvent concrete objects and successfully restored counted hierarchy.',
        'Actual target track owns a nonnull data node; no substitution with an arbitrary similarly named archive object.',
        'Source setting is nonnull and the local track setting is null; otherwise evaluate the local override or retain unsupported state.',
        'Read/attachment/post-read calls complete normally. No later host edit, replacement, external observer or extension mutation is included.'],
    source_fixture_correlation=dict(scope='Root-owned independent forward parse, cited at its exact hash; source-byte interpretation is separate from native control-flow evidence.',
        source=ref(base+'autofade-source/source-forward-probe.json'),
        lofi=dict(root_identity=392,track_identity=197664,local_null_token_offset=243938,root_setting_identity=1291031,root_setting_body=1291035,serialized_flags=0),
        classic=dict(track_identity=207199,local_null_token_offset=258258,root_setting_identity=1154672,root_setting_body=1154676,serialized_flags=0)),
    implications=['Combined with independently forward-decoded nonnull source MAutoFadeSetting flags0 and local-null token, this resolves which saved setting the normal track fallback reads.',
        'Builder zero-flags gate is already retained in event-rendering pass1/final-linkage; this ownership appendix does not use builder override0x28 as a substitute for source settings.',
        'This closes one source-backed automatic-fade predicate for a bounded event-local reconstruction. It does not promote the containing project to playable timeline equivalence.'],
    limitations=['No Cubase execution, runtime comparison, target modification or whole-image Ghidra analysis.',
        'Normal-path data-flow is established; arbitrary callbacks, exceptions, allocation failure, later owner replacement or hosted state mutation are not proven invariant.',
        'MAudioTrackEvent+220 also has preliminary +5f0/+538 behavior; its final forwarding arguments are preserved. This is not an assertion that every side effect of those branches is harmless.',
        'When node datum tag is0,1016e8e80 also fills its datum using root+518/+520; this appendix makes no new time-unit or audio-processing claim from that branch.',
        'Raw REA slices omit imports, globals, neighboring functions and type layouts. Original-image cells and instructions supply the specific linkage; C-like output is not original or necessarily compilable/bit-faithful source.',
        'No claim about nonzero auto-fade flags, fade shape interpolation, track mixing, plugins, PDC, transport, or whole-host rendering.'],
    custody=ref(base+'event-rendering/ownership-verification.json'),
    linkage=ref(base+'event-rendering/ownership-linkage.json'),
    preservation='Earlier event-rendering and sealed application/evidence records are unchanged; this is a new ownership appendix.')
(h/'ownership-finding.json').write_text(json.dumps(finding,indent=2)+'\n')
print(json.dumps({'finding_sha256':hashlib.sha256((h/'ownership-finding.json').read_bytes()).hexdigest(),'cells':len(cells),'spans':len(spans)}))
