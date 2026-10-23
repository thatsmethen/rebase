#!/usr/bin/env python3
"""Authored comparison-gate controls. These are not Windows or CI observations."""
from pathlib import Path
import argparse, copy, hashlib, json, os, shutil, subprocess, sys

HERE = Path(__file__).resolve().parent
ROOT = next((p for p in HERE.parents if (p / ".git").exists()), None)
if ROOT is None:
    raise SystemExit("Run this instrument from its Git checkout")
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True, help="New output directory beneath this checkout's ignored .local directory")
parser.add_argument("--instrument", choices=("initial", "intermediate", "corrected"), default="corrected")
args = parser.parse_args()
OUT = (ROOT / args.output).resolve()
if (ROOT / ".local").resolve() not in OUT.parents:
    raise SystemExit("Output must remain below this checkout's ignored .local directory")
OUT.mkdir(parents=True, exist_ok=False)
SOURCE = HERE / "fixtures/helper-protocol.json"
snapshot = HERE / "instruments" / args.instrument
app = OUT / "instrument/Application"
(app / "scripts").mkdir(parents=True)
(app / "Examples/Rebase Preview.rebaseproj").mkdir(parents=True)
for name in ("compare-portable-renders.py", "windows_automation_gate.py", "example-render-lock.json"):
    shutil.copyfile(snapshot / name, app / "scripts" / name)
shutil.copyfile(snapshot / "Project.json", app / "Examples/Rebase Preview.rebaseproj/Project.json")
SCRIPT = app / "scripts/compare-portable-renders.py"
GATE = app / "scripts/windows_automation_gate.py"
lanes = [('Darwin','Debug'), ('Darwin','Release'), ('Windows','Debug'), ('Windows','Release')]
source_session = json.loads(SOURCE.read_text())
assert source_session['status'] == 'passed' and len(source_session['checks']) == 169
source_commit = subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip()
render_template = json.loads((HERE/'fixtures/example-render-template.json').read_text())
checks = []


def set_render(rows, key, value, all_lanes=False):
    for row in rows if all_lanes else rows[:1]: row['render'][key] = value


def set_automation(rows, key, value, all_lanes=False):
    for row in rows if all_lanes else rows[:1]:
        row['session']['automation'][key] = value
        row['lane']['automation_control'] = copy.deepcopy(row['session']['automation'])


def remove_automation(rows, key):
    del rows[0]['session']['automation'][key]
    rows[0]['lane']['automation_control'] = copy.deepcopy(rows[0]['session']['automation'])


def baseline():
    rows = []
    for system, configuration in lanes:
        render = copy.deepcopy(render_template)
        render.update(platform=system, configuration=configuration,
                      architecture='arm64' if system == 'Darwin' else 'AMD64', commit=source_commit,
                      scope='Authored comparison-gate control; not an executed platform lane')
        session = copy.deepcopy(source_session)
        lane = dict(schema='rebase.portable-ci.v1', status='passed', commit=source_commit,
                    platform=system, configuration=configuration, architecture=render['architecture'],
                    automation_control=copy.deepcopy(session['automation']),
                    scope='Authored comparison-gate control; copied macOS helper receipt, not a Windows run')
        rows.append(dict(render=render, lane=lane, session=session))
    return rows


def case(name, expect, mutate=lambda rows: None, files=lambda folder: None):
    folder = OUT/name
    folder.mkdir(exist_ok=False)
    rows = baseline()
    mutate(rows)
    for index, row in enumerate(rows):
        target=folder/'input'/f'lane-{index+1}'
        target.mkdir(parents=True)
        for key, filename in [('render','example-render.json'),('lane','conformance.json'),('session','session-protocol.json')]:
            (target/filename).write_text(json.dumps(row[key],indent=2)+'\n')
    files(folder)
    result = folder/'comparison-result.json'
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
    process=subprocess.run([sys.executable,str(SCRIPT.relative_to(ROOT)),'--input',str((folder/'input').relative_to(ROOT)),'--output',str(result.relative_to(ROOT))],
                           capture_output=True,text=True,env=env,timeout=30,cwd=ROOT)
    (folder/'process.log').write_text(process.stdout+process.stderr)
    report=json.loads(result.read_text()) if result.exists() else {}
    passed=process.returncode==0 and report.get('status')=='passed'
    rejected=process.returncode==1 and report.get('status')=='failed'
    matched=passed if expect=='accept' else rejected
    checks.append(dict(name=name,expected=expect,exit_code=process.returncode,
                       observed=report.get('status','missing-report'),expectation_matched=matched,
                       error=report.get('error'),result_sha256=hashlib.sha256(result.read_bytes()).hexdigest() if result.exists() else None))
    (folder/'authored-control.json').write_text(json.dumps(dict(evidence_class='authored-gate-control',
       platform_execution_claim=False,source_session=str(SOURCE.relative_to(ROOT)),expected=expect),indent=2)+'\n')


