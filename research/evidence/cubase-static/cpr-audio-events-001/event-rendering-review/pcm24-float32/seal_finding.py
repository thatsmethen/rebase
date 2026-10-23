"""Seal the bounded static PCM24 contract without changing prior evidence."""
from pathlib import Path
import datetime,hashlib,json,re,struct
H=Path(__file__).resolve().parent;R=H.parents[5];B=H.parent.parent
SOURCE=R/'research/targets/derived/Cubase15-arm64'
def sha(b):return hashlib.sha256(b).hexdigest()
def pin(p):return dict(path=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=sha(p.read_bytes()))
expected='dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb'
before=SOURCE.stat();data=SOURCE.read_bytes();after=SOURCE.stat();assert sha(data)==expected
assert (before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)
segments=[];pos=32
for _ in range(struct.unpack_from('<I',data,16)[0]):
 c,n=struct.unpack_from('<II',data,pos)
 if c==25:
  v=struct.unpack_from('<II16sQQQQIIII',data,pos);segments.append((v[3],v[5],v[6]))
 pos+=n
def raw(a,n):
 v,o,s=next(x for x in segments if x[0]<=a and a+n<=x[0]+x[2]);k=o+a-v;return k,data[k:k+n]
tables=json.loads((H/'table-bytes.json').read_text())
for t in tables:
 off,b=raw(int(t['address'],16),t['length']);assert off==t['offset']and b.hex()==t['bytes_hex']and sha(b)==t['sha256']
# The PCM24 switch index is the exact ARM EXTR of sourcebits and sourcebits-8.
sourcebits=24;index=(((sourcebits-8)>>3)|((sourcebits<<29)&0xffffffff))&0xffffffff;assert index==2
switch=[]
for a,expected_target in [(0x103934708,0x10032e214),(0x103934718,0x10032e4fc)]:
 off,b=raw(a,16);value=struct.unpack_from('<H',b,index*2)[0];target=0x10032ddf0+4*value;assert target==expected_target
 switch.append(dict(table_address=hex(a),source_offset=off,bytes_hex=b.hex(),source_bitwidth=24,index=index,entry_u16=value,branch_target=hex(target)))
constants=[]
for a,word,bits in [(0x1003312cc,0x0f016681,0x34000000),(0x1003320f8,0x0f016681,0x34000000),(0x1037d88d4,0x0f016601,0x30000000),(0x1037d8f94,0x0f016601,0x30000000)]:
 off,b=raw(a,4);assert struct.unpack('<I',b)[0]==word
 constants.append(dict(address=hex(a),source_offset=off,instruction_word=f'{word:08x}',float32_scale_bits=f'{bits:08x}'))
used=[B/'rate-converter'/f'native-{s}.txt'for s in ['100323688','1003237d8','100323904','100323b24','100330cd4','10032ddd0']]+[B/'segment-consumer'/f'native-{s}.txt'for s in ['10036e34c','10036e858','10036eff0']]+[H.parent/'native-candidate-10018fb40.txt']
checks=[]
for p in used:
 words=re.findall(r'^([0-9a-f]+):\s+([0-9a-f]{8})\s',p.read_text(),re.M);assert words
 for a,w in words:assert struct.unpack('<I',raw(int(a,16),4)[1])[0]==int(w,16)
 checks.append(dict(**pin(p),original_words_verified=len(words)))
binding=dict(source_sha256=expected,tables_verified_against_source=True,pcm24_switch=switch,scale_instructions=constants,reused_native=checks,
 scope='Original byte/word and dispatch checks; conditional path only, no target execution.',passed=True)
