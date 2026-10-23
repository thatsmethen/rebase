"""Assemble a bounded static finding; no target execution and no audio decoding."""
from pathlib import Path
import datetime, hashlib, json

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
def ref(path):
    p=Path(path)
    if not p.is_absolute(): p=HERE/p
    return dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def save(name, value):
    with (HERE/name).open('x') as f: json.dump(value,f,indent=2); f.write('\n')

verification=json.loads((HERE/'verification-final.json').read_text())
iterator=json.loads((HERE/'iterator-byte-verification.json').read_text())
imported=json.loads((HERE/'evidence-import.json').read_text())
assert imported['structuredContent']['result']['imported']==60
assert all(json.loads(p.read_text()).get('isError') is not True for p in HERE.glob('close-*.json'))
prior=json.loads((HERE.parent/'cluster/finding.json').read_text())
vectors=json.loads((HERE/'interval-and-rate-vectors.json').read_text())
assert len(vectors['intervals'])==6 and len(vectors['rate_seek_vectors'])==24
rate_example=next(v for v in vectors['rate_seek_vectors'] if
                 (v['source_rate'],v['output_rate'],v['requested_position'])==(44100,48000,48000))
assert (rate_example['stored_source_position'],rate_example['returned_output_position'])==(44099,47998)

finding=dict(
    schema_version=1, finding_id='CPR-AUDIO-SEGMENT-CONSUMER-001',
    created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    status='Bounded source-frame read interval established statically; differing-format conversion remains outside this contract',
    scope='Default AudioCluster access-stream construction and one-segment successful direct-read path. '
          'No Cubase execution, decoded media, relinking, audition or audible conformance observation.',
    source=prior['source'],
    evidence={name:ref(name) for name in ['bound-source-bytes.json','verification-final.json',
        'iterator-byte-verification.json','segment-evidence-bundle.json','evidence-import.json',
        'interval-and-rate-vectors.json','interval_oracle.py']},
    prerequisite_evidence={
        'stored_fields_and_factory_bytes':ref(HERE.parent/'cluster/finding.json'),
        'exact_fixture_correlations':ref(HERE.parent/'cluster/fixture-byte-correlations.json'),
        'prior_literal_binding':ref(HERE.parent/'cluster/bound-literal-bytes.json')},
    verification=dict(rea_functions=30,rea_records=60,rea_addresses=verification['counts']['rea_addresses'],
        rea_readback_bytes=verification['counts']['native_bytes'],
        original_native_functions=verification['counts']['native_functions']+len(iterator['rows']),
        original_native_words=verification['counts']['native_words']+sum(r['native_words'] for r in iterator['rows']),
        original_native_bytes=verification['counts']['native_bytes']+sum(r['length'] for r in iterator['rows']),
        exact_vtable_slots=22,analytical_interval_vectors=6,analytical_rate_vectors=24,
        mcp_sessions_closed=True),
    field_meaning={
        'Stream': 'AClusterSegment+0x10: source object; the read path finds the accessor whose backend-stream+8 is this exact object.',
        'Offset': 'AClusterSegment+0x18: additive source-accessor seek offset, in the integer stream position domain.',
        'Length': 'AClusterSegment+0x20: selected segment extent in the cluster integer position domain.',
        'Start': 'AClusterSegment+0x28: origin subtracted from the cluster read position before adding Offset.',
        'equal_rate_domain': 'For the direct path below, these integer positions/counts pass to the source stream as sample frames. '
                             'They are not event seconds or native musical ticks.'},
    accepted_static_contract=dict(
        domain=[
            'Exactly one non-null AClusterSegment, linked to the sole expected source AudioStream/AudioFile; matching accessor exists.',
            'Read-mode constructor path10036cd94 has flags bit1 clear (self+0x68=0), copied segment list with restored flags1, no subsequent segment mutation.',
            'Integers satisfy Start>=0, Offset>=0, Length>0 and Start<=p<Start+Length. Request is positive signed32. '
            'All source/cluster additions and subtractions fit signed64; all byte-count products used in signed32 arithmetic fit positive signed32; destination storage is sufficient.',
            'AudioAccessor has non-null source access stream. Current source rate is finite positive and equals requested Float32 rate; '
            'every remaining format comparison in10036fb74 matches, and accessor gain is exactly Float32 1.',
            'Backend seek succeeds at the requested position and source read returns the complete bounded count. '
            'Current source format and source identity stay stable across these calls.',
            'For a relink candidate policy, verify Offset+Length does not exceed the validated actual source frame count. '
            'This is a safe bounded precondition, not a claim that this read method checks it.'
        ],
        equations={
            'bounded_source_count':'n = min(request, Start + Length - p)',
            'source_seek':'a = p - Start + Offset',
            'source_interval':'[a, a+n)',
            'full_inside_read':'If request<=Start+Length-p and the backend returns n, cluster position becomes p+request and return count is request.',
            'ordinary_cross_end':'If request exceeds the remaining segment extent and the bounded source read succeeds fully, '
                'the remainder is filled with the cluster silence byte and counted. '
                'Silence byte is0x80 when cluster+0x168 returns1, otherwise0. This is not asserted for short-read/error paths.'
        },
        exact_ranges=['10036d350..378 and10036d3a8..3c0: extent/count',
                      '10036d3d0..3f4: Offset and p−Start+Offset',
                      '10036d420..428: exact source object identity',
                      '10036d440..468: wrapper seek then read',
                      '10036f954..968: equal-rate integer position store',
                      '10036f040..070 and10036f1cc..1fc: backend seek equality, direct read, position update'],
        implementation_implication='A finite standalone source-interval projection can implement these equations for this declared subset. '
            'Selection of the outer renderer, event start/duration scalar conversion, media identity, event gain/fades/warp and actual decoded audio remain separate gates.'),
    constructor_and_dispatch=[
        dict(id='SEG-CTOR',claim='AudioCluster+0xf8 points to10036a52c, which allocates0x70, calls10036cd94 '
            'and rejects a nonzero stream error byte+0x69. The constructor installs AudioClusterAccessStream vtable104466378, '
            'sets position+0x10 to0 and mode+0x68 from requested flags bit1.',
            ranges=['10036a52c','10036cdc0..cdcc','10036ce04..ce24']),
        dict(id='SEG-COPY',claim='The constructor copies cluster+0x48 into stream+0x40 through103103e80. '
            'Its concrete list+0x148 implementation1030f9b20 copies flags and, when flags1, clones each object via+0xc8. '
            'AClusterSegment+0xc8 is10036dddc, which copies Stream, Offset, Length and Start exactly. '
            'Other list flags append references; that case is outside the accepted snapshot subset.',
            ranges=['10036ce18..ce24','103103e80','1030f9b20..bd4','10036de08..de28']),
        dict(id='SEG-ACCESSOR',claim='The constructor iterates cluster files, creates AudioAccessor10036e34c for each, '
            'appends it and applies cluster requested format via10036e97c→+0x1a8→10036fea0. '
            'Source-file+0xf8 provides its backend access stream. +0xd8 initialization10036e858 copies current source format and sets gain1.',
            ranges=['10036ce28..ceb8','10036e3b8..e40c','10036e858..e958','10036fea0..ffc4']),
        dict(id='SEG-ITERATOR',claim='List+0x140→103104dd0 creates iterator vtable104e31478 with current node from list+0x18. '
            'Iterator+0x10→1031041f8 tests current node null; +0x18→103104208 returns node object+8 then advances to node next+0. '
            'This binds segment traversal without inferring behavior from an unrelated container.',
            ranges=['103104dd0..e04','1031041f8..204','103104208..224']),
        dict(id='SEG-SEEK',claim='Cluster stream+0x20→10036d848 stores the requested position when mode byte0, '
            'when position is unchanged, or when cluster segment count<=1. In mode nonzero with multiple segments it can retain the previous position. '
            'Read uses copied list when mode0 and original cluster list otherwise.',
            ranges=['10036d848..874','10036d2d8..2f4'])
    ],
    direct_format_predicate=dict(function='10036fb74',
        equalities=[['source+0x140 Float32','accessor+0x30 Float32'],
                    ['source+0x158 int','accessor+0x40 signed16'],
                    ['source+0x128 int','accessor+0x42 signed16'],
                    ['source+0x150 int','accessor+0x38 int32'],
                    ['source+0x120 int','accessor+0x3c int32'],
                    ['source+0x138 int','accessor+0x44 signed16'],
                    ['source+0x130 int','accessor+0x46 signed16'],
                    ['accessor+0x34 Float32','Float32(1)']],
        note='False selects direct read. Missing backend/source also makes this predicate false, so backend existence is a separate required precondition. '
             'Constructor format setters can normalize frame-byte metadata; do not infer this predicate only from the saved CPR rate/channel count.'),
    rate_mismatch_seek=dict(function='10036f89c',range='10036f8f8..954',
        domain='Finite positive normal rates, finite nonnegative positions and intermediate signed64 conversion results. '
               'Oracle uses nearest/ties-even FP rounding as an explicit assumption; target FPCR was not observed.',
        operations=['Compare source+0x140 Float32 with requested accessor+0x30.',
                    'When unequal, reread source rate and compute ratio32 = Float32(sourceRate / requestedRate).',
                    'Widen ratio32 to Float64; convert requested signed64 position to Float64.',
                    'storedSourcePosition = FCVTZS_i64(Float64(position) * Float64(ratio32)).',
                    'Return FCVTZS_i64(Float64(storedSourcePosition) / Float64(ratio32)).',
                    'When equal, store and return the original integer without conversion.'],
        example=rate_example,
        caveat='Cluster read ignores the wrapper seek return. This seek contract alone does not establish the number or content of samples returned by the differing-rate converter.'),
    other_branches_and_boundaries=[
        dict(kind='concrete_exclusion',edge='Position before Start',
             detail='Read does not enforce p>=Start. A gap or a first segment starting after p can produce a negative relative seek. '
                    'The accepted formula requires p inside the segment; zero factory Start cannot discriminate this precondition.'),
        dict(kind='concrete_exclusion',edge='Short backend read',
             detail='10036d4a4..4d8 compares the selected segment against the copied list tail. For that tail it sets Length=wrapper tell−Offset '
                    'and suppresses ordinary final padding; a different segment reaches an error path. These mutations are outside the full-read contract.'),
        dict(kind='concrete_unresolved_branch',edge='Format/rate conversion in10036eff0',
             detail='Predicate true creates converter1003237d8 and configures100323904/100323b24. '
                    '100330d84 derives source count;100330cd4 converts returned data. Those bodies were not reconstructed here; no resampler or converted-interval equivalence is claimed.'),
        dict(kind='backend_boundary',edge='AudioFile+0xf8→10033a4f8',
             detail='Calls lazy preparation10033a054 when needed, then active backend+0xd0. The returned stream services seek+0x20/read+0x10. '
                    'The finite accepted path assumes a validated matching backend and successful calls; serialized metadata alone does not prove backend identity or availability.'),
        dict(kind='outer_state_boundary',edge='Event/render state',
             detail='Event scalar/timebase and audible-state findings remain separate. Default restored source-state acceptance does not require proving every possible host callback immutable, '
                    'but selection of this path and its explicit state preconditions must hold. No claim extends to arbitrary relink, editing, warp, effects or alternate renderer.'),
        dict(kind='excluded_mutator',edge='Access-stream+0x18→10036d668',
             detail='This is a write/grow path, distinct from+0x10 read. Captured for discrimination, not included in the accepted read rule.')
    ],
    fixture_implications=[dict(source=f['source'],source_sha256=f['source_sha256'],segment_body=f['segment_body'],
        stored_offset_length_start=f['stored_offset_length_start'],
        conditional_interval=[0,f['declared_file_frames']],
        meaning='Under the explicit direct-read and valid-backend preconditions, the single stored segment covers these source frames. '
                'This is not a media-file validation, an event-time projection or a playback observation.') for f in prior['fixtures']],
    prospective_discriminating_cases=[
        'Start100/Offset7/Length123,p140,request100 must address source[47,130), leaving17 requested frames outside the source interval. '
        'This distinguishes swapped Start/Offset and absolute versus relative seeking.',
        'Compare p=Start, p=Start+Length−1, p=Start+Length, and p<Start. The last two are excluded from this interval projection and must not silently reuse the inside-segment result.',
        'At source44100/output48000,p48000, preserve Float32 ratio3f6b3333: stored44099, returned47998. A Float64-only ratio gives the wrong stored44100.',
        'Hold format/rate equal but alter gain from1 or one format field; converter branch must be treated separately.',
        'Distinguish complete read, short read at copied tail, and short read elsewhere; do not treat all as zero padding.',
        'Reject negative or overflowing fields/counts and source ranges exceeding verified actual frames as candidate policy, rather than reproducing unchecked native arithmetic.'
    ],
    independent_challenge=dict(reviewer='/root/cubase_evidence',
        scope='Read-only original native10036d22c and10036f89c; no general multi-segment/error review.',
        result='No disagreement in bounded one-segment formula. Reviewer specifically required p>=Start precondition and both stored and returned truncations in rate mismatch; both retained.',
        evidence_type='Peer source inspection communicated in this task, not an independent target run.'),
    analysis_limits=[
        'REA raw slices omit imported symbols, global data, original vtables and full exception context; original-image instructions plus separately pinned pointer bytes are authoritative.',
        'LC_FUNCTION_STARTS interval is not proof of a body. Retained intervals include exception tails and, for the clone, a distinct registration routine after RET.',
        'C-like decompiler expressions and inferred ABI types are not compilable or bit-faithful recovered source.',
        'Analytical vectors execute self-authored integer/Fraction IEEE arithmetic only. No source backend, decoder or Cubase function ran.'
    ],
    target_execution_count=0,reference_runtime_conformance_count=0)

save('finding.json',finding)
print(json.dumps(dict(finding=ref('finding.json'), verification=finding['verification'])))
