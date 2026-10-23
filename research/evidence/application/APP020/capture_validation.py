"""Build, test fixed binaries, and package with before/after source custody."""
from pathlib import Path
from datetime import datetime, timezone
import importlib.util, json, re, shutil, subprocess, time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
spec = importlib.util.spec_from_file_location('prior_custody', HERE.parent/'APP015/seal_application.py')
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
def write(name, value):
    with (HERE/name).open('x') as f: json.dump(value, f, indent=2); f.write('\n')
    return c.record(HERE/name)
def inventory(): return [c.record(p) for p in c.application_source_entries()]
def run(name, command):
    start = datetime.now(timezone.utc).isoformat(); clock = time.monotonic()
    with (HERE/(name+'.log')).open('x') as log:
        result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    record = dict(command=command, started_utc=start, elapsed_seconds=time.monotonic()-clock,
                  exit_code=result.returncode, log=c.record(HERE/(name+'.log')))
    write(name+'.json', record)
    assert result.returncode == 0, record
    return record

before = inventory(); write('test-source-before.json', dict(files=before))
# Explicit build/list phase separates compilation from the fixed-binary run.
run('test-build', ['sh', 'Application/test-app.sh', '--list-tests'])
assert inventory() == before
debug = ROOT/'Application/.build-tests/arm64-apple-macosx/debug'
binaries = [debug/'Rebase', debug/'RebasePackageTests.xctest/Contents/MacOS/RebasePackageTests']
snapshot = HERE/'test-build-snapshot'; snapshot.mkdir()
pre = [c.record(p) for p in binaries]
saved = []
for p in binaries:
    shutil.copy2(p, snapshot/p.name)
    assert c.record(snapshot/p.name)['sha256'] == c.record(p)['sha256']
    saved.append(dict(observed_original_path=str(p.relative_to(ROOT)), snapshot=c.record(snapshot/p.name)))
tests = run('core-tests', ['sh', 'Application/test-app.sh', '--skip-build'])
post = [c.record(p) for p in binaries]
after = inventory(); write('test-source-after.json', dict(files=after))
matches = re.findall(r'Test run with (\d+) tests in (\d+) suites passed', (HERE/'core-tests.log').read_text())
record = dict(**tests, tests=int(matches[-1][0]) if matches else None,
    suites=int(matches[-1][1]) if matches else None, source_unchanged=before==after,
    binaries_unchanged=pre==post, fixed_binaries=saved,
    before=c.record(HERE/'test-source-before.json'), after=c.record(HERE/'test-source-after.json'),
    scope='Own implementation tests on pre/post-identical debug binaries after a separate build/list phase. No Cubase runtime comparison.')
write('core-test-run.json', record)
assert before == after and pre == post and len(matches)==1, record
release = run('final-build-release', ['sh', 'Application/build-app.sh'])
assert inventory() == before
shutil.copytree(ROOT/'Application/dist/Rebase.app', HERE/'final-build-snapshot/Rebase.app', symlinks=True)
executable = HERE/'final-build-snapshot/Rebase.app/Contents/MacOS/Rebase'
assert c.record(executable)['sha256'] == c.record(ROOT/'Application/dist/Rebase.app/Contents/MacOS/Rebase')['sha256']
write('release-build.json', dict(**release, source_unchanged=True,
    source_inventory=c.record(HERE/'test-source-before.json'), executable=c.record(executable)))
print(json.dumps(dict(tests=record['tests'], suites=record['suites'], source_files=len(before), executable=c.record(executable))))
