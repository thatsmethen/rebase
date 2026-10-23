"""Verify retained REA bytes against the immutable original; seal bounded claims."""
import hashlib,json,sys
from pathlib import Path
P=Path(__file__).resolve().parent
sys.path.insert(0,str(P.parent.parent/'cpr-map-clock-001'/'attributes'))
import source_tools as s
R=s.ROOT;H=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();proof=[]
for d in sorted(P.glob('pass*/derivation.json'),key=lambda p:int(p.parent.name[4:])):
 assert json.loads(d.read_text())['source_sha256']==s.PIN
 for row in json.loads(d.read_text())['derivatives']:
  a=int(row['entry'],16);b=(d.parent/row['raw_file']).read_bytes();assert H(d.parent/row['raw_file'])==row['raw_sha256']
  assert b==s.data[s.offset(a,len(b)):s.offset(a,len(b))+len(b)]
  raw=json.loads((d.parent/f'bytes-{a:x}.json').read_text())['structuredContent']['raw_result']
  assert raw['complete']and bytes.fromhex(raw['bytes_hex'])==b
  close=json.loads((d.parent/f'close-{a:x}.json').read_text());assert not close.get('isError')
  fn=d.parent/f'function-{a:x}.json';out=json.loads(fn.read_text());assert not out.get('isError')
  pseudo=out['structuredContent']['raw_result']['value']['pseudocode'];(d.parent/f'pseudocode-{a:x}.txt').write_text(pseudo)
  proof.append(dict(entry=row['entry'],bytes=len(b),source_file_offset=s.offset(a,len(b)),sha256=H(d.parent/row['raw_file']),dossier=str(fn.relative_to(R)),dossier_sha256=H(fn),warnings_present='WARNING:'in pseudo))
refs=[]
for rel in ['cpr-objects-001/audio-native/function-1017017a0.json','cpr-objects-001/audio-native/function-1000ee164.json','cpr-objects-001/audio-native/function-1000faff8.json','cpr-audio-timing-001/function-101c22dc0.json','cpr-audio-timing-001/native-101c22dc0.txt','cpr-audio-timing-001/function-101c22884.json','cpr-audio-timing-001/finding-v1.json','cpr-map-clock-001/list-review/constructor-context/function-101c246b4.json']:
 p=P.parent.parent/rel;assert p.is_file();refs.append(dict(path=str(p.relative_to(R)),sha256=H(p)))
links=[]
for n in ['event-data-slots.json','context-data-vtables.json','constructor-vtables.json','edit-method-vtables.json','list-vtables.json','containing-node-slots.json','transform-provider-vtable.json','class-name-bindings.json','fixture-projection.json']:
 p=P/n;links.append(dict(path=str(p.relative_to(R)),sha256=H(p)))
