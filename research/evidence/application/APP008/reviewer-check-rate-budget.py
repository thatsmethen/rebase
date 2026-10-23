"""Independent optimized candidate check. Never loads or executes Cubase code."""
from pathlib import Path
from fractions import Fraction as F
import ctypes as C, datetime, hashlib, importlib.util, json, random, subprocess, sys
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent;R=H.parents[3]
SRC=R/'Application/Sources/RebaseTimingDSP/cpr_rate_budget.c';HEADER=SRC.parent/'include/cpr_rate_budget.h'
E=R/'research/evidence/cubase-static/cpr-audio-events-001/rate-converter'
O=R/'research/evidence/cubase-static/cpr-map-clock-001/oracle-iterator/map_oracle.py'
spec=importlib.util.spec_from_file_location('review_ieee',O);ieee=importlib.util.module_from_spec(spec);spec.loader.exec_module(ieee)
MAX=(1<<31)-1
ceil=lambda x:-((-x.numerator)//x.denominator)
class Result(C.Structure):
 _fields_=[(n,C.c_int32)for n in ['source','pad','adjusted','initial','reverse','decrements']]+[('search',C.c_uint32)]+[(n,C.c_uint64)for n in ['inbits','outbits','productbits']]
def pin(p):return dict(path=str(p.relative_to(R)),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size)
shim=H/'reviewer-rate-budget-shim.c'
shim.write_text('#include <fenv.h>\nint review_nearest(void){return FE_TONEAREST;}\nint review_upward(void){return FE_UPWARD;}\nint review_downward(void){return FE_DOWNWARD;}\nint review_zero(void){return FE_TOWARDZERO;}\n')
libpath=H/'reviewer-rate-budget.dylib';asm=H/'reviewer-rate-budget.arm64.s'
flags=['clang','-O2','-std=c11','-fno-fast-math','-ffp-contract=off','-frounding-math','-I',str(HEADER.parent)]
commands=[flags+['-dynamiclib',str(SRC),str(shim),'-o',str(libpath)],flags+['-S',str(SRC),'-o',str(asm)]]
for cmd in commands:subprocess.run(cmd,check=True,capture_output=True)
lib=C.CDLL(str(libpath));fn=lib.rb_cpr_rate_read_budget;fn.argtypes=[C.c_uint32,C.c_uint32,C.c_int32,C.c_int,C.POINTER(Result)];fn.restype=C.c_int
system=C.CDLL(None);system.fegetround.restype=C.c_int;system.fesetround.argtypes=[C.c_int]
assert system.fegetround()==lib.review_nearest()
def normal(a):return a>>31==0 and 0<(a>>23&255)<255
def reference(a,b,n,branch):
 if not normal(a) or not normal(b) or n<=0 or branch not in (0,1):return 1,None
 if a==b:return 0,dict(source=n,pad=0,adjusted=n,initial=n,reverse=n,decrements=0,inbits=ieee.encode(1),outbits=ieee.encode(1),productbits=ieee.encode(n))
 x=ieee.decode(a,p=24,eb=8);y=ieee.decode(b,p=24,eb=8)
 outbits=ieee.encode(y/x);q=ieee.decode(outbits)
 if not ieee.decode(0x3f847ae147ae147b)<=q<=100:return 3,None
 pad=2048*ceil(q) if branch else 0;N=n+pad
 if N>MAX:return 3,None
 inbits=ieee.encode(x/y);prod=ieee.op(inbits,ieee.encode(N),'mul');k=ceil(ieee.decode(prod))
 if k>MAX:return 3,None
 initial=k;steps=0
 while True:
  rev=ieee.decode(ieee.op(outbits,ieee.encode(k),'mul'))
  if rev>=1<<31:return 3,None
  m=int(rev)
  if m<=N:break
  k-=1;steps+=1;assert k>=0 and steps<1000
 return 0,dict(source=k,pad=pad,adjusted=N,initial=initial,reverse=m,decrements=steps,inbits=inbits,outbits=outbits,productbits=prod)
rows=[]
def check(a,b,n,branch,expect=None,label='generated'):
 status,want=reference(a,b,n,branch) if expect is None else expect
 value=Result();C.memset(C.byref(value),0xa5,C.sizeof(value));before=bytes(value)
 got=fn(a,b,n,branch,C.byref(value));assert got==status,(hex(a),hex(b),n,branch,status,got)
 if status:assert bytes(value)==before
 else:
  for k,v in want.items():assert getattr(value,k)==v,(hex(a),hex(b),n,branch,k,v,getattr(value,k))
  assert value.search<=33
 rows.append(dict(label=label,source_f32_bits=f'{a:08x}',output_f32_bits=f'{b:08x}',requested=n,branch=branch,status=got,expected=want,search_evaluations=value.search if status==0 else None))
sealed=json.loads((E/'analytical-count-controls.json').read_text())
for v in sealed['budget_vectors']+sealed['controls']:
 a=int(v['source_f32_bits'],16);b=int(v['output_f32_bits'],16);branch=int(v['mode']==2 and v['first'] and v['available'])
 want=dict(source=v['returned_source_frames'],pad=v['padding'],adjusted=v['total_budget'],initial=v['initial_ceil'],reverse=v['reverse_mapped_frames'],decrements=v['correction_decrements'],inbits=int(v['input_ratio_f64_bits'],16),outbits=int(v['output_ratio_f64_bits'],16),productbits=int(v['initial_product_f64_bits'],16))
 check(a,b,v['requested'],branch,(0,want),'sealed244')
rng=random.Random(0x43505208)
counts=[1,2,3,7,127,147,2047,2048,4096,65535,MAX,MAX-1,MAX-2,MAX-4096,MAX-4097]
# Positive-normal bits across exponents, close rates, both sides of ratio limits,
# and large count transitions. References use exact rational rounding and a
# literal decrement loop, independent of the candidate binary-search method.
pairs=[]
for _ in range(400):
 exp=rng.randrange(1,255);other=max(1,min(254,exp+rng.randrange(-7,8)))
 a=(exp<<23)|rng.randrange(1<<23);b=(other<<23)|rng.randrange(1<<23);pairs.append((a,b))
for a in [0x00800000,0x00800001,0x3f800000,0x42c80000,0x472c4400,0x473b8000,0x7f7ffffe,0x7f7fffff]:
 for b in [a,max(0x00800000,a-1),min(0x7f7fffff,a+1)]:pairs.append((a,b))
for a,b in pairs:
 for n in [rng.choice(counts),rng.randrange(1,MAX+1)]:
  for branch in [0,1]:check(a,b,n,branch)
for a in [0,0x80000000,1,0x007fffff,0x80800000,0xbf800000,0x7f800000,0xff800000,0x7fc00000,0x7f800001]:
 for branch in [0,1]:check(a,0x473b8000,1,branch);check(0x473b8000,a,1,branch)
for n in [-2147483648,-1,0]:check(0x472c4400,0x473b8000,n,0)
for branch in [-2147483648,-1,2,2147483647]:check(0x472c4400,0x473b8000,1,branch)
assert fn(0x472c4400,0x473b8000,1,0,None)==1
rounding=[];saved=system.fegetround()
try:
 for mode in [lib.review_upward(),lib.review_downward(),lib.review_zero()]:
  assert system.fesetround(mode)==0
  for a,b in [(0x472c4400,0x473b8000),(0x472c4400,0x472c4400)]:
   result=Result();C.memset(C.byref(result),0xa5,C.sizeof(result));old=bytes(result)
   assert fn(a,b,1,0,C.byref(result))==2 and bytes(result)==old and system.fegetround()==mode
  rounding.append(mode)
finally:assert system.fesetround(saved)==0
text=asm.read_text();assert all(x in text for x in ['fdiv','fmul','frintp','fcvtzs']);assert not any(x in text for x in ['fmadd','fmsub','fnmadd','fnmsub'])
controls=H/'reviewer-rate-budget-controls.json'
with controls.open('x')as f:json.dump(rows,f,indent=2);f.write('\n')
summary=dict(id='APP008-INDEPENDENT-RATE-BUDGET-CHECK',at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),status='passed',commands=commands,
 compiler=subprocess.run(['clang','--version'],check=True,capture_output=True,text=True).stdout.splitlines()[0],
 sealed_vectors=244,additional_cases=len(rows)-244,accepted=sum(r['status']==0 for r in rows),rejected=sum(r['status']!=0 for r in rows),
 corrected_cases=sum(bool(r['expected'] and r['expected']['decrements'])for r in rows),max_correction=max(r['expected']['decrements']for r in rows if r['expected']),max_search=max(r['search_evaluations']or 0 for r in rows),
 exact_intermediate_bits_checked=True,error_output_preserved=True,rounding_modes_rejected=rounding,rounding_environment_restored=system.fegetround()==saved,null_output_rejected=True,
 emitted_operations={'required':['fdiv','fmul','frintp','fcvtzs'],'fused_operations_absent':True,'scope':'Presence check plus exact control results, not formal compiler proof'},
 pins=[pin(p)for p in [SRC,HEADER,Path(__file__),shim,libpath,asm,controls,O,E/'count_oracle.py',E/'analytical-count-controls.json']],
 scope='Only self-authored candidate arithmetic executed. New controls use independent Fraction instruction rounding with literal native decrement loop; no Cubase, backend, sample-resampling or runtime fidelity claim.',target_executions=0)
with(H/'reviewer-rate-budget-check.json').open('x')as f:json.dump(summary,f,indent=2);f.write('\n')
print(json.dumps({k:summary[k]for k in ['status','sealed_vectors','additional_cases','accepted','rejected','corrected_cases','max_correction','max_search']}))
