"""Assemble bounded native findings from retained dossiers; no target execution."""
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path
P=Path(__file__).resolve().parent
ROOT=P.parents[4]
def load(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
verification=[load(d/'verification.json')for d in [P,P/'pass2',P/'pass3',P/'pass4']]
functions={}
for d,v in zip([P,P/'pass2',P/'pass3',P/'pass4'],verification):
 for f in v['functions']:
  a=f['entry']; ident=a[2:]
  functions[a]=dict(path=str((d/f'function-{ident}.json').relative_to(ROOT)),sha256=sha(d/f'function-{ident}.json'),evidence_id=f['analyze_function_evidence_id'],readback_evidence_id=f['read_bytes_evidence_id'],raw_sha256=f['raw_sha256'],profile=f['analysis_profile'],native_instruction_count=f['native_interval_instruction_count'],rea_instruction_count=f['rea_body_instruction_count'],warnings=f['pseudocode_warnings'])
def refs(*addresses):return [dict(address=a,**functions[a])for a in addresses]
report={
 'finding_id':'CPR-NATIVE-001', 'created_utc':datetime.now(timezone.utc).isoformat(),
 'scope':'Bounded static archive, node and tempo contracts from Cubase Pro 15.0.30.287 arm64 instructions; no target execution, no host project-load observation, no complete CPR decoder claim',
 'source':{'path':'research/targets/derived/Cubase15-arm64','sha256':verification[0]['source_sha256']},
 'status':'partial_static_contract_supported_by_original_bytes_and_REA',
 'key_results':[
  'Class references and object references use different keys: declaration-token offset versus payload-length-field offset, both relative to the captured archive origin.',
  'Cached -2 declarations bind each own class descriptor/version. A safe strict parser may restrict missing-reference fallback to earlier explicit -1 declarations; that is a deliberate subset of native recursive seek behavior.',
  'Normal MDataNode tag 0/17 carries two archive objects; other tags carry a binary64 datum. MListNode adds a counted child sequence; MTrackList inserts an additional 16-bit field before that sequence.',
  'MTempoTrackEvent reads counted 22-byte records, then for version>0 a fixed binary32 value and a TWO-byte nonzero boolean. The stored boolean occupies one object byte and selects fixed versus map lookup.',
  'The fixed getter returns the stored fixed value directly. Map items expose float32 60.0/storedPeriod; coordinate units remain unbound, so this finding does not authorize a tempo-map import in quarter notes or seconds.'
 ],
 'linkage_provenance':{'path':str((P/'linkage-provenance.json').relative_to(ROOT)),'sha256':sha(P/'linkage-provenance.json'),'method':'Verified exact mangled class-name bytes, typeinfo name pointers, zero offset-to-top/vtable typeinfo prefixes and 17 selected slots; not all neighboring locator words are vtable members.'},
 'archive_contract':{
  'evidence':refs('0x103192464','0x1031930f8','0x1031934bc','0x1031696b0','0x103193a04'),
  'identity':{'class':'FNewArchive','primary_vtable':'0x104e44b70','object_reader_slot':'0x28 -> 0x1031930f8','header_helper':'0x1031934bc','object_callback':'virtual +0x98'},
  'width_and_origin':'Constructor stores current underlying-stream position in archive+0x48. Constructor argument x4 is stored at +0x68; exactly 1 selects 8-byte token/length fields, other values use 4-byte fields. The complete CPR caller and choice of width have not been traced here; shipped-byte validation establishes the 4-byte subset separately.',
  'header_32bit':[
   {'token':'0','meaning':'null object; no class descriptor returned'},
   {'token':'positive signed int32','meaning':'object identity reference; caller looks up object table at archive+0x50, then optionally checks requested class'},
   {'token':'-2','meaning':'class declaration: length-prefixed class bytes plus signed16 version; register this marker-relative offset and its own looked-up descriptor/version, then read another token'},
   {'token':'-1','meaning':'concrete class declaration: class bytes, signed16 version and unsigned32 payload length; register this marker-relative offset and looked-up descriptor/version'},
   {'token':'other negative signed int32','meaning':'class reference: clear sign bit to obtain class-declaration-relative offset, then read unsigned32 payload length; use class table at archive+0x58'}
  ],
  'class_fallback':{'observed':'On a missing class-table key, save stream position, seek to archiveOrigin+key, recursively run header decoder, restore position and return recursive result. This is an explicit seek, not a string scan.','nuance':'When recursively entered at -2, the helper can consume a declaration chain and return its final descriptor; this is not equivalent to the cached own-descriptor lookup in every state.','strict_subset':'Earlier explicit -1 declarations with validated bounds are sufficient for the observed missing FNPath references and avoid the -2 fallback ambiguity. Forward reference support, arbitrary backward chains and native error recovery are not required by this bounded parser proposal.'},
  'object_registration':{'key':'position after class/header and payload-length field - archiveOrigin - tokenWidth','meaning':'offset of the payload-length field, not offset of the class marker','ordering':'Register factory-created, class-checked object before calling its virtual +0x98 reader. Push current class version to archive+0x14 for that call and restore previous value afterward.','reference_limits':'Positive references use existing object-table entries; no seek fallback for unknown positive references was observed.'},
  'payload_end':'After successful object callback, compare current stream position with payloadStart+payloadLength and seek to that declared end if different. Failed callback also seeks to declared end and invalidates the table entry. These instructions do not prove complete input-bound validation.',
  'not_established':['Whole CPR load call chain into this constructor/reader','Complete factory registry, every archive width/version or unknown-class recovery policy','Safe native behavior for malformed, cyclic, truncated or adversarial streams']
 },
 'primitive_contract':{
  'evidence':refs('0x10221d068','0x10221d38c','0x10221d9c8','0x10221dc34','0x10221e188','0x10221e3fc','0x10221e5fc','0x10221eb28'),
  'byte_order':'Read helpers conditionally reverse 2/4/8 bytes when underlying stream uint16 field +8 is nonzero. Their native CPR initialization is not traced here; template-byte evidence independently supports big-endian serialized numbers.',
  'scalar_widths':{'int32':'4','uint32':'4','int16':'2','int64':'8','binary32':'4','binary64':'8','boolean':'2 serialized bytes -> 1 object byte (value!=0)'},
  'boolean':'0x10221e5fc requests exactly 2 bytes, swaps if required, stores (uint16!=0) to destination, returns whether read count was 2; a short read stores false. The uint16 encoding 0x0001 is true, as is any other nonzero uint16. Do not read only one serialized byte.',
  'class_name_string':'0x10221eb28 reads a 4-byte length and accepts 1...262144 bytes; allocates and requests that length. Its returned string read count and terminal NUL are not explicitly checked in the retained helper; a strict decoder should validate rather than emulate malformed-input unsafety.'
 },
 'node_contract':{
  'evidence':refs('0x1016ea554','0x101c23184','0x101715fb0','0x101759190','0x101716008','0x103109ff0'),
  'dispatch':{'MDataNode':'0x1016ea554','MListNode':'0x101715fb0','MTrackList':'0x101759190','counted_children':'0x101716008'},
  'normal_path_condition':'Global compatibility byte at 0x104ff4020 bit1 clear. Its runtime value is unobserved. The shipped-template structural parsing agrees with this path; the alternative raw-pointer path is outside the strict subset.',
  'prefix':'MDataNode calls archive-string wrapper 0x10310a240 (two verified instructions: load archive+8; tail branch to 0x103109ff0) on object+0x18, then normal datum reader on object+0x38.',
  'name_string':'Length is signed32, successful positive lengths are limited to 50000 and require an exact byte read. UTF-8 BOM EF BB BF is recognized at beginning or trailing marker location and conversion helper is called with 65001. Without that marker the bytes remain in the string representation; universal UTF-8 decoding of all legacy strings is not established.',
  'datum':'Read signed32 tag. If compatibility global bit4 is set and tag>15, effective tag becomes17. Effective tag0/17 reads two archive objects through archive virtual+0x28; each may be null, a positive identity reference, or an inline class payload under the archive contract. All other effective tags read one binary64. Generic enum meanings are not inferred.',
  'list':'MListNode: MDataNode prefix then signed32 count and that many archive objects requested as class MEvent. MTrackList: same prefix, one extra serialized int16, then same child sequence. Child callback virtual+0x288 receives parent before append when a parent is supplied.',
  'bounds_policy':'Native count<=0 returns success with no children; strict application importer should reject negative or excessive counts and enforce enclosing payload/file bounds. No explicit class-version gate in these individual node readers establishes support for unobserved versions.',
  'not_established':['Runtime global compatibility configuration','General string legacy code page','Meaning of extra MTrackList int16','Every child subtype or every datum tag semantic']
 },
 'tempo_contract':{
  'evidence':refs('0x10173bdac','0x10173c17c','0x10173ac84','0x10173acb0','0x10173824c','0x101740db0','0x101740dc4','0x101739f00','0x101739f3c'),
  'dispatch':{'MTempoTrackEvent_reader':'primary vtable 0x104674d18 +0x98 -> 0x10173bdac','writer':'+0xa0 -> 0x10173c17c','selection_getter':'+0x600 -> 0x10173ac84','MTempoEvent_primary_vtable':'0x1046746f0'},
  'record_layout':{'count':'signed32; reader returns false for count<1 or missing iterator','stride_bytes':22,'fields':[{'relative_offset':0,'serialized':'binary32','object_offset':'0x48','meaning':'stored period-like quantity; getter is float32 60.0/value'},{'relative_offset':4,'serialized':'binary64','object_offset':'0x50','meaning':'coordinate A, units unbound'},{'relative_offset':12,'serialized':'binary64','object_offset':'0x58','meaning':'coordinate B used for interpolation, units unbound'},{'relative_offset':20,'serialized':'signed16','object_offset':'0x60 (sign extended to 32 bits)','meaning':'kind value, getter +0x4a0'}]},
  'post_records':[{'condition':'current archive version>0','fields':'binary32 fixed value -> track+0x170, then uint16 nonzero boolean -> track+0x174 (one byte)'},{'condition':'named MTempoTrackEvent class version>=2','fields':'attribute helper on track+0x20; update bits0x4048 from an attribute when available'},{'condition':'named class version>=3','fields':'attribute helper on each tempo object+0x20'}],
  'selection':'0x10173ac84 reads byte+0x174: nonzero returns float32+0x170 directly; zero tail-branches to 0x10173824c with query coordinate D0 preserved. The raw decompiler reports halt_baddata at the unmapped external branch; original instruction is a valid B, not a target halt.',
  'item_value':'MTempoEvent vtable+0x498 ->0x101740db0 performs float32 FDIV(60.0f, storedFloat+0x48). +0x4a0 ->0x101740dc4 loads the int32 kind at+0x60.',
  'map_lookup':{'domain':'Conditional on the two iterator results (A=current candidate, B=next candidate) supplied by untraced iterator helpers. Query-position selection, ordering, coordinate units and whole lifecycle are not established here.','conditions':['A null ->120.0f','B null ->A value','B kind0 ->A value','B kind other than0/1 ->120.0f','B kind1 and abs(B.coordinate-A.coordinate)<binary64 1e-8 ->repeat iterator loop','B kind1 otherwise ->arithmetic below'],'fp_sequence':['aBPM=float32(60.0f/A.storedPeriod); bBPM=float32(60.0f/B.storedPeriod)','delta=FP64(B.coordinate-A.coordinate)','slope=FP64(FP64(FP64(bBPM)-FP64(aBPM))*480.0)/delta','intercept=FP64(aBPM)-FP64(FP64(A.coordinate*slope)/480.0)','result=float32(FP64(FP64(slope*query)/480.0)+intercept)'],'instruction_note':'Explicit FCVT/FSUB/FMUL/FDIV/FADD instructions; no FMADD in this interpolation sequence. Algebraic cancellation/reassociation of 480 factors can change floating-point results. The comparison uses FCMP plus B.MI; nonfinite, zero-period and exceptional FP behavior are not validated by a target run.'},
  'quantized_value_getter':'Separate vtable+0x190 function 0x101739f00 computes float32 60/period, promotes to binary64, FMADD(value,100.0,0.5), then signed FCVTZS W0. Do not replace this order with a generic host-language rounding rule or infer a UI display binding.',
  'post_read_lifecycle_limit':'Reader invokes list callbacks and track virtual+0x5f8 ->0x10174c194; that callback and its transitive effects are not fully traced here. This contract establishes the direct serialized-field/getter relationship, not immutable lifetime state.',
  'safe_application_scope':'Recover a validated positive finite fixed tempo when the full serialized uint16 mode is nonzero, labeling recovery as static subset. Preserve raw tempo records and opaque attributes. Do not turn their coordinates into beat/time positions or import ramps until unit and iterator bindings are proven. Metadata MusicalTempo is not the authority for this native selection.'
 },
 'verification':{
  'functions':len(functions),'raw_bytes':sum(v['total_native_interval_instructions']*4 for v in verification),'native_interval_instruction_words':sum(v['total_native_interval_instructions']for v in verification),'rea_decoded_instructions':sum(v['total_rea_body_instructions']for v in verification),'all_original_slices_and_REA_readbacks_exact':True,'bundled_records':62,
  'reports':[{'path':str((d/'verification.json').relative_to(ROOT)),'sha256':sha(d/'verification.json')}for d in [P,P/'pass2',P/'pass3',P/'pass4']],
  'canonical_bundle':{'path':str((P/'native-evidence-bundle.json').relative_to(ROOT)),'sha256':sha(P/'native-evidence-bundle.json')},
  'REA_bundle_validation':{'path':str((P/'evidence-import-validation.json').relative_to(ROOT)),'sha256':sha(P/'evidence-import-validation.json')},
  'decoder_differences':'14 mnemonic-spelling differences: B.CS/B.HS, B.CC/B.LO, ORR/MOV aliases and vector suffix rendering. All instruction addresses and original words are retained in reports; this is not a proof of every operand or decompiler type.',
  'omitted_body_words':'89 native interval words are outside Ghidra inferred reachable bodies; retained original disassembly covers them. They include disconnected tails and LC_FUNCTION_STARTS intervals containing additional code. Do not call whole intervals fully decompiled.',
  'session_cleanup':'31 snapshots and close responses retained; all four MCP clients closed. No target code executed.'
 },
 'retained_failures':[{'path':'noncanonical-concatenation-rejection.json','reason':'Naively concatenated exported bundle manifests were rejected as noncanonical. Original records were unchanged; createEvidenceBundle from pinned REA produced the canonical aggregate subsequently accepted by evidence-import. This was bundle assembly failure, not a native-analysis failure.'}],
 'general_limits':['Every raw slice is an exact unmodified original interval at its linked address; imports, globals, typeinfo/vtables, neighboring code and unwind metadata are absent from the raw analysis image. Selected original-file linkages are separately verified.','Generated pseudocode is not original source and is not guaranteed compilable or bit-faithful. Addressed ARM64 instructions take precedence for widths, FP operation order and external branches.','Static conditions are not runtime observations. Cubase comparison count remains zero. No full-project roundtrip, target load, audio playback or host parser acceptance is demonstrated.','Archive and tempo facts apply to the pinned 15.0.30.287 arm64 artifact and investigated branches; unsupported versions/content remain opaque rather than inferred.']
}
(P/'finding.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'finding_sha256':sha(P/'finding.json'),'functions':len(functions),'raw_bytes':report['verification']['raw_bytes'],'native_words':report['verification']['native_interval_instruction_words'],'rea_instructions':report['verification']['rea_decoded_instructions']}))
