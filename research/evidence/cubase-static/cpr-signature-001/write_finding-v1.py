"""Assemble bounded native signature findings and their immutable evidence pins."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p): return json.loads(p.read_text())
def pin(p): return {'path':str(p.relative_to(ROOT)), 'sha256':sha(p)}
directories = [HERE] + [HERE/f'pass{i}' for i in range(2,14)]
functions = []
for directory in directories:
    verification = load(directory/'verification.json')
    assert verification['passed']
    assert 'CLOSED: isolated raw-slice MCP session' in (directory/'analysis-progress.log').read_text()
    for row in verification['functions']:
        ident = row['entry'][2:]
        functions.append(dict(row, evidence_directory=str(directory.relative_to(ROOT)),
                              function_record=pin(directory/f'function-{ident}.json'),
                              native_disassembly=pin(directory/f'native-{ident}.txt')))
def evidence(*addresses):
    selected = [r for r in functions if r['entry'] in addresses]
    assert len(selected) == len(addresses)
    return [dict(entry=r['entry'],evidence_id=r['analyze_function_evidence_id'],path=r['function_record']['path']) for r in selected]

facts = [
 dict(id='SIG-001', title='Compact archive records and version-3 replacement are distinct',
      contract='MSignatureTrackEvent archive reader reads signed32 count; version3 compact records are signed32 coordinate plus six signed16 fields (16 bytes each). The first two shorts become numerator/denominator. It subsequently reads numeric-ID attributes, finds key0x736b6c43, and calls101730d90. That routine obtains a fresh mode2 accessor, removes/releases the current list items, then appends typed SignatureEvent objects. Consequently a contradictory compact prefix must not override a valid later typed representation.',
      details=['The fresh accessor constructor stores a null filter at+0x20. Accessor+150 iterates current node list; +120 detaches each item, and103101e50 relinks neighbors, nulls item links and decrements list count.',
               'If first typed object is absent or fails MTimeSignatureEvent class test, native code creates a default4/4 item. A strict importer should report unsupported instead of calling that fallback a recovered source signature.',
               'Unlike the tempo reader, nonpositive compact signature count has a native default-item path. This finding does not assign malformed-count acceptance to the importer.'],
      evidence=evidence('0x101730874','0x101730d90','0x1017015b8','0x10174a698','0x101758eec','0x101716448','0x1016c137c','0x101716db0','0x101716814','0x103101e50')),
 dict(id='SIG-002', title='Typed compound objects reach the named attribute reader',
      contract='FAttributes archive reader1031a2cf0 calls1031a2e64 then1031ab5b8. Original jump-table bytes bind type2 to compound dispatch. Subtype201 reads a signed32 count; item subtype20 reads a class-name string, uint64 identity and recursive named attributes into an FXmlInstance. FAttributes getter1031a032c unwraps its FXmlObject interface by+d0;1031ae4e8 creates the named class and calls its+b0 named-attribute reader. MTimeSignatureEvent+b0 is10172b378. This is not its packed archive reader10172b08c.',
      details=['Raw REA image omits external jump table103c7a6d2, so its1031ab5b8 pseudocode is incomplete. Dispatch claims use original native instructions and separately pinned table bytes, not invented pseudocode.',
               'The typed uint64 identity is not an FNewArchive payload offset. It participates in typed-object bookkeeping; this study does not promote arbitrary typed reference/cycle recovery.',
               'Selected scalar type1 uses signed64 stream read; type4 uses binary64; type8 uses the string path. Exact fixture types remain stricter than the native coercing getter.'],
      evidence=evidence('0x1031a2cf0','0x1031a2e64','0x1031ab5b8','0x1031ab444','0x1031a032c','0x1031ae4e8','0x10172b378')),
 dict(id='SIG-003', title='Bar precedence and exact named property offsets',
      contract='Named reader10172b378 first calls the base event reader, then requests Bar into signed64+0x48. Only when Bar is absent does it set+0x48=0 and request Position, storing Position as internal numeric attribute0x504c4153. Thus an explicit Bar wins over a contradictory named Position. Numerator and Denominator write signed16+0x50/+0x52. SubNumerator1/2/3 map to+0x54/+0x56/+0x58. Named Flags writes+0x5a; TimeSignatureDisplayFlags, when present, overrides that display field.',
      details=['10319de60 accepts integer, double conversion or numeric string according to type.10319dfd0 stores only the low16 bits on successful conversion, with no observed range check. A safe application subset requires exact integer fields within application range and rejects coercion/truncation cases.',
               'Missing numerator/denominator does not establish a safe default: the native reader ignores the short getter success and copies local shorts. Require both fields.',
               'Base reader101701cf4 maps Start -> virtual+d8, Length ->+e8, Offset ->+f8 (missing offset becomes0), Flags through mask+360, then Additional Attributes. A compatibility global selects an alternate base path; no runtime global value was observed.',
               'Signature+d8 rounds a double to integer ordinal with sign-dependent half adjustment; the subsequent explicit Bar read overwrites it. Signature+e0 converts ordinal+48 to double.'],
      evidence=evidence('0x10172b378','0x10172b250','0x10319de60','0x10319dfd0','0x101701cf4','0x10172adf0','0x10172ae80')),
 dict(id='SIG-004', title='Restored origin and coordinate arithmetic',
      contract='During typed restoration, an internal position attribute on the first event forces its Bar ordinal to0; without that attribute the named Bar value is preserved. For the single explicit Bar=0 case, no prior signature segment contributes an offset. The coordinate consumer10172fff4 reads signed numerator/denominator and ordinal directly. For nonzero denominator: perBeat=int16(SDIV32(1920,denominator)); perBar=int16(numerator)*perBeat. It accumulates previous ordinal intervals and returns Double(accum + perBar*(queryBar-currentBar)) + Double(int32(perBeat*queryBeatIndex)) + tickOffset, in that FADD order.',
      details=['For the observed4/4 origin item, one denominator beat contributes480 internal units and one bar1920. Numerator/denominator change the bar and denominator-beat span by this exact integer rule.',
               'The denominator-zero branch uses1920 per bar and480 per beat. Invalid denominator/range/overflow behavior is excluded from the application subset.',
               'Inverse helper10172fb78 has absolute-value,1e-7 tolerance, conversion and negative-coordinate branches. This is retained evidence, not a claim that the application reproduces those rounding or negative-domain rules.',
               'This binds ordinal zero and meter ratios within native signature coordinates. It does not alone bind all serialized tempo/audio coordinates to seconds or prove host-wide musical-time equivalence.'],
      evidence=evidence('0x101730d90','0x101734b80','0x101734b88','0x10172fff4','0x10172fb78')),
 dict(id='SIG-005', title='Strict null-alternate variation branch',
      contract='The final callback10174c194 conditionally processes track variations. Collection reader1017a43f0 tails to1030f2cdc: signed32 field is stored at+14 (serialized10 becomes-1);1030f91c4 reads signed16 flags and signed32 object count, then reads that many archive objects. MTrackVariation reader1017a4250 reads its name, one archive object requested as MDataNode into+28, then signed32 into+38. A zero archive reference means no alternate node. It is not a second integer or a second object reference.',
      details=['For a variation with+28 nil, binding1017a3f98 resets+30, attaches the current track list from+258 to+28, invokes that list+150 (MTrackList implementation is exactly RET), reads track+4f0 (exact getter of+68), and sets ownership links. This branch does not replace the current signature item list.',
               'Non-null alternate nodes, multiple variations, unknown flag/selector combinations and variation switching are outside the supported source projection. No host UI selection, feature global or post-load state was observed.',
               'Track-visibility branch calls1017064c4 with0, which removes numeric attribute0x64696854; valid external tail branches are misrepresented as halt_baddata in a raw decompilation. Native instructions retain their actual targets.'],
      evidence=evidence('0x10174c194','0x1017a5898','0x1017a4fb4','0x1017a3f98','0x1017064c4','0x1017a43f0','0x1030f2cdc','0x1030f91c4','0x1017a4250')),
]
finding = dict(
 id='CPR-SIGNATURE-001',created_utc=datetime.now(timezone.utc).isoformat(),
 status='Bounded native restoration and named-field contract; no target runtime execution or equivalence measurement',
 source={'path':'research/targets/derived/Cubase15-arm64','sha256':'dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb','product':'Cubase Pro15.0.30.287 macOS arm64'},
 method={'provider':'Ghidra12.1.4 through pinned REA6.7.0','profile':'ghidra-default, raw-binary, AARCH64:LE:64:v8A,2G heap',
         'function_count':len(functions),'evidence_records':len(functions)*2,
         'native_interval_words':sum(load(d/'verification.json')['total_native_interval_instructions'] for d in directories),
         'rea_decoded_instruction_addresses':sum(load(d/'verification.json')['total_rea_body_instructions'] for d in directories),
         'derived_bytes':sum(sum(r['length'] for r in load(d/'derivation.json')['derivatives']) for d in directories),
         'byte_readbacks_exact':True,'mcp_sessions_closed':len(directories),'canonical_bundle_import':load(HERE/'evidence-import-validation.json')},
 facts=facts,
 independent_fixture_contract=pin(HERE/'fixtures/finding-v1.json'),
 fixture_correlation={'source':'Ten immutable shipped Pro templates; exact source and prior probe pins rechecked.',
                      'observation':'All ten have one compact4/4 record at coordinate0 and one typed MTimeSignatureEvent with Bar0,Numerator4,Denominator4,Position0,Flags8,Start0,Length1. Equality of these representations was not used to infer precedence.',
                      'additional_attributes':'Some fixtures contain nested score attributes; these are preserved opaque unless separately supported. Metadata MusicalSignature is not used as authority.'},
 supported_projection_proposal={
  'scope':'Recover one explicit constant origin signature into application musical-quarter-beat0, as a source-field projection under the bounded native branch, not a complete Cubase load equivalence claim.',
  'requirements':['Structurally reached MSignatureTrackEvent version3 and FAttributes version0; exact body/count bounds and class/reference validation.',
                  'Exactly one SignatureEvent subtype201 item, subtype20 class MTimeSignatureEvent; exact integer Bar=0, required exact integer Numerator/Denominator within application-supported ranges. Do not derive recovery from compact prefix or metadata.',
                  'Named Position may differ when Bar is present: Bar wins. Unsupported fallback/coercion/missing-Bar inputs must remain explicit until implemented and tested against this contract.',
                  'Strictly supported top-level flags and signature extras; no unrecognized fields silently promoted to supported. Opaque score/extra state remains listed as unsupported rather than discarded from the preserved original.',
                  'If variations present, accept only explicitly parsed supported collection header/flags/count with one MTrackVariation having null alternate MDataNode; reject non-null alternate data and other variation states.'],
  'counterexamples':['Compact4/4 followed by typed7/8 must project7/8 if all other gates pass.',
                     'Bar0 plus Position1920 must remain origin when Bar is explicitly present.',
                     'Missing numerator, duplicate keys, noninteger/coerced numerator, out-of-range short, unknown object class/version, multiple items or non-null variation alternate must not become a recovered default.']},
 limits=['Static code and immutable fixture evidence only. Native runtime comparison count remains0.',
         'Raw slices omit imports, global data, external jump tables, relocation/unwind context and neighboring functions; retained original bytes/LLVM/linkage evidence supplies only the explicitly claimed links.',
         'Decompiler text is generated non-source, not guaranteed compilable or bit-faithful. halt_baddata at unmapped valid tails is not proof of invalid target instructions.',
         'No general malformed-input acceptance, complete archive graph identity/cycles, full signature-track variation model, display/pickup/subdivision behavior or all-version compatibility is claimed.',
         'The legacy packed MTimeSignatureEvent archive layout is retained for distinction; it is not substituted for actual named-field fixture bodies.'],
 linkage=pin(HERE/'linkage-provenance.json'),correction_record=pin(HERE/'verification-corrections.json'),
 functions=functions)
(HERE/'finding.json').write_text(json.dumps(finding,indent=2)+'\n')
print(json.dumps({'finding_sha256':sha(HERE/'finding.json'),'functions':len(functions),'records':len(functions)*2,'native_words':finding['method']['native_interval_words'],'rea_addresses':finding['method']['rea_decoded_instruction_addresses']}))
