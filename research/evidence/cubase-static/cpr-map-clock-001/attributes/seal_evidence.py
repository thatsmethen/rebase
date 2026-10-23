#!/usr/bin/env python3
"""Seal independently verifiable original-byte links for the static finding."""
import hashlib,json,struct
from pathlib import Path
import source_tools as s
P=Path(__file__).resolve().parent
R=s.ROOT
H=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
proof=[]
for d in sorted(P.glob('pass*/derivation.json')):
 for row in json.loads(d.read_text())['derivatives']:
  b=(d.parent/row['raw_file']).read_bytes();a=int(row['entry'],16)
  assert b==s.data[s.offset(a,len(b)):s.offset(a,len(b))+len(b)]
  response=json.loads((d.parent/f'bytes-{a:x}.json').read_text())['structuredContent']['raw_result']
  assert response['complete'] and bytes.fromhex(response['bytes_hex'])==b
  fn=d.parent/f'function-{a:x}.json';q=json.loads(fn.read_text())['structuredContent']
  assert not json.loads(fn.read_text()).get('isError')
  (d.parent/f'pseudocode-{a:x}.txt').write_text(q['raw_result']['value']['pseudocode'])
  proof.append(dict(entry=row['entry'],bytes=len(b),original_offset=s.offset(a,len(b)),sha256=H(d.parent/row['raw_file']),
                    dossier=str(fn.relative_to(R)),dossier_sha256=H(fn)))
slots={}
for name,base,offsets in [('score_container',0x104556990,[0x30,0x98,0xe8]),('note_data',0x104556b08,[0x30,0x98,0xb0]),('numeric_container',0x104e315f0,[0xe8,0x108,0x118]),('numeric_entry',0x104e33638,[0x78,0x80,0x98]),('named_container',0x104e2f648,[0xe8,0x118]),('named_entry',0x104e33540,[0x78])]:
 slots[name]=dict(vtable=hex(base),slots=[dict(slot=hex(o),target=hex(struct.unpack_from('<Q',s.data,s.offset(base+o,8))[0]),**s.region(base+o,8))for o in offsets])
refs=[]
for rel in ['cpr-objects-001/audio-native/function-1000ee8c4.json','cpr-signature-001/pass13/function-1030f2cdc.json','cpr-signature-001/pass13/function-1030f91c4.json','cpr-signature-001/pass4/function-10319dfd0.json','cpr-signature-001/pass5/function-1031a2cf0.json','cpr-signature-001/pass6/function-1031a2e64.json','cpr-signature-001/pass6/function-1031ab5b8.json','cpr-signature-001/pass6/native-1031ab5b8.txt']:
 p=R/'research/evidence/cubase-static'/rel;assert p.exists();refs.append(dict(path=str(p.relative_to(R)),sha256=H(p)))
