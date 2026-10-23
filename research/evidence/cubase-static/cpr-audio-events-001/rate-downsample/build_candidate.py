"""Compile and inspect only our reconstruction; no proprietary code execution."""
from pathlib import Path
import subprocess,hashlib,json,shutil
H=Path(__file__).resolve().parent;ROOT=H.parents[4];C=H/'candidate';C.mkdir(exist_ok=True)
source=ROOT/'Application/Sources/RebaseTimingDSP/native_rate_mode0_down.c';header=source.parent/'include/native_rate_mode0_down.h'
for p in [source,header]:shutil.copyfile(p,C/p.name)
cmd=['/usr/bin/clang','-std=c11','-O2','-fno-fast-math','-ffp-contract=off','-Wall','-Wextra','-Werror','-dynamiclib','-I',str(C),str(C/source.name),'-o',str(C/'mode0-down.dylib')]
p=subprocess.run(cmd,text=True,capture_output=True);(C/'compile-output.txt').write_text(p.stdout+p.stderr);assert p.returncode==0
objcmd=['/Library/Developer/CommandLineTools/usr/bin/llvm-objdump','-d',str(C/'mode0-down.dylib')]
asm=subprocess.check_output(objcmd,text=True);(C/'optimized-disassembly.txt').write_text(asm)
assert 'fmadd\t'in asm and'fmul\t'in asm and'fcvt\ts'in asm
ref=lambda p:dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
r=dict(compile_command=cmd,compile_returncode=p.returncode,disassembly_command=objcmd,source=[ref(source),ref(header)],binary=ref(C/'mode0-down.dylib'),optimized_assembly=ref(C/'optimized-disassembly.txt'),method='Explicit binary64 fma after separately rounded arithmetic. Compiler contraction disabled. State and sample validation remain part of our defensive wrapper, not target behavior.',target_execution=False,reconstruction_execution=False)
(C/'build.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r['source']))