with(H/'dispatch-binding.json').open('x')as f:json.dump(binding,f,indent=2);f.write('\n')
verify=json.loads((H/'verification-final.json').read_text());assert verify['passed']and verify['counts']==dict(native_functions=4,native_bytes=1872,native_words=468,rea_functions=4,rea_addresses=468)
imported=json.loads((H/'evidence-import.json').read_text())['structuredContent']['result'];assert imported['imported']==8 and imported['total']==8
r={
 'schema_version':1,'finding_id':'CPR-EVENT-PCM24-FLOAT32-001','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'status':'static_bound_conditional_unit_conversion_and_post_gain; runtime_unvalidated',
 'scope':'Packed signed24 to Float32 for the already selected event-local stream, equal rate/channel/layout and unit converter gain. Independent reconstruction contract, not Cubase playback or a complete event selector.',
 'source':{'path':str(SOURCE.relative_to(R)),'bytes':len(data),'sha256':expected},
 'exact_rule':{
  'decode':'For each packed24 triplet, p is the signed two-complement integer in[-8388608,8388607]. LE p=signextend24(b0|(b1<<8)|(b2<<16)); BE p=signextend24(b2|(b1<<8)|(b0<<16)).',
  'convert':'With exact converter gain1, x=Float32(p/8388608), exactly representable for every signed24 value. No division by8388607, clipping, dither or channel reorder occurs in these kernels.',
  'endpoints':{'negative_full_scale':'-8388608 -> bf800000 (-1)','positive_full_scale':'8388607 -> 3f7ffffe (1-2^-23)','zero':'0 -> 00000000 (+0)'},
  'post_event_gain':'The separate bounded consumer 0x10018fb40 loads segment Float32 gain at +0x68. If gain compares equal to 1 it skips multiplication; otherwise each returned Float32 sample is multiplied once by gain using FMUL (vector 0x100190ebc..ec8, scalar 0x100190ee8). Before the output writer y=RN32(x*g) under nearest-even arithmetic, with finite normal-or-zero operands and no underflow/overflow. The IEEE product sign applies to exact zero, including zero gain. This loop contains no clipping, mixing, gain ramp, FMA, or finite-value guard.',
  'precision_boundary':'Unit conversion is exact. Nonunity event multiplication can round; finite gain alone does not guarantee a finite normal output. The conditional equation permits either sign of finite normal gain and signed zero; the retained numerical gain controls exercise six positive values. A candidate must separately reject overflow/nonfinite results and define denormal/FP rounding behavior for any bit-equivalence claim. Arbitrary converter gain is not promoted to the unit-conversion theorem.'},
 'kernels':[
  {'entry':'0x1003312c4','source_byte_order':'little','selection':'capability AND bit0x80 clear','scale_bits':'34000000','operation':'Signed24 reconstructed directly; SCVTF Float32 exact; multiply by precomputed Float32(converterGain*2^-23). Scalar100331328..348; vector16/8 then scalar remainder.'},
  {'entry':'0x1003320f0','source_byte_order':'big','selection':'capability AND bit0x80 clear','scale_bits':'34000000','operation':'Same direct signed24 rule with high byte first; scalar100332150..170; vector16/8 then scalar remainder.'},
  {'entry':'0x1037d88d4','source_byte_order':'little','selection':'capability AND bit0x80 set','scale_bits':'30000000','operation':'Assemble signed32(p<<8); SCVTF exact; multiply by precomputed Float32(converterGain*2^-31). Vector16/8/4 then scalar1..3. All lane/table origins checked against source bytes.'},
  {'entry':'0x1037d8f94','source_byte_order':'big','selection':'capability AND bit0x80 set','scale_bits':'30000000','operation':'Same left-aligned rule with high byte first; vector16/8/4 then scalar1..3.'}
 ],
 'dispatch_and_state':[
  'AudioAccessor10036eff0 configures source via100323904 and destination via100323b24; destination buffer isx1 and sourcebufferx2 of100330cd4. Fast dispatcher10032ddd0 swaps these into kernel(source,destination,samplecount).',
  'Converter constructor100323688 (1003237d8 tail) initializes fast flag+a8=1.100330cd4 tries10032ddd0 first when that flag remainsnonzero; success returnswithoutgenericfallback.',
  'Admitted10032ddd0 path requires equal Float32rates, destinationbits32/kind2/byteorder0, sourcebits24/kind1, equalpositivechannels, equal layoutcode not2. It passes framecount*channels as signed32 samplecount and gain+28 as Float32.',
  'Sourcebyteorder+8=0 chooses table103934718 index2 ->10032e4fc ->LE kernels. Nonzero chooses103934708 index2 ->10032e214 ->BE kernels. Runtime capability words10502c0e0/e4 are ANDed then bit0x80 selects generic/specialized. Both unit-gain results established, no capability value inferred.',
  'Accessor initialization10036e858 stores exactgain1 at+34; read10036eff0 copies current+34 to converter+28. Unit-gain condition must remain true for the declared conversion. The eventgain+68 is applied later by consumer, not silently combined with convertergain.',
  'Format5 is float32 from separately pinned event-rendering descriptors. Explicit Float32output is mandatory: unityeventgain does not itself change outputformat.10036e34c argumentx2=5 is constructorflags, NOT sampleformatselector; this corrects the numerical-format wording in prior consumer-lead-review.json. Actual formatsetter is10036ee80.'
 ],
 'accepted_domain':[
  'Exact selected packed signed24 buffer; file parsing, RIFF custody, source identity and segment/event eligibility established separately. No AVAudioFile conversion equivalence assumed.',
  'Same finite positive source/outputrate, samepositivechannelcount and same supported interleaved layout, destinationnativeLEfloat32. Framecount×channels positive and <=INT32_MAX-16, byteproducts/addresses representable, adequate disjoint input/output buffers; no alias behavior inferred.',
  'Convertergain exact1 and stable objectfields duringcall. Arbitrary convertergain, differentrate, channelmatrix/layoutchange, genericfallback and callbacks outside path excluded.',
  'For later event gain, finite normal gain or signed zero, with finite normal or exact-zero products and a declared FP mode; subnormal input/output and underflow are outside this contract. Full source reads and writes, no cancellation, no added fades, loops, warp, overlap or track-mixer processing. Unity preserves conversion bits.'
 ],
 'evidence':{k:pin(H/v)for k,v in [('verification','verification-final.json'),('dispatch','dispatch-binding.json'),('tables','table-bytes.json'),('controls','analytical-controls.json'),('oracle_script','analytical_controls.py'),('rea_bundle','pcm24-evidence-bundle.json'),('rea_import','evidence-import.json')]},
 'prior_context':[pin(B/'event-rendering/finding.json'),pin(B/'event-rendering/final-linkage.json'),pin(H.parent/'consumer-lead-review.json')],
 'analytical_validation':{'scalar_vectors':31,'post_gain_vectors':186,'symbolic_vector_byte_origin_checks':6,'generic_lane_groups':4,'classification':'Exact rational and symbolic derivation from retained instructions/tables, not target output or execution.','universal_unit_proof':'Every signed24 p has atmost24 significant bits; p*256 has the same significance and fits signed32. Both integer-toFloat32 conversions are exact. Power-of-two scaling gives exact normal-or-zero p/2^23; capability branch and vector chunking therefore agree for every signed24 value at unitgain.'},
 'independent_review':{'reviewer':'/root/cubase_evidence','scope':'Original little-endian scalar100331328..348 and specialized1037d89d8..9f8 plus scaleinstructions.','result':'Agrees with signextension, scale2^-23/2^-31 and exact unitgain theorem. Didnot independently verify vector tables, full dispatcher or lifecycle; those remain author checks above.'},
 'disconfirming_controls':['Positivefullscale/8388607 wouldwrongly yield1.0.','Wrong signedness changes signset values.','Bytepattern010203 distinguishes endian interpretation.','Leftshift8 with2^-23scale gives256xerror.','Remainder lengths1,4,8,16 byte-origin paths distinguish shuffle/reordering errors.','Nonunityeventgain is a separate Float32rounding step, not presumed convertergain.'],
 'limits':['No proprietary code executed; actual Cubase audio comparisons0.','The observed consumer is an offline action with progress/cancel/output setup; its ordinarytimeline callerrole remainsunbound. This is not complete Cubase playback or projectrender fidelity.','Selected stream cloning/backend, sourceevent selection, automaticfades and formatwriter are separate contracts; no unproved whole-host immutability demanded or implied.','No production source change or candidate PCM execution in this finding.'],
 'target_execution_count':0,'cubase_runtime_comparisons':0,'application_changes':0
}
with(H/'finding.json').open('x')as f:json.dump(r,f,indent=2);f.write('\n')
files=[]
for p in sorted(H.rglob('*')):
 if p.is_file() and '__pycache__'not in p.parts and p.name!='artifact-manifest.json':files.append(pin(p))
manifest={'schema_version':1,'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'All retained files in this new study excluding this manifest and Python cache. Prior studies untouched.','source_sha256':expected,'files':files,'file_count':len(files)}
with(H/'artifact-manifest.json').open('x')as f:json.dump(manifest,f,indent=2);f.write('\n')
print(json.dumps({'finding':pin(H/'finding.json'),'manifest':pin(H/'artifact-manifest.json'),'files':len(files)}))
