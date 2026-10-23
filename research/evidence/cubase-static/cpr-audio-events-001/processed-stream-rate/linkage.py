"""Recheck exact original dispatch cells and selected direct calls; no execution."""
from pathlib import Path
import sys,json,struct,hashlib
HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[4]
sys.path.insert(0,str(ROOT/'research/evidence/cubase-static/cpr-map-clock-001/attributes'))
import source_tools as s
checks=[]
def descend(x):
 if isinstance(x,dict):
  if {'address','bytes_hex','file_offset','length','sha256'} <= x.keys():
   r=s.region(int(x['address'],16),x['length'])
   assert all(r[k]==x[k] for k in r),x
   if 'target' in x: assert int(x['target'],16)==struct.unpack('<Q',bytes.fromhex(x['bytes_hex']))[0]
   checks.append(dict(address=x['address'],bytes=x['length'],sha256=x['sha256']))
  for v in x.values():descend(v)
 elif isinstance(x,list):
  for v in x:descend(v)
for p in sorted(HERE.glob('*dispatch.json')):descend(json.loads(p.read_text()))
def branch(at,target):
 word=struct.unpack('<I',s.data[s.offset(at):s.offset(at)+4])[0]
 assert word&0x7c000000==0x14000000
 imm=word&0x3ffffff
 if imm&0x2000000:imm-=0x4000000
 assert at+imm*4==target
 return dict(instruction=hex(at),target=hex(target),word=f'{word:08x}')
branches=[branch(a,b)for a,b in [
 (0x100110c38,0x10035a0f4),(0x100112cb0,0x10035a0f4),
 (0x1002b5e78,0x10036e34c),(0x10035a318,0x10036e34c),
 (0x1002ef7dc,0x1002c2040),(0x1002ef82c,0x1002c3730),
 (0x1002ef3e0,0x1002d89fc),(0x1002d8dd4,0x1002d91a4),
 (0x1002d9218,0x10036e34c)]]
# Receiver-specific accessor slots used by current constructors and group reader.
accessor=[]
for slot,target in [(0xe8,0x1003704cc),(0xf0,0x1003704d4),
                    (0x118,0x1003704fc),(0x198,0x10036ee80)]:
 r=s.region(0x1044664f0+slot,8)
 assert struct.unpack('<Q',bytes.fromhex(r['bytes_hex']))[0]==target
 r.update(slot=hex(slot),target=hex(target));accessor.append(r)
# Original immutable format5 descriptor: kind2,bits32,id5,size4.
r=s.region(0x10391d140,16)
assert struct.unpack('<IIII',bytes.fromhex(r['bytes_hex']))==(2,32,5,4)
result=dict(passed=True,target_executed=False,source_sha256=s.PIN,
 dispatch_cells_checked=len(checks),dispatch_checks=checks,direct_calls=branches,
 accessor_dispatch=accessor,format5_descriptor=r,
 limitation='Original-image pointer cells and branch targets, not runtime receiver substitution or provider behavior.')
with (HERE/'linkage.json').open('x')as f:json.dump(result,f,indent=2);f.write('\n')
print(f'{len(checks)} dispatch cells, {len(branches)} direct calls, 4 accessor slots and format5 checked')
