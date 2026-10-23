"""Own-kernel API/error/count controls, separate from independent IEEE oracle."""
from pathlib import Path
import ctypes as c,struct,json,hashlib
H=Path(__file__).resolve().parent;C=H/'candidate';ROOT=H.parents[4]
class S(c.Structure):_fields_=[('step',c.c_double),('phase',c.c_double),('history',c.c_double*2),('source',c.c_uint32),('output',c.c_uint32),('channels',c.c_uint32),('pending',c.c_uint32)]
l=c.CDLL(str(C/'mode0-down.dylib'));sp=c.POINTER(S);fp=c.POINTER(c.c_float);np=c.POINTER(c.c_size_t)
l.rb_native_mode0_down_init.argtypes=[c.c_float,c.c_float,c.c_uint32,sp]
l.rb_native_mode0_down_reset.argtypes=[sp]
l.rb_native_mode0_down_count.argtypes=[sp,c.c_size_t,c.c_uint32,c.c_uint32,np]
l.rb_native_mode0_down_count_blocks.argtypes=[sp,c.c_size_t,c.c_size_t,c.c_uint32,np]
l.rb_native_mode0_down_process.argtypes=[sp,fp,c.c_size_t,fp,c.c_size_t,c.c_uint32,c.c_uint32,np]
l.rb_native_mode0_down_next_block.argtypes=[c.c_size_t,c.c_size_t];l.rb_native_mode0_down_next_block.restype=c.c_size_t
passed=[]
def check(name,condition):assert condition,name;passed.append(name)
def state(a=48000,b=44100,ch=2):
 s=S();assert l.rb_native_mode0_down_init(a,b,ch,c.byref(s))==0;return s
arena=(c.c_float*128)(*[.25]*128);source=c.cast(arena,fp);dest=c.cast(c.addressof(arena)+64*4,fp)
def process(s,n,cap=32,layout=1,flush=0,src=source,dst=dest):
 out=c.c_size_t(8675309);before=(bytes(s),bytes(arena),out.value)
 r=l.rb_native_mode0_down_process(c.byref(s),src,n,dst,cap,layout,flush,c.byref(out))
 return r,out.value,before,(bytes(s),bytes(arena),out.value)
s=state();r,n,b,a=process(s,12,cap=0);check('insufficient_capacity_is_transactional',r==2 and b==a)
s=state();source[9]=float('nan');r,n,b,a=process(s,12);check('late_nan_is_transactional',r==3 and b==a);source[9]=.25
source[9]=float('inf');s=state();r,n,b,a=process(s,12);check('late_infinity_is_transactional',r==3 and b==a);source[9]=.25
source[9]=2**-149;s=state();r,n,b,a=process(s,12);check('subnormal_input_is_transactional',r==3 and b==a);source[9]=.25
s=state();r,n,b,a=process(s,12,dst=source);check('overlap_is_transactional',r==1 and b==a)
s=state();r,n,b,a=process(s,12,layout=0);check('wrong_actual_layout_is_transactional',r==1 and b==a)
for layout,flush in [(2,0),(1,2)]:
 s=state();r,n,b,a=process(s,12,layout=layout,flush=flush);check('reject_flags_'+str((layout,flush)),r==1 and b==a)
for rate in [(44100,48000),(192001,48000),(48000,7999),(float('nan'),44100)]:
 s=state();before=bytes(s);r=l.rb_native_mode0_down_init(*rate,2,c.byref(s));check('reject_rate_'+str(rate),r==1 and bytes(s)==before)
for ch in [0,3,64]:
 s=state();before=bytes(s);r=l.rb_native_mode0_down_init(48000,44100,ch,c.byref(s));check('reject_channels_'+str(ch),r==1 and bytes(s)==before)
for a,b,ch in [(48000,44100,1),(48000,44100,2),(48000,48000,1),(192000,8000,2)]:
 s=state(a,b,ch);before=bytes(s);r,n,x,y=process(s,0,flush=1);check('zero_flush_noop_'+str((a,b,ch)),r==0 and n==0 and bytes(s)==before)
 s=state(a,b,ch);r,n,x,y=process(s,12);check('positive_call_'+str((a,b,ch)),r==0)
 check('reset_'+str((a,b,ch)),l.rb_native_mode0_down_reset(c.byref(s))==0 and bytes(s)==bytes(state(a,b,ch)))
for ch in [1,2]:
 s=state(48000,32000,ch);s.phase=.5;s.pending=1;s.history[0]=.25;s.history[1]=.25
 r,n,b,a=process(s,1);check('unsafe_singleton_process_'+str(ch),r==4 and b==a)
 out=c.c_size_t(555);before=bytes(s);r=l.rb_native_mode0_down_count(c.byref(s),1,1,0,c.byref(out));check('unsafe_singleton_count_'+str(ch),r==4 and out.value==555 and bytes(s)==before)
projection=[]
for a,b,n in [(44100,32000,1058400),(44100,22050,1058400),(44100,11025,1058400),(48000,44100,1151999),(48000,32000,16385),(48000,48000,100)]:
 s=state(a,b);out=c.c_size_t();before=bytes(s);r=l.rb_native_mode0_down_count_blocks(c.byref(s),n,8192,1,c.byref(out));check('count_blocks_'+str((a,b,n)),r==0 and bytes(s)==before)
 projection.append(dict(source_rate=a,output_rate=b,input_frames=n,output_frames=out.value,layout='above',input_limit=8192))
check('partition_8193',l.rb_native_mode0_down_next_block(8193,8192)==8191)
check('partition_tail2',l.rb_native_mode0_down_next_block(2,8192)==2)
check('partition_invalid2',l.rb_native_mode0_down_next_block(100,2)==0)
s=state();out=c.c_size_t(31);before=bytes(s);check('aggregate_reject_bad_limit',l.rb_native_mode0_down_count_blocks(c.byref(s),100,2,1,c.byref(out))==1 and out.value==31 and bytes(s)==before)
r=dict(kind='Candidate defensive wrapper/count controls; not independent arithmetic oracle or target comparison',target_execution=False,reconstruction_execution=True,passed=len(passed),controls=passed,projections=projection,kernel_sha256=hashlib.sha256((C/'native_rate_mode0_down.c').read_bytes()).hexdigest(),binary_sha256=hashlib.sha256((C/'mode0-down.dylib').read_bytes()).hexdigest())
(C/'controls.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'passed':len(passed),'projections':projection},indent=2))
