"""Replay/verify this bounded static study and seal its report without rewriting probes."""
from pathlib import Path
import hashlib, json, re, struct, subprocess, sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(HERE))
import probe_source as probe

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def reference(path):
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    assert path.is_file(), path
    return dict(path=str(path.relative_to(ROOT)), bytes=path.stat().st_size, sha256=digest(path))

def evidence(path):
    value=json.loads(path.read_text())
    assert not value.get('isError',False), path
    return value.get('structuredContent') or json.loads(value['content'][0]['text'])

immutable = {p: digest(p) for p in [HERE/'source-forward-probe.json', HERE/'source-controls.json',
    HERE/'verification.json', ROOT/'scripts/cpr_probe.py', HERE/'probe_source.py']}
source=ROOT/'research/targets/derived/Cubase15-arm64'
source_bytes=source.read_bytes()
source_sha=digest(source)
assert source_sha=='dda1a4b68a275cf7fa58541022ad02462b17b749a36b819d2c5dcd654bfa67bb'
verification=json.loads((HERE/'verification.json').read_text())
native_rows=[]
record_ids=[]
for number in range(1,6):
    directory=HERE/f'pass{number}'
    derivation=json.loads((directory/'derivation.json').read_text())
    assert derivation['source_sha256']==source_sha
    for row in derivation['derivatives']:
        address=int(row['entry'],16); name=row['entry'][2:]
        raw=(directory/row['raw_file']).read_bytes()
        assert len(raw)==row['length']
        assert hashlib.sha256(raw).hexdigest()==row['raw_sha256']
        offset=row['source_file_offset']
        assert raw==source_bytes[offset:offset+len(raw)]
        readback=evidence(directory/f'bytes-{name}.json')['raw_result']
        assert readback['complete'] and readback['returned_bytes']==readback['requested_bytes']==len(raw)
        assert bytes.fromhex(readback['bytes_hex'])==raw
        native=(directory/row['original_native_disassembly']).read_text()
        words={int(a,16):int(w,16) for a,w in re.findall(r'^([0-9a-f]+):\s+([0-9a-f]{8})\s',native,re.M)}
        assert len(words)==len(raw)//4
        assert all(struct.unpack_from('<I',raw,a-address)[0]==w for a,w in words.items())
        function=evidence(directory/f'function-{name}.json')
        addresses=[int(x.split(':')[0],16) for x in function['raw_result']['value']['assembly']]
        assert len(addresses)==len(set(addresses)) and all(a in words for a in addresses)
        records=evidence(directory/f'bundle-{name}.json')['result']['records']
        record_ids.extend(x['evidence_id'] for x in records)
        evidence(directory/f'close-{name}.json')
        assert (directory/f'snapshot-{name}.json').is_file()
        native_rows.append(dict(entry=row['entry'],source_bytes=len(raw),native_words=len(words),
            rea_instruction_addresses=len(addresses),evidence_ids=[x['evidence_id'] for x in records]))
totals=dict(functions=len(native_rows),source_bytes=sum(x['source_bytes'] for x in native_rows),
    native_words=sum(x['native_words'] for x in native_rows),
    rea_instruction_addresses=sum(x['rea_instruction_addresses'] for x in native_rows),
    unique_evidence_ids=len(set(record_ids)))
assert totals==verification['totals']==dict(functions=9,source_bytes=5716,native_words=1429,
    rea_instruction_addresses=1326,unique_evidence_ids=18)
bundle=json.loads((HERE/'evidence-bundle.json').read_text())
assert {x['evidence_id'] for x in bundle['records']}==set(record_ids)
imported=evidence(HERE/'evidence-import.json')['result']
assert imported==dict(imported=18,unknowns_added=0,total=18)
assert (HERE/'import-run.log').read_text().endswith('CLOSED: evidence import session\n')
assert json.loads((HERE/'import-session-completion.json').read_text())['exit_code']==0
for row in json.loads((HERE/'reader-class-literals.json').read_text())['strings']:
    raw=bytes.fromhex(row['bytes_hex']);offset=row['file_offset']
    assert source_bytes[offset:offset+len(raw)]==raw
    assert hashlib.sha256(raw).hexdigest()==row['sha256']
    assert raw==row['text'].encode('ascii')+b'\0'

