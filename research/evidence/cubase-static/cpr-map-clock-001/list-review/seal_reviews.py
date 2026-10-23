"""Seal scoped static findings without modifying prior evidence or application code."""
import datetime,hashlib,json
from pathlib import Path
H=Path(__file__).resolve().parent;R=H.parents[4];M=H.parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def pin(p):return {'path':str(p.relative_to(R)),'bytes':p.stat().st_size,'sha256':sha(p)}
def save(p,d):p.write_text(json.dumps(d,indent=2)+'\n')
verified=json.loads((H/'final-verification.json').read_text());assert verified['new_unique_functions']==30
link=json.loads((H/'closure-linkage.json').read_text())
source=verified['source'];timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
local_ids={r['entry']:r['evidence_ids'] for r in verified['functions']}
common_limits=[
 'Static original-byte/control-flow evidence only. Target executions and Cubase runtime comparisons are zero.',
 'Raw imports omit linked external globals/types/vtables/imports/unwind. Original source slices and explicit linkage support the bounded interpretations; pseudocode is generated non-source and is not guaranteed compilable or bit-faithful.',
 'Successful normal construction/read is the scope. Allocation failure, exception/unwind cleanup, concurrency and arbitrary host observers are outside it.',
 'Exact native bytes and REA readback equality are custody checks. They do not prove the runtime globals, actual registry selection, full application behavior or target floating-point environment.'
]
service={
 'id':'CPR-MAP-DEFAULT-HOST-CALLBACK-001','revision':1,'created_utc':timestamp,'source':source,
 'scope':'Concrete default TrackLoopHandler callback reached from fresh tempo base-track construction, plus explicit registry replacement boundary.',
 'result':'The retained default factory initializes a new handler and copies the fresh list scalar datum into handler-local objects. No source track/list timing mutation is present in the traced normal default path. The selected root context and keyed factory remain replaceable runtime state; this is not an invariant across arbitrary providers.',
 'preconditions':[
  'Successful fresh archive-factory construction10173a5ac→10173a7c0; base track construction101747fe4 attaches the concrete empty MTempoTrackNode.',
  'If the IComponents predicate is enabled, the selected root context resolves to the retained default concrete implementation and its TrackLoopHandlerParam key resolves to the retained default factory. Otherwise this default-path conclusion is inapplicable.',
  'The freshly created list+0x38 datum has kind1 and scalar1.0 before serialized source read. Both stack descriptor values supplied to the handler have kind1 and scalar1.0.',
  'No provider replacement, keyed-factory overwrite, concurrent mutation or arbitrary postconstruction observer is presumed absent outside this explicit default-path scope.'
 ],
 'call_chain':[
  {'entry':'0x101747fe4','statement':'After list attachment, stores the track pointer in a stack context, constructs two kind1/value1 descriptors, calls1005c01a8, stores its returned handler only in track+0x70, then destroys those local descriptors.'},
  {'entry':'0x1005c01a8','statement':'If selected IComponents is nil or its+0x18 predicate is false, returns nil. Otherwise obtains IRootContext, applies vptr[-0x60] adjustment, invokes adjusted+0x20 with {TrackLoopHandlerParam,contextPointer}. Extracts the returned pointer and calls ownership cleanup with null; does not itself modify the track.'},
  {'entry':'0x103806f64','statement':'Loads runtime selected root-context pointer from10501e350. The slot is not an immutable pointer in source bytes.'},
  {'entry':'0x103806748','statement':'Concrete root context sets primary104f73d78 and secondary104f73e48 at object+0x18. Secondary virtual-base adjustment is-24. Embedded registry vptr104e288c0 is initialized by10307ed44.'},
  {'entry':'0x1005ca2f0','statement':'Product root factory registers exact TrackLoopHandlerParam key104f866e1 with wrapper1044b0160 holding factory1005ca878. It subsequently exposes the root to optional global104fefc10 virtual+0x30, so later changes cannot be excluded.'},
  {'entry':'0x10307eefc','statement':'Default root+0x20 adds8 and tails10307e3d8. That bounded string-key tree lookup calls the selected factory wrapper+0 or returns an empty ownership result if absent.'},
  {'entry':'0x1005ca8c0','statement':'Wrapper+0 takes descriptor+8 and calls stored factory1005ca878. It returns the new handler with cleanup1005ca90c; cleanup with null immediately returns.'},
  {'entry':'0x1005ca878','statement':'Allocates0x4b8 bytes and calls1017664c8→101765ffc with the context.'},
  {'entry':'0x101765ffc','statement':'Initializes newly allocated handler state, stores the source track pointer in handler+0x348, copies two context descriptors into allocated handler-local objects, and reads track+0x258/list+0x108 to copy the fresh list datum. There is no direct source-track/list store in this normal body.'},
  {'entry':'0x1016e9a18','statement':'Concrete list+0x108 returns list+0x38 without mutation.'},
  {'entry':'0x101c246b4','statement':'Initializes local descriptor kind1/value1.0.'},
  {'entry':'0x101c22c0c','statement':'Initializes fresh list datum kind1/value1.0.'},
  {'entry':'0x101c245e4','statement':'With kind1 source, copies scalar descriptor to new handler-local storage and skips interface retain branches.'},
  {'entry':'0x101c247b0','statement':'Converts the handler-local coordinate from its local datum to the list datum, then assigns the datum to handler-local storage. Conversion101c22dc0 takes equal kind1/value1 fast return. Assignment101c22c7c uses scalar copy; no source write or interface callback occurs in this branch.'}
 ],
 'registry_boundary':{
  'enabled_gate':'Independent host-gate-global/finding.json proves normal concrete IComponents initialization sets byte8=1. Startup zero cannot exclude this branch.',
  'typed_subscription':'103806fa4 subscribes under Lego::IRootContext;10380710c writes the supplied selected pointer into10501e350 and conditionally clears registry owner. Supplied/replaced root-context implementations are supported.',
  'factory_replacement':'Default registry+0x38→10307eac8 locates/creates a keyed node, releases a previous factory if present, transfers new wrapper into node+0x30 and clears the caller ownership pointer. Registry replacement is an observed implementation mechanism.',
  'product_extension_hook':'1005ca2f0 invokes optional global104fefc10+0x30 with the constructed root after default registrations. The receiver and any resulting changes are not resolved here.',
  'not_claimed':'This finding does not identify every runtime root context/factory or assert that every provider leaves tempo data unchanged. It also does not characterize later TrackLoopHandler methods.'},
 'supported_reconstruction_claim':'A source-bound parser may preserve serialized periods/anchors and apply the pinned default native arithmetic to its explicit accepted subset. Such a result is a native-derived interpretation of serialized data; it is not a measurement of the effective clock in an arbitrary hosted Cubase environment.',
 'evidence':{'verification':pin(H/'final-verification.json'),'linkage':pin(H/'closure-linkage.json'),'global_gate':pin(M/'host-gate-global/finding.json'),'canonical_bundle':pin(H/'closure-evidence-bundle-v2.json'),'canonical_import':pin(H/'closure-evidence-import-v2.json'),'local_function_ids':local_ids},
 'limits':common_limits
}
save(H/'host-gate-service/finding.json',service)
review={
 'id':'CPR-MAP-LIST-INDEPENDENT-REVIEW-001','revision':1,'created_utc':timestamp,'source':source,
 'scope':'Independent root list passes1–7/retry review, three missing local receiver/tail functions, and bounded default host-constructor callback closure. No app edits and no target execution.',
 'decision':{'serialized_source_reconstruction':'Supported under the explicit source-shape, metadata, default-path and canonical arithmetic gates. This means interpreting pinned source records with recovered native calculations, preserving original source and unsupported state.',
             'unconditional_whole_host_invariance':'Not supported. Registry-selected components/factories and external observers are concrete runtime dependencies.',
             'actionable_unsafe_import_found_in_this_scope':False,
             'qualification':'No unsafe parser behavior or newly unsupported numeric field interpretation was identified by this bounded comparison. This is not a full security or app correctness audit.'},
 'checked_claims':[
  {'claim':'Archivefactory10173a5ac selects empty constructor10173a7c0, not default-item constructor10173a5ec. The successful retry and original64-byte instructions agree. Nonempty accepted source items therefore do not silently retain a preinserted default item.'},
  {'claim':'Base list1016e8a68 zeros owner+0x30, owner-chain head/tail+0x70/+0x78 and dirty+0x90. Parent list ctor1016c24d4 initializes array state; tempo ctor clears list+0x50 bit0x8.'},
  {'claim':'Track+0x250→10174a630 writes track+0x58 and calls1016e9a30. That appends track to linked owners at list+0x58 and clears bit0x40, with no list+0x30 store.103103ed0 tests head pointer, not count, before assigning head/tail on first append; the base constructor explicitly zeroes both pointers.'},
  {'claim':'1017379b8 forces accessor mode2 when list+0x30 is nil.1016c31b0/1016c32dc avoid mode0/1 close-notification branches for mode2. Unmapped tail-branch halt_baddata warnings in raw decompilation are not target bad instructions; full original branch words are retained.'},
  {'claim':'Reader append1016c3a8c→1016c1df4 uses103105a2c and item+0x80 comparator1017016e4, whose Start getter is101739edc. Only strictly ordered accepted source coordinates are claimed; malformed/duplicate ordering is excluded.'},
  {'claim':'1016e9d58 attaches item through+0x288→1017014ec (item+0x38=list). Nil list+0x30 excludes context propagation. Item+0x348→1000f01a0 returns0; +0x3a8→1000f01b4 returns. Dirty flags change; this is not an unchanged-object claim.'},
  {'claim':'List+0x100→1016e93fc sets dirty flags and checks ownertrack+0x2e0→1. Tempo class predicate10173f4b8 only strcmp-checks the MTrackEvent string; +0x5881001fcf00 reads track+0x78 bit0x40 without writes. Neither can mutate timing fields. Constructor-cleared list bit0x8 excludes the downstream coordinate-propagation branch.'},
  {'claim':'Concrete list+0x68→1016e9058 clears dirty+0x90 directly for nil list+0x30. Nonempty +0x1501017409ec skips default insertion, but may initialize name and dirty6 then notify. No assertion of arbitrary notification/observer invariance is made.'},
  {'claim':'Ctor tail1017060f4(track,1) sets scalar key0x696e6943 via track+0x20 attributes and1000eed94. Fresh scalar setter has no release callback. The positive source attribute read clears old collection contents before serialized track attrs. No direct track+0x50/+0x58/+0x68 write occurs in this tail.'},
  {'claim':'The newly traced host construction path is closed for the retained default provider as documented separately. It stores the handler into track+0x70 and copies fresh scalar datum into handler-local state. Arbitrary replacement providers are not covered.'},
  {'claim':'1017411c8 writes key0x6b636f4c at1050802e4 before its retained later MTempoTrackEvent class-factory/version3 registration. It is reached from1017407c4. This proves local ordering conditional on that registration path, not that1017411c8 is a Mach-O module initializer or that all startup paths were inspected.'}
 ],
 'acceptance_gates':[
  'Structurally shared track timing role and exact supported v3 tempo object; original source digest/object/record ranges retained. Unknown classes/versions/alternate identities remain unsupported.',
  'One or two finite jump records with positive binary32 periods and exact positive-zero origin, strictly increasing coordinates, supported bounded domain and kind. Ramp and extrapolated unsupported kinds are excluded.',
  'Canonical stored anchor must equal the separately rounded recovered cache recurrence bit-for-bit; this makes the accepted stored-cache/recomputed-anchor interpretations agree. Floating-point environment and actual host execution remain unobserved.',
  'Exact observed supported positive track-attribute combinations, singleton null alternate and absent ThiD per variation/finding.json; only default per-item score attributes per attributes/finding.json. Arbitrary metadata is not declared timing-inert.',
  'Default local fresh-construction receiver chain as retained, with later hosted overrides/observers outside the source-bound reconstruction claim.'
 ],
 'source_comparison':{
  'reviewed_reader':pin(R/'Application/Sources/RebaseCore/CPRRecoveryV3.swift'),
  'observed_gates':'CPRJumpMapReader rejects extra bytes/unknown keys, unverified track combinations, non-singleton or non-null alternate variations and nondefault score attrs. NativeTempoClock validation is a separately reviewed arithmetic boundary.',
  'wording_boundary':'The phrase branch-invariant applies to explicitly proved local/default arithmetic and cache branches. It must not be expanded to all possible host providers or registry states.',
  'source_unchanged':True},
 'verification_summary':{'root_unique_functions':45,'root_attempts':46,'root_bytes':12060,'root_words':3015,'root_rea_addresses':1654,'new_unique_functions':30,'new_bytes':5004,'new_words':1251,'new_rea_addresses':1045,'supporting_reused_functions':11,'root_canonical_records':90,'local_plus_supporting_canonical_records':82,'alias_only_rendering_differences':4,'semantic_word_discrepancies':0},
 'failure_custody':'The original pass6 analyze_function10173a5ac failed because the Ghidra bridge class could not be written during temporary disk exhaustion. The original function failure remains pinned, while readback/bundle/close succeeded. Separate retry-factory response succeeded; no attempt is overwritten or retroactively relabeled.',
 'evidence':[pin(H/p)for p in ['peer-byte-audit.json','final-verification.json','closure-linkage.json','supporting-evidence-checks-v2.json','host-gate-service/finding.json']]+[pin(M/p)for p in ['list/final-linkage.json','variation/finding.json','attributes/finding.json','host-gate-global/finding.json']],
 'limits':common_limits+['Scope excludes every later handler method, unknown registration providers, lifecycle edits, variations, arbitrary extensions and runtime observer effects. No broad closure of all Cubase code is claimed.']
}
save(H/'finding.json',review)
status={'scope':'All owned analysis clients and target-free evidence imports completed; no target code was run.','analysis_session_directories':verified['sessions'],'canonical_imports':verified['canonical_imports'],'open_owned_REA_session_count':0,'current_import_log':pin(H/'closure-import-progress-v2.log')}
save(H/'session-completion.json',status)
files=[pin(p)for p in sorted(H.rglob('*'))if p.is_file()and p.name!='manifest.json']
save(H/'manifest.json',{'created_utc':timestamp,'scope':'Pins owned review files at final seal, plus explicit external pins within findings; no historical files changed.','files':files})
print(json.dumps({str(p.relative_to(R)):sha(p)for p in [H/'finding.json',H/'host-gate-service/finding.json',H/'final-verification.json',H/'closure-linkage.json',H/'session-completion.json',H/'manifest.json']},indent=2))
