"""Seal the bounded differing-rate count finding; never runs target code."""
from pathlib import Path
import datetime,hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[4]
def ref(p):
 p=Path(p);p=p if p.is_absolute() else HERE/p
 return dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def save(n,v):
 with (HERE/n).open('x')as f:json.dump(v,f,indent=2);f.write('\n')
verify=json.loads((HERE/'verification-final.json').read_text())
assert verify['passed'] and verify['counts']['rea_functions']==61
assert json.loads((HERE/'evidence-import.json').read_text())['structuredContent']['result']['imported']==122
for p in HERE.glob('progress*.log'):assert 'CLOSED: isolated raw-slice MCP session' in p.read_text()
prior=HERE.parent/'segment-consumer'
old=json.loads((prior/'artifact-manifest.json').read_text())
for row in old['files']:
 p=ROOT/row['path'];assert p.stat().st_size==row['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256']
save('prior-evidence-integrity.json',dict(manifest=ref(prior/'artifact-manifest.json'),files_unchanged=len(old['files']),passed=True))
controls=json.loads((HERE/'analytical-count-controls.json').read_text())
examples=[r for r in controls['budget_vectors'] if (r['source_rate'],r['output_rate'],r['requested'],r['mode']) in [('48000','44100',147,1),('48000','96000',1,1),('44100','48000',1024,2)]]
finding=dict(schema_version=1,finding_id='CPR-AUDIO-RATE-CONVERTER-001',created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
 status='Source-frame budget established; conditional initialized mode2 no-flush count bookkeeping established; full resampling output not reconstructed',
 scope='Static AudioAccessor differing-rate branch, integer frame budgeting, concrete converter selection and count propagation. No decoded target media, target execution, candidate DSP or runtime conformance.',
 source=dict(path='research/targets/derived/Cubase15-arm64',sha256=verify['source_sha256'],architecture='arm64'),
 prerequisites=[ref(prior/'finding.json'),ref(prior/'native-10036eff0.txt'),ref(prior/'native-10036f89c.txt')],
 evidence={n:ref(n)for n in ['verification-final.json','rate-evidence-bundle.json','evidence-import.json','original-table-and-name-bindings.json',
  'initialization-table-addendum.json','algorithm-vtable-slots.json','algorithm-init-slots.json','soxr-wrapper-slots.json','analytical-count-controls.json','count_oracle.py','prior-evidence-integrity.json']},
 counts=dict(**verify['counts'],rea_records=122,budget_vectors=240,extra_budget_controls=4,no_flush_state_blocks=12,mcp_sessions_closed=True),
 input_domain=['Stored rates Rin and Rout are finite positive Float32 values, widened exactly before the budget arithmetic; different unless the equal-rate control is selected.',
  'Requested frames and adjusted budget are positive signed32; initial ceil, reverse-mapped count, produced counts and byte products fit their signed32 operations. Position/cumulative additions fit their signed64 storage.',
  'Analytical vectors assume IEEE nearest/ties-even floating arithmetic. Native FPCR was not observed. Ceiling and truncation instructions are explicit independently of that assumption.',
  'Mode selection, rates, channels and buffers are stable across the bounded call. Allocation and external calls return successfully. These are acceptance conditions, not assertions that native validates them.'],
 budget_contract=dict(entry='0x100330d84',helper='0x10030a430',ranges=['100330d84..dd8','10030a444..4a4','100313c0c..c1c'],
  mode='If converter+a9 is zero, mode0; otherwise100309fe8 returns2 when100314ca0 availability is true,1 otherwise. The budget queries current availability independently of the cached resampler object.',
  formula=['If Rin==Rout, return requested unchanged before adding any initial allowance.',
   'P=0 normally. If mode2 and first-call flag!=0 and availability succeeds, P=2048*ceil(RN64(Double(Rout)/Double(Rin))); 100313bf8 uses FRINTP then FCVTZU with 11 fractional bits.',
   'N=requested+P using32-bit ADD; overflow excluded by this contract.',
   'k0=ceil_to_signed32(RN64(RN64(Double(Rin)/Double(Rout))*Double(N))). Native FCVTPS is ceiling, not the cast printed by raw decompilation.',
   'r=RN64(Double(Rout)/Double(Rin)). Starting k=k0, compute m=trunc_to_signed32(RN64(r*Double(k))). If N<m, decrement k and repeat; otherwise return the tested k.',
   'The machine decrements its working register before the comparison, but returns the saved tested value, not the decremented value.'],
  termination='For the finite nonnegative domain, the reverse rounded product is monotone and is0 at k=0. Each failed test decreases k by1; at most k0+1 tests. No universal one-decrement bound is inferred from the sampled controls.',
  zero_result='A positive requested count can produce0. AudioAccessor10036eff0 tests this result<1 and returns0 before reading/converting source data; first-call flag has already been cleared.',
  examples=examples),
 caller_count_binding=dict(function='0x10036eff0',ranges=['10036f140..1bc','10036f2f8..310','10036f318..3c4'],
  sequence=['Call budget helper with requested output count and accessor first-call byte+4a, then clear that byte.',
   'Read at most budget frames from source backend+10. Retain its actual nonnegative returned source count in w27.',
   'Pass a stack copy of that count by address to100330cd4. It may replace the count with produced output frames.',
   'On conversion success, accessor integer source position+18 advances by the original backend returned count, and return value becomes the replaced produced count.',
   'On conversion false, return sentinel Int32.min. A negative source read branches to its existing error return.'],
  flush_predicate='For unequal rates, let end=(backend tell>=current source frame count), first=old accessor+4a, short=(budget>actual source count). Instructions10036f360..37c compute end && (!end || (first && short)), equivalent to end && first && short for stable values. Equal rates force false.',
  distinction='Accessor advancement is frames read from its backend, not the external resampler input-used value. Pending source frames can remain buffered inside the converter.'),
 conversion_dispatch=dict(
  entries=['100330cd4','10033035c','1003261a8','100326318'],
  fast_paths='Both10032ddd0 and10032f014 returnfalse at their entry rate comparison when rates differ. Their full raw intervals are retained; their equal-rate sample transformations are not reconstructed here.',
  ordering='General conversion invokes rate conversion before other operations when Rin>Rout or output bits24 with input bits!=24. Otherwise Rin<Rout is converted after other format/channel/gain steps. Rate-only matching32-bit kind2 input/output with gain1, matching channels/endian/layout bypasses those other transformations.',
  concrete_float32='For bits32/kind2,100326318 branches to100326738..754, calls10030a534 and stores its returned count through the supplied count pointer.10030a534 packet contains source,destination,inputCount,flush; child vtable+40 is the processing entry.',
  state_requirements='Generic resampler requires nonnull child, positive stored ratio and positive channel count. Constructor10030a008 accepts positive ratio in[0.01,100] else stores0 for the finite domain. Unsupported domains are not projected.',
  modes=[dict(mode=0,vtable='104461990',float32_dispatch='10030de00→10030ffb0',status='Dispatch and partial inline interpolation retained. Channel/rate branches tail to external bodies; complete count/sample contract not claimed.'),
   dict(mode=1,vtable='1044618f0',float32_dispatch='10030af58→10030b8a8',status='Stateful alternate path retained, not reconstructed as a complete count/sample rule.'),
   dict(mode=2,vtable='104461a08',float32_dispatch='100313c78→1003141bc',status='Conditional no-flush wrapper count rule below. External SoXR sample behavior not reconstructed.')],
  precision_limit='The int16 and Float64 virtual dispatch targets are byte-bound, but their full processing bodies were not traced. No extension of the Float32 bookkeeping rule to those bodies is asserted.'),
 mode2_initialization=dict(
  factory='1003136b8 creates vtable104461a08, child100314ce0/vtable104461a80, input capacity65536, positive chunk cap65408 and quality argument1. Raw factory type map[2,1,3,0,1] indexed by type−2 maps supported type5(Float32) to internal format0.',
  successful_path='1003261a8→10030a3bc→mode2+28(100313c2c) detects initial firstbyte1. It then invokes+20(100313b74), which clears firstbyte and calls child+48(100315000). Successful initialization uses the factory format0. Later1003141bc initialized check skips its format2 fallback.',
  failure_boundary='If initialization fails,1003141bc attempts a format2 initialization and ignores that return. This anomalous fallback is outside the accepted successful-format0 path; it must not be treated as proven Float32 recovery behavior.',
  rate_state='100313adc sets child rates, reads child delay+40, stores that uint32 into uint64 totalDelay+10 and remainingDiscard+18, and stores Double(Rout/Rin) at+40. Default child modebyte+a=0 gives delay=2048*ceil(Rout/Rin).',
  runtime_dependency='100316414 initializes availability and resolves six exact named exports: soxr_io_spec,soxr_create,soxr_delete,soxr_runtime_spec,soxr_quality_spec,soxr_process. Candidate paths are Externals/SoXR/0.1.3/soxr and Externals/SoXR/soxr. No library was loaded or executed by this study.',
  fallback='If mode2 factory returnsnull,10030a008 installs mode1 and changes stored mode to1. The earlier budget mode query is not automatically equal to this fallback object mode.'),
 mode2_no_flush_contract=dict(function='1003141bc',domain='Successful prior format0 initialization, positive count, constant positive channels and ratio, no flush, adequate buffers, representable arithmetic; external call returns.',
  fields=dict(ratio='Double+40',totalDelay='UInt64+10',remainingDiscard='UInt64+18',cumulativeInput='Int64+20',cumulativeVisibleOutput='Int64+28',cumulativeIdeal='Double+30',chunkCap='Int32+48=65408'),
  operations=['Split count>65408 into recursive65408-frame calls with flushfalse; advance input by inputchunk*channels and output by returnedcount*channels; final remainder is positive and<=65408.',
   'For each bounded block: ideal=RN64(Double(count)*ratio); base=trunc_i32(ideal); drift=RN64(RN64(cumulativeIdeal+ideal)−Double(cumulativeVisibleOutput+base)).',
   'n=base+(drift>1 ?1:0), then ifn==0 setn=1. Equality drift==1 doesnotincrement.',
   'Call child+68 with original input count and requested outputn. If remainingDiscard>=n, visible0, decrement discard byn and contribution0. If0<discard<n, copy output after discard; visible=n−discard; contribution=RN64(ideal−Double(discard)); clear discard. Otherwise visible=n and contribution=ideal.',
   'cumulativeInput+=count; cumulativeVisibleOutput+=visible; cumulativeIdeal=RN64(cumulativeIdeal+contribution). Return summed visible counts across chunks.'],
  termination='Cap65408 is strictlypositive; each outer iteration removes that many input frames and nested calls fit the cap. Sample-copy loops have bounded count/channel counters under checked products. No termination guarantee is made for an external call that doesnotreturn.',
  meaning='This is wrapper-visible count bookkeeping, not a proof that the external resampler generated that many valid sample frames.'),
 buffered_soxr_boundary=dict(function='100315438',entry='child+68→100315434→100315438',ranges=['100315cac..dd8','100315e7c..edc','100315ee0..6040'],
  format0_buffers='Input atchild+38; output atchild+40. Original jump-table index0 pins this routing. Other formats have separate arrays.',
  indices=dict(inputEnd='+80',outputRead='+84',inputConsumed='+88',outputEnd='+8c',pendingInput='+90'),
  setup='Initialization places delayP at outputEnd,0 at outputRead and initializes sample storage tozero. Thus wrapper-visible output can include retained/padded storage, not just newly produced frames.',
  call='Exactly one call through global10502bcc8(soxr_process) in this method: (handle,inputPointer,pendingInput+newInputCount,&inputUsed,outputPointer,requestedOutputCount,&outputProduced). Null input or zero new count selects null pointer and clears previous pending count before the call.',
  updates=['pendingInput += newInputCount−low32(inputUsed)','inputConsumed += low32(inputUsed)','outputEnd += low32(outputProduced)','Copy requestedOutputCount from outputRead to destination; inputEnd+=newInputCount and outputRead+=requestedOutputCount; reset paired indices when equal.'],
  unresolved='The returned error pointer is not inspected here. There is no retry-until-produced loop aroundsoxr_process. Correct source consumption, production, capacity and sample results require the actual initialized library contract; the retained static wrapper alone does not prove those conditions.'),
 flush_path=dict(status='Instruction path retained, excluded from no-flush oracle/accepted formula',
  facts=['AudioAccessor predicate is bound above.1003141bc computes extraInput=trunc_i32(Double(totalDelay)/ratio), fills with repeated final frame orzeros, then recurses with flushfalse.',
   'It restores cumulativeInput after that recursive call; iftrunc_i64(totalInput*ratio)−cumulativeOutput>0, it makes an additional null-input child call and adds that requested count to the returned count.',
   'The final null-input addition is not added to cumulativeOutput in the inspected tail. Repeat-after-flush semantics are not inferred.'],
  next_discriminator='Before promoting flush/sample behavior, bind actual library build and validate one final short read, exact-end full read, repeated flush and initial tiny read separately.'),
 allocation_only_counts=dict(function='10030a408',formulas=['mode0:trunc_i32(FMA(Double(inputCount),Rout/Rin,16))','mode1:trunc_i32(FMA(Double(Int32(inputCount+64)),Rout/Rin,20))','mode2:low32(trunc_u64(ceil(Rout/Rin)*Double(Int64(inputCount)+2048)))+32'],
  caveat='These are buffer capacities, not returned frame counts. Bounds and rounding are separate from source budget and process state.'),
 prospective_controls=['48k→44.1k requested147 distinguishes rounded initialceil161 from exact-rational160; correction returns160.',
  '48k→96k requested1 produces source budget0; distinguish from unconditionalceil1 or forcedminimum1.',
  'Firstmode2 versus latermode2 versus unavailablelibrary changes initial allowance; testwithouttreating availabilityasstatic BSSvalue.',
  'Maintain exact drift==1 versusdrift>1; split65408/65409 and multiplechunks; initialdiscard versussteady state.',
  'Distinguish backendreadcount, libraryinputUsed, libraryoutputProduced and wrappervisible count; none may substitute for another.',
  'Do not promote rate-seek Float32 ratio into count budgeting; the latter uses widened rates and Float64 division.'],
 analysis_limits=['Raw slices lack original data/virtual tables, imports, full exception context and externalbranch targets. Original native words and separately retained source tables govern these claims.',
  'C-like decompilation loses FCVTPS/FRINTP details and indirect switches; its pseudocode is neither compilable nor bit-faithful recovered source.',
  'Metadata intervals include exception tails and static-registration code;61intervals are not61fullyreconstructed implementations.',
  'No complete resampler candidate, arbitrary-format converter or target fidelity is claimed. Equal-format sealed finding is preserved unchanged.'],
 target_execution_count=0,reference_runtime_conformance_count=0)
save('finding.json',finding)
print(json.dumps(ref('finding.json')))
