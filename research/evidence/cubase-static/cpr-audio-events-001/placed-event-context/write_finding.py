"""Seal this bounded context study after all REA clients have closed."""
from pathlib import Path
import hashlib
import json

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]


def pin(path):
    raw=path.read_bytes()
    return dict(path=str(path.relative_to(ROOT)), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


verification=json.loads((HERE/'verification.json').read_text())
bindings=json.loads((HERE/'original-bindings.json').read_text())
imported=json.loads((HERE/'evidence-import.json').read_text())['structuredContent']['result']
assert verification['passed'] and imported['imported']==verification['totals']['unique_evidence_records']==70
for p in HERE.glob('pass[0-9]*'):
    assert 'CLOSED: isolated raw-slice MCP session' in (p/'session.stdout.txt').read_text()
assert 'CLOSED: evidence import session' in (HERE/'import.stdout.txt').read_text()
assert json.loads((HERE/'analytical-controls.json').read_text())['passed']
for row in bindings['external_references']:
    assert pin(ROOT/row['path'])==row

finding=dict(
    id='CPR-PLACED-EVENT-CONTEXT-001',
    evidence_class='bounded original-image static contract and supplied-state analytical controls',
    target_executed=False, target_runtime_comparisons=0,
    source_sha256=verification['source_sha256'],
    conclusion='For a direct audio-track context with zero ancestor origins, the recovered Start query converts containing-datum ticks through its bound native clock. Length and Offset use the target clip datum selected by the audio-track edit methods. This closes nonzero source coordinates under the stated fresh-resource, default-provider and explicit builder-rate conditions; it does not establish effective hosted track state.',
    admitted_context=[
        'Concrete MRoot / direct MAudioTrackEvent / MListNode ancestry; no intervening folder, part or additional shared-owner ambiguity.',
        'Root and containing audio track have positive-zero Start and Offset. Default concrete transform provider remains installed, with no substitute transform.',
        'Containing MListNode datum0 points to the same source-bound tempo/signature roles independently accepted by the fixed or bounded jump-map clock contract.',
        'Own PAudioClip datum10 carries the separately verified source period; its accessor/current-rate refresh is admitted only under the existing matching-rate source context.',
        'Native event Length normalization is inert (finite length at least1); Offset normalization is inert (finite nonnegative offset). Application restriction to whole-frame length/offset is stricter.',
        'Saved MTrackEvent v2 number is positive-zero. The reconstructed resource starts with MTrack+18 positive-zero and has no later resource-delay modification or inherited copy state.',
        'Builder root rate is explicitly supplied. Matching the PCM source rate is an application context choice, not inference of an unknown live root+128 provider.',
        'Finite bounded arithmetic under nearest rounding; source/media identity and all sound-processing gates remain separately required.'
    ],
    operations={
        'notation':'RN64 means a separately rounded binary64 operation. Native clock inverse is the separately sealed +0x30 tick-to-seconds operation; it preserves its own fixed/map rounding and knot rules.',
        'start':'q=RN64(rawStart+contextOrigin); S=RN64(clock.inverse(q)/1.0), where accepted contextOrigin is +0. This is not rawStart*clipPeriod.',
        'length':'For nonzero scalar datum10: L=RN64(RN64(rawLength*clipPeriod)/1.0). Delta helper returns +0 immediately for either signed zero. Native tag1 is a distinct direct-return path; datum0/17 use endpoint differences and are excluded for clip Length/Offset here.',
        'offset':'Read rawOffset, FNEG, delta-convert, FNEG. For nonzero datum10: O=-RN64(RN64((-rawOffset)*clipPeriod)/1.0). Either raw zero yields -0 because the delta converter returns +0.',
        'event_end':'E=RN64(S+L), separately from the later segment builder quantization and stored length/getter end.',
        'ancestor_origin':'MContext+108 computes RN64(ConvertDelta(-ancestorOffset)+ConvertStart(ancestorStart)); the two canonical positive-zero ancestor inputs yield +0. Context range assignment converts this canonical value into the child datum before storing context+78.',
        'track_shift':'MAudioTrackEvent virtual+558 returns RN64(resource+18 + track+90) when resource exists, else track+90. Ordinary caller enables this getter.10020ee24 skips the shift loop for numerical zero, otherwise adds it to each generated segment Start via virtual+d0; it does not recompute source Offset there.',
        'ordinary_window':'1002115a0 passes [0,2592000] to10020ee24. Direct-track range collection clips the selected child event to this interval. The application nonnegative <=86400 subset is contained within it; an event-local window is equivalent there. Nested folders/parts are excluded.',
        'builder_rate':'10020ee24 calls MContext+d0 ->1016e70ec -> context+18 root, and passes it to10020f2e8.10171c5a0 queries root+128 interface slot0 when present, otherwise returns exact44100. This rate is not automatically the serialized AudioFile sample rate.'
    },
    native_edges=[
        dict(id='CTX1', entries=['0x1002115a0','0x1017014e4','0x1016e6744','0x1016ea7fc','0x103104c40'],
             claim='Track+280 returns its containing node. Recursive context construction gets the first associated event from node+58 list, compares it to node+30 owner, creates the root case or recurses through the parent container, then binds the explicit node if needed. This is a concrete counted/owned graph path, not nearest-name ancestry.'),
        dict(id='CTX2', entries=['0x1016e1894','0x1016e1ce4','0x1016e1bd0','0x1016e222c','0x1016e4d98','0x1016e20b8','0x101c247f4'],
             claim='Root context begins canonical with zero ranges. Copies retain parent state, then bind child event/node datum and recompute child origin from parent+108. Context+78 is a datum-bound origin, not a raw event offset. Direct positive-zero ancestor inputs make the admitted origin zero.'),
        dict(id='CTX3', entries=['0x1016e300c','0x101c22dc0','0x1016e3990','0x1016e3794','0x1016e39c8'],
             claim='Start uses containing datum, whereas scalar Length/Offset use audio-track-selected own clip datum. Datum0 to canonical1 calls clock+30 then divides1; datum10 multiplies its scalar then divides1. Offset negation/zero behavior is explicit.'),
        dict(id='CTX4', entries=['0x10174b610','0x10174b638','0x1017427e0','0x101747fe4','0x1001fc8b0','0x101744d58'],
             claim='Concrete slot+558 adds runtime resource+18 and saved track+90. Resource constructor zeros+18; track constructor zeros+90; MTrackEvent v2 reads a double into+90 after its signed32 word. The normal inspected resource readers do not directly deserialize+18. This does not exclude their callbacks or later host mutation.'),
        dict(id='CTX5', entries=['0x10020ee24','0x1016e70ec'],
             claim='The builder receives the context root as its rate receiver. The start-only shift is applied after segment construction. Rate, filtering, sample rendering and actual host scheduling remain separate concerns.')
    ],
    saved_fields=bindings['saved_track_fields'],
    application_review={
        'scope':'Read-only review of new CPRPlacedSourceEventPlan.swift during APP015 development; final application source identity and tests belong to application acceptance.',
        'result':'No actionable coordinate-gate defect found in reviewed direct-source domain. Source clock replay is independent of edited application tempo; track.numberBits is the correct saved shift field; whole-frame/source bounds and separate reader bounds are conservative.',
        'qualification':'Fresh MTrack+18 zero and explicit source-rate builder are declared state choices. The saved number alone is not evidence of zero effective hosted shift. No additional arbitrary trackWord rejection is justified by these inspected coordinate paths.'
    },
    limits=[
        'No Cubase executable, plugin or vendor library was run. No target audio/render/transport comparison.',
        'Resource+18 can be copied by101742a98 and may be changed after construction. MTrack reader calls101744688 registration/callback machinery; its complete downstream effects were not traced. Fresh-resource acceptance deliberately excludes them.',
        'The inspected concrete default transform provider rejects MRoot/MAudioTrackEvent/MListNode for audio-event/clip transforms. Replaceable global provider and later host changes are outside this conditional state.',
        'Saved shared-node object graphs must satisfy the counted direct ancestry/role conditions. General nested origins, transformations, musical clip deltas and arbitrary shared-resource lifecycle remain unimplemented.',
        'Root rate-provider identity and hosted project sample rate are not derived from CPR AudioFile metadata. Source-rate reconstruction is explicit.',
        'Raw Ghidra slices omit imports, globals, vtables, relocations and unwind context. Metadata interval is not proved reachable function body; decompiler warnings and omitted exception tails are retained. Original instructions and exact table cells are authority.',
        'Analytical controls are finite supplied-state calculations, not proprietary runtime outputs, complete numerical conformance or general project playback.'
    ],
    disconfirming_controls=[
        'Positive raw Start480 with clip period1/44100 must use source clock inverse, not480/44100; change fixed BPM while leaving clip rate constant.',
        'Move positive Start across the accepted jump knot while leaving clip Length/Offset unchanged; their seconds must remain scalar-domain values.',
        'Nonzero saved track+90 or nonzero fresh resource+18 violates zero-shift admission. Copying a resource does not reset+18.',
        'Changed or mismatched tempo/signature role references must not reuse an edited or stale application tempo clock.',
        'Nonzero ancestor Start/Offset, a nested folder/part, alternate transform provider, or a changed clip-rate accessor requires another contract.',
        'Offset+0 and Offset-0 pass through the native delta-zero fast path and both produce canonical offset-0.',
        'Root+128 provider rate differing from file rate distinguishes hosted builder context from the explicit source-rate reconstruction.'
    ],
    verification=verification['totals'], canonical_import=imported,
    analytical_control_count=7,
    primary_artifacts=[pin(HERE/x) for x in ['original-bindings.json','verification.json','evidence-bundle.json','evidence-import.json','analytical-controls.json']],
    external_references=bindings['external_references'],
    reproduction=['derive.py N then analyze_pass.mjs N in a new unsealed directory',
                  'verify_evidence.py; combine_evidence.mjs; import_evidence.mjs',
                  'bind_source.py; analytical_controls.py; write_finding.py'],
    sessions='Ten isolated raw-slice MCP clients and the canonical-import client closed explicitly.'
)
(HERE/'finding.json').write_text(json.dumps(finding,indent=2)+'\n')
rows=[]
for p in sorted(HERE.rglob('*')):
    if p.is_file() and p.name!='artifact-manifest.json' and '__pycache__' not in p.parts:
        rows.append(pin(p))
manifest=dict(schema_version=1,kind='cold immutable local static study inventory',target_executed=False,
    source_sha256=verification['source_sha256'],files=rows,external_references=bindings['external_references'],
    excludes=['artifact-manifest.json itself','Python __pycache__'],
    limits='Raw derivatives/provider captures remain local evidence; this manifest is not a publication allowlist.')
with (HERE/'artifact-manifest.json').open('x') as f: f.write(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(dict(finding=pin(HERE/'finding.json'),manifest=pin(HERE/'artifact-manifest.json'),files=len(rows),external=len(bindings['external_references']))))
