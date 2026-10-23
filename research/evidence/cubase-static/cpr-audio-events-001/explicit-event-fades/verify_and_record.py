from pathlib import Path
import hashlib,json,re,sys
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent;R=H.parents[4]
sys.path.insert(0,str(R/'research/evidence/cubase-static/cpr-map-clock-001/attributes'))
import source_tools as s

def pin(p):
 b=p.read_bytes();return dict(path=str(p.relative_to(R)),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def env(p):
 d=json.loads(p.read_text());assert not d.get('isError');return d.get('structuredContent')or json.loads(d['content'][0]['text'])
rows=[]
for folder in sorted(H.glob('pass*')):
 log=(folder/'run.log').read_text().splitlines()
 assert log[-1]=='CLOSED: isolated raw-slice MCP session'
 assert all(not json.loads(line)['isError'] for line in log[:-1])
 derivative=json.loads((folder/'derivation.json').read_text())
 assert derivative['source_sha256']==s.PIN
 for row in derivative['derivatives']:
  a=int(row['entry'],16);raw=folder/row['raw_file'];original=bytes.fromhex(s.region(a,row['length'])['bytes_hex'])
  assert raw.read_bytes()==original and pin(raw)['sha256']==row['raw_sha256']
  native=folder/f'native-{a:x}.txt'
  words=re.findall(r'^([0-9a-f]+):\s+([0-9a-f]{8})\s',native.read_text(),re.M)
  assert len(words)*4==len(original)
  for pc,w in words: assert int.from_bytes(bytes.fromhex(s.region(int(pc,16),4)['bytes_hex']),'little')==int(w,16)
  fun=env(folder/f'function-{a:x}.json');read=env(folder/f'bytes-{a:x}.json');bundle=env(folder/f'bundle-{a:x}.json')
  q=read['raw_result'];assert q['complete'] and q['requested_bytes']==q['returned_bytes']==len(original)
  assert bytes.fromhex(q['bytes_hex'])==original
  assert len(bundle['result']['records'])==2
  assert fun in bundle['result']['records'] and read in bundle['result']['records']
  assert all(int(line.split(':')[0],16) in {int(pc,16) for pc,w in words} for line in fun['raw_result']['value']['assembly'])
  rows.append(dict(entry=hex(a),directory=str(folder.relative_to(R)),bytes=len(original),words=len(words),
    evidence_ids=[fun['evidence_id'],read['evidence_id']],files=[pin(folder/f'{p}-{a:x}.json')for p in ['function','bytes','bundle']]+[pin(native),pin(raw)]))
refs=[]
for folder,a in [('event-rendering/pass2',0x100212f3c),('event-rendering/pass2',0x1000ea79c),('event-rendering/pass2',0x1000ea87c),('placed-event-context/pass7',0x1016e39c8),('placed-event-builder/pass1',0x10020f2e8),('processed-stream-rate/pass2',0x1001113f8)]:
 d=H.parent/folder;read=env(d/f'bytes-{a:x}.json');raw=bytes.fromhex(read['raw_result']['bytes_hex']);assert raw==bytes.fromhex(s.region(a,len(raw))['bytes_hex'])
 fun=env(d/f'function-{a:x}.json')
 refs.append(dict(entry=hex(a),evidence_ids=[fun['evidence_id'],read['evidence_id']],files=[pin(d/f'{p}-{a:x}.json')for p in ['function','bytes','bundle']]+[pin(d/f'native-{a:x}.txt')]))
bindings=[]
for offset,target in [(0x40,0x100113494),(0xc8,0x100113564),(0xf8,0x1001113f8),(0x140,0x10035a744),(0x148,0x10035a704),(0x1a8,0x100110f6c)]:
 reg=s.region(0x1044360a8+offset,8);assert int.from_bytes(bytes.fromhex(reg['bytes_hex']),'little')==target
 bindings.append(dict(table='0x1044360a8',slot=hex(offset),target=hex(target),source=reg))
strings=[]
for a,value in [(0x103891e39,'MFadeIn'),(0x103891e55,'MInterpolator'),(0x1038926e7,'AudioVolumeCurveStream')]:
 reg=s.region(a,len(value)+1);assert bytes.fromhex(reg['bytes_hex'])==value.encode()+b'\0'
 strings.append(dict(value=value,source=reg))
result=dict(schema_version=1,id='EXPLICIT-EVENT-FADES-PROGRESS-01',status='partial static research; NOT application admission',source_sha256=s.PIN,target_executed=False,native_runtime_comparisons=0,
 summary=dict(captured_intervals=len(rows),bytes_verified=sum(r['bytes']for r in rows),native_words=sum(r['words']for r in rows),reused_intervals=len(refs),closed_sessions=3),
 captures=rows,reused=refs,dispatch=bindings,typed_strings=strings,
 observations=[
  dict(addresses=['0x100212f3c','0x1000ea7b4','0x1000ea95c','0x10018b714'],claim='Explicit fade extents are computed from event+90/+98. Fade-in getter delegates through MFade object+10 interpolator virtual+1a0. Fade-out getter computes RN64(RN64(event+70+event+68)-interpolatorExtent); its subsequent context conversion is distinct from the fade-in duration conversion. Exact serialized interpolator semantics remain unresolved.'),
  dict(addresses=['0x10020f7b8','0x10020f868','0x100210208','0x1002102c8'],claim='Builder creates explicit fade sections using AudioVolumeCurveStream100110c18, a clone of the saved MInterpolator and per-event Float32 gain on the containing PAudioSegment. Fade-in and fade-out supply different source origins/lengths; fade-out wrapper extent is incremented by5. Exact clipping/overlapping-fade cases and meaning of the extra5 remain to be closed.'),
  dict(addresses=['0x100110c18','0x1001113f8'],claim='Curve stream stores/retains its curve interface at+50 and normalization flag at+58. Open path invokes curve interface+48 with wrapper length and then+50, conditional on first open and supplied flag. This is separate from canonical segment projection.'),
  dict(addresses=['0x100110f6c','0x10011100c','0x100111018','0x1001110fc','0x1001112a4'],claim='Concrete curve-processing virtual+1a8 queries interface+40 at input position and position+100, computes a binary64 slope and fused intercept, and uses fused multiply-add to evaluate piecewise linear gains with100-frame refresh. When block extent approaches wrapper length, short remaining requests use direct interpolator evaluation. Exact update endpoints and read scheduling require authored controls before promotion; arbitrary block-partition invariance is not presumed.'),
  dict(addresses=['0x1001111a0','0x100111354','0x100111124','0x1001112d8'],claim='The inner scalar and vector sample loops promote each Float32 input to Double, multiply by the Double envelope, then round to Float32. This differs from first rounding the envelope to Float32. Event gain remains a separately ordered stage. No clipping is visible in this concrete processing loop.'),
 ],
 next_application_feature='Restore explicitly saved fade-in/fade-out envelopes on source-track fragments, with their real source origins and double-precision envelope arithmetic, then qualify interactions with overlap splits and saved-rate contexts.',
 required_next_evidence=['Bind MFadeIn/MFadeOut serialized readers and concrete MInterpolator object tags to lengths, point payloads and virtual evaluation.','Follow AudioVolumeCurveStream clone100110c9c and base processing read dispatch to establish block sizes, absolute position, seek behavior and curve-reset lifetime.','Recover interface+40 interpolation evaluation, +48 domain normalization, +50 reset and primary+1a0 extent getters; pin concrete dispatch, not interface guesses.','Reconstruct builder explicit fade clipping and fade-in/out overlap cases, especially fade-out extent+5 and original source offset.','Create independent rational/FMA and Float32 rounding controls, including block-size and seek cases, before adding source admission.'],
 limits=['All proprietary bytes stayed unexecuted; REA/Ghidra static analysis only.','This record is an unsealed progress artifact, not a final finding or completed numerical reconstruction.','Pass2 repeated100110c18 even though prior matching capture existed; retained repeated output is labeled corroborating capture, not independent evidence. Future work should reuse the earlier capture.','No app/source/binaries from APP020 or overlap study changed.','Open/raw tool results may omit globals/imports; original target byte readbacks bind source identity, not hosted state.'],
 script=pin(Path(__file__)))
with(H/'progress-01.json').open('x')as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps(dict(summary=result['summary'],output=pin(H/'progress-01.json'))))
