"""Own reconstructed wrapper only; fake backend, no target/library execution."""
from pathlib import Path
import ctypes as C,json,subprocess,hashlib
H=Path(__file__).resolve().parent;R=H.parents[4];D=H/'candidate';D.mkdir(exist_ok=True)
lib=D/'libmode2-controls.dylib'
cmd=['clang','-dynamiclib','-O2','-std=c11','-Wall','-Wextra','-Werror','-ffp-contract=off','-I',str(R/'Application/Sources/RebaseTimingDSP/include'),str(R/'Application/Sources/RebaseTimingDSP/native_rate_mode2.c'),'-o',str(lib)]
subprocess.run(cmd,check=True)
P=C.c_void_p;SZ=C.c_size_t;U=C.c_uint32;F=C.c_float
CREATE=C.CFUNCTYPE(C.c_int,P,C.c_double,C.c_double,U,C.POINTER(P));PROCESS=C.CFUNCTYPE(C.c_int,P,C.POINTER(F),SZ,C.POINTER(SZ),C.POINTER(F),SZ,C.POINTER(SZ));DESTROY=C.CFUNCTYPE(None,P)
class Backend(C.Structure):_fields_=[('context',P),('create',CREATE),('process',PROCESS),('destroy',DESTROY)]
class Snapshot(C.Structure):_fields_=[('ratio',C.c_double),('ideal',C.c_double)]+[(n,C.c_uint64)for n in ['input','visible','returned','calls','used','produced']]+[(n,U)for n in ['channels','delay','discard','icap','ocap','iend','iconsumed','pending','oread','oend','finished','failed']]
a=C.CDLL(str(lib));a.rb_native_mode2_create.argtypes=[C.c_double,C.c_double,U,Backend,C.POINTER(P)];a.rb_native_mode2_destroy.argtypes=[P];a.rb_native_mode2_snapshot.argtypes=[P,C.POINTER(Snapshot)];a.rb_native_mode2_count.argtypes=[P,SZ,U,C.POINTER(SZ)];a.rb_native_mode2_count_blocks.argtypes=[P,SZ,SZ,C.POINTER(SZ)];a.rb_native_mode2_process.argtypes=[P,C.POINTER(F),SZ,C.POINTER(F),SZ,U,C.POINTER(SZ)]
class Spy:
 def __init__(self,ch,fail=False):
  self.ch=ch;self.fail=fail;self.created=0;self.destroyed=0;self.offers=[];self.offset=0
  def create(_,rin,rout,ch,handle):self.created+=1;handle[0]=P(0x1234);return 0
  def process(_,src,n,used,dst,cap,produced):
   self.offers.append((bool(src),n,cap))
   if self.fail:return 9
   used[0]=n if src else 0;produced[0]=cap
   for i in range(cap*ch):dst[i]=((self.offset+i)%257-128)/256
   self.offset+=cap*ch;return 0
  def destroy(_):self.destroyed+=1
  self.cb=(CREATE(create),PROCESS(process),DESTROY(destroy));self.backend=Backend(None,*self.cb)
 def state(self,rin,rout):
  state=P();assert a.rb_native_mode2_create(rin,rout,self.ch,self.backend,C.byref(state))==0;return state
 def snap(self,state):
  s=Snapshot();assert a.rb_native_mode2_snapshot(state,C.byref(s))==0;return bytes(s)
controls=[]
for rin,rout in [(44100,48000),(48000,44100),(44100,44100),(8000,192000),(192000,8000)]:
 for ch in [1,2]:
  for total,block in [(1,1),(4097,1024),(65537,65408),(100000,8192)]:
   spy=Spy(ch);state=spy.state(rin,rout);pred=SZ(123);before=spy.snap(state)
   assert a.rb_native_mode2_count_blocks(state,total,block,C.byref(pred))==0 and spy.snap(state)==before and not spy.offers
   remain=total;returned=0
   while remain:
    n=min(remain,block);final=n==remain;count=SZ(999)
    assert a.rb_native_mode2_count(state,n,final,C.byref(count))==0
    src=(F*(n*ch))(*[((i%17)-8)/16 for i in range(n*ch)]);out=(F*max(1,count.value*ch))();got=SZ(998)
    assert a.rb_native_mode2_process(state,src,n,out,count.value,final,C.byref(got))==0
    assert got.value==count.value;returned+=got.value;remain-=n
   assert returned==pred.value
   closed=spy.snap(state);bad=SZ(99);assert a.rb_native_mode2_count(state,1,0,C.byref(bad))==5 and bad.value==99
   assert spy.snap(state)==closed;a.rb_native_mode2_destroy(state);assert spy.created==spy.destroyed==1
   controls.append(dict(rin=rin,rout=rout,channels=ch,input=total,block=block,returned=returned,backend_calls=len(spy.offers)))
spy=Spy(2);state=spy.state(44100,48000);initial=spy.snap(state);src=(F*200)(*([.25]*200));out=(F*32)(*([.75]*32));got=SZ(99)
assert a.rb_native_mode2_process(state,src,100,out,16,0,C.byref(got))==0 # initial discard; no visible output
state2=spy.state(44100,48000);before=spy.snap(state2);bad=(F*2)(float('nan'),0)
assert a.rb_native_mode2_process(state2,bad,1,out,16,0,C.byref(got))==3 and spy.snap(state2)==before
assert a.rb_native_mode2_process(state2,None,0,out,16,0,C.byref(got))==1
assert a.rb_native_mode2_count(state2,65409,0,C.byref(got))==1
a.rb_native_mode2_destroy(state);a.rb_native_mode2_destroy(state2)
spy=Spy(1,True);state=spy.state(44100,48000);src=(F*1)(.5);out=(F*8)(*([.75]*8));got=SZ(77)
assert a.rb_native_mode2_process(state,src,1,out,8,0,C.byref(got))==4 and got.value==77 and list(out)==[.75]*8
s=Snapshot();a.rb_native_mode2_snapshot(state,C.byref(s));assert s.failed==1 and a.rb_native_mode2_count(state,1,0,C.byref(got))==5
a.rb_native_mode2_destroy(state);assert spy.destroyed==1
report={'scope':'Own reconstructed C only with synthetic callbacks; no public SoXR or proprietary execution. Counts here are self-consistency checks, independent native numerical oracle is separate.','compiler_command':cmd,'source_sha256':hashlib.sha256((R/'Application/Sources/RebaseTimingDSP/native_rate_mode2.c').read_bytes()).hexdigest(),'controls':controls,'additional_checks':['query state unchanged/no backend calls','finished rejection preserves result','invalid samples preserve usable state','zero nonterminal and oversized blocks rejected','backend error poisons state/output and result unchanged','owned handle destroyed exactly once'],'passed':True}
(D/'controls.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'passed':True,'stream_cases':len(controls),'additional_groups':len(report['additional_checks'])}))