case('valid-four-lanes','accept')
case('missing-lane','reject',lambda r:r.pop())
case('duplicate-lane','reject',lambda r:r.__setitem__(3,copy.deepcopy(r[2])))
case('extra-lane','reject',lambda r:r.append(copy.deepcopy(r[0])))
for key,file in [('render','example-render.json'),('lane','conformance.json'),('session','session-protocol.json')]:
    case('malformed-'+key+'-json','reject',files=lambda p,f=file:(p/'input/lane-1'/f).write_text('{malformed'))
for filename in ('conformance.json','session-protocol.json'):
    case('missing-'+filename.replace('.json',''),'reject',files=lambda p,f=filename:(p/'input/lane-1'/f).unlink())
case('missing-render-field','reject',lambda r:r[0]['render'].pop('pcm_sha256'))
case('missing-automation','reject',lambda r:r[0]['session'].pop('automation'))
case('missing-lane-summary','reject',lambda r:r[0]['lane'].pop('automation_control'))
for kind in ('lane','session'):
    case('failed-'+kind+'-status','reject',lambda r,k=kind:r[0][k].__setitem__('status','failed'))
    case('missing-'+kind+'-status','reject',lambda r,k=kind:r[0][k].pop('status'))
case('source-commit-mismatch','reject',lambda r:r[0]['lane'].__setitem__('commit','0'*40))
case('source-platform-mismatch','reject',lambda r:r[0]['lane'].__setitem__('platform','Windows'))
case('source-configuration-mismatch','reject',lambda r:r[0]['lane'].__setitem__('configuration','Release'))
case('source-architecture-mismatch','reject',lambda r:r[0]['lane'].__setitem__('architecture','unrelated-architecture'))
case('edited-wav-divergence','reject',lambda r:set_automation(r,'edited_wav_sha256','a'*64))
case('edited-pcm-divergence','reject',lambda r:set_automation(r,'edited_pcm_sha256','b'*64))
case('restored-wav-divergence','reject',lambda r:set_automation(r,'restored_wav_sha256','c'*64))
case('summary-receipt-divergence','reject',lambda r:r[0]['lane']['automation_control'].__setitem__('mutation_count',11))
case('automation-gate-false','reject',lambda r:set_automation(r,'pan_edit_read_roundtrip',False))
case('automation-gate-missing','reject',lambda r:remove_automation(r,'pan_edit_read_roundtrip'))
case('automation-gate-numeric-true','reject',lambda r:set_automation(r,'pan_edit_read_roundtrip',1))
case('automation-malformed-hash','reject',lambda r:set_automation(r,'edited_wav_sha256','not-a-hash'))
case('automation-unchanged-render','reject',lambda r:set_automation(r,'edited_pcm_sha256',source_session['automation']['restored_pcm_sha256']))
case('automation-wrong-original-identity','reject',lambda r:set_automation(r,'original_track_id','00000000-0000-4000-8000-000000000001'))
case('automation-point-count-bool','reject',lambda r:set_automation(r,'original_point_count',True))
case('automation-missing-mutations','reject',lambda r:set_automation(r,'mutation_count',9))
case('automation-missing-invalid-controls','reject',lambda r:set_automation(r,'invalid_requests_checked',14))
case('original-lock-not-matched','reject',lambda r:set_render(r,'matches_predeclared_lock',False))
case('original-file-not-regular','reject',lambda r:set_render(r,'regular_file',False))
case('original-overwrite-unverified','reject',lambda r:set_render(r,'repeat_render_refused_without_modification',False))
for kind in ('render','lane','session'):
    case('unsupported-'+kind+'-schema','reject',lambda r,k=kind:r[0][k].__setitem__('schema','unsupported-schema'))
