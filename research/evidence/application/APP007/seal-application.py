"""Seal bounded media attachment evidence; does not execute Cubase."""
from pathlib import Path
import datetime,hashlib,json,plistlib,shutil,subprocess
ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
NOW=datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def record(p): return {'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p)}
def write(name,value): (OUT/name).write_text(json.dumps(value,indent=2)+'\n')
assert not (OUT/'application-validation.json').exists(), 'Do not reseal published evidence'
tests=OUT/'core-tests-final.log'
assert 'Test run with 138 tests in 20 suites passed' in tests.read_text()
for name in ['media-attachment-review.json','gui-packages-independent-check.json','historical-integrity.json']:
    assert (OUT/name).is_file()
assert json.loads((OUT/'historical-integrity.json').read_text())['status']=='passed'
app=ROOT/'Application/dist/Rebase.app'; binary=app/'Contents/MacOS/Rebase'
info=plistlib.loads((app/'Contents/Info.plist').read_bytes())
assert info['CFBundleShortVersionString']=='0.7.0' and info['CFBundleVersion']=='7'
verified=subprocess.run(['codesign','--verify','--strict',str(app)],capture_output=True,text=True)
(OUT/'codesign-verify.log').write_text(verified.stdout+verified.stderr)
assert verified.returncode==0
files=sorted([p for folder in ['Application/Sources','Application/Tests'] for p in (ROOT/folder).rglob('*') if p.is_file()]+[ROOT/'Application'/n for n in ['Package.swift','Package.resolved','build-app.sh','test-app.sh']])
for p in files:
    dst=OUT/'final-source-snapshot'/p.relative_to(ROOT);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst)
write('final-source-manifest.json',{'created_utc':NOW,'scope':'Checked independent application source, tests, and build inputs','files':[record(p) for p in files]})
shutil.copytree(app,OUT/'final-build-snapshot/Rebase.app')
write('build-identity.json',{'version':'0.7.0','build':7,'created_utc':NOW,'executable':record(binary),'info_plist':record(app/'Contents/Info.plist'),'build_log':record(OUT/'build-initial.log'),'strict_codesign_exit':0,'source_manifest':record(OUT/'final-source-manifest.json'),'test_log':record(tests),'source_change_after_build':'Tests added; production source unchanged after the release build and all GUI checks.'})
groups=[
('frozen-v4-open',['gui-backward-open.ax.txt'],'APP006 V4 package copied before edits; opens with exact24-second event, native timing, no attachment.'),
('mismatch-rejected',['gui-mismatch-refused.ax.txt','gui-after-mismatch.ax.txt'],'1058399-frame file rejected against1058400-frame reference; no association.'),
('explicit-attachment',['gui-media-attached.ax.txt','gui-media-attached.png','gui-attachment-inspector.png'],'Native file picker copies matching synthetic PCM; selected filename/hash and unresolved playback state visible. Inspector scroll reaches controls without overlap.'),
('attachment-undo-redo',['gui-attachment-undo.ax.txt','gui-attachment-redo.ax.txt'],'Undo removes association; Redo restores it.'),
('replacement-undo',['gui-media-replaced.ax.txt','gui-replacement-undo.ax.txt'],'Replacement selects a different synthetic file; Undo restores the initial file/hash.'),
('playback-and-mixdown-refusal',['gui-attached-play-refused.ax.txt','gui-attached-mixdown-refused.ax.txt'],'Attachment does not bypass unresolved native-processing gates.'),
('event-removal-and-undo',['gui-event-and-binding-removed.ax.txt','gui-removed-project-checkpoint.json','gui-event-and-binding-restored.ax.txt'],'Removing event prunes association before save; Undo restores source event and attachment, then saves successfully.'),
('save-reopen',['gui-attached-saved.ax.txt','gui-attached-reopened.ax.txt'],'Saved attachment reopens with identical checksum and24-second source placement.'),
('save-as-reopen',['gui-attached-save-as.ax.txt','gui-attached-copy-reopened.ax.txt'],'Save As copy reopens; independent package audit checks copied assets and source proof.'),
('changed-media-refusal',['changed-media-control.json','gui-changed-media-refused.ax.txt','gui-final-open.ax.txt'],'One changed PCM sample in a separate package copy is detected on reopen; valid current project remains open.')]
write('gui-observations.json',{'created_utc':NOW,'application_executable_sha256':sha(binary),'method':'Native Rebase accessibility and visual checks via cua_repl','target_executed':False,'groups':[{'id':k,'status':'passed','observation':o,'evidence':[record(OUT/n) for n in names]} for k,names,o in groups],'boundary':'Self-authored media validates application behavior only; no Cubase runtime or audio-equivalence measurements.'})
native=ROOT/'research/evidence/cubase-static/cpr-audio-events-001'
findings=[native/area/'finding.json' for area in ['segment-consumer','renderer-selection','rate-converter']]
write('application-validation.json',{'id':'APP007','version':'0.7.0','build':7,'created_utc':NOW,'status':'bounded_media_attachment_implemented_and_checked','autonomous_goal_status':'active','interpretation_profile':'cpr-static-subset-v4 unchanged','serialization_schema':2,'executable':record(binary),'test_methods_passed':138,'test_suites':20,'test_log':record(tests),'gui_groups_passed':len(groups),'gui_record':record(OUT/'gui-observations.json'),'independent_review':record(OUT/'media-attachment-review.json'),'package_audit':record(OUT/'gui-packages-independent-check.json'),'historical_audit':record(OUT/'historical-integrity.json'),'static_findings':[record(p) for p in findings],
'implemented':['Checked integer source-segment mapping with nonzero Start/Offset discriminator, overflow and source-capacity rejection.','Explicit user-selected PCM attachment bound to preserved source SHA and AudioFile identity; copied media SHA, actual decoded frame count and format verified.','Every source-sharing event validated before accepting a copy; failed transactions leave project manifest unchanged and clean copied media.','Native Attach/Replace controls, attachment Undo/Redo, removal/pruning, save/reopen and Save As.','Frozen V1/V2/V3/V4 imports unchanged; attachments are separate user edits. Native-event playback/render/exchange still refuses unresolved processing.'],
'retained_corrections':[{'record':'media-attachment-tests-initial.log','cause':'New test macro could not use a throwing right-hand conjunction; split into independent assertions, production code unchanged.'},{'record':'media-attachment-review.json','cause':'Pre-acceptance shared-file validation and failed-copy cleanup order corrected before build and GUI checks.'}],
'limits':['Cubase/proprietary runtime executions and measured reference comparisons remain0.','Matching file metadata does not prove original recording identity; every attachment is explicitly user-selected.','Attachment currently supports one file and one segment per linked event, mono/stereo PCM, exact saved format, at most256MiB and16million frames.','Direct segment arithmetic does not establish active backend format/gain or actual complete reads; stream selection is conditional on bounded unchanged restored state.','Native event-local gain/fades/looping, timeline mixer/output path, differing-rate output samples, general placement and musical duration remain open.','CPR writing/roundtrip, MIDI editing, recording, plugin hosting, PDC, complete routing and full interface fidelity remain open.'],
'next':'Trace finite event rendering consumer gain/fade/loop state, then implement supported event-local rendering in a new frozen profile with explicit conditions. Full Cubase fidelity goal remains active.'})
print(json.dumps({'sources':len(files),'tests':138,'gui_groups':len(groups),'executable_sha256':sha(binary),'validation_sha256':sha(OUT/'application-validation.json')}))
