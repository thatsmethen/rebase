"""Compile/snapshot only our C reconstruction; proprietary target is never executed."""
from pathlib import Path
import subprocess,hashlib,json,shutil,ctypes
H=Path(__file__).resolve().parent;ROOT=H.parents[4];C=H/'candidate';C.mkdir(exist_ok=True)
source=ROOT/'Application/Sources/RebaseTimingDSP/native_rate_mode0.c';header=source.parent/'include/native_rate_mode0.h'
for p in [source,header]:shutil.copyfile(p,C/p.name)
cmd=['/usr/bin/clang','-O2','-ffp-contract=off','-Wall','-Wextra','-Werror','-dynamiclib','-I',str(C),str(C/source.name),'-o',str(C/'mode0.dylib')]
p=subprocess.run(cmd,text=True,capture_output=True);(C/'compile-output.txt').write_text(p.stdout+p.stderr);assert p.returncode==0
objcmd=['/Library/Developer/CommandLineTools/usr/bin/llvm-objdump','-d',str(C/'mode0.dylib')]
asm=subprocess.check_output(objcmd,text=True);(C/'optimized-disassembly.txt').write_text(asm)
assert 'fmadd\t'in asm and'fmul\t'in asm and'fcvt\ts'in asm
class S(ctypes.Structure):_fields_=[('step',ctypes.c_double),('phase',ctypes.c_double),('previous',ctypes.c_double*2),('src',ctypes.c_uint32),('dst',ctypes.c_uint32),('channels',ctypes.c_uint32),('reserved',ctypes.c_uint32)]
lib=ctypes.CDLL(str(C/'mode0.dylib'));lib.rb_native_mode0_init.argtypes=[ctypes.c_float,ctypes.c_float,ctypes.c_uint32,ctypes.POINTER(S)];lib.rb_native_mode0_count.argtypes=[ctypes.POINTER(S),ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)]
s=S();assert lib.rb_native_mode0_init(44100,48000,2,ctypes.byref(s))==0
rows=[]
for n,expected in [(0,0),(1,0),(2,2),(3,3),(147,159),(44100,47999),(1058400,1151999)]:
 out=ctypes.c_size_t();assert lib.rb_native_mode0_count(ctypes.byref(s),n,ctypes.byref(out))==0 and out.value==expected;rows.append(dict(input=n,output=out.value))
(C/'count-projection.json').write_text(json.dumps(dict(source_rate=44100,output_rate=48000,channels=2,step=s.step.hex(),reset_phase=s.phase.hex(),counts=rows,kind='Our reconstructed C count recurrence; not target execution'),indent=2)+'\n')
def ref(p):return dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
report=dict(compile_command=cmd,compile_returncode=p.returncode,disassembly_command=objcmd,source=[ref(source),ref(header)],binary=ref(C/'mode0.dylib'),optimized_assembly=ref(C/'optimized-disassembly.txt'),method='Compiled own reconstruction with contraction disabled; explicit fma is retained separately after a rounded multiply. Full arithmetic validation is in the independent oracle and tests.',cubase_execution=False,reconstruction_execution=True)
(C/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'source':report['source'],'projection':rows[-1]}))
