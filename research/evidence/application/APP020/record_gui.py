"""Bind final release transport observations to retained synthetic controls."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, re

H = Path(__file__).resolve().parent
R = H.parents[3]
def pin(p):
    b = p.read_bytes()
    return dict(path=str(p.relative_to(R)), bytes=len(b), sha256=hashlib.sha256(b).hexdigest())
def text(n): return (H / ('gui-' + n + '.txt')).read_text()
def time(n):
    m = re.search(r'(\d\d):(\d\d):(\d\d\.\d+) TEMPO', text(n)); assert m, n
    return int(m[1])*3600 + int(m[2])*60 + float(m[3])
def peaks(n):
    m = re.search(r'Details: Left ([0-9.]+), right ([0-9.]+)', text(n)); assert m, n
    return float(m[1]), float(m[2])
def positive(n, start, end):
    assert start < time(n) < end and min(peaks(n)) > 0, n
def ended(n, end):
    assert time(n) == end and peaks(n) == (0,0) and 'Source track audition ended' in text(n), n

assert 'Recovered 2 unresolved audio events' in text('two-import-review')
assert '2 unresolved audio events · 2 media attached' in text('two-attached')
assert 'Complete counted track · 2 source events' in text('two-mode')
assert 0 < time('two-playing') < 1.5 and peaks('two-playing') == (0,0)
positive('two-first-active', 1.5, 5.5)
assert 5.5 < time('two-first-output') < 8 and peaks('two-first-output') == (0,0)
assert time('two-seek-second') == 9
positive('two-second-active', 8, 13)
ended('two-ended', 13)
positive('two-saved-seek-output', 3, 5.5)
assert 'audition paused' in text('two-saved-paused') and peaks('two-saved-paused') == (0,0)
positive('two-saved-resumed', time('two-saved-paused'), 5.5)
assert time('two-saved-stopped') == 0 and peaks('two-saved-stopped') == (0,0)
assert 'Complete counted track · 3 source events' in text('three-mode')
positive('three-last-output', 17, 18)
assert 'Symbolic source 2, start 16.000000 seconds, duration 2.000000 seconds' in text('three-last-output')
ended('three-ended', 18)
assert '48,000 Hz' in text('saved32-opened') and 'Value: 37' in text('saved32-opened')
assert 'Saved project rate 32000 Hz' in text('saved32-mode')
assert 0 < time('saved32-prefix') < 1.5 and peaks('saved32-prefix') == (0,0)
assert time('saved32-seek') == 9
positive('saved32-output', 9, 13)
assert '32,000 Hz saved CPR clock · unconverted' in text('saved32-output')
ended('saved32-ended', 13)
assert '48,000 Hz' in text('saved32-exited') and 'project playback selected' in text('saved32-exited')
for n, reason in [('deleted-track-rejected-final', 'Restore removed events'),
                  ('unknown-track-rejected', 'Every counted track child must be a supported audio event')]:
    assert reason in text(n) and 'button (disabled) Description: Play Complete Track' in text(n)
for n in ['deleted-selected-event-admitted', 'unknown-selected-event-admitted']:
    assert 'button Description: Play Event on Timeline' in text(n)
assert 'This project contains unresolved Cubase audio events' in text('project-blocked')

baseline = json.loads((H / 'gui-inputs.json').read_text())
assert len(baseline['files']) == 20
for row in baseline['files']: assert pin(R / row['path']) == row
saved = json.loads((H / 'gui-two-saved-inputs.json').read_text())
for row in saved['files']: assert pin(R / row['path']) == row
release = json.loads((H / 'release-build.json').read_text())['executable']
assert pin(R / release['path']) == release
process = json.loads((H / 'gui-process.json').read_text())
assert process['binary']['sha256'] == release['sha256'] and process['pid'] == 99498
groups = [
    ('two_complete_transport', ['two-import-review','two-attached','two-mode','two-playing','two-first-active','two-first-output','two-seek-second','two-second-active','two-ended','two-saved-reopened','two-saved-mode','two-saved-seek-output','two-saved-paused','two-saved-resumed','two-saved-stopped'],
     'GUI import/attachment admits both events; observed prefix and intervening gap are silent, both contributors produce engine output, natural completion is 13 seconds. Saved-package reopen, seek, pause, resume and stop also pass.'),
    ('three_complete_transport', ['three-opened','three-mode','three-playing','three-last-output','three-ended'],
     'Three-event track admits every contributor; seeking to 17 seconds produces third-event output and ends naturally at 18 seconds.'),
    ('saved_clock_controls', ['saved32-opened','saved32-mode','saved32-prefix','saved32-seek','saved32-output','saved32-ended','saved32-exited'],
     'Saved 32000 Hz clock and original timing remain in use despite editable 48000 Hz/37 BPM project settings. Raw source mode produces engine output, ends at 13 seconds, and exit restores project transport.'),
    ('deleted_contributor_guard', ['deleted-event','deleted-track-rejected-final','deleted-selected-event-admitted','deleted-saved'],
     'Explicitly removing one original contributor in an isolated copy blocks complete-track audition; the surviving selected event remains admitted.'),
    ('unknown_contributor_guard', ['unknown-opened','unknown-track-rejected','unknown-selected-event-admitted'],
     'An unknown counted child blocks complete-track mode even though two known events were retained. Selected-event mode remains admitted.'),
    ('whole_project_guard', ['two-exited','project-blocked'],
     'Exiting source audition restores project transport; unresolved native events still block whole-project playback.')]
value = dict(id='APP020-GUI', created_utc=datetime.now(timezone.utc).isoformat(), final_release=True,
    executable=release, process=pin(H/'gui-process.json'), groups_passed=len(groups),
    groups=[dict(name=n,result='passed',records=[pin(H/('gui-'+f+'.txt')) for f in files],observations=[o]) for n,files,o in groups],
    package_files_unchanged=len(baseline['files']), package_files=baseline['files'], package_baseline=pin(H/'gui-inputs.json'),
    helper_preparation=pin(H/'gui-helper-preparation.json'),
    screenshots=[pin(H/n) for n in ['gui-two-second-active.png','gui-three-track.png','gui-saved32-output.png']],
    retained_intermediates=[
        'An earlier Oct21 process had unsaved unrelated audio edits. GUI Quit/Save preserved them locally; accepted GUI observations use fresh release PID99498 started Oct23.',
        'Initial two-event attachment was unsaved app state. Its package stayed unchanged through first audition, then explicit Save persisted attachment. gui-two-inputs.json is a superseded pre-save observation, not a current package baseline; gui-two-saved-inputs.json and gui-inputs.json pin the saved package used for reopen/seek/pause/resume/stop.',
        'The first-output and second-output filenames from early sampling are timing attempts: first-output actually observes the silent gap at6.906 seconds, second-output observes the13-second end. Only their measured states support claims.',
        'A pause attempt after completion restarted playback; gui-two-pause-attempt.txt is not pause evidence. Final saved-paused/resumed captures establish pause/resume.',
        'A stationary initial series captured a stopped cursor only and is not live-output evidence. Final first-active, second-active and saved-seek-output captures establish output.',
        'Some menu captures retained selection before dismissal; Return completed those choices. Final-suffix captures establish admission/rejection. Several stale-state tool calls were refreshed; no failed call is acceptance evidence.'
    ],
    limits=[
        'Self-authored symbolic parser graphs and exact integer PCM controls are not Cubase-generated/native-valid CPR projects.',
        'Engine peaks are own-application telemetry, not DAC capture, latency certification, hardware rate-conversion proof or Cubase runtime output.',
        'This mode uses the saved clock without source rate conversion. Existing explicit selected-event conversion modes remain separate; no automatic converter choice is inferred.',
        'Admission remains chronological disjoint/touching direct-track sources, fresh root mode0, supported plain processing only. Overlaps, fades, routing, mixer, effects, automation and full-project fidelity remain unresolved.',
        'Track banner/footer show complete scope, but individual timeline lane labels still distinguish the anchor as Source event audition and other included events as Unresolved audio.'
    ])
with (H/'gui-observations.json').open('x') as f: json.dump(value,f,indent=2); f.write('\n')
print(json.dumps(dict(groups=len(groups), package_files=len(baseline['files']), executable=release)))
