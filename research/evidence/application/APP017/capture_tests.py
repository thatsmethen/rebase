"""Run the full application suite with before/after source custody."""
from pathlib import Path
from datetime import datetime,timezone
import importlib.util,json,re,subprocess,time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
spec=importlib.util.spec_from_file_location('app015_custody',HERE.parent/'APP015/seal_application.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
def write(name,value):
    with (HERE/name).open('x') as f:json.dump(value,f,indent=2);f.write('\n')
def inventory():return [c.record(p) for p in c.application_source_entries()]

for n in ['core-tests-first.log','core-test-run.json','test-source-before.json','test-source-after.json']:
    assert not (HERE/n).exists(),n
before=inventory();write('test-source-before.json',dict(files=before))
started=datetime.now(timezone.utc).isoformat();clock=time.monotonic()
command=['sh','Application/test-app.sh']
with (HERE/'core-tests-first.log').open('x') as out:
    result=subprocess.run(command,cwd=ROOT,stdout=out,stderr=subprocess.STDOUT)
after=inventory();write('test-source-after.json',dict(files=after))
text=(HERE/'core-tests-first.log').read_text()
passed=re.findall(r'Test run with (\d+) tests in (\d+) suites passed',text)
record=dict(command=command,started_utc=started,elapsed_seconds=time.monotonic()-clock,
            exit_code=result.returncode,source_unchanged=before==after,
            tests=int(passed[-1][0]) if passed else None,suites=int(passed[-1][1]) if passed else None,
            log=c.record(HERE/'core-tests-first.log'),
            before=c.record(HERE/'test-source-before.json'),after=c.record(HERE/'test-source-after.json'),
            scope='Own application implementation tests and linked debug app; no new packaged GUI release or Cubase runtime comparison.')
write('core-test-run.json',record)
assert result.returncode==0 and before==after and passed,record
print(json.dumps(record))