case('common-original-pcm-diverges-from-lock','reject',lambda r:set_render(r,'pcm_sha256','d'*64,True))
case('common-original-lock-digest-malformed','reject',lambda r:set_render(r,'expected_render_lock_sha256','not-a-hash',True))
case('common-original-frame-count-negative','reject',lambda r:set_render(r,'frames',-1,True))
case('common-source-identity-null','reject',lambda r:[(x['render'].__setitem__('commit',None),x['lane'].__setitem__('commit',None)) for x in r])
case('common-source-identity-malformed','reject',lambda r:[(x['render'].__setitem__('commit','not-a-commit'),x['lane'].__setitem__('commit','not-a-commit')) for x in r])


case('source-common-valid-sha-not-checkout','reject',lambda r:[(x['render'].__setitem__('commit','f'*40),x['lane'].__setitem__('commit','f'*40)) for x in r])
case('unsupported-matching-architecture','reject',lambda r:[(x['render'].__setitem__('architecture','unsupported'),x['lane'].__setitem__('architecture','unsupported')) for x in r])
case('session-original-wav-mismatch','reject',lambda r:r[0]['session'].__setitem__('wav_sha256','a'*64))
case('session-original-pcm-mismatch','reject',lambda r:r[0]['session'].__setitem__('pcm_sha256','b'*64))
case('session-original-frames-mismatch','reject',lambda r:r[0]['session'].__setitem__('frames',960001))
case('session-original-frames-bool','reject',lambda r:r[0]['session'].__setitem__('frames',True))
case('session-checks-empty','reject',lambda r:r[0]['session'].__setitem__('checks',[]))
case('session-checks-repeat-observation','accept',lambda r:r[0]['session']['checks'].append(r[0]['session']['checks'][0]))
case('session-checks-nonstring','reject',lambda r:r[0]['session']['checks'].append(7))
case('render-numeric-type-float','reject',lambda r:set_render(r,'bits_per_sample',32.0,True))
case('common-positive-frames-diverge','reject',lambda r:set_render(r,'frames',960001,True))
case('render-flag-numeric-true','reject',lambda r:set_render(r,'regular_file',1))
case('render-digest-uppercase','reject',lambda r:set_render(r,'pcm_sha256',render_template['pcm_sha256'].upper(),True))
case('lane-summary-gate-numeric-true','reject',lambda r:r[0]['lane']['automation_control'].__setitem__('tested',1))
case('common-wav-bytes-zero','reject',lambda r:set_render(r,'wav_bytes',0,True))
case('common-wav-bytes-too-small','reject',lambda r:set_render(r,'wav_bytes',100,True))
for kind in ('render','lane','session'):
    case('missing-'+kind+'-schema','reject',lambda r,k=kind:r[0][k].pop('schema'))
case('render-json-array','reject',files=lambda p:(p/'input/lane-1/example-render.json').write_text('[]'))
case('render-json-nonfinite','reject',lambda r:r[0]['render'].__setitem__('unsupported_numeric',float('nan')))
case('render-json-duplicate-key','reject',files=lambda p:(p/'input/lane-1/example-render.json').write_text('{"schema":"unsupported-schema",'+(p/'input/lane-1/example-render.json').read_text()[1:]))

summary=dict(schema='rebase.authored-comparison-gate-controls.v1',
    evidence_class='authored-gate-control',platform_execution_claim=False,
    scope='Four labelled lane records are constructed from one actual macOS helper receipt. No Windows execution is implied.',
    source_session={'path':str(SOURCE.relative_to(ROOT)),'sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest()},
    instrument_sources=[{'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in (SCRIPT,GATE)],
    cases=len(checks),matched=sum(r['expectation_matched'] for r in checks),
    unexpected=[r for r in checks if not r['expectation_matched']],checks=checks)
(OUT/'results.json').write_text(json.dumps(summary,indent=2)+'\n')
(OUT/'README.md').write_text('# Authored comparison-gate controls\n\nThese are instrument controls, not platform runs. Four lane labels are constructed from one actual macOS Release helper receipt to test comparison admission and rejection. Each case preserves its authored inputs and comparison output. No synthetic result establishes Windows execution, cross-platform parity or reference fidelity.\n')
print(json.dumps({key:summary[key] for key in ('cases','matched','unexpected')},indent=2))

raise SystemExit(0 if all(item['expectation_matched'] for item in checks) else 1)
