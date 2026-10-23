"""Original-image custody and typed binding checks. Never executes target code."""
from pathlib import Path
import sys,json,re,hashlib
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent;R=H.parents[4]
sys.path.insert(0,str(R/'research/evidence/cubase-static/cpr-map-clock-001/attributes'));import source_tools as s
pin=lambda p:dict(path=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def env(p):
 d=json.loads(p.read_text());assert not d.get('isError'),p
 return d.get('structuredContent') or json.loads(d['content'][0]['text'])
uses={}
for folder in sorted(H.glob('pass*')):
 if not folder.is_dir():continue
 deriv=json.loads((folder/'derivation.json').read_text());assert deriv['source_sha256']==s.PIN
 for row in deriv['derivatives']:
  raw=folder/row['raw_file'];assert pin(raw)['sha256']==row['raw_sha256']
  assert raw.read_bytes()==bytes.fromhex(s.region(int(row['entry'],16),row['length'])['bytes_hex'])
 lines=(folder/'run.log').read_text().splitlines();assert lines[-1]=='CLOSED: isolated raw-slice MCP session'
 assert all(json.loads(line)['isError']is False for line in lines[:-1])
 uses[folder]=[int(row['entry'],16)for row in deriv['derivatives']]
 for a in uses[folder]:
  close=env(folder/f'close-{a:x}.json')['result'];assert close['evidence_records']==2
  assert Path(close['path']).stat().st_size==close['bytes']
prior=[
('cpr-objects-001/audio-native',0x1017017a0),('cpr-objects-001/audio-native',0x1000ee164),('cpr-objects-001/native/pass3',0x101715fb0),('cpr-objects-001/native/pass3',0x101716008),('cpr-signature-001/pass9',0x1017154a0),('cpr-map-clock-001/list',0x1017014ec),('cpr-audio-events-001/timebase/pass10',0x101700d64),('cpr-audio-events-001/timebase/pass10',0x101700d6c),('cpr-audio-events-001/audible-state/pass2',0x101701934),('cpr-audio-events-001/audible-state/pass15',0x1000e9148),('cpr-map-clock-001/attributes/pass3',0x101700aac),('cpr-audio-events-001/builder-rate-provider/pass2',0x10171bcdc),('cpr-audio-events-001/autofade-source/pass1',0x101722120),('cpr-audio-events-001/renderer-selection/pass17',0x10020ee24),('cpr-audio-events-001/event-rendering/pass4',0x1002115a0),('cpr-audio-events-001/placed-event-builder/pass1',0x10020e354),('cpr-audio-events-001/placed-event-builder/pass1',0x10020e7c8),('cpr-audio-events-001/placed-event-builder/pass1',0x10020f2e8),('cpr-audio-events-001/event-rendering/pass2',0x100212f3c),('cpr-audio-events-001/event-rendering/pass2',0x1000ea704),('cpr-audio-events-001/event-rendering/pass2',0x1000ea694),('cpr-map-clock-001/variation/pass2',0x1000e8c38),('cpr-signature-001/pass11',0x1016c137c),('cpr-audio-events-001/timebase/pass7',0x1016e1bd0),('cpr-map-clock-001/attributes/pass4',0x1030f88d4),('cpr-map-clock-001/list',0x1016e8a68)]
for d,a in prior:uses.setdefault(R/'research/evidence/cubase-static'/d,[]).append(a)
rows=[]
for folder,addresses in uses.items():
 for a in addresses:
  paths=[folder/f'{v}-{a:x}.json'for v in ['function','bytes','bundle']];native=folder/f'native-{a:x}.txt'
  words={int(pc,16):int(w,16)for pc,w in re.findall(r'^([0-9a-f]+):\s+([0-9a-f]{8})\s',native.read_text(),re.M)}
  for pc,w in words.items():assert int.from_bytes(bytes.fromhex(s.region(pc,4)['bytes_hex']),'little')==w
  d,read,b=[env(p)for p in paths];q=read['raw_result'];assert q['complete']and q['requested_bytes']==q['returned_bytes']
  original=bytes.fromhex(s.region(a,q['returned_bytes'])['bytes_hex']);assert original==bytes.fromhex(q['bytes_hex'])and len(original)==len(words)*4
  asm=d['raw_result']['value']['assembly'];assert all(int(v.split(':')[0],16)in words for v in asm)
  assert len(b['result']['records'])==2
  rows.append(dict(entry=hex(a),new=folder.parent==H,directory=str(folder.relative_to(R)),bytes_verified=len(original),original_native_words=len(words),rea_instruction_addresses=len(asm),evidence_ids=[d['evidence_id'],read['evidence_id']],files=[pin(p)for p in [native]+paths]))
bindings=[]
for table,label,slots in [
 (0x104670218,'MListNode', {0xf0:0x1017154a0,0x98:0x101715fb0,0x158:0x1016ea4c4}),
 (0x1046703b8,'MListNode iterator',{0xd0:0x101715bac,0xd8:0x101715bbc,0xf8:0x101715c20,0x158:0x1016c1700}),
 (0x10442e898,'MAudioEvent',{0x98:0x1000ee164,0x178:0x1000e9cf8,0x1a8:0x1000ea130,0x288:0x1017014ec,0x2e0:0x101700d64,0x2e8:0x101700d6c,0x360:0x101701934}),
 (0x10466be98,'MContext',{0xd8:0x1016e70f4}),
 (0x104447470,'default builder predicate',{0x10:0x1001e4fa0}),
 (0x10444dc60,'optional root predicate',{0x10:0x1002139f0}),
 (0x104447210,'predicate composite',{0x10:0x1001e4884}),
 (0x10444da18,'range',{0xc8:0x1002136ec}),
 (0x10444d8a0,'range list',{0xd8:0x100213534}),
 (0x104678ea8,'MTrackList different iterator (excluded)',{0xf0:0x101758eec})]:
 for slot,value in slots.items():
  reg=s.region(table+slot,8);assert int.from_bytes(bytes.fromhex(reg['bytes_hex']),'little')==value,(label,slot)
  bindings.append(dict(label=label,table=hex(table),slot=hex(slot),target=hex(value),source=reg))
spans=[]
for label,a,n in [
 ('fresh event flags zero',0x101700ac8,12),('fresh root mode zero',0x10171bd54,20),('root reader preserves bit0 in direct store',0x1017225a8,12),('MEvent masks and ORs serialized flags',0x1017017b8,76),('ordinary no-overlap normalizer',0x10020e884,108),('no explicit fade initialized extents',0x100212f5c,16),('optional root filter condition',0x10020ef0c,96),('auto-fade flags zero branch',0x10020f738,20),('no-neighbor/no-fade branches',0x10020fae4,12),('zero end fade to remainder',0x100210208,12),('plain remainder builder',0x1002104fc,220),('auto-only adjacency scan',0x100210620,32)]:
 spans.append(dict(label=label,source=s.region(a,n)))
x=dict(source_sha256=s.PIN,target_executed=False,functions=rows,dispatch=bindings,original_ranges=spans,summary=dict(new_captures=sum(r['new']for r in rows),reused_captures=sum(not r['new']for r in rows),bytes_verified=sum(r['bytes_verified']for r in rows),original_native_words=sum(r['original_native_words']for r in rows),rea_instruction_addresses=sum(r['rea_instruction_addresses']for r in rows),closed_raw_sessions=len(list(H.glob('pass*/run.log'))),canonical_records=sum(len(r['evidence_ids'])for r in rows)),passed=True,limits=['Custody checks do not establish semantic completeness.','LC_FUNCTION_STARTS intervals can include disconnected exception tails.','Raw Ghidra imports omit external globals/types and can misrepresent floating-point unordered comparisons and inferred signatures. Original instructions govern stated local contracts.','New captures may recapture earlier functions. Counts describe this study inventory, not unique discoveries across repository.'])
(H/'verification.json').write_text(json.dumps(x,indent=2)+'\n');print(x['summary'])
