"""Retain authored semantics; all runtime-equivalence claims remain excluded."""
from pathlib import Path
import json,hashlib
H=Path(__file__).resolve().parent;R=H.parents[4]
def pin(p):return dict(path=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
x={
 'scope':'Ordinary channel reader value-level plan, mapped-entry rounding and exact-read result classification, conditional on supplied datum/constructed segment values. No live host or whole timeline equivalence.',
 'target_execution':False,
 'quantization':{'entry':'0x101d3eb24','datum':'global1050105e0 receiver+388:tag and +390:period',
  'scale':'Double(Float32(RN64(1 / period)))',
  'coordinates':'Concrete getter values: start +d8, end +f8, source offset +108. PAudioSegment end itself is RN64(start+length), independently bound by timeline-provider.',
  'result':'signed64 truncation toward zero of FMA64(coordinate,scale,+0.5)',
  'order':'Quantize start; if start>requestEnd return tail silence. Then quantize end and apply invalid/before-request skips. Then quantize offset.',
  'not_equivalent_to':['generic Double coordinate*nominalRate','separately rounded multiply then add','symmetric nearest rounding for negative coordinates']},
 'datum_lifecycle':{'initializer':'101d983c0 allocates0x520 and calls101d99034, then storesglobal1050105e0.',
  'fresh':'Constructor constants+310/+318 are44100.0/1.0; separate101c22c0c initializes datum+388 as type1,period1.0. Do not infer active audio rate from constructor alone.',
  'setter':'101d9b3b4 on d0>0 computes RN64(d0*d1), calls101c22884(datum,10,product); exact type10 switch target101c22988 stores RN64(1/product) at datum+8.',
  'host_limits':'The effective d0/d1 inputs and subsequent host mutation are call-context state; this study does not assert runtime values. Copy ctor101d9f068 includes datum-copy call101c22a98; no complete copy/lifecycle semantic claim.'},
 'window':{'inputs':'original requestStart S, requestEnd E, current cursor C; S<=C<=E; actual selector returned segment or nil.',
  'nil_or_A_greater_than_E':'Zero [C,E), terminate.',
  'A_ge_B':'Skip selected segment with unchanged cursor.',
  'B_less_than_S':'Strict before-request skip; B==S is not this branch.',
  'prefix':'If C<A zero [C,A); begin=max(C,A).',
  'seek':'Q(offset) if C<=A; otherwise Q(offset)+(C-A).',
  'read':'[begin,min(B,E)) if positive; equality has no source read. A==E can zero prefix then terminate.',
  'advancement':'Successful full read advances to min(B,E); zero-length intersection advances at most through prefix. Selector advancement and node lifetime are outside pure planner.',
  'source_readiness':'Native missing source, zero source length or unready accessor zeros the planned read span. App helper does not invent accessor readiness.'},
 'read_contract':{'native_configuration':'101d3eb24 creates AudioAccessor via10036e34c with flags0x25/policy1; layout2 only source/output stereo, else0; output Float32/Float64 follows format1/2. Sets segment Float32gain via+160, seeks via+178, reads via+168.',
  'retry':'Return -2147483645 is retried once only when saved readBegin equals quantized segment start; repeat the read without repeating seek.',
  'success':'Return must equal requested positive count.',
  'failure':'Other negative value propagates; other nonnegative value maps INT32_MIN. Native prefix/partial samples may already be written; no native transactional guarantee.',
  'gain_scope':'Gain is passed into native accessor before read; equal-rate explicit app memory backend applies checked gain once after copying. No claim about arbitrary conversion/layout/poststage gain ordering.'},
 'mapped_partition':{'entry':'101d3e704','record_bytes':40,'layout':{'0':'start Double','8':'end Double','16':'origin/offset Double','24':'extra qword','32':'datum type32','36':'flags32'},
  'count':'TruncSigned64(min(RN64(RN64(end-start)+0.5),Double(remainingFrames)))',
  'start':'For non-silence: TruncSigned64(RN64(start+(start<0?-0.5:+0.5))); end=startFrame+count.',
  'silence':'flags&4 skips start/end-frame computation and zeros count.',
  'outer_retry':'Distinct outer retry on -2147483645 depends on entry flags bit0 or host service mode2. Not modeled by inner read_result.',
  'mapping':'101d3ea38 selects active project mapper101c3579c when channel+1848/+90 permits; otherwise global mapper101c351e4. No automatic identity-map claim.',
  'conditional_default_mapper':'101c351e4 tag10 threshold1; positive sub-threshold interval suppressed. Under no delegate or host mode2, obtains origin O by datum conversion, yields startOut=RN64(start-O), endOut=RN64(RN64(end-start)+startOut), offset O,type,flags0. Delegate branch remains external.',
  'excluded':'Active loop/locator expansion, mapper ownership/default origin, general host state and external callback mutation.'},
 'candidate_domain':{'inputs':'Finite signed normal-or-zero coordinates, positive normal period yielding positive normal Float32 multiplier; arm64 nearest IEEE with FZ/DN/AH/FIZ off. Signed64 fused result, checked integer differences/sums and request span<=16m. Disjoint input/output structs.',
  'validation':'Upfront finite validation can reject fields that a native early return would not consume. Invalid segments A>=B skip normally; native nonfinite/saturating/wrapping cases reject.',
  'transactionality':'Pure outputs unchanged on validation/range/FP error; no sample buffers are owned or modified.',
  'application_policy':'Caller supplies an explicit rate-derived period and verified constructed descriptors. Synthetic multi-segment windows do not promote arbitrary CPR objects to playable tracks.'},
 'current_candidate':[pin(R/'Application/Sources/RebaseTimingDSP/cpr_timeline_reader.c'),pin(R/'Application/Sources/RebaseTimingDSP/include/cpr_timeline_reader.h')]
}
(H/'working-contract.json').write_text(json.dumps(x,indent=2)+'\n')
review={'scope':'Author read-only composition review; not independent oracle, runtime or device validation.',
 'reviewed_sources':[pin(R/'Application/Sources/RebaseCore/CPRNativeTimelineStream.swift'),pin(R/'Application/Sources/RebaseTimingDSP/cpr_timeline_reader.c'),pin(R/'Application/Sources/RebaseTimingDSP/include/cpr_timeline_reader.h')],
 'result':'No actionable plan/cursor composition defect found in the declared ordered nonoverlap/equal-rate stereo immutable-memory domain.',
 'checks':['End equality keeps the segment until the next block planner skips its empty intersection.','Gap and tail samples begin zero; read spans are bounded by destination and source lengths.','Cursor publication occurs only after a complete block; direct full-read backend does not fabricate transient I/O behavior.','Exactly one checked gain application follows copied source samples.','No converter or audition FIFO is inserted in this direct stream.'],
 'limits':['Gain-positive and complete-media gates are stricter application policy.','Provider/datum/mapper lifetime and live Cubase behavior are not tested.','Only the current source identity was reviewed; future edits need a new review.']}
(H/'author-integration-review.json').write_text(json.dumps(review,indent=2)+'\n')
