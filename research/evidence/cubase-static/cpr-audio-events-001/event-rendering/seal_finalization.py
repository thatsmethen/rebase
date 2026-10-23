"""Finalize the conditional event-local contract while preserving all earlier records."""
from pathlib import Path
import hashlib,json,re,struct

H=Path(__file__).resolve().parent
R=H.parents[4]
P='research/evidence/cubase-static/cpr-audio-events-001/'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def ref(path):
    path=Path(path)
    if not path.is_absolute():path=R/path
    assert path.is_file(),path
    return dict(path=str(path.relative_to(R)),bytes=path.stat().st_size,sha256=sha(path))
def ev(path):
    result=json.loads(path.read_text());assert not result.get('isError',False),path
    return result.get('structuredContent') or json.loads(result['content'][0]['text'])

original=ref(H/'finding.json')
assert original['sha256']=='7a493eaca5021ef876a557ec4159c82df5aa51554f13995f57f14e0670140623'
old=json.loads((H/'finding.json').read_text())
v=json.loads((H/'verification.json').read_text())
source=Path(v['source']['path']);data=source.read_bytes()
assert sha(source)==v['source']['sha256']=='dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb'
rows=[];ids=set()
for number in range(1,12):
    base=H/f'pass{number}'
    for item in json.loads((base/'derivation.json').read_text())['derivatives']:
        a=int(item['entry'],16);key=item['entry'][2:];raw=(base/item['raw_file']).read_bytes()
        assert raw==data[item['source_file_offset']:item['source_file_offset']+item['length']]
        assert sha(base/item['raw_file'])==item['raw_sha256']
        rb=ev(base/f'bytes-{key}.json')['raw_result']
        assert rb['complete'] and rb['returned_bytes']==len(raw) and bytes.fromhex(rb['bytes_hex'])==raw
        native=(base/item['original_native_disassembly']).read_text()
        words={int(x,16):int(w,16) for x,w in re.findall(r'^([0-9a-f]+):\s+([0-9a-f]{8})\s',native,re.M)}
        assert len(words)==len(raw)//4
        assert all(struct.unpack_from('<I',raw,x-a)[0]==w for x,w in words.items())
        dossier=ev(base/f'function-{key}.json')
        locations=[int(x.split(':')[0],16) for x in dossier['raw_result']['value']['assembly']]
        assert len(locations)==len(set(locations)) and all(x in words for x in locations)
        records=ev(base/f'bundle-{key}.json')['result']['records']
        ids.update(x['evidence_id'] for x in records)
        ev(base/f'close-{key}.json');assert (base/f'snapshot-{key}.json').is_file()
        rows.append(dict(entry=item['entry'],source_bytes=len(raw),native_words=len(words),rea_instruction_addresses=len(locations)))
    assert 'CLOSED: isolated raw-slice MCP session' in (base/'analysis-progress.log').read_text()
totals=dict(functions=len(rows),source_bytes=sum(x['source_bytes'] for x in rows),native_words=sum(x['native_words'] for x in rows),
    rea_instruction_addresses=sum(x['rea_instruction_addresses'] for x in rows),unique_evidence_ids=len(ids))
assert totals==v['totals']
assert ev(H/'evidence-import.json')['result']==dict(imported=116,unknowns_added=0,total=116)
assert 'CLOSED: evidence import session' in (H/'import-run.log').read_text()
assert {x['evidence_id'] for x in json.loads((H/'evidence-bundle.json').read_text())['records']}==ids

paths={
    'original_draft':H/'finding.json',
    'source_state':P+'audible-state/finding.json',
    'stream_selector':P+'renderer-selection/finding.json',
    'source_placement':P+'timebase/finding.json',
    'segment_read':P+'segment-consumer/finding.json',
    'automatic_fade_source':P+'autofade-source/finding.json',
    'fallback_ownership':H/'ownership-finding.json',
    'pcm24_to_float32':P+'event-rendering-review/pcm24-float32/finding.json',
    'independent_consumer_review':P+'event-rendering-review/consumer-lead-review.json',
    'native_linkage':H/'final-linkage.json',
    'native_verification':H/'verification.json',
}
references={name:ref(path) for name,path in paths.items()}
expected={'automatic_fade_source':'421a3e5bf51f892b2b68a37e69c8171440ee39d114385d9934bd05a6cc7ca08c',
          'fallback_ownership':'14aaee2b8096ee1f0c2f502b4942140111ba4b86ecc703617e50c27d03861a85',
          'pcm24_to_float32':'698f1f9fac7d3947f513ad25dbed67e5d6425eb31dfd91c99832b77aa7b231f3'}