base=ROOT/'research/targets/full-reference/expanded/Cubase 15.app.pkg/Payload/Cubase 15.app/Contents/Project Templates/Cubase Pro'
saved=json.loads((HERE/'source-forward-probe.json').read_text())
sources={}; fixture_rows=[]
for expected in saved['fixtures']:
    path=base/(expected['fixture']+'.cpr')
    data=path.read_bytes();sources[expected['fixture']]=data
    assert hashlib.sha256(data).hexdigest()==expected['source_sha256']
    actual=probe.inspect(data);actual['fixture']=expected['fixture']
    assert actual==expected, expected['fixture']
    setting=actual['project']['setting']
    assert setting is not None and setting['flags']==0
    assert setting['duration_bits']=='3f847ae147ae147b'
    assert len(setting['interpolators'])==4
    assert all(x['class']=='MLinearInterpolator' and x['version']==0 and x['body_bytes']==68 for x in setting['interpolators'])
    assert all(t['local']['setting'] is None and t['local']['token']['kind']=='null' for t in actual['tracks'])
    fixture_rows.append(dict(fixture=actual['fixture'],source=reference(path),
        root_identity=actual['root_identity'],root_parsed_end=actual['root_parsed_end'],
        root_attribute_count=actual['root_attribute_tail']['count'],
        root_auxiliary_count=actual['root_auxiliary_list']['count'],
        root_keyed_event_count=len(actual['root_event_table']['entries']),
        setting_identity=setting['object']['size_offset'],setting_body=setting['object']['body_offset'],
        setting_end=setting['object']['end'],flags_offset=setting['flags_offset'],flags=setting['flags'],
        duration_bits=setting['duration_bits'],interpolators=[dict(identity=c['size_offset'],class_name=c['class'],version=c['version'],body_bytes=c['body_bytes'],body_sha256=c['body_sha256']) for c in setting['interpolators']],
        tracks=[dict(identity=t['track_identity'],parsed_end=t['parsed_end'],numeric_attribute_count=t['attribute_tail']['count'],
            local_null_offset=t['local']['token']['offset'],effective_origin=t['effective_origin'],effective_flags=t['effective_flags'],
            opaque_word=t['word'],opaque_number_bits=t['number_bits']) for t in actual['tracks']]))
controls=json.loads((HERE/'source-controls.json').read_text())
assert controls['count']==len(controls['controls'])==20
control_rows=[]
for control in controls['controls']:
    data=sources[control['fixture']]
    offset=control['changed_offset'];old=bytes.fromhex(control['original_bytes']);new=bytes.fromhex(control['changed_bytes'])
    assert len(old)==len(new) and data[offset:offset+len(old)]==old
    mutated=bytearray(data);mutated[offset:offset+len(old)]=new
    assert hashlib.sha256(mutated).hexdigest()==control['mutated_sha256']
    try:
        actual=probe.inspect(bytes(mutated))
    except (ValueError,struct.error) as error:
        outcome=dict(rejected=True,reason=str(error))
    else:
        track=actual['tracks'][0]
        outcome=dict(rejected=False,effective_flags=track['effective_flags'],zero_flag_bypass=track['zero_flag_bypass'],opaque_track_word=track['word'])
    assert outcome==control['outcome'],control['name']
    assert control['passed']
    control_rows.append(dict(fixture=control['fixture'],name=control['name'],replayed_equal=True,rejected=outcome['rejected']))

# Scope process inspection to this study's actual clients, not unrelated applications.
processes=subprocess.run(['ps','-axo','pid=,args='],capture_output=True,text=True,check=True).stdout.splitlines()
markers=[str(HERE),str(HERE.relative_to(ROOT))]
active=[line for line in processes if any(marker in line for marker in markers) and ('.mjs' in line or 'rea --mcp' in line)]
assert not active,active
for path,before in immutable.items():assert digest(path)==before
closure=dict(target_executed=False,source_forward_probe_unchanged=True,original_verification_unchanged=True,
    native=totals,canonical_import=imported,source_fixture_replays=2,source_control_replays=20,
    controls=control_rows,all_checks_passed=True,
    session_state=dict(binary_close_and_snapshot_receipts=9,currently_active_study_clients=active,
        import_completion=reference(HERE/'import-session-completion.json'),
        limitation='Per-function close receipts are direct retained evidence; parent import exit status is explicitly attributed. No invented exit codes for earlier capture shells.'))
