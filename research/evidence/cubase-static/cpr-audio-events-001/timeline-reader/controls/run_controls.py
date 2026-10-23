from pathlib import Path
import subprocess,json,hashlib
H=Path(__file__).resolve().parent;R=H.parents[5]
source=R/'Application/Sources/RebaseTimingDSP/cpr_timeline_reader.c'
header=R/'Application/Sources/RebaseTimingDSP/include/cpr_timeline_reader.h'
exe=H/'author-controls-ubsan'
command=['clang','-std=c11','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off','-fsanitize=undefined','-fno-sanitize-recover=all','-I',str(header.parent),str(source),str(H/'author_controls.c'),'-o',str(exe)]
build=subprocess.run(command,capture_output=True,text=True)
(H/'compile.log').write_text(build.stdout+build.stderr);assert build.returncode==0
run=subprocess.run([str(exe)],capture_output=True,text=True)
(H/'run.log').write_text(run.stdout+run.stderr);assert run.returncode==0
pin=lambda p:dict(path=str(p.relative_to(R)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
result=dict(passed=True,proprietary_execution=False,controls=16,compiler=subprocess.check_output(['clang','--version'],text=True),command=command,compile_exit=build.returncode,run_exit=run.returncode,inputs=[pin(p)for p in(source,header,H/'author_controls.c')],logs=[pin(p)for p in(H/'compile.log',H/'run.log')],scope='Hand-derived simple controls and defensive bounds; independent IEEE oracle is separate.')
(H/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(run.stdout,end='')