for name,expected_sha in expected.items():assert references[name]['sha256']==expected_sha
sealed=[]
for path in [H/'ownership-manifest.json',R/(P+'autofade-source/artifact-manifest.json'),R/(P+'event-rendering-review/pcm24-float32/artifact-manifest.json')]:
    manifest=json.loads(path.read_text())
    for item in manifest['files']+manifest.get('external_inputs',[]):
        assert sha(R/item['path'])==item['sha256'],item['path']
    sealed.append(dict(manifest=ref(path),file_count=len(manifest['files']),all_listed_hashes_rechecked=True))
for entry in old['new_functions']:
    assert sha(R/entry['dossier']['path'])==entry['dossier']['sha256']
for entry in old['artifacts'].values():assert sha(R/entry['path'])==entry['sha256']
assert sha(H/'finding.json')==original['sha256']
validation=dict(scope='Mechanical custody recheck and sealed dependency verification; no new target analysis/execution.',
    target_execution=False,original_draft_unchanged=True,original_capture_totals=totals,
    capture_sessions_closed=11,canonical_imported_records=116,canonical_import_session_closed=True,
    dependency_manifests=sealed,passed=True)
(H/'finalization-verification.json').write_text(json.dumps(validation,indent=2)+'\n')

finding=dict(schema_version=1,finding_id='CPR-EVENT-RENDERING-001-FINALIZATION',
    status='sealed conditional event-local static reconstruction contract; runtime unvalidated',
    scope='Finalization appendix to the unchanged original draft. Automatic-fade source, fallback ownership and packed24 conversion gates are separately sealed. No complete action or timeline equivalence.',
    native_source_sha256=v['source']['sha256'],target_execution=False,cubase_runtime_comparisons=0,
    conclusion='The retained native instructions support an independently implemented event-local Float32 reader for the explicitly admitted saved-source state. Source-backed project flags0 now have a bound normal root fallback; the already selected segment consumer supplies finite frame bounds and one Float32 event-gain multiply. This is a composition of bounded static contracts, not an observation of Cubase rendering the source.',
    finalization_changes=[
        'ER2 pending source-role gate is resolved by the separate auto-fade source and ownership findings, without changing the original draft bytes.',
        'Packed signed24 to Float32 at exact converter gain1 is supplied by the separate PCM24 finding; arbitrary system decoder equivalence is not assumed.',
        'The earlier independent consumer lead described AudioAccessor constructor argument5 as a sample format. It is constructor flags; explicit output format5 comes from format configuration/setter. The PCM24 finding documents the correction. Unity event gain alone never selects Float32.',
        'No new proprietary execution, native function capture, application changes, or runtime acceptance is introduced by this finalization.'
    ],
    conditional_contract=[
        dict(stage='Source admission',facts='A structurally reached supported MAudioEvent/PAudioClip and one verified AudioCluster segment, known source bounds/rate/layout and actual matching attached media. The first admitted timing subset is typed10 with the bound zero source coordinate; no string-name attribution.',dependencies=['source_state','source_placement','segment_read']),
        dict(stage='Fresh selected stream',facts='Use the explicit renderer-selection predicates: unmuted event, finite positive event volume, empty numeric event attrs/volume curve, no inversion/fades/neighbors, TransposeLock1, no Warpscale/Bypass/Pitch/replacement content. Restrict counted clip children to the supported plain26-byte MHitPointEvent v3 source subset; reject arbitrary children or serialized NoteEvent/MicroPitchChangeFactors. Packed no-pitch state remains an explicit fresh reconstruction/call-time assumption, not an implication of absent serialized names. No external pitch context or later state mutation is admitted.',dependencies=['source_state','stream_selector']),
        dict(stage='Automatic fades',facts='Both pinned LoFi and Classic source trees contain null local track setting and nonnull project MAutoFadeSetting v0 flags0. The sealed ownership finding identifies that same MRoot as the normal fallback receiver. The builder therefore takes its effective-flags0 automatic-fade bypass. Four serialized interpolator bodies remain opaque and unused on this branch. Classic still fails other admission predicates, notably Warpscale; this gate does not make Classic renderable.',dependencies=['automatic_fade_source','fallback_ownership']),
        dict(stage='Segment bounds',facts='Normal remainder builds concrete PAudioSegment with stream+38, start+50, nonnegative end-minus-start length+58, source offset+60 and Float32 gain+68. Datum conversion and sign-selected ±0.5 then FCVTZS occur in construction. For the nonnegative converted source offset/length at the inner reader, seek=FCVTZS(offsetFrames+0.5) and count=FCVTZS(lengthFrames+0.5). Require representable positive count and a complete source interval.',dependencies=['original_draft','native_linkage']),
        dict(stage='Conditional inner PCM consumer',facts='Conditioned on an already selected PAudioSegment/AudioStream clone,10018fb40 inner path seeks, requests min(remaining,10000), and consumes returnedFrames. Nonunity gain applies exactly one Float32 FMUL per returned frame×channel element (vector groups then scalar tail); unity skips arithmetic. No mix, clipping, ramp or FMA occurs in this loop. Under successful full reads/writes emitted source indices are [seek,seek+count), with no extra endpoint sample. Short reads, errors, cancellation and general output-writer encoding are excluded.',dependencies=['original_draft','independent_consumer_review']),
        dict(stage='Explicit Float32 and packed24',facts='Declare native little-endian Float32 output format5 even at unity event gain. For the separate admitted packed signed24 conversion, require equal finite positive source/output rate, same positive channel count and supported interleaved layout, exact converter gain1, safe signed sample/byte counts and adequate disjoint buffers. Decode signed p then x=Float32(p/8388608), exactly representable. Event gain is a separate subsequent operation, never folded into converter gain.',dependencies=['pcm24_to_float32','native_linkage']),
        dict(stage='Arithmetic domain',facts='For the admitted positive finite-normal event gain and nearest-even FP mode, y=x when gain equals1, otherwise y=RN32(x*g). Require normal-or-zero finite products; reject nonfinite/overflow/underflow/subnormal domains in a conservative reconstruction. Native loop itself has no corresponding safety clamp or finite guard. No generic sample-rate conversion is substituted.',dependencies=['pcm24_to_float32']),
    ],
    whole_action_boundary=dict(entry='0x10018fb40',mutation='The containing offline action temporarily writes event numeric attribute0x74616462 (tadB) while constructing segments, then restores it.',
        restriction='The whole action must not be composed with the earlier empty-attribute source selector as though it preserved that state. Only the already-selected inner consumer is used here; its caller role, output setup and general backend mutation remain separate.'),
    timeline_boundary='The separate MAudioTrack producer uses builderflags0x80 and an inclusive-end selection predicate. That relation does not identify the offline consumer as live timeline playback and does not establish mixer/automation/plugin/PDC/transport or live exact-end behavior.',
    lofi_analytical_projection=dict(rate=44100,seconds=24,source_offset_frames=0,frames=1058400,full_10000_frame_chunks=105,tail_frames=8400,
        classification='Arithmetic projection under the explicit matching-rate source subset, not measured Cubase output or a claim that bundled VSTsound audio was decoded.'),
    unresolved=['Actual Cubase PCM comparisons remain0; runtime equivalence has not been demonstrated.',
        'Host edits, extension callbacks, selected-stream replacement and arbitrary live state can invalidate source assumptions.',
        'General fades, nonzero automatic-fade modes, overlapping/linked events, loops, pitch/warp layers, rate conversion and multitrack mixing are excluded.',
        'Serialized interpolators, mixer/track automation and plugin state remain outside this contract.',
        'No universal bit-faithfulness outside the stated arithmetic, representation and successful-I/O domain.'],
    references=references,verification=ref(H/'finalization-verification.json'),
    preservation='Earlier finding, native dossiers, ownership/autofade/PCM24 seals and manifests remain byte-identical. This appendix supersedes only the pending-finalization status and adds explicit composition limits.')
(H/'finalization-finding.json').write_text(json.dumps(finding,indent=2)+'\n')
files=[ref(path) for path in sorted(H.rglob('*')) if path.is_file() and '__pycache__' not in path.parts and path.name!='finalization-manifest.json']
external=list(references.values())+[x['manifest'] for x in sealed]
manifest=dict(id='CPR-EVENT-RENDERING-001-FINALIZATION-MANIFEST',target_execution=False,
    files=files,external_inputs=external,file_count=len(files),total_bytes=sum(x['bytes'] for x in files),
    scope='All current event-rendering artifacts plus exact dependency references. Earlier sealed records are included unchanged; external study counts are not summed as unique new analysis.',
    sealed_dependency_manifests=sealed)
(H/'finalization-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
for item in files+external:assert sha(R/item['path'])==item['sha256']
assert sha(H/'finding.json')==original['sha256']
print(json.dumps(dict(passed=True,files=len(files),finding_sha256=sha(H/'finalization-finding.json'),manifest_sha256=sha(H/'finalization-manifest.json'))))
