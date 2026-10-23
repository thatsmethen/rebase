"""Byte-origin and exact-rational controls; no target or native kernel execution."""
from pathlib import Path
from fractions import Fraction as F
import hashlib,importlib.util,json,struct,sys
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent;R=H.parents[5]
P=R/'research/evidence/cubase-static/cpr-map-clock-001/oracle-iterator/map_oracle.py'
s=importlib.util.spec_from_file_location('ieee',P);ieee=importlib.util.module_from_spec(s);s.loader.exec_module(ieee)
tables=json.loads((H/'table-bytes.json').read_text())
def data(a,n):
 t=next(t for t in tables if int(t['address'],16)<=a and a+n<=int(t['address'],16)+t['length'])
 b=bytes.fromhex(t['bytes_hex']);off=a-int(t['address'],16);return list(b[off:off+n])
def tbl(v,m):return [v[i] if i<16 else None for i in m]
# The generic kernels LD3 deinterleaves low/middle/high bytes, then the four
# masks select contiguous groups0..3. Signed high-byte widening supplies sign
# extension, while zero-extended low and middle bytes occupy bits0 and8.
fallback=[]
for group in range(4):
 mask=data(0x103934570+16*group,16)
 expected=sum(([4*group+i,None,None,None]for i in range(4)),[])
 assert tbl(list(range(16)),mask)==expected
 fallback+=expected[::4]
assert fallback==list(range(16))
# Specialized kernels put the24-bit sample into bits8..31. Track original byte
# positions through each original TBL mask; None denotes TBL zero fill.
alternate=[]
for endian in ['little','big']:
 for n in [4,8,16]:
  result=[]
  if endian=='little' and n>=8:
   for base in range(0,n*3,24):
    result+=tbl(list(range(base,base+16)),data(0x103d9f520,16))
    result+=tbl(list(range(base+8,base+24)),data(0x103d9f530,16))
  else:
   for base in range(0,n*3,12):
    v=list(range(base,base+8))+list(range(base+4,base+12))
    result+=tbl(v,data(0x103d9f540 if endian=='little' else 0x103d9f550,16))
  expected=[]
  for sample in range(n):
   origins=list(range(sample*3,sample*3+3))
   if endian=='big':origins.reverse()
   expected += [None]+origins
  assert result==expected
  alternate.append(dict(byte_order=endian,samples=n,output_int32_byte_origins=result,identity_sample_order=True))
values=[-8388608,-8388607,-8388606,-4194305,-4194304,-65537,-65536,-32769,-32768,-257,-256,-255,-2,-1,0,1,2,255,256,257,32767,32768,65535,65536,66051,4194303,4194304,4194305,8388605,8388606,8388607]
rows=[]
for p in values:
 bits=ieee.encode(F(p,1<<23),p=24,eb=8)
 assert ieee.decode(bits,p=24,eb=8)==F(p,1<<23)
 # The signed integer conversions themselves are exact, including shift8.
 assert ieee.decode(ieee.encode(F(p),p=24,eb=8),p=24,eb=8)==p
 assert ieee.decode(ieee.encode(F(p*256),p=24,eb=8),p=24,eb=8)==p*256
 little=(p&0xffffff).to_bytes(3,'little');big=little[::-1]
 assert int.from_bytes(little,'little',signed=True)==int.from_bytes(big,'big',signed=True)==p
 rows.append(dict(signed24=p,little_bytes=little.hex(),big_bytes=big.hex(),float32_bits=f'{bits:08x}',exact_value=str(F(p,1<<23))))
assert next(r for r in rows if r['signed24']==8388607)['float32_bits']=='3f7ffffe'
assert next(r for r in rows if r['signed24']==-8388608)['float32_bits']=='bf800000'
assert next(r for r in rows if r['signed24']==0)['float32_bits']=='00000000'
# Later reviewed PAudioSegment consumer: convert at unit accessor gain, then
# one Float32 event-gain multiplication. These are prospective analytical
# controls, not target audio or evidence that a fixture uses these gains.
consumer=[]
for gain in [0x3e800000,0x3dcccccd,0x3f000000,0x3f800000,0x3f800001,0x40000000]:
 g=ieee.decode(gain,p=24,eb=8)
 for row in rows:
  p=row['signed24'];v=F(p,1<<23)*g;bits=ieee.encode(v,p=24,eb=8)
  consumer.append(dict(signed24=p,event_gain_bits=f'{gain:08x}',input_f32_bits=row['float32_bits'],output_f32_bits=f'{bits:08x}'))
result=dict(scope='Static analytical byte-order/lane and unit-gain conversion controls, plus separate event Float32 gain controls. No target/native kernel execution.',
 scalar_vectors=rows,scalar_vectors_count=len(rows),specialized_vector_byte_origin_checks=alternate,generic_vector_group_order=fallback,
 consumer_vectors=consumer,consumer_vectors_count=len(consumer),
 constants={'generic_scale_float32_bits':'34000000','generic_scale_exact':'1/8388608','specialized_scale_float32_bits':'30000000','specialized_scale_exact':'1/2147483648'},
 exactness_argument='Every signed24 integer p is exactly representable inbinary32; p*256 also has atmost24significantbits and remains signed32 representable. Multiplication by2^-23 or2^-31 yields the same exact normal-or-zero p/2^23. Unit-gain arithmetic therefore has no finite rounding error, clipping, dithering, endpoint renormalization or capability-dependent difference in the traced kernels.',
 domain='Packed signed24, exact unit converter gain, disjoint contiguous input/output buffers, nonnegative samplecount with positive framecount×channels fitting signed32, same-rate same-channel path. Arbitrary converter gain/alias/negativecount not generalized.',
 negative_controls=['Maxpositive divided by8388607 would incorrectly yield1.0(3f800000).','Unsigned24 would misdecode sign-set values.','Wrongendian swaps66051(010203) to197121(030201).','Specialized leftshift8 withgeneric2^-23 scale would be256times too large.'],
 rational_helper={'path':str(P.relative_to(R)),'sha256':hashlib.sha256(P.read_bytes()).hexdigest()},target_execution_count=0)
with (H/'analytical-controls.json').open('x')as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps(dict(scalar_vectors=len(rows),consumer_vectors=len(consumer),symbolic_vector_checks=len(alternate),passed=True)))
