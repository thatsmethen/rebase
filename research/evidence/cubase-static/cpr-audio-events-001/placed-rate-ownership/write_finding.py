"""Seal only this new static study after capture/import/review are closed."""
from pathlib import Path
import hashlib, json
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]

def pin(path):
    raw=path.read_bytes()
    return dict(path=str(path.relative_to(ROOT)),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())

v=json.loads((HERE/'verification.json').read_text())
b=json.loads((HERE/'original-bindings.json').read_text())
owner=json.loads((HERE/'owner-and-metadata-bindings.json').read_text())
imported=json.loads((HERE/'evidence-import.json').read_text())['structuredContent']['result']
controls=json.loads((HERE/'analytical-controls.json').read_text())
assert v['passed'] and owner['passed'] and controls['passed']
assert v['totals']['rea_dossiers']==36 and imported['imported']==72
for p in HERE.glob('pass[0-9]*'):
    assert 'CLOSED: isolated raw-slice MCP session' in (p/'progress.log').read_text()
assert 'CLOSED: evidence import session' in (HERE/'import.stdout.txt').read_text()
external=b['external_references']+[r['record'] for r in owner['checked_original_records']]
external=list({r['path']:r for r in external}.values())
for row in external: assert pin(ROOT/row['path'])==row
functions={row['entry']:row for row in v['functions']}
def evidence(*entries):
    return [dict(entry=e,directory=functions[e]['directory'],
                 source_file_offset=functions[e]['source_file_offset'],
                 bytes=functions[e]['source_bytes'],sha256=functions[e]['raw_sha256'],
                 evidence_ids=functions[e]['evidence_ids']) for e in entries]

