from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import plistlib
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT/".local-validation"
APP = ROOT/"Application"


def record(path):
    if path.is_symlink():
        return dict(path=str(path.relative_to(ROOT)), symlink=os.readlink(path))
    raw = path.read_bytes()
    return dict(path=str(path.relative_to(ROOT)),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def write(name,value):
    with (OUT/name).open("x") as f: json.dump(value,f,indent=2);f.write("\n")
    return record(OUT/name)


def source():
    paths = [APP/name for name in ["Package.swift","Package.resolved","build-app.sh","test-app.sh"]]
    for name in ["Sources","Tests","ThirdParty"]:
        paths += [p for p in (APP/name).rglob("*") if p.is_file() or p.is_symlink()]
    return [record(p) for p in sorted(paths)]


def run(name,command):
    started = datetime.now(timezone.utc).isoformat();clock=time.monotonic()
    with (OUT/(name+".log")).open("x") as f:
        result=subprocess.run(command,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
    value=dict(command=command,started_utc=started,elapsed_seconds=time.monotonic()-clock,
        exit_code=result.returncode,log=record(OUT/(name+".log")))
    write(name+".json",value)
    assert result.returncode==0,value
    return value


before=source();before_pin=write("source-before-final-02.json",dict(files=before))
debug=APP/".build-tests/arm64-apple-macosx/debug"
binaries=[debug/"Rebase",debug/"RebasePackageTests.xctest/Contents/MacOS/RebasePackageTests"]
fixed_before=[record(p) for p in binaries]
results=[]
for name,args,expected_skips in [
    ("private-tests-final-02",["--with-research","/workspace/rebase"],0),
    ("public-tests-final-02",["--public"],116)]:
    result=run(name,["sh","Application/Tests/run-tests.sh",*args,"--skip-build"])
    text=(OUT/(name+".log")).read_text()
    matches=re.findall(r'Test run with (\d+) tests in (\d+) suites passed',text)
    assert matches==[("332","52")]
    skipped=len(re.findall(r'Test .+ skipped:',text))
    assert skipped==expected_skips
    assert source()==before and [record(p) for p in binaries]==fixed_before
    results.append(dict(lane=name,discovered_tests=332,suites=52,skipped=skipped,
        executed_tests=332-skipped,record=record(OUT/(name+".json"))))
release=run("release-final-02",["sh","Application/build-app.sh"])
assert source()==before and [record(p) for p in binaries]==fixed_before
bundle=APP/"dist/Rebase.app";executable=bundle/"Contents/MacOS/Rebase"
info=plistlib.loads((bundle/"Contents/Info.plist").read_bytes())
assert info["CFBundleShortVersionString"]=="0.21.0" and info["CFBundleVersion"]=="21"
signature=run("signature-final-02",["codesign","--verify","--strict","--deep",str(bundle)])
dependencies=run("dependencies-final-02",["otool","-L",str(executable)])
rpaths=run("rpaths-final-02",["otool","-l",str(executable)])
for path in re.findall(r'cmd LC_RPATH\s+cmdsize \d+\s+path (.*?) \(offset',(OUT/"rpaths-final-02.log").read_text()):
    assert not path.startswith("/") or path.startswith(("/usr/lib/","/System/Library/")),path
assert "@rpath/libsoxr.0.dylib" in (OUT/"dependencies-final-02.log").read_text()
after_pin=write("source-after-final-02.json",dict(files=source()))
files=[record(p) for p in sorted(bundle.rglob("*")) if p.is_file() or p.is_symlink()]
bundle_pin=write("bundle-final-02.json",dict(files=files))
result=dict(status="passed",scope="Prepared application code: fixed-binary public/private test lanes and separately signed release. No GUI or reference runtime comparison.",
    source_entries=len(before),source_before=before_pin,source_after=after_pin,
    source_unchanged=True,fixed_binaries=fixed_before,binaries_unchanged=True,test_lanes=results,
    version=info["CFBundleShortVersionString"],build=info["CFBundleVersion"],executable=record(executable),
    release_record=record(OUT/"release-final-02.json"),bundle_manifest=bundle_pin,
    signatures=record(OUT/"signature-final-02.json"),dependencies=record(OUT/"dependencies-final-02.json"),
    rpaths=record(OUT/"rpaths-final-02.json"),target_executed=False,gui_observed=False)
print(json.dumps(write("validation-final-02.json",result)))
