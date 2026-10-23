"""Seal the local static variation gate; never executes the target."""
import datetime, hashlib, json
from pathlib import Path
H=Path(__file__).resolve().parent; R=H.parents[4]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def pin(p):
 p=Path(p); return {'path':str(p.relative_to(R)), 'bytes':p.stat().st_size,'sha256':sha(p)}
new=[]
for rel in ['verification.json','pass2/verification.json','pass3/verification.json']:
 d=json.loads((H/rel).read_text()); assert d['passed'];new+=d['functions']
reuse=json.loads((H/'reused-evidence.json').read_text())
link=json.loads((H/'linkage-and-fixtures.json').read_text())
imp=json.loads((H/'evidence-import.json').read_text())
refs=[pin(H/p) for p in ['verification.json','pass2/verification.json','pass3/verification.json','reused-evidence.json','linkage-and-fixtures.json','external-evidence-checks.json','native-evidence-bundle.json','evidence-import.json']]
f={
 'id':'CPR-MAP-GATE-2', 'revision':1, 'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'scope':'Static successful fresh detached MTempoTrackEvent v3 restore, local post-read variation and visibility callback; no target execution.',
 'source':{'path':'research/targets/derived/Cubase15-arm64','sha256':link['source_sha256']},
 'conclusion':'The accepted singleton/null-alternate source form does not substitute a different tempo list or insert a default item into a nonempty list in the traced local callback. It may initialize the list name, retain references, write owner-related state and set dirty bits. Cache equivalence and observer limits remain separate list/arithmetic gates.',
 'acceptance_gate':{
  'restore_context':'Successful fresh detached archive construction and v3 reader; no later host edits or arbitrary observers.',
  'tempo_item_count':'Strictly positive; zero-item source is excluded because concrete list+0x150 inserts a default tempo item.',
  'track_attributes':'Positive serialized count, complete successful read, exact parsed extents, no duplicate accepted keys; zero count is excluded because 1000ee8c4 then does not clear an existing collection.',
  'variation_attribute':{'numeric_key':'0x69435654','serialized_bytes_ascii':'iCVT','type':'0x22','payload_class':'MTrackVariationCollection','version':0,'serialized_selector':10,'native_selector':-1,'flags':2,'count':1,'member':{'class':'MTrackVariation','version':0,'name':'Bounded archive string; all ten observed names are v1. Importer may deliberately restrict to v1.','alternate_MDataNode':'null','trailing_i32':0},'exact_body_consumption_required':True},
  'absent_numeric_key':'0x64696854 (ThiD in little-endian native-key display; use exact numeric ID, not a guessed text reversal)',
  'other_attributes':'Must satisfy MAP-GATE-1 independently, including score/item attribute restrictions. This report does not provide an unrestricted attribute allowlist.',
  'anchors_and_cache':'Must satisfy root list/iterator/cache arithmetic gate. Name notification is not assumed globally inert; requiring source anchors to equal native recomputation bitwise can make the supported cache branches equivalent.'},
 'claims':[
  {'claim':'Feature branches are explicit, not assumed disabled. 10174c194 calls 1017a5898 when TRACK_VARIATIONS is truthy; when TRACK_VISIBILITY bit0 is clear it calls 1017064c4(track,0).','functions':['10174c194'],'authority':'Retained native instructions and pinned global string-pointer linkage.'},
  {'claim':'Tempo +0x550 returns1. Existing iCVT resolves to the concrete collection; count1 means nonempty, excluding default collection/member creation. 1017a5898 visits the sole member.','functions':['10173f61c','1017a4fb4','1017a5898','1006f3b24','1030f1b4c','1006f3b2c','1017a5ed0']},
  {'claim':'For null alternate at variation+0x30, 1017a3f98 captures track+0x58 via +0x258 into variation+0x28 and retains it, then calls concrete tempo-list+0x150. +0x4f0 returns track+0x68, zero in the verified fresh base-track constructor. This is reference/ownership mutation, not a no-op.','functions':['1017a3f98','101747fe4','10174a630'],'getters':['10174a698','10174aa6c']},
  {'claim':'Concrete MTempoTrackNode vtable104675ec8 +0x150 is1017409ec, not the signature-list no-op. A nonzero count skips default item creation. If the list name is empty, +0xd0 sets its name and dirty+0x90 |=6, then notifies. 6 does not intersect cache-cleanup mask0x11. Deferred or arbitrary observer effects are not proven inert.','functions':['1017409ec','1016c29ac','1000fd13c','1016e9990','1016e8fe8','101740948','1016e8ff4']},
  {'claim':'Fresh owner attachment inserts the same track into list+0x58 linked owners without populating list+0x30. The first-owner lookup is read-only; owner +0x258 returns that same list and the null-alternate path therefore writes list+0x88 nil.','functions':['1016e8a68','1016e9a30','103103ed0','1016ea7fc','103104c40','1017a3f98']},
  {'claim':'Accepted0x22 entries use direct stored payload. Numeric lookup and exact FIntIDAttribute key comparison are read-only; temporary key cleanup has zero flags/payload. Absent ThiD makes 1000e8db0 skip removal. Positive-count attribute restoration clears old entries before source entries, so accepted successful reads cannot inherit an unrecorded ThiD.','functions':['1000ee8c4','1000e8c38','1000e8db0','103105d1c','103106254','103117b9c','103117bb0','103115e54','10221bae0']},
  {'claim':'The +8 retain reached for the concrete list/variation is an atomic increment at object+8 via10221baec→10307d074; no additional callback is present in those bounded instructions.','functions':['10221baec','10307d074']}
 ],
 'evidence':{'new_functions':17,'new_source_bytes':1788,'new_original_instruction_words':447,'new_rea_instruction_addresses':421,'new_mnemonic_differences':0,'reused_functions':10,'reused_source_bytes':sum(x['length'] for x in reuse['functions']),'canonical_bundle_records':54,'bundle_import':imp,'pins':refs,'function_evidence':[{'entry':x['entry'],'function_evidence_id':x['analyze_function_evidence_id'],'readback_evidence_id':x['read_bytes_evidence_id']} for x in new]+[{'entry':x['entry'],'function_evidence_id':x['function_evidence_id'],'readback_evidence_id':x['readback_evidence_id']} for x in reuse['functions']]},
 'fixture_corroboration':{'source_count':10,'details':'linkage-and-fixtures.json rechecks original CPR bytes, numeric key/type, singleton collection fields, null member datum, trailing zero, absent ThiD and exact ranges. Fixture agreement is not runtime validation.'},
 'provider_failure_boundary':'Selected external factory10173a5ac original64-byte native slice was verified, but its first REA attempt failed due to bridge compilation failure. external-evidence-checks.json explicitly excludes that attempt from REA success. The root-owned isolated retry is evaluated separately in list-review; this report does not overwrite or promote the failed artifact.',
 'limits':['Raw-slice pseudocode lacks linked types, imports and full program context; indirect targets are bound only through explicitly retained original vtable/constructor bytes. Generated pseudocode is not source or a compilable reconstruction.', 'The local callback contract is not a proof of arbitrary global notifications, later lifecycle, concurrent host observers, editing, switching variations, map iterator behavior, or cache invalidation equivalence.', 'No default or alternate variation payloads, empty lists, failed reads, inherited zero-count track attributes or unsupported attribute payloads are accepted.', 'List+0x88 owner-related write and dirty/name/refcount changes are real; preserving tempo item fields locally does not mean the object is unchanged.', 'Target runtime executions and runtime comparisons: zero. Full Cubase behavior remains unverified.']}
(H/'finding.json').write_text(json.dumps(f,indent=2)+'\n')
files=[pin(p) for p in sorted(H.rglob('*')) if p.is_file() and p.name!='manifest.json']
(H/'manifest.json').write_text(json.dumps({'scope':'Immutable local variation evidence file pins at seal time; external pins are in finding/supporting records.','files':files},indent=2)+'\n')
print(json.dumps({'finding_sha256':sha(H/'finding.json'),'manifest_sha256':sha(H/'manifest.json'),'files':len(files)}))