finding=dict(
 id='CPR-PLACED-RATE-OWNERSHIP-001',revision=1,
 evidence_class='Original-image static rate/format/ownership contracts and supplied-state analytical discriminators',
 target_executed=False,target_runtime_comparisons=0,
 source_sha256=v['source_sha256'],
 conclusion='The ordinary reader configures sample format but does not assign its timeline or builder rate to a newly created AudioAccessor. The accessor snapshots the rate of the returned reader owner. For the concrete unchanged AudioCluster path that owner is the cluster, whose rate comes from its first current file. This closes a conditional direct one-file rate relationship; it does not prove that native differing-rate timeline playback is absent, because selected/cached/transformed streams, mixed-file cluster accessors and later output stages are separate concrete boundaries.',
 correction={
   'seed_label':'The investigation seed called10036ec30 a rate setter.',
   'verified':'AudioAccessor1044664f0+110→10036ec30 sets frame byte size at+42 and may adjust bit width+40. Actual rate setter is+f0→1003704d4, which stores Float32 S0 at+30 and returns1.',
   'custody':'Earlier sealed evidence was preserved. Receiver-specific slots, original pointer cells and setter instructions in this new study are authoritative.'},
 roles=[
   dict(name='builder rate',owner='context root passed to10020f2e8;10171c5a0',
        use='Creates a type10 period for descriptor coordinate quantization. Not passed to10011376c as stream configuration.'),
   dict(name='reader coordinate period',owner='global1050105e0 object+390, datum+388',
        use='Quantizes descriptor coordinates in101d3eb24. This function does not copy that rate into accessor+30.'),
   dict(name='selected stream',owner='100211a7c return → ordinary remainder constructor10011376c → PAudioSegment+38',
        use='May be exact clip+188 AudioCluster, a cached AudioStream, or an optional processed stream. Constructor retains pointer; no rate conversion/configuration there.'),
   dict(name='reader owner',owner='accessor+28 read context, then readContext+8',
        use='10036e858 queries this owner+140 and stores its Float32 result into accessor+30. Arbitrary factory owner identity is not assumed.'),
   dict(name='output accessor rate',owner='AudioAccessor+30',
        use='Sampled from reader owner on successful initialization; explicit+f0 or format-copy can overwrite it. Not automatically synchronized after owner/host mutation.'),
   dict(name='current file format',owner='AudioFile lazy backend/property bag',
        use='Current kind/bits/rate getters can consult backend state; serialized CPR values and a .wav extension alone do not prove their effective values.'),
 ],
 contracts=[
   dict(id='RATE1',claim='Constructor10036e34c installs1044664f0, zeros converter+20/read-context+28, stores caller policy at+49 and first-read flag1 at+4a. If the source readiness predicate permits and source+f8 returns a reader, it stores that reader at+28, retains reader+8 owner, then invokes+d8→10036e858. That copier queries owner+140, not an unconditional ctor-input getter.',
        evidence=evidence('0x10036e34c','0x10036e858')),
   dict(id='RATE2',claim='Concrete AudioCluster104466150+f8→10036a52c allocates a read context and calls10036cd94(context,cluster,flags). The constructor stores the exact cluster atcontext+8. On the successful factory return, this binds RATE1 owner to the selected cluster; factory failure returns nil. Cluster primary+140→10036af9c and secondary-format+40→10036afc8 consult first file through head/node+8 and call file+140; empty case returns44100. Empty or failed sources are excluded from direct-file admission.',
        evidence=evidence('0x10036cd94','0x10036af9c','0x10036afc8'),
        supplemental='owner-and-metadata-bindings.json checks original factory and dispatch cell'),
   dict(id='RATE3',claim='101d3eb24 at101d3f040..0c0 creates with selected stream, flags0x25, policy1. It sets+150 alignment0, +100 layout2 only for stereo/stereo (otherwise0), +130 kind2, and+120 bits32 or64 according to output format1/2, then transfers accessor into segment+78. There is no actual+f0 rate setter or format-copy call in this initialization. The existing cache path checks layout and can reuse the prior accessor without resampling its rate property.',
        evidence=evidence('0x101d3eb24','0x10036ed34','0x1003704e8','0x10037050c','0x100370528')),
   dict(id='RATE4',claim='1001139d0 releases the previous segment+78 accessor via+10 when nonnil and stores the supplied pointer. It neither retains the new pointer nor directly configures rate/format; the old release remains a possible external lifecycle callback. On another selector call within101d3eb24,101d3ec60..eca0 clears the prior local descriptor cache before validating the new selection. For prior-invocation channel+1840,101d3eccc..ecfc clears only when the new selected pointer differs (including nil); identical selection preserves the cache. Exit101d3f484..4a0 retains the final nonnil descriptor in channel+1840, preserving the same-descriptor cache across block calls. Layout mismatch separately clears at101d3eff4.101d3e5b0 explicitly clears current descriptor accessor and releases channel+1840 under its lock. These are not automatic resets on every source seek or every block boundary.',
        evidence=evidence('0x1001139d0','0x101d3e5b0','0x101d3eb24')),
   dict(id='RATE5',claim='Actual rate setter1003704d4 is a Float32 store to+30; gain100370538 stores Float32 to+34.10036fca0 and10036fea0 also overwrite+30 from supplied format-interface+40, then copy other properties using different interface slots.10036e964 passes object+10 to accessor+1a0;10036e97c passes object+10 to+1a8. Their inspected bodies contain no direct converter+20 or first-read+4a reset. This is not proof that an arbitrary virtual source getter cannot have side effects.',
        evidence=evidence('0x1003704d4','0x100370538','0x10036fca0','0x10036fea0','0x10036e964','0x10036e97c')),
   dict(id='RATE6',claim='100211a7c first honors builder flag bit5 with direct clip+188. Otherwise it looks up typed AudioStream from event numeric attributes with runtime key at105028978. A hit is returned directly. A miss calls10021225c(event,context,0,builder+38); a result different from exact clip+188 is cached and the event added to builder cleanup storage. The sealed selector contract gives a sufficient direct LoFi no-processing branch; arbitrary cached/processed stream format is not constrained by the original clip metadata.',
        evidence=evidence('0x100211a7c','0x10011376c'),
        external='renderer-selection/finding.json and original-bindings.json builder excerpts'),
   dict(id='RATE7',claim='10036cd94 constructs one inner AudioAccessor for each iterated cluster file with caller flags/policy1, then calls10036e97c(inner,cluster,1) to overwrite its output format from the cluster secondary interface. This can establish a real differing-rate inner file→first-file-cluster conversion. It is independent of builder/project rate. For a stable one-file cluster, the inner source and cluster rate query agree by the same file receiver.',
        evidence=evidence('0x10036cd94','0x10036e97c','0x10036fea0','0x10036afc8')),
   dict(id='RATE8',claim='AudioCluster primary+150→10036b0bc and+158→10036b244 obtain first-file+168 format ID, map it through10012c5e0, then load descriptor kind+10/bits+14. Original AudioFile+168→10033d530 delegates file+150 kind and+158 bits through10012c64c. Those concrete file getters first invoke lazy10033a054 then query AudioSampleFormat/AudioSampleSize; kind query failure defaults1, bits query failure invokes the frame-size/channel fallback. This preserves the current-provider boundary relevant to PCM24→resample→PCM24 versus already-Float32 source order.',
        evidence=evidence('0x10036b0bc','0x10036b244'),
        supplemental='owner-and-metadata-bindings.json independently verifies peer-captured getter instructions and exact property-name bytes'),
 ],
 bounded_application_implications=[
   'A direct one-file ordinary-reader reconstruction may supply a verified stable reader owner and inherit that owner rate, preserving independent builder and reader-period inputs. Matching the source-rate builder/reader is an explicit accepted context, not a recovered global project default.',
   'An explicit application destination-rate setter can exercise the recovered accessor capability, but must be labeled supplied configuration until a concrete ordinary-path caller or prepared owner proves that destination rate.',
   'Do not compose the existing whole-source Float32 conversion pipeline with placed reads and call it the native ordinary path. Source sample format, current owner rate, seek history, first-read allowance, converter state and read partition are distinct inputs.',
   'For a current integer24 backend, retain source-format-dependent conversion ordering. This study binds format ownership but does not implement or independently establish the complete differing-rate PCM pipeline.',
 ],
 disconfirming_cases=[
   'Change builder/root rate while holding direct cluster reader owner fixed: RATE3 contains no rate write reflecting that change.',
   'Change reader datum period only: coordinate quantization changes while accessor initialization rate remains owner-derived.',
   'Return a prepared48000Hz owner from a stream factory whose original clip/file is44100Hz: generic inheritance from original metadata would be wrong.',
   'Two cluster files with differing rates: inner format copy can convert the second file to the first-file cluster rate even though outer initialization has no rate setter.',
   'Populate cached AudioStream key or activate a selector layer: the direct clip+188 equality gate no longer establishes selected-stream rate/format.',
   'Change lazy backend AudioSampleFormat/AudioSampleSize or first-file rate after snapshot: current query and cached output configuration need not remain equal.',
   'Invoke+110 with an integer frame size: it cannot substitute for Float32+f0 rate assignment. Invoking only+f0 does not directly rearm+4a or replace+20.',
 ],
 next_edges=[
   dict(addresses=['0x100211a7c','global0x105028978','0x10021225c'],question='Bind cached/processed selected-stream receiver and its factory owner before attributing project-rate conformance to a general event.'),
   dict(addresses=['0x100339108','global0x10502c0f8','0x10033a054'],question='Bind actual file registry probe/creator and property population for the selected backend; peer accessor-seek-state retains the current focused evidence.'),
   dict(addresses=['0x1003704d4','0x10036fca0','0x10036fea0'],question='Find a concrete ordinary-path call that assigns target/project rate, if any; no direct B/BL matches to the tiny rate setter does not enumerate virtual calls.'),
   dict(addresses=['0x101d9b3b4','0x10171c5a0'],question='Bind effective reader datum and builder-root rate inputs to the same hosted source graph; defaults or capability alone do not establish their relationship.'),
 ],
 limits=[
   'No proprietary executable/library was executed, activated or linked. No target audio, device or transport comparison was performed.',
   'Conditional successful concrete initialization and stable admitted source state are required. This is not whole-host immutability, general loop/cache/transform support or proof that Cubase lacks ordinary differing-rate playback.',
   'Raw REA slices omit external callees, imports, globals, RTTI and unwind context. LC_FUNCTION_STARTS intervals are not proved function bodies; exception tails and decompiler warnings are retained. Original instructions/cells are authority.',
   'Direct B/BL scans are address candidates only and do not enumerate indirect calls. Numerical analytical controls are supplied-state dependency examples, not observed Cubase states or PCM conformance.',
   'Current AudioFile backend/format state is separate from the bytes of an attached file and its saved CPR metadata. Runtime provider selection, transformed owner identity and downstream device-rate conversion remain bounded external edges.',
 ],
 verification=v['totals'],canonical_import=imported,
 supplemental_original_words=sum(x['original_words_checked'] for x in owner['checked_original_records']),
 analytical_controls=controls['control_count'],
 primary_artifacts=[pin(HERE/p) for p in ['original-bindings.json','owner-and-metadata-bindings.json','verification.json','evidence-bundle.json','evidence-import.json','analytical-controls.json']],
 external_references=external,
 sessions='Four isolated raw-slice MCP clients and canonical-import client closed explicitly.',
 reproduction=['derive.py N in a new output directory; analyze_pass.mjs N','verify_evidence.py; combine_evidence.mjs; import_evidence.mjs','bind_source.py; bind_owner_and_metadata.py; analytical_controls.py; write_finding.py'],
)
review=HERE/'independent-rate-ownership-review.json'
if review.exists(): finding['independent_review']=pin(review)
with (HERE/'finding.json').open('x') as f:json.dump(finding,f,indent=2);f.write('\n')
rows=[pin(p) for p in sorted(HERE.rglob('*')) if p.is_file() and p.name!='artifact-manifest.json' and '__pycache__' not in p.parts]
manifest=dict(schema_version=1,kind='cold immutable local static study inventory',target_executed=False,
              source_sha256=v['source_sha256'],files=rows,external_references=external,
              excludes=['artifact-manifest.json itself','Python __pycache__'],
              limits='Raw derivatives/provider captures remain local evidence; this is not a publication allowlist. No mutable Application files are pinned.')
with (HERE/'artifact-manifest.json').open('x') as f:json.dump(manifest,f,indent=2);f.write('\n')
print(json.dumps(dict(finding=pin(HERE/'finding.json'),manifest=pin(HERE/'artifact-manifest.json'),files=len(rows),external=len(external))))