(HERE/'seal-verification.json').write_text(json.dumps(closure,indent=2)+'\n')

prefix='research/evidence/cubase-static/cpr-audio-events-001/'
ownership=reference(prefix+'event-rendering/ownership-finding.json')
assert ownership['sha256']=='14aaee2b8096ee1f0c2f502b4942140111ba4b86ecc703617e50c27d03861a85'
owner_contract=json.loads((ROOT/ownership['path']).read_text())
assert owner_contract['source_fixture_correlation']['source']['sha256']==digest(HERE/'source-forward-probe.json')
finding=dict(id='CPR-AUTOFADE-SOURCE-001',status='sealed bounded static saved-source contract',
    target_executed=False,runtime_comparisons=0,native_source_sha256=source_sha,
    conclusion='Forward structural parsing reaches the project and local audio-track automatic-fade slots in both pinned templates. Both local slots are null; both nonnull project MAutoFadeSetting v0 objects store flags0. The separately sealed root-ownership study binds the normal fallback to this same project setting. Zero flags satisfy the retained builder automatic-fade bypass predicate; no entire event or timeline rendering equivalence follows.',
    claims=[
        dict(id='AF1',claim='MRoot reader101722120 calls10170ee20→10171862c→1017017a0. After the MEvent26-byte prefix/data-node/numeric-attribute sequence,1030f91c4 consumes a u16 list word, signed32 count and counted archive objects. The pinned root auxiliary count is0. Remaining normal version6 slots are FNPath, PPool, marker, tempo, signature, MAutoFadeSetting, signed16 keyed-event count and pairs, then loudness; the probe reaches exact root end in both templates.',functions=['0x101722120','0x10170ee20','0x10171862c','0x1017017a0','0x1030f91c4']),
        dict(id='AF2',claim='Normal MAudioTrackEvent reader1001f76dc first calls10174b638, which restores MEvent, required MTrack resource, versioned signed32 word/double and optional MAutomationNode. Audio-track version1 then reads the MAutoFadeSetting slot into+170. The pinned source has a literal null there and exact track end. The special0x46706d49 import branch and arbitrary post-read callbacks are outside this normal-restoration contract.',functions=['0x1001f76dc','0x10174b638','0x1017017a0']),
        dict(id='AF3',claim='103116a6c reads the numeric ID then tail-branches to103116478 for typed payload. Native type-bit dispatch distinguishes objects/strings/integer/double and other families. The probe deliberately supports only its explicit observed type allowlist and rejects unknown types/counts/references; it is not a general attribute decoder.',functions=['0x103116a6c','0x103116478']),
        dict(id='AF4',claim='Both source project settings are MAutoFadeSetting version0, 364-byte bodies: u16flags0, f64duration bits3f847ae147ae147b (0.01), followed by four MLinearInterpolator version0 objects of68-byte bodies. The existing native setting reader10018cd6c expects four MInterpolator objects and binds flags to+c/duration to+10. Probe class checks are a stricter observed subset; interpolator bodies are retained opaque, not decoded as curves.',external_reader=reference(prefix+'event-rendering/pass5/function-10018cd6c.json')),
        dict(id='AF5',claim='Source-local null does not independently prove automatic fades disabled. The linked ownership finding supplies the normal restored MRoot fallback; the retained builder10020f2e8 obtains that effective setting and skips automatic-fade work when its u16+c iszero. Builder override flags0x28 are not substituted for this source-backed predicate.',ownership=ownership,builder_linkage=reference(prefix+'event-rendering/final-linkage.json')),
    ],
    parser_scope=dict(arrangement='PArrangement version4 containing MRoot version6 via existing bounded archive walker',
        base_versions=dict(MEvent=1,MTrackEvent=2),
        required_root_roles=[dict(class_name='FNPath',version=0),dict(class_name='PPool',version=5),dict(class_name='MTempoTrackEvent',version=3),dict(class_name='MSignatureTrackEvent',version=3)],
        nullable_root_roles=[dict(class_name='MMarkerTrackEvent',version=0),dict(class_name='MLoudnessTrackEvent',version=0)],
        track_classes=dict(event='MAudioTrackEvent v1',resource='MAudioTrack v0',automation='MAutomationNode v1 nullable'),
        settings='MAutoFadeSetting v0 nullable in parser; this zero-flag source conclusion requires actual nonnull effective setting. Null project setting is unresolved default, never silently zero.',
        numeric_attribute_types=['0x1','0x801','0x2','0x12','0x22','0x92','0x8(CmString v0)'],
        boundaries='Exact source class/identity resolution, duplicate/key/count checks, exact object-end checks; no nearest-string resynchronization.'),
    fixtures=fixture_rows,validation=dict(native=totals,canonical_records_imported=18,
        fixture_replays=2,source_controls=20,rejected_controls=16,accepted_classification_controls=4,
        control_scope='In-memory mutated parser inputs only: flagsnonzero disables zero bypass; nonfinite duration, unknown version/type/reference, wrong local/loudness class and negative counts reject; track word stays opaque.'),
    limitations=['No Cubase execution, native reader invocation, audio capture, runtime comparison or full timeline equivalence.',
        'Flags0 only bypasses automatic-fade construction; event fades/gain/warp/source selection and PCM are separate contracts.',
        'The four interpolation payloads, pool/resource/automation and unknown attribute bodies remain opaque. No curve shape or nonzero fade mode is inferred.',
        'Typed class/version and bounds checks are intentionally narrower than all native acceptance paths; special import/legacy/recovery branches are not projected.',
        'Root and track callbacks may change live state. The separate ownership proof covers successful normal restoration, not later hosted mutation or extension replacement.',
        'Raw slices omit global data/types/imports and can omit disconnected exception tails.103116a6c halt_baddata is the valid unmapped external tail branch to103116478, not evidence of a broken target.',
        'REA instruction-address counts and parser controls establish evidence custody/mechanical consistency, not semantic or acoustic equivalence.'],
    references=[reference(HERE/name) for name in ['source-forward-probe.json','source-controls.json','reader-class-literals.json','verification.json','seal-verification.json','evidence-import.json']]+[
        reference(ROOT/'scripts/cpr_probe.py'),reference(HERE/'probe_source.py'),ownership],
    preservation='Existing source-forward-probe, controls and original verification retained byte-identical; new finding/seal verification/manifest only.')