manifest=json.loads((R/'research/evidence/cubase-static/cpr-audio-timing-001/reviewer-template-state.json').read_text())
report=dict(schema_version=1,target_executed=False,source=dict(path=str(s.SOURCE.relative_to(R)),sha256=s.PIN,bytes=len(s.data)),
 verification=dict(exact_source_ranges=len(proof),bytes=sum(x['bytes']for x in proof),all_REA_read_bytes_match_original=True,functions=proof),
 vtables=slots,original_regions=dict(note_constructor_defaults=s.region(0x1039c6120,16),registration_initializer=s.region(0x100c1b384,152),mod_init_pointer=s.region(0x10440b008,8),named_type_switch=s.region(0x103c7a6d2,8)),
 reused_evidence=refs,fixture_decoder=dict(path=str((P/'decoded-fixtures.json').relative_to(R)),sha256=H(P/'decoded-fixtures.json'),complete_bodies=4,negative_controls=20),
 result='MAP-GATE-1 load-time materialization is bounded for the exact observed default NoteData subset. This alone does not establish overall tempo-map acceptance.',
 allowlist=['Fresh MTempoEvent attribute slot +0x20 is null; successful bounded archive reading.',
 'Per-item attribute count is zero, or exactly one key0x5343436e type0x22 with explicit ScoreEventAttributeContainer v1.',
 'Container index10, flags1, count1; exact NoteData v2 positional payload13 bytes or v3 named payload146 bytes.',
 'Fields voiceIndexOnStave=-1, staveIndex=-1, isGraceNote=0, noteNameOptionalIsSet=0, noteName=0; v3 has exactly these five unique integer fields. No extra bytes/objects/fields/aliases.',
 'All bytes are consumed exactly and original source is preserved; arbitrary attributes, additional objects, changed flags and nondefault values remain unsupported.'],
 native_chain=[
 {'edge':'Concrete class registration/factory', 'detail':'__mod_init_func pointer10440b008 targets100c1b384. Original initializer passes ScoreEventAttributeContainer literal1038c1b81, factory100c1a810, version1 and NoteData literal1038c1b9e, factory100c1a864, current version4 to1022138c4. Constructors set the respective vtables; class-name getters and read slots independently agree. NoteData reader explicitly handles shipped v2 and v3. LC_FUNCTION_STARTS begins at100c1b37c with an earlier return; Ghidra dossier at that entry does not substitute for the original initializer instructions.'},
 {'edge':'Fresh parent item', 'detail':'101700aac writes item+20=null after its base call. Caller10173bdac passes item+20 to1000ee8c4 after timing fields are read. Parent owns concrete item/list lifecycle review.'},
 {'edge':'Numeric attachment', 'detail':'1000ee8c4 reads positive count then allocates/clears container104e315f0; count0 leaves an existing container untouched. Fresh path has count0 and flags1. It materializes FIntIDAttribute104e33638, reads key at+1c and type0x22 at+18;103116478 object branch stores only the new object pointer at wrapper+10. The key is not interpreted as a timing operation.'},
 {'edge':'No outer insertion callback on this path', 'detail':'Fresh clear103106144 has no old entries. Insert10310587c chooses index0 through103105a2c without comparator. Callback1030f9c44 invokes entry+8 only for flags2, excluded by flags1. Writes are vector storage/count and the parent attribute pointer, not period48/seconds50/tick58/kind60.'},
 {'edge':'Container materialization', 'detail':'Factory100c1a810 allocates40 bytes, constructor1030f14e4 sets count0/data-null, then vtable104556990. Read slot98→100c1ae50→1030f2cdc maps index10 to-1 then1030f91c4 reads flags/count/NoteData. During insertion flags are0; append1030f1b5c only updates own count/vector and1030f9c44 has no callback. Serialized flags1 are assigned after loading.'},
 {'edge':'NoteData version2', 'detail':'100c1a8e0 writes i32 voice to+10, i32 stave to+0c, sign-extended i16 grace to+1c, reads full u16 optional flag plus u8 note. With false optional it does not assign noteName. Base103105140 returns1 without writes. Factory defaults pin the remaining state.'},
 {'edge':'NoteData version3', 'detail':'100c1a8e0 creates independent FAttributes via10319dc94 (+18=null), reads named fields via1031a2cf0/1031a2e64/1031ab5b8, then invokes own slotb0→100c1ab9c. Original jump-table byte1c maps integer type1 to1031ab6e8: readi64 then1000a5798 with flag4. This allocates own named entries and list, appends with flags1 and writes scalar payload through103115c74; fresh scalar state excludes release callbacks. No object/reference named fields occur in this allowlist.'},
 {'edge':'Named-field consumers', 'detail':'100c1ab9c and base helper100bdd6f4 query only local attributes and write NoteData-owned members.100bdd6f4 is a field reader, not a reset: it reads stave/voice, absent SuppressPlayback and absent Visibility (local default0). Getters10319e00c/10319dfd0/10319e138 use10319de60. Named list+118→1030f2b7c performs linear entry+78 comparison; concrete named entry+78→10304ea84 calls strcmp on key pointers. Integer payload103116224 takes direct+10 branch for type1; no polymorphic payload callback. Optional-name=false excludes note-name getter path. Absent spelledForPitch/notationOffset leave ctor defaults-1/0.'}],
 track_positive_count_cross_gate=[dict(source=Path(f['source']).name,counts=[t['track_attributes']['count']for t in f['tempo_objects']])for f in manifest['fixtures']],
 limits=['Static byte/control-flow deductions, not Cubase runtime measurements or FP environment observations.',
 'Scope is successful read/materialization and attachment of this exact data, not all later consumers, editing, playback suppression or arbitrary score metadata.',
 'The observed load chain has no parent timing/list pointer supplied to NoteData and no branch-specific callback that writes timing fields. It does not prove arbitrary target code globally side-effect free.',
 'Memory allocation/string helpers retain their ordinary data-structure role; exceptional allocation/unwind paths are outside successful parsing.',
 'Remaining map gates include list receiver/cache lifecycle, variation/visibility effects, record order, interpolation/quantization and supported FP semantics; parent and peers own those findings.',
 'Original source unchanged; raw REA imports omit external globals/relocations/vtables and are reconciled against original-image bytes here.'])
(P/'finding.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(report=str(P/'finding.json'),sha256=H(P/'finding.json'),functions=len(proof),bytes=sum(x['bytes']for x in proof))))
