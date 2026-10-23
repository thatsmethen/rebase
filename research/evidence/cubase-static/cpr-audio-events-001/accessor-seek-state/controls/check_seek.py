"""Original-instruction derived Fraction controls against authored C only."""
from pathlib import Path
from fractions import Fraction as F
import ctypes as C,subprocess,json,importlib.util,sys,hashlib,struct
sys.dont_write_bytecode=True
H=Path(__file__).resolve().parent.parent;R=H.parents[4]
p=R/'research/evidence/cubase-static/cpr-map-clock-001/oracle-iterator/map_oracle.py'
spec=importlib.util.spec_from_file_location('ieee',p);ieee=importlib.util.module_from_spec(spec);spec.loader.exec_module(ieee)
lib=H/'controls/candidate-seek.dylib'
cmd=['clang','-std=c11','-O2','-fno-fast-math','-ffp-contract=off','-dynamiclib','-Wall','-Wextra','-Werror',str(H/'candidate/cpr_accessor_seek.c'),'-o',str(lib)]
r=subprocess.run(cmd,capture_output=True,text=True);(H/'controls/compile.log').write_text(r.stdout+r.stderr);assert r.returncode==0
class Out(C.Structure):_fields_=[('sourceFrame',C.c_int64),('returnedOutputFrame',C.c_int64),('ratio',C.c_uint32),('product',C.c_uint64),('quotient',C.c_uint64)]
c=C.CDLL(str(lib));f=c.rb_cpr_accessor_seek;f.argtypes=[C.c_uint32,C.c_uint32,C.c_int64,C.POINTER(Out)];f.restype=C.c_int
bits32=lambda n:ieee.encode(F(n),p=24,eb=8)
rows=[]
for sr,dr in [(48000,44099),(48000,47998),(44100,48000),(48000,44100),(8000,192000),(192000,8000),(44100,44100),(192000,192000)]:
 for n in [0,1,2,3,7,127,1023,8191,8192,1000001,1058400,2**31-1,2**53-1,2**53]:
  rb=bits32(F(sr,dr));ratio=ieee.decode(rb,p=24,eb=8)
  pb=ieee.encode(F(n)*ratio);sp=int(ieee.decode(pb));qb=ieee.encode(F(sp)/ratio);rp=int(ieee.decode(qb))
  if sr==dr:rb=bits32(1);pb=qb=ieee.encode(n);sp=rp=n
  out=Out();status=f(bits32(sr),bits32(dr),n,C.byref(out));expected=(sp,rp,rb,pb,qb);actual=(out.sourceFrame,out.returnedOutputFrame,out.ratio,out.product,out.quotient)
  assert status==0 and expected==actual,(sr,dr,n,status,expected,actual)
  rows.append({'source_rate':sr,'output_rate':dr,'request':n,'source_frame':sp,'returned_frame':rp,'ratio_bits':f'{rb:08x}','product_bits':f'{pb:016x}','quotient_bits':f'{qb:016x}'})
invalid=[(0,bits32(48000),1),(0x7f800000,bits32(48000),1),(0x7fc00000,bits32(48000),1),(bits32(7999),bits32(48000),1),(bits32(192001),bits32(48000),1),(bits32(F(16001,2)),bits32(48000),1),(bits32(48000),bits32(48000),-1),(bits32(48000),bits32(48000),2**53+1)]
for a,b,n in invalid:
 out=Out();C.memset(C.byref(out),0xa5,C.sizeof(out));before=bytes(out);assert f(a,b,n,C.byref(out))==1 and bytes(out)==before
assert f(bits32(48000),bits32(48000),1,None)==1
# Test alternate rounding-mode rejection without touching the target.
process=C.CDLL(None);process.fegetround.restype=C.c_int;process.fesetround.argtypes=[C.c_int]
old=process.fegetround();assert old==0
try:
 assert process.fesetround(0x400000)==0
 out=Out();C.memset(C.byref(out),0xa5,C.sizeof(out));before=bytes(out);assert f(bits32(48000),bits32(44099),8192,C.byref(out))==2 and bytes(out)==before
finally:assert process.fesetround(old)==0
pin=lambda p:{'path':str(p.relative_to(R)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
report={'id':'ACCESSOR-SEEK-CANDIDATE-CONTROLS','passed':True,'target_execution_count':0,'method':'Separate Fraction IEEE nearest/ties-even quantization derives FDIV.S then FCVT.D, SCVTF/FMUL.D, FCVTZS64, SCVTF/FDIV.D, FCVTZS64; C output diagnostics compared exactly. Authored C compiled/executed only.','vectors':rows,'invalid_transactional_controls':len(invalid)+1,'FP_environment_transactional_controls':1,'inputs':[pin(H/'candidate/cpr_accessor_seek.c'),pin(H/'candidate/cpr_accessor_seek.h'),pin(p)],'compile_command':cmd,'limits':['Fixed stable positive integral binary32 rates and nonnegative requests<=2^53.','Successful numeric projection does not validate source IO, converter samples or hosted playback.']}
(H/'controls/seek-controls.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'passed':True,'exact_vectors':len(rows),'invalid_controls':len(invalid)+1,'fp_controls':1}))
