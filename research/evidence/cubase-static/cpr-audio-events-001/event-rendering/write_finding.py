"""Roll up retained static evidence; does not execute the target."""
from pathlib import Path
import hashlib, json, datetime

h = Path(__file__).resolve().parent
r = h.parents[4]
def pin(p):
    p = Path(p)
    if not p.is_absolute(): p = r / p
    return {'path': str(p.relative_to(r)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
def evidence(p):
    d=json.loads(p.read_text()); assert not d.get('isError',False)
    return d.get('structuredContent') or json.loads(d['content'][0]['text'])

verification=json.loads((h/'verification.json').read_text())
functions=[]
for row in verification['functions']:
    base=h/row['directory']; p=base/f"function-{row['entry'][2:]}.json"
    e=evidence(p)
    functions.append({'entry':row['entry'],'evidence_id':e['evidence_id'],
                      'raw_source_sha256':row['source_range_sha256'],'dossier':pin(p)})

prior={}
for label,p in [
    ('source_state','research/evidence/cubase-static/cpr-audio-events-001/audible-state/finding.json'),
    ('selected_stream','research/evidence/cubase-static/cpr-audio-events-001/renderer-selection/finding.json'),
    ('one_segment_read','research/evidence/cubase-static/cpr-audio-events-001/segment-consumer/finding.json'),
    ('placement','research/evidence/cubase-static/cpr-audio-events-001/timebase/finding.json'),
    ('independent_consumer_review','research/evidence/cubase-static/cpr-audio-events-001/event-rendering-review/consumer-lead-review.json'),
    ('autofade_source_forward_probe','research/evidence/cubase-static/cpr-audio-events-001/autofade-source/source-forward-probe.json'),
]: prior[label]=pin(p)

reused=[]
for p in [
    'research/evidence/cubase-static/cpr-map-clock-001/list/function-101700eb4.json',
    'research/evidence/cubase-static/cpr-objects-001/audio-native/function-1001f76dc.json',
    'research/evidence/cubase-static/cpr-audio-events-001/renderer-selection/pass10/function-100211a7c.json',
    'research/evidence/cubase-static/cpr-audio-events-001/renderer-selection/pass8/function-10021225c.json',
    'research/evidence/cubase-static/cpr-audio-events-001/segment-consumer/function-10036e34c.json',
    'research/evidence/cubase-static/cpr-audio-events-001/segment-consumer/function-10036eff0.json',
    'research/evidence/cubase-static/cpr-audio-events-001/segment-consumer/function-10036f89c.json',
]:
    p=r/p; e=evidence(p); reused.append({**pin(p),'evidence_id':e['evidence_id']})

claims=[
 {'id':'ER1','status':'static_bound','claim':'The concrete normal remainder construction produces a PAudioSegment carrying selected stream, rounded/reconverted start, end-derived nonnegative length, source offset and the event Float32 volume.',
  'addresses':['10020f2e8','100210508..1002105c0','10011376c','101a179cc','101a17ccc','101a17cec','101a17cdc','101a17d14'],
  'details':['PAudioSegment vptr104436be0; stream+38; start+50; length+58; sourceOffset+60; Float32 volume+68.',
             'The end setter subtracts stored start then FMAX with0 before storing length; finite inputs only in this contract.',
             'Coordinates use native datum conversion then sign-selected +/-0.5 and FCVTZS in construction. This is not ties-to-even frame rounding.',
             'The constructor and stores establish segment data, not sample consumption.']},
 {'id':'ER2','status':'static_bound_with_source_role_dependency','claim':'A source-backed zero effective auto-fade flag word bypasses automatic fades without a builder suppression override.',
  'addresses':['1001f7554','1001fcf1c','101700eb4','101720d58','10018cd6c','10020f708..10020f78c'],
  'details':['Local track+170 nonnull is used directly. Otherwise track+618 tail101700eb4 obtains selected list+30 owner, and101720d58 loads that receiver+c0.',
             'MAutoFadeSetting vtable104440de0 +98 reads u16 into+c, Double into+10, then four expected MInterpolator objects into+18/+20/+28/+30.',
             'Builder10020f740/748 skips automatic fades for nil effective setting or u16+c==0 before duration/interpolator use. Nonzero settings are outside this first subset.',
             'Parent-owned forward probe reaches the MRoot project setting and local track null objects by native reader order; exact source/project role and clone/mutation scope remain in the separate autofade-source finding.',
             'Builder flags0x28 can suppress automatic fades but are not used as source-fidelity evidence. Flags0 and0x80 do not suppress them.']},
 {'id':'ER3','status':'static_bound_conditional','claim':'Null event fade pointers and absent neighbor attributes yield the normal remainder path when effective automatic fades are disabled and the event is otherwise eligible.',
  'addresses':['100212f3c','1000ea79c','1000ea87c','1000ea704','1000ea694','10020f2e8'],
  'details':['100212f3c initializes both fade extents to0 and computes them only for nonnull event+90/+98.',
             'Neighbor getters use numeric keys0x76504643 and0x744e4643; source absence and unchanged fresh state are required.',
             'Require actual MAudioEvent, nonnull clip with current validity predicate nonzero, unmuted event, finite Float32 volume>0, positive finite rounded range, and no explicit fades/neighbors/other processing state.',
             'No assertion that null local auto-fade, absent fade objects, or one event alone proves a dry timeline.']},
 {'id':'ER4','status':'static_bound','claim':'A MAudioTrack virtual path builds a segment list with flags0x80 and exposes inclusive-end selection, independently of the offline PCM consumer.',
  'addresses':['10444aa98+118','1001f9090','1001f91a0','1002115a0','10444aa98+1b0','1001f96f8'],
  'details':['RTTI/vtable binds MAudioTrack; private1001f91a0 passes owner+130 track, constructs flags0x80 builder and commits generated segments to owner+68.',
             '1001f96f8 returns the first segment with end>=query on its search path, or cached successor after generation checks.',
             'This is a concrete track-side producer/selection relation; its initialized host receiver, live callback execution and exact-end PCM handling are not established here. Do not project a half-open live selection rule from this iterator.']},
 {'id':'ER5','status':'static_bound_conditional_pcm','claim':'The inner10018fb40 consumer reads a PAudioSegment stream and applies its Float32 volume before writing returned frames.',
  'addresses':['100190b08..100190b78','100190c9c..100190fdc'],
  'details':['Class check PAudioSegment; length>0; stream loaded+38 and Float32 gain+68.',
             'Source offset and length are converted from segment canonical datum to caller output datum. For finite nonnegative values, seekFrame=FCVTZS(offsetFrames+0.5), frameCount=FCVTZS(lengthFrames+0.5).',
             'Selected stream is cloned through+c8 and checked as AudioStream. AudioAccessor10036e34c is created with flags5/read mode, then10036e964 copies output format properties.',
             'If segment gain differs from Float32 1, accessor and output are set to numeric sample format5. The accessor source-rate field is separately loaded from cloned stream+140.',
             'For a successful bounded read, request=min(remaining,10000);10036eff0 returns count. The code checks backend position against total length, refuses nonpositive returned count and flags short output writes.',
             'Nonunity gain multiplies returnedFrames*outputChannels contiguous Float32 samples, in16-sample vector groups then scalar remainder. No clipping, addition, gain ramp or FMA appears in this loop. Unity skips arithmetic.',
             'The finite reconstruction equation is y[k,c]=Float32(x[k,c]*g) for nonunity g, otherwise byte-preserved x, before the output writer. FP rounding/denormal state must be specified for bit claims.',
             'For full successful reads before or exactly at source EOF, emitted source indices are [seekFrame,seekFrame+frameCount); no extra endpoint sample is requested. Short-read/error/cancel outcomes are outside this success equation.']},
 {'id':'ER6','status':'static_bound','claim':'Numeric sample format5 is the concrete float32 descriptor; equal source/output format is a separately required direct-read gate.',
  'addresses':['10012c444','10012c5e0','10036ee80','10036e964','10036fca0'],
  'details':['Descriptor bytes10391d140=(type2,bits32,id5,4), materialized with literal1038928f0 float32. Lookup compares descriptor+18 id.',
             '10036ee80 applies descriptor bit width through virtual+120 and type through+130.',
             '10036e964 passes output+10 format interface into accessor+1a0→10036fca0, copying rate, frame-byte layout, bit width, format/byte-order and channel/alignment fields.',
             'In the unity-gain branch the caller output format is preserved; it is not automatically Float32. A Float32 reconstruction must declare outputformat5.',
             'Input PCM24 conversion and rate mismatch are separate numerical studies, not silently replaced by generic system conversion.']},
 {'id':'ER7','status':'scope_limit','claim':'The offline action is not identified with ordinary live playback, even though its inner segment PCM contract is concrete.',
  'addresses':['10018fb40','1001901d0..100190304'],
  'details':['The containing action has progress/cancel/output creation and temporarily writes event attribute0x74616462 while constructing segments. Its entire action is not stitched to the earlier empty-attribute selector.',
             'The inner loop is conditioned on an already selected concrete segment stream. MAudioTrack production and the source selector are separately established local contracts.',
             'This supports a bounded independently implemented event-local reader under explicit source state; it does not establish complete Cubase timeline/mixer/automation/plugin/latency behavior or runtime equivalence.']},
]

result={'schema_version':1,'finding_id':'CPR-EVENT-RENDERING-001',
 'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'status':'draft pending external source-auto-fade seal; native evidence complete and verified',
 'scope':'Static PAudioSegment construction, source-effective automatic-fade zero gate, track producer relation, and one bounded offline Float32 PCM consumer. No target execution or application changes.',
 'source':verification['source'],'verification':{**verification['totals'],'capture_sessions_closed':11,'imported_records':116,'import_session_closed':True},
 'artifacts':{p:pin(h/p) for p in ['verification.json','final-linkage.json','evidence-bundle.json','evidence-import.json']},
 'prior_evidence':prior,'reused_dossiers':reused,'new_functions':functions,'claims':claims,
 'admissible_first_reconstruction':[
  'LoFi-style structurally reached MAudioEvent v6/PAudioClip v4 with already bound zero-only source coordinates and source-backed event length; no arbitrary name or string scan attribution.',
  'Source-effective automatic-fade flags0; no event fade pointers, neighbor attributes, volume curve points, phase inversion, loop/warp/pitch/replacement layers; selected stream remains the verified one-segment AudioCluster.',
  'Current unmuted event, finite positive volume; one event with no overlap; no subsequent source/state mutation. Whole-host observer invariance is not asserted.',
  'Explicit Float32 outputformat5; source/output rate and full direct-format predicates match, or a separately verified sample-format conversion is used. Generic linear resampling is excluded.',
  'Finite nonnegative source range/length and safe signed integer/byte-count products; source media contains the complete requested interval; successful seek/full reads/full writes and no cancellation.',
  'Live timeline/mixer processing is outside this local equation. Any application promotion must name this reconstructed source-state scope and preserve its original unresolved history.'
 ],
 'lofi_analytical_projection':{'sample_rate':44100,'seconds':24,'offset_frames':0,'length_frames':1058400,'read_chunks':{'full_10000_frame_chunks':105,'tail_frames':8400},'provenance':'Arithmetic illustration from already bound LoFi placement and an explicit matching44100 output rate; not target execution or decoded media observation.'},
 'unknowns':['Actual Cubase PCM capture and runtime comparison remain0.','Full live host receiver path, track/mixer gain/pan/automation, effects, PDC, sample-accurate transport and project lifecycle are not closed.','Dynamic callbacks or source/state mutation can change selected streams/settings.','General fades, overlapping/linked events, loops, warped Classic source, nonfinite values, short reads, cancellation, rate conversion and general output writer behavior are not this bounded success contract.'],
 'target_execution':False,'cubase_runtime_comparisons':0}
(h/'finding.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'finding_sha256':hashlib.sha256((h/'finding.json').read_bytes()).hexdigest(),'functions':len(functions)}))
