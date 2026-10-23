"""Bind final release observations, retained controls and unchanged QA packages."""
from pathlib import Path
from datetime import datetime,timezone
import importlib.util,json,re,hashlib,struct
H=Path(__file__).resolve().parent;R=H.parents[3]
spec=importlib.util.spec_from_file_location('custody',H.parent/'APP015/seal_application.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
def txt(n):return (H/('gui-'+n+'.txt')).read_text()
def rec(n):return c.record(H/('gui-'+n+'.txt'))
def time(n):
 m=re.search(r'(\d\d):(\d\d):(\d\d\.\d+) TEMPO',txt(n));assert m,n
 return int(m[1])*3600+int(m[2])*60+float(m[3])
def peaks(n):
 m=re.search(r'Details: Left ([0-9.]+), right ([0-9.]+)',txt(n));assert m,n
 return float(m[1]),float(m[2])
assert 'base rate at 32000 Hz with a rate factor of 1' in txt('import-review')
assert '32,000 Hz' in txt('v5-imported') and 'Media attached Synthetic.wav' in txt('v5-attached')
assert '32,000 Hz' in txt('v4-opened') and 'Saved project rate 44100 Hz' in txt('v4-saved-clock')
assert 'button Description: Play Event on Timeline' in txt('v4-saved-clock')
assert 0<time('v4-playing')<1.5 and peaks('v4-playing')==(0,0)
assert 1.5<time('v4-output')<23.5 and min(peaks('v4-output'))>0
assert 'audition paused' in txt('v4-paused') and peaks('v4-paused')==(0,0)
assert time('v4-resumed')>time('v4-paused') and min(peaks('v4-resumed'))>0
assert time('v4-ended')==23.5 and 'audition ended' in txt('v4-ended')
assert 'This project contains unresolved Cubase audio events' in txt('project-blocked')
assert '48,000 Hz' in txt('v5-edited-opened')
assert '48,000 Hz clock' in txt('v5-rebase-clock-rejected-final') and 'window exceeds the attached media' in txt('v5-rebase-clock-rejected-final')
assert 'button (disabled) Description: Play Event on Timeline' in txt('v5-rebase-clock-rejected-final')
assert 'Saved project rate 32000 Hz' in txt('v5-saved-clock-final')
assert 'saved offset 2.000000 s' in txt('v5-saved-clock-final')
assert 'button Description: Play Event on Timeline' in txt('v5-saved-clock-final')
assert 0<time('v5-playing')<1.5 and peaks('v5-playing')==(0,0)
assert time('v5-seek')==15.75 and 15.75<time('v5-seek-output')<23.5 and min(peaks('v5-seek-output'))>0
assert '32,000 Hz' in txt('v5-seek-output') and time('v5-ended')==23.5 and peaks('v5-ended')==(0,0)
assert 'project playback selected' in txt('v5-exited') and '48,000 Hz' in txt('v5-exited')
packages=[]
for name in ['gui-inputs.json','gui-v5-inputs.json']:
 rows=json.loads((H/name).read_text())['files']
 for row in rows:assert c.record(R/row['path'])==row
 packages+=rows
assert len(packages)==8
control=json.loads((H/'gui-source-inputs.json').read_text());c.check_pinned_records(control)
a=bytearray((R/control['prior']['path']).read_bytes());struct.pack_into('>f',a,control['mutation']['offset'],32000)
assert bytes(a)==(H/'gui-source-inputs/Saved32k.cpr').read_bytes()
old=json.loads((H/'gui-v5-before-rate-edit.json').read_text());new=json.loads((H/'Saved V5 QA.rebaseproj/Project.json').read_text())
assert old['sampleRate']==32000;old['sampleRate']=48000;assert old==new
report=json.loads((H/'Saved V5 QA.rebaseproj/Compatibility/CPR/ImportReport.json').read_text())
assert report['interpretationProfile']=='cpr-static-subset-v5' and report['recoveredProject']['sampleRate']==32000
release=json.loads((H/'release-build.json').read_text())['executable'];assert c.record(R/release['path'])==release
process=json.loads((H/'gui-process.json').read_text());assert process['executable']['sha256']==release['sha256']
groups=[
 ('new_import',['import-review','v5-imported','v5-attached'],'Final GUI imported the source-derived32k setup into V5, displayed32000Hz recovered configuration and attached matching self-authored PCM.'),
 ('historical_configuration',['v4-opened','v4-saved-clock'],'Historical V4 package retains32000Hz application rate while fresh saved configuration shows44100Hz and admits saved-clock audition.'),
 ('historical_transport',['v4-playing','v4-output','v4-paused','v4-resumed','v4-ended'],'Saved44100Hz audition has silent prefix, nonzero stereo engine peaks, pause/resume and natural23.5s completion.'),
 ('whole_project_guard',['project-blocked'],'Whole-project playback still rejects unresolved native events after source audition exit.'),
 ('edited_rate_admission',['v5-edited-opened','v5-rebase-clock-rejected-final','v5-saved-clock-final'],'Edited48000Hz application clock exceeds raw source capacity and is rejected; preserved32000Hz setup admits the same source window.'),
 ('saved_clock_seek_output',['v5-playing','v5-seek','v5-seek-output','v5-ended','v5-exited'],'Saved32000Hz mode preserves silent prefix and seek15.75s, produces nonzero stereo engine peaks, ends23.5s and restores48000Hz project transport.')]
value=dict(id='APP019-GUI',created_utc=datetime.now(timezone.utc).isoformat(),final_release=True,executable=release,
 groups_passed=len(groups),groups=[dict(name=n,result='passed',records=[rec(f) for f in files],observations=[o]) for n,files,o in groups],
 package_files_unchanged=len(packages),package_files=packages,source_controls=c.record(H/'gui-source-inputs.json'),
 screenshot=c.record(H/'gui-saved-clock.png'),process=c.record(H/'gui-process.json'),
 intermediate_observations=['Media-path keyboard submission repeatedly returned to a slash-only Go To field; reconnecting CUA and selecting the visible path row with a double-click completed attachment.',
 'Two rate-menu captures retained a selected menu before its dismissal; final-suffix captures record the completed states. One stale-element call failed during that transition without changing the app.',
 'The first V5 playback completed before an output capture; clicking the transport then restarted it, so gui-v5-paused.txt does not prove pause. Final seek-output and ended records establish the accepted V5 transport observations.'],
 limits=['All audio is self-authored synthetic PCM; source-derived CPR controls are not original project audio.',
 'Own-engine peaks and GUI observations are not DAC capture, latency certification, callback equivalence or Cubase runtime output.',
 'Only selected source-event playback is accepted; complete native contributors, routing, mixer, effects and automation remain unresolved.'])
with (H/'gui-observations.json').open('x') as f:json.dump(value,f,indent=2);f.write('\n')
print(json.dumps(dict(groups=len(groups),package_files=len(packages),executable=release)))