(HERE/'finding.json').write_text(json.dumps(finding,indent=2)+'\n')
external=[reference(source),reference(ROOT/'scripts/cpr_probe.py'),ownership,
    reference(prefix+'event-rendering/final-linkage.json'),reference(prefix+'event-rendering/pass5/function-10018cd6c.json')]
external.extend(x['source'] for x in fixture_rows)
files=[reference(p) for p in sorted(HERE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.name!='artifact-manifest.json']
manifest=dict(id='CPR-AUTOFADE-SOURCE-001-MANIFEST',target_executed=False,
    files=files,external_inputs=external,file_count=len(files),total_bytes=sum(x['bytes'] for x in files),
    verification='All listed files exist and are SHA256-pinned; source bytes/readbacks/native words, two exact forward replays and20 controls rechecked by seal_study.py.',
    sessions='Every native analysis has successful close_binary and snapshot; no active study client. Parent import session73654 exited0 and its exact completion stdout is retained with attribution.')
(HERE/'artifact-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
for entry in files+external:
    assert digest(ROOT/entry['path'])==entry['sha256']
print(json.dumps(dict(passed=True,files=len(files),native=totals,controls=20,
    finding_sha256=digest(HERE/'finding.json'),manifest_sha256=digest(HERE/'artifact-manifest.json'))))
