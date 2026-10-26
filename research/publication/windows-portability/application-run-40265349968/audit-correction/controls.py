import copy,hashlib,importlib.util,json,subprocess,os
from pathlib import Path
ROOT=Path.cwd();HERE=Path(__file__).resolve().parent
P=ROOT/'.local/work/rebase-source-stream-20261024/package-review/audit-v3/audit_context.py'
spec=importlib.util.spec_from_file_location('audit_context_controls',P);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
rows=[{'name':'example-render','exit_code':0},{'name':'example-overwrite-refusal','exit_code':1},{'name':'tests','exit_code':0}]
controls=[]
def run(name,value,accept):
 try:m.validate_shared_command_exits(value);actual=True
 except ValueError:actual=False
 assert actual==accept,name
 controls.append({'name':name,'accepted':actual,'expected_accept':accept,'passed':True})
run('explicit-negative-control-accepted',rows,True)
run('missing-overwrite-refusal-rejected',[rows[0],rows[2]],False)
x=copy.deepcopy(rows);x[1]['exit_code']=0;run('successful-overwrite-rejected',x,False)
x=copy.deepcopy(rows);x[2]['exit_code']=1;run('unexpected-failing-test-rejected',x,False)
x=copy.deepcopy(rows);x[1]['exit_code']=2;run('wrong-refusal-exit-rejected',x,False)
x=copy.deepcopy(rows);x[1]['exit_code']=True;run('boolean-exit-rejected',x,False)
run('duplicate-refusal-rejected',rows+[rows[1]],False)
run('empty-commands-rejected',[],False)
real=json.loads((HERE.parent/'evidence/shared/conformance.json').read_bytes())
run('actual-committed-run-exits-accepted',real['commands'],True)
env=dict(os.environ,GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',TZ='UTC')
source=subprocess.check_output(['git','show','2934b9a0b6e96a5b3bd654a3e6a4fb00abe64e31:Application/scripts/run-portable-ci.py'],env=env)
assert b'"example-overwrite-refusal", expected_exit_codes=(1,)' in source
report={'schema':'rebase.private-audit-correction-controls.v1','evidence_class':'authored-exit-validation-controls-with-read-only-actual-receipt','source_commit':'2934b9a0b6e96a5b3bd654a3e6a4fb00abe64e31','controls':controls,'control_count':len(controls),'run_portable_ci_sha256':hashlib.sha256(source).hexdigest(),'audit_context_sha256':hashlib.sha256(P.read_bytes()).hexdigest(),'actual_native_execution':False,'actual_package_accepted':False}
(HERE/'observation.json').write_bytes(json.dumps(report,indent=2).encode()+b'\n')
print(json.dumps({'passed':len(controls),'source_commit':report['source_commit']}))