report=dict(schema_version=1,target_executed=False,status='Bounded serialized-source coordinate gate established; playback/rendering gate remains separate.',source=dict(path=str(s.SOURCE.relative_to(R)),sha256=s.PIN,bytes=len(s.data)),verification=dict(exact_ranges=len(proof),bytes=sum(x['bytes']for x in proof),all_REA_readbacks_match_original=True,all_slices_closed=True,ranges=proof),reused_evidence=refs,linkage_and_fixture_artifacts=links,
 result=dict(lofi='Direct audio event can be represented as an unresolved source event at0 seconds, duration24 seconds, source offset0 under the explicit type10 source-coordinate gate. No source media was acquired or played.',classic='Excluded from this type10 coordinate gate. Its own clip datum0 is musical; its14880 raw length cannot be interpreted as samples. Existing Warpscale state also needs the separate audible-state contract.'),
 source_coordinate_gate=[
 'Successful bounded versioned archive decode with exact original custody and known object identities; no regex/scanning recovery. PArrangement v4→MRoot v6→root MTrackList v0→direct MAudioTrackEvent v1→MListNode v0→MAudioEvent v6→PAudioClip v4.',
 'MRoot, containing audio track, and audio event each have serialized Start and Offset bits+0. Restrict this initial application profile to direct counted hierarchy with no nested parts/folders between root and audio track. Serialized prefix word0 on these three objects; all raw fields finite; event Length at least1 as required by native restore clamping, and positive finite converted duration.',
 'Containing track MListNode datum0 must resolve the accepted shared tempo/signature identities already validated by the clock-role reader; do not infer placement units from own clip datum.',
 'Own clip datum must be exactly type10 with finite positive stored f64 scalar. For initial source reconstruction require its bits equal f64(1.0/Double(serialized AudioFile f32 rate)); this agreement is evidence consistency, not proof of the later runtime file backend rate.',
 'Convert duration with distinct f64 operations product=storedScalar*rawLength; seconds=product/1.0. Initial zero placement/offset produce0 seconds. Keep raw bits, object offsets, identities, rate, source hash and profile alongside projected values.',
 'Recover an explicitly unresolved media event; do not manufacture a playable Clip or claim rendered sound parity. Source-file/segment, gain/fade/mute/warp/variation and routing gates are separate and must pass before any relink-to-playback promotion.',
 'Do not silently broaden to datum0/17, nonzero ancestors/Start/Offset, nested parts, multiple/changed clock identities, unsupported archive versions or an unexplained current-media-rate mismatch.'],
 native_chain=[
 dict(edge='Serialized event fields',detail='Retained MEvent reader1017017a0 reads u16 and threef64. MAudioEvent setters/getters bind Start+60(+d8/+e0), Length+68(+e8/+f0), Offset+70(+f8/+100). Native reader1000ee164 normalizes Length to at least1 and Offset to at least0; accepted source subset excludes normalization changes.'),
 dict(edge='Own clip versus parent context',detail='MAudioEvent+258→1000ea594 returns event+48. Generic event+270→1017015fc asks own clip+108. PAudioClip+108→1000f8598 returns clip+38 datum: tag0 unchanged, nonzero may refresh to type10 from current owner/cluster rate. PAudioClip+110→1000f8638 returns separate clip+198 type10 sample datum. These accessors are not interchangeable.'),
 dict(edge='Parent context construction',detail='1016e1894 initializes MContext+50 from canonical datum and zero origin;1016e1bd0 copies parent state then1016e222c binds a child event. For a containing audio track, event+258→10174a698 returns its MListNode; node+110→1016e9a20 returns node+38 stored datum. MListNode+108→1016e9a18 is the same address. Entering an audio event instead uses clip+110 for its child context.1016e222c obtains child origin from parent+108(event), not directly from raw event Start.'),
 dict(edge='Start coordinate',detail='MContext/MEditContext/MPlayContext slot+f8→1016e300c reads target event+e0, optionally transforms in context datum, adds context+78, then converts context+50→canonical. Source gate restricts zero origins and direct containing track, avoiding a generalized hierarchy placement assumption.'),
 dict(edge='Length datum selector',detail='MContext+100→1016e3990 reads event+f0 and calls1016e39c8. It asks context-owned event+2d0 then returned edit-method+28(context,targetEvent). MAudioTrackEvent+2d0→1001f7e24 returns global105028698. Original initializer1001ffd98 establishes base105028670;1001ffe68..80 constructs atbase+28 and stores vtable104446e60. Its+28→1001c4840 falls to1016f2d88 when the target has a clip.1016f2d88 asks targetEvent+258 then clip+108; absent clip falls back to context datum. The literalMAudioEvent class predicate does not turn clip-less inputs into musical clips.'),
 dict(edge='Length and offset conversion',detail='1016e39c8 returns+0 for zero delta. Selected datum0/17 uses converted endpoint differences about actual Start; tag1 returns delta; other scalar tags call101c22dc0. Generic scalar branch multiplies source scalar then divides destination scalar. Context+108→1016e4d98 negates event Offset, converts as a delta, then adds converted Start, establishing an origin shift; this initial gate only projects zero offset.'),
 dict(edge='Canonical scalar',detail='Original initializer101c26ea0..ec0 writes global10500f150 tag1 and f64bits3ff0000000000000. This is disconnected initializer code within the retained LC_FUNCTION_STARTS interval101c26df0; the original instructions, not that interval entry pseudocode, establish it.'),
 dict(edge='Concrete default transform selection',detail='1016e222c queries replaceable global105005fc0 provider+18 for context event then node. Setter1016e1840 retains/replaces it. Native100300954 installs adjusted vtable1044613e8; its+18→100300950→100300694. After common-object QI, this provider only accepts classMAudioEvent orPAudioClip. Explicit class predicates for MAudioTrackEvent and MListNode/MTrackList reject both; no transform is supplied for the containing audio-track context by this implementation. This is not an assertion that arbitrary provider replacements are inert.'),
 dict(edge='Audio-event child transform',detail='100300694 may return a composite even without Warpscale.100300b5c asks clip Warpscale through100300a7c and appends it if present; it also appends a scalar transform when1000edb70(event)!=1. These affect the child/source context and are assigned to the separate audible-state review. No nil-transform shortcut is used for an audio-event child.'),
 dict(edge='Fixture difference',detail='Byte-pinned LoFi own datum10 scalarbits3ef7c6f8c751f177 and Length1058400 give24s bits4038000000000000 by the scalar branch. Classic own datum0 uses different endpoint arithmetic and is excluded here. Both direct roots/tracks/events have+0 Start/Offset; source media remains unavailable.')],
 runtime_boundaries=[
 'This is interpretation of serialized source values through recovered native operations, not observation of effective hosted Cubase playback.',
 'PAudioClip+108 may update a nonzero scalar from owner/cluster rate. Peer cluster work proves the first-file rate path invokes a lazy backend/property bag; a serialized rate match alone does not establish its later runtime return.',
 'The transform provider is replaceable; a different provider can return different transforms even for otherwise accepted classes. Default concrete class rejection is the bounded native path, not universal host invariance.',
 'Event data attachment1000ea374 may dispatch a rate-ratio change when replacing an existing nonnull clip; successful fresh-source reconstruction does not assert editing/reattachment invariance.',
 'Full waveform/segment orientation, relink behavior, warp/timestretch, event gain/fades/mute, track processing/routing, external observers and actual FP environment remain separate. Missing-media placement must stay visibly unresolved.',
 'REA slices omit imports/globals/RTTI/relocations/unwind. Original pointers/instructions and pinned source strings bind the material edges. Some intervals contain disconnected initializer/exception code; pseudocode warnings are retained and no warning-heavy split/join pseudocode is used as authority.'],
 recommended_tests=[
 'Pinned LoFi source reconstructs one unresolved event at0,duration24,offset0 with exact source bits/proof; Classic raw event retained but excluded by datum0 gate.',
 'Negative controls mutate event or ancestor Start/Offset to a nonzero value or negative zero; initial zero-only profile rejects conversion while preserving raw record.',
 'Reject datum aliases, NaN/Inf/nonpositive scalar or Length, Length<1 normalization case, changed shared clock roles, rate/scalar-bit mismatch, unsupported versions or ambiguous object references.',
 'Keep original/report bytes and unresolved event identities unchanged on SaveAs/reopen; reject forged projected seconds or altered source offsets against replay.',
 'Do not use a synthetic PCM fixture to assert Cubase runtime equality. Later relink/render oracle must separately validate exact media hash, one-segment admissibility and audible-state gates.'])
(P/'finding.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(finding=str(P/'finding.json'),sha256=H(P/'finding.json'),ranges=len(proof),bytes=sum(x['bytes']for x in proof))))
