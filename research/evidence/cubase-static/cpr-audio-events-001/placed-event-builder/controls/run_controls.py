from pathlib import Path
import json,subprocess,hashlib
H=Path(__file__).resolve().parent;R=H.parents[5]
C=R/'Application/Sources/RebaseTimingDSP'
def pin(p):return {'path':str(p.relative_to(R)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
commands=[];counts=[]
for name,flags in [('optimized',['-O2']),('ubsan',['-O1','-g','-fsanitize=undefined','-fno-sanitize-recover=all'])]:
 cmd=['/usr/bin/clang','-std=c11','-Wall','-Wextra','-Werror','-ffp-contract=off','-fno-fast-math',*flags,'-I',str(C/'include'),str(C/'cpr_timeline_builder.c'),str(H/'control.c'),'-o',str(H/name)]
 result=subprocess.run(cmd,text=True,capture_output=True)
 (H/(name+'-compile.log')).write_text(result.stdout+result.stderr);assert result.returncode==0
 run=subprocess.run([str(H/name)],text=True,capture_output=True)
 (H/(name+'-run.log')).write_text(run.stdout+run.stderr);assert run.returncode==0
 value=json.loads(run.stdout);assert value['passed'];counts.append(value['controls']);commands.append(cmd)
assert counts[0]==counts[1]
doc={'passed':True,'controls':counts[0],'commands':commands,'proprietary_target_executions':0,
 'inputs':[pin(p)for p in[C/'cpr_timeline_builder.c',C/'include/cpr_timeline_builder.h',H/'control.c',H/'run_controls.py']],
 'logs':[pin(p)for p in sorted(H.glob('*.log'))],
 'limits':['Hand-computable author controls, not an independent native behavioral oracle.','UBSan execution covers own reconstructed helper only.']}
(H/'result.json').write_text(json.dumps(doc,indent=2)+'\n');print(json.dumps({'passed':True,'controls':counts[0]}))
