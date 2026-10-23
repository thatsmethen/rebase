"""Seal this new study only after capture/import and optional independent review."""
from pathlib import Path
import json,hashlib
HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[4]
def pin(p):
 b=p.read_bytes();return dict(path=str(p.relative_to(ROOT)),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
v=json.loads((HERE/'verification.json').read_text())
i=json.loads((HERE/'evidence-import.json').read_text())['structuredContent']['result']
l=json.loads((HERE/'linkage.json').read_text());c=json.loads((HERE/'analytical-controls.json').read_text())
assert v['passed'] and l['passed'] and c['passed'] and i['imported']==104
assert v['totals']['rea_dossiers']==54
for d in HERE.glob('pass[0-9]*'):
 assert 'CLOSED: isolated raw-slice MCP session' in(d/'progress.log').read_text()
assert 'CLOSED: evidence import session' in(HERE/'import-final.log').read_text()
functions={r['entry']:r for r in v['functions']}
def ev(*entries):
 return [dict(entry=e,directory=functions[e]['directory'],source_file_offset=functions[e]['source_file_offset'],
  bytes=functions[e]['source_bytes'],sha256=functions[e]['raw_sha256'],evidence_ids=functions[e]['evidence_ids'])for e in entries]
base=ROOT/'research/evidence/cubase-static/cpr-audio-events-001'
ext=[base/'placed-rate-ownership'/x for x in ['finding.json','artifact-manifest.json',
 'pass2/native-1003704d4.txt','pass2/native-1003704fc.txt',
 'pass3/native-10036e34c.txt','pass3/native-10036e858.txt',
 'pass4/native-10036cd94.txt','pass4/native-10011376c.txt']]
ext += [base/'renderer-selection'/x for x in ['finding.json','pass9/native-1002125e0.txt']]
ext += [base/'event-rendering'/x for x in ['pass9/native-10036ee80.txt','pass10/native-10012c5e0.txt','pass11/native-10012c444.txt']]
ext += [ROOT/'research/evidence/cubase-static/cpr-map-clock-001/attributes/source_tools.py',
 ROOT/'.tools/rea/node_modules/rea-agents/skills/reverse-engineer-anything/SKILL.md',
 ROOT/'.tools/rea/node_modules/rea-agents/skills/reverse-engineer-anything/references/native-and-artifacts.md',
 ROOT/'.tools/rea/node_modules/rea-agents/skills/reverse-engineer-anything/references/evidence-workflows.md',
 ROOT/'.tools/rea/node_modules/rea-agents/package.json']
external=[pin(p)for p in ext]
f=dict(id='CPR-PROCESSED-STREAM-RATE-001',revision=1,
 evidence_class='Original-image static receiver/rate/format contracts; supplied-state analytical controls',
 target_executed=False,target_runtime_comparisons=0,source_sha256=v['source_sha256'],
 conclusion='The inspected processed wrappers do not establish project-rate conformance. Curve and inversion streams expose Float32 while forwarding their input rate. The fallback warp stream reports the rate snapshotted by its input accessor. A fresh grouped path explicitly converts each member accessor to the chosen first-collected reference stream rate and format, then exposes Float32 output views at that reference rate. This is a concrete differing-rate conversion boundary within grouped processing, distinct from project/device timeline rate.',
 correction_history=[dict(issue='Initial working interpretation equated group reference with incoming requested event.',resolution='Independent review tracked X23 overwrite: first collected event controls reference flag. Fresh1002ede48 capture also binds count>1. Initial parent messages are superseded; no prior sealed study changed.')],
 contracts=[
 dict(id='PSR1',claim='100211a7c returns exact clip+188 when builder byte+8 bit5 is set. Otherwise it first requests typed AudioStream from event numeric attributes using runtime key105028978. A cache hit bypasses construction. A miss calls10021225c(event,context,0,builder+38); a result different from clip+188 is cached and event is queued for builder cleanup. Thus saved clip format does not constrain an arbitrary cached stream.',evidence=ev('0x100211a7c')),
 dict(id='PSR2',claim='10021225c starts from event clip+188, permits pre-replacement1004642e0(manager,event,0), curve1002125e0, inversion100112ca8, optional pitch100211c80, warp1002126dc, and post-replacement1004642e0(manager,event,1), in that order. Non-null layer results replace the current source; final result is retained and local layer references released. A later layer may supersede an earlier wrapper. No rate equality is inferred across opaque pre/post/pitch replacements.',evidence=ev('0x10021225c')),
 dict(id='PSR3',claim='Curve ctor100110c18 and inversion ctor100112ca8 invoke10035a0f4, which stores/retains their supplied input at+30 and stores source offset/length at+38/+40. Their concrete vtables1044360a8/1044368c8 both route rate+140 to10035a744, which tail-calls input+140. Kind+150 returns2 and bits+158 returns32. These wrappers therefore change exposed sample format to Float32 without assigning project rate.',evidence=ev('0x100110c18','0x100112ca8','0x10035a0f4','0x10035a744','0x10035a0d4','0x10035a0e4'),dispatch='initial-wrapper-dispatch.json'),
 dict(id='PSR4',claim='Their reader factories use10035a2b8: flagbit1 rejects; an existing wrapper+48 accessor is retained/reused. A fresh accessor is constructed from input+30 with supplied flags and policy1, then alignment/layout/kind/bits32 are set. No actual rate setter occurs in this factory. Successful return is wrapper+20; base construction stores wrapper at returnedReader+8. Thus the outer accessor sees wrapper rate, while the inner accessor retains its own initialized owner-derived rate. Seek10035a640 adds stored source offset to the existing inner accessor seek and subtracts it from nonnegative result. No fresh converter is constructed by this seek.',evidence=ev('0x1001113f8','0x100112df8','0x10035a2b8','0x10035a640')),
 dict(id='PSR5',claim='1002126dc requires nonnil event/context/source/clip, a config from1002bf008, successful1002bc2f0, and config+18 returning0 with true readiness byte. Context+d0 root rate10171c5a0 creates local datum10 for offset/start coordinate conversion and signed half-away rounding. The context rate is not passed as a stream-rate setter here. Feature10450a7a8 selects optional grouped1002eeea8; failure/off falls back1002c2040. Nonzero caller flag additionally sets fallback range1002c2748. Config status2 uses a wait path then returnsnil; other failure paths returnnil.',evidence=ev('0x1002126dc','0x1002c2748')),
 dict(id='PSR6',claim='Fallback1002c2040 constructs vtable10445a9f8 and input holder1002b603c→1002b5e20. Holder creates AudioAccessor(source,0x25,1), sets source channel count, alignment0, layout2, formatID5 and seeks0 after readiness; it does not invoke actual rate setter+f0. Fallback rate+140→1002c2c58→holder secondary+38→1002b6664→accessor+e8, so it reports that accessor rate snapshot. Fallback kind/bits getters are2/32. It returns its own+20 reader only after single-open byte+40 is clear, holder seek0 succeeds exactly, and config+20 returns0; then sets byte+40. Detailed warp processing is not reconstructed.',evidence=ev('0x1002c2040','0x1002b603c','0x1002b5e20','0x1002c2c58','0x1002b6664','0x1002b6504','0x1002c2aa8'),dispatch='initial-wrapper-dispatch.json; secondary-wrapper-dispatch.json'),
 dict(id='PSR7',claim='Grouped1002eeea8 does not simply wrap the incoming current stream: after the nonnil check it derives member events/context through1002ee09c and group state through1002ee258/1002ee24c. Collector1002ede48 invokes10177929c/1017792dc, type-filters and inserts entries; count<=1 is cleared at1002ee044..60, so this branch requires at least two collected events. First-entry ordering/provenance is not resolved. Fresh state1002ef378 creates group manager1002d89fc (vtable10445cbf0) and output service1002ef4d8. For each member,1002eeea8 passes that member event clip+188 to1002d8c20, with isReference true only when member event equals the first event pointer in the collected array (1002eefa4 and1002ef07c); this is not automatically the incoming requested event.1002d8c20 retains each stream, stores entry offset, and writes selected reference index+38 only for that flag. Manager+140→1002d9034 delegates to the selected entry stream+140; kind/bits similarly delegate. A preexisting group state, missing/changed members, callbacks, and state+44 already set are separate conditions; fresh construction alone is not a guarantee about every cached group.',evidence=ev('0x1002eeea8','0x1002ee09c','0x1002ede48','0x1002ee24c','0x1002ee258','0x1002ed698','0x1002ef6b4','0x1002ef378','0x1002d89fc','0x1002ef4d8','0x1002d8c20','0x1002d9034','0x1002d90cc','0x1002d9114'),dispatch='group-source-dispatch.json'),
 dict(id='PSR8',claim='1002ef7a8 constructs fallback warp1002c2040(manager,config), then installs it as service+10 with1002c3730; invalid/empty ranges are handled separately1002c2748. Per-member output object1002c3968 (vtable10445ad48) stores service+30/index+38/channels+3c/offset+40.1002c3d7c returns that indexed object. Its rate+140→1002c4700 delegates service+10 stream+140; normal nonnil service exposeskind2/bits32.1002c3730 rejectsnil,new stream replacement while any output is opened, or total requested channels exceeding nonzero available channels. Output reader1002c4534 is single-open via+48 and uses locked service state; this is not an independent stateless stream per member.',evidence=ev('0x1002ef7a8','0x1002c3730','0x1002c3968','0x1002c3d7c','0x1002c4700','0x1002c4790','0x1002c47b8','0x1002c4534'),dispatch='secondary-wrapper-dispatch.json'),
 dict(id='PSR9',claim='Group reader factory1002d8d5c requires all existing entries nonnil, then1002d91a4 stores exact group at reader+8 and creates a separate AudioAccessor per member withflags5/policy1. It copies alignment/layout and configures per-member channel frame size. Crucially1002d9300..931c queries group+140 and invokes each member accessor+f0 actual Float32 rate setter.1002d9320..9358 copies the selected reference stream formatID via accessor+198. Therefore heterogeneous members are explicitly converted to the reference stream format/rate before the outer Float32 warp/view. The reference may be PCM24: outerFloat32 does not justify deleting an inner integer-format conversion. No project/device rate argument appears in this constructor.',evidence=ev('0x1002d8d5c','0x1002d91a4'),dispatch='linkage.json; group-reader-dispatch.json'),
 dict(id='PSR10',claim='Group reader+10→1002d9620 issues the same requestN to each persistent member accessor+168. Destination offsets use signed32 arithmetic from bitWidth*N/8 times cumulative channels; for valid positive bounded inputs this concatenates member channel blocks. It returnsN if every result is nonnegative, otherwise the last negative response; it does not reduceN to a short positive member count. Group reader+20→1002d96f0 seeks each existing accessor at requestedPosition+storedEntryOffset, returnsrequestedPosition if all results nonnegative, or the last negative narrowed signed32 result. Neither method directly rebuilds member accessors or rearms first-read/converter state. These are supplied partition/seek-state semantics, not proved PCM equality or whole-host scheduling.',evidence=ev('0x1002d9620','0x1002d96f0'))
 ],
 bounded_application_implications=[
 'Keep original file/cluster rate, selected processed-stream rate, initialized reader-owner rate, each internal accessor output rate, builder coordinate rate and device/reader datum rate as separate inputs.',
 'The fresh curve/inversion path can justify Float32 selected-source format at an unchanged source rate when its exact processing operation is also supported. It does not justify applying arbitrary curve/inversion or silently bypassing them.',
 'A future grouped implementation can explicitly configure member accessors to a designated reference member and preserve inner format ordering, persistent accessor histories, sameN read calls and per-entry seek offsets. This is a grouped processing contract, not a recovered project-rate policy.',
 'Do not promote the existing source-bound placed-event gate to arbitrary processed or grouped events from these metadata/getter bindings. Configuration, pitch/pre/post replacements, processor DSP, group membership/caches and current backend identity remain additional admission gates.',
 'No absence claim: untraced pre/post replacement, pitch layer, prepared/cache stream and later channel/device stages could establish other rate contexts. This study closes only the enumerated receiver paths.'
 ],
 next_edges=[
 dict(addresses=['0x1002ede48','0x10177929c','0x1017792dc','0x1001fe840'],question='Bind grouped collection membership/order before equating first collected reference with requested event, another particular event, or project rate.'),
 dict(addresses=['0x1004642e0','0x100213d2c','0x100211c80'],question='Bind pre/post prepared stream and pitch constructor/output getter before claiming every selected source preserves original cluster rate.'),
 dict(addresses=['0x1002bf008','0x1002bc2f0','0x1002c3e2c','0x1002c7960'],question='Close processor/configuration and service read/cache operations before implementing general warp/group PCM or reset/EOF behavior.'),
 dict(addresses=['0x1002d976c'],question='Its tell-like slot has nontrivial pointer adjustment; not used to infer an ordinary integer frame-position contract here.'),
 dict(addresses=['0x101d9b3b4','0x101d3eb24','0x10171c5a0'],question='Downstream device datum and source/builder root ownership are an independent peer study; no equality follows from the source/reference paths above.')
 ],
 limits=[
 'No proprietary target/library execution, activation, audio capture or runtime conformance comparison. No Application or earlier evidence files changed.',
 'Exact original Mach-O pointer cells and instructions are authority. REA raw slices omit externals, globals, imports, RTTI and unwind context; metadata intervals include disconnected exception tails. Pseudocode ABI/type artifacts are not compilable faithful source.',
 'Non-null initialized receivers, valid indices/membership and successful factory/readiness/configuration branches are required. Later host callbacks or cached-state substitution are bounded external conditions, not assumed immutable.',
 'Current stream/provider format is separate from saved CPR metadata and attached file bytes. This finding does not identify a proprietary decoder implementation.',
 'Analytical controls are supplied-state discriminators, not target observations. Integer/offset/byte arithmetic controls stay inside representable bounds; malformed count/index/pointer behavior is not reconstructed.'
 ],
 verification=v['totals'],canonical_import=i,analytical_control_count=c['count'],
 artifacts=[pin(HERE/n)for n in ['verification.json','evidence-bundle.json','evidence-import.json','linkage.json','analytical-controls.json']],
 external_references=external,sessions='Ten isolated raw-slice MCP capture clients and one canonical import client explicitly closed.',
 reproduction=['Exclusive derive.py PASS; analyze_pass.mjs PASS using pinned local scripts/rea and Ghidra2G.',
 'verify_evidence.py; combine_evidence.mjs; import_evidence.mjs; linkage.py; analytical_controls.py.',
 'write_finding.py creates finding and cold manifest exclusively; do not rerun into sealed directory.'])
review=ROOT/'research/evidence/application/APP017/reference-rate-independent-review.json'
if review.exists():
 f['independent_review']=pin(review); external.append(pin(review))
with (HERE/'finding.json').open('x')as out:json.dump(f,out,indent=2);out.write('\n')
rows=[pin(p)for p in sorted(HERE.rglob('*'))if p.is_file()and p.name!='artifact-manifest.json'and'__pycache__'not in p.parts]
m=dict(schema_version=1,kind='cold immutable local static study inventory',target_executed=False,
 source_sha256=v['source_sha256'],files=rows,external_references=external,
 excludes=['artifact-manifest.json itself','Python __pycache__'],
 limits='Raw derivatives/provider captures remain local evidence. This is not a publication allowlist; no mutable Application pins.')
with (HERE/'artifact-manifest.json').open('x')as out:json.dump(m,out,indent=2);out.write('\n')
print(json.dumps(dict(finding=pin(HERE/'finding.json'),manifest=pin(HERE/'artifact-manifest.json'),files=len(rows),external=len(external))))
