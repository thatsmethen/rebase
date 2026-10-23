"""Bind observed final Rebase UI states and unchanged synthetic QA packages."""
from pathlib import Path
from datetime import datetime, timezone
import importlib.util, json, re
HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[3]
spec=importlib.util.spec_from_file_location('custody',HERE.parent/'APP015/seal_application.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
def text(name):return (HERE/('gui-final-'+name+'.txt')).read_text()
def file(name):return c.record(HERE/('gui-final-'+name+'.txt'))
def time(name):
    m=re.search(r'(\d\d):(\d\d):(\d\d\.\d+) TEMPO',text(name));assert m,name
    return int(m[1])*3600+int(m[2])*60+float(m[3])
def peaks(name):
    m=re.search(r'Details: Left ([0-9.]+), right ([0-9.]+)',text(name));assert m,name
    return float(m[1]),float(m[2])
assert 'saved offset 2.000000 s' in text('admitted')
assert '32,000 Hz clock without conversion' in text('admitted')
assert 'button Description: Play Event on Timeline' in text('admitted')
assert 0 < time('playing') < 1.5 and peaks('playing')==(0,0)
assert 1.5 < time('output') < 23.5 and min(peaks('output')) > 0
assert 'audition paused' in text('paused') and peaks('paused')==(0,0)
assert time('resumed') > time('paused') and min(peaks('resumed')) > 0
assert time('seek') == 15.75 and 15.75 < time('seek-playing') < 23.5
assert min(peaks('seek-playing')) > 0
assert time('ended')==23.5 and peaks('ended')==(0,0) and 'audition ended' in text('ended')
assert 'project playback selected' in text('exited') and 'SOURCE EVENT AUDITION' not in text('exited')
assert 'This project contains unresolved Cubase audio events' in text('project-blocked')
assert '48,000 Hz clock' in text('capacity-blocked') and 'window exceeds the attached media' in text('capacity-blocked')
assert 'button (disabled) Description: Play Event on Timeline' in text('capacity-blocked')
assert 'button Description: Play Event on Timeline' in text('original-rate-admitted')
baseline=[]
for name in ['gui-inputs.json','gui-capacity-inputs.json']:
    rows=json.loads((HERE/name).read_text())['files']
    for row in rows:assert c.record(ROOT/row['path'])==row
    baseline+=rows
assert len(baseline)==8
release=json.loads((HERE/'release-build.json').read_text())['executable']
assert c.record(ROOT/release['path'])==release
assert c.record(ROOT/'Application/dist/Rebase.app/Contents/MacOS/Rebase')['sha256']==release['sha256']
groups=[
    ('admission',['admitted'],'New menu choice admits a supplied32kHz clock, labels changed speed/pitch and unrecovered original project rate, and retains saved1.5s start/22s duration/2s offset.'),
    ('silent_prefix_and_output',['playing','output'],'At0.638s both engine peaks are zero; at12.138s stereo peaks are nonzero. These are own-engine buffer readings.'),
    ('pause_resume',['paused','resumed'],'Pause retains mode/position with zero peaks; resume advances and produces stereo peaks.'),
    ('seek_and_end',['seek','seek-playing','ended'],'Ruler seek sets15.750s; resumed output advances with stereo peaks; natural completion reaches23.500s and stops.'),
    ('exit_and_project_guard',['exited','project-blocked'],'Exit removes the event mode; ordinary project playback still rejects unresolved CPR events.'),
    ('capacity_and_original_rate',['capacity-blocked','original-rate-admitted'],'At48kHz the requested complete source window does not fit, so playback is disabled with reason; original-rate native timeline remains enabled.')]
record=dict(id='APP018-GUI',created_utc=datetime.now(timezone.utc).isoformat(),final_release=True,
    executable=release,groups_passed=len(groups),
    groups=[dict(name=name,status='passed',records=[file(f) for f in files],observations=[observation]) for name,files,observation in groups],
    package_files_unchanged=len(baseline),package_files=baseline,
    screenshot=c.record(HERE/'gui-final-project-clock.png'),process=c.record(HERE/'gui-final-process.json'),
    interrupted_attempts=['During final capacity rerun the CUA request timed out and reset its kernel; one subsequent getApp also timed out. Recovery found the existing open-file panel, then completed the final capacity/original-rate checks. No app/source repair or evidence overwrite.'],
    initial_build=dict(executable=c.record(HERE/'gui-initial-build-snapshot/Rebase.app/Contents/MacOS/Rebase'),
        scope='Earlier GUI captures without gui-final prefix observed the initial build before the media-offset caption was corrected to saved-offset. They are retained separately and are not final-release acceptance.'),
    limits=['Synthetic PCM in a source-derived CPR control; no original project audio is asserted.',
            'GUI observations and engine peaks are not exact sample comparisons, DAC capture, underrun/latency certification or Cubase runtime measurements.',
            'Supplied application integral project clock with factor1, one admitted event and complete source capacity. Whole native project/channel/device context remains incomplete.'])
with (HERE/'gui-observations.json').open('x') as f:json.dump(record,f,indent=2);f.write('\n')
print(json.dumps(dict(groups=len(groups),package_files=len(baseline),executable=release)))
