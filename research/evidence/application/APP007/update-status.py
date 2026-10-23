"""Advance current status after APP007 validation, preserving APP006 status."""
from pathlib import Path
import copy,hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).resolve().parent
load=lambda p:json.loads(p.read_text())
def save(p,d): p.write_text(json.dumps(d,indent=2)+'\n')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
v=load(OUT/'application-validation.json')
prefix='research/evidence/application/APP007/';native='research/evidence/cubase-static/cpr-audio-events-001/'
proof=[prefix+n for n in ['application-validation.json','artifact-manifest.json','media-attachment-review.json','gui-observations.json','gui-packages-independent-check.json','historical-integrity.json']]+[native+a+'/finding.json' for a in ['segment-consumer','renderer-selection','rate-converter']]
cpr=('Frozen CPR profiles V1/V2/V3/V4 retain their source interpretations. V4 preserves exact unresolved audio objects and LoFi zero-origin24-second source placement; Classic remains unplaced. '
'User-selected PCM attachments are separate edits, copied and bound to source SHA/AudioFile identity with an actual-media SHA. Exact frame count/rate/channels/bit-depth/frame-size, decoded finite samples and every linked segment bound are validated before acceptance and on save/load. '
'Attachment supports one file and one segment per linked event, mono/stereo PCM, up to256MiB and16million frames. Undo/Redo, replacement, removal/pruning and Save As retain custody. '
'Playback/render/exchange still refuse unresolved native processing. Matching format does not establish original-media identity. General coordinates, event rendering, backend/rate state and output parity remain open.')
scope='138 implementation tests in20 suites, ten bounded native Rebase GUI groups, two independently audited valid GUI packages and an intentional changed-media negative package. No Cubase execution or reference audio-conformance measurements.'
gui='Ten native GUI groups passed: frozen V4 open, rejection/attachment/replacement, Undo/Redo, removal, save/reopen, Save As, playback/mixdown barriers and changed-PCM rejection.'
build='0.7.0 build7 release built and strictly code-signature verified; final source/test/bundle snapshots retained.'
paths=[ROOT/'research'/n for n in ['study.json','coverage.json','rea-steering.json']]
history=ROOT/'research/status-history/pre-APP007';history.mkdir(parents=True,exist_ok=True)
for p in paths:
    assert not (history/p.name).exists(),'Do not rewrite prior status'
    shutil.copy2(p,history/p.name)
study=load(paths[0]);app=study['application'];oldcpr=app['cpr_status']
app['validation_history'].append({k:app[k] for k in ['version','build_executable_sha256','implementation_test_count','implementation_test_suites','implementation_test_log','implementation_test_log_sha256','validation_record']})
app.update(version='0.7.0',build_executable_sha256=v['executable']['sha256'],implementation_test_count=138,implementation_test_suites=20,implementation_test_log=prefix+'core-tests-final.log',implementation_test_log_sha256=sha(OUT/'core-tests-final.log'),previous_validation_record='research/evidence/application/APP006/application-validation.json',validation_record=prefix+'application-validation.json',cpr_status=cpr,evidence_boundary=scope,build_status=build,gui_validation_status=gui)
app['implementation_evidence']+=proof
app['implemented'].append('Explicit source-bound PCM attachment/replacement with whole-shared-file interval validation, transactional cleanup, SHA custody, Undo/Redo and package persistence; integer segment mapping integrated into actual-media validation.')
for area in ['segment-consumer','renderer-selection','rate-converter']: study['static_evidence']['cpr_audio_events_'+area.replace('-','_')]=native+area+'/finding.json'
save(paths[0],study)
coverage=load(paths[1]);coverage['previous_application_iterations'].append(copy.deepcopy(coverage['application_iteration']))
coverage['application_iteration']={'id':'APP007','version':'0.7.0','validation_record':prefix+'application-validation.json','gui_validation_status':gui,'release_verification_status':build,'swift_test_methods_passed':138,'test_suites':20,'test_log':prefix+'core-tests-final.log','test_log_sha256':sha(OUT/'core-tests-final.log'),'implementation_evidence':proof,'scope':scope,'build_executable_sha256':v['executable']['sha256']}
for domain in coverage['domains']:
    if domain['id']=='project-media':
        domain['application_implementation']='Independent project/media bundle. '+cpr
        domain['static_mapping']+=' Concrete segment interval/seek/read, conditional restored-state stream selection and differing-rate request-count arithmetic now have original-byte traces. Final event PCM remains unverified.'
        domain['static_evidence'] += [native+a+'/finding.json' for a in ['segment-consumer','renderer-selection','rate-converter']]
    elif domain['id']=='import-export':
        domain['application_implementation']=domain['application_implementation'].split('Bounded CPR profile-v4')[0]+cpr
    elif domain['id']=='audio-editing':
        domain['application_implementation']+=' Explicit recovered-event media attachment/replacement and Undo/Redo are implemented; imported native events remain unresolved for rendering.'
save(paths[1],coverage)
steering=load(paths[2]);steering['previous_iteration_status'].append(copy.deepcopy(steering['iteration_status']));current=steering['iteration_status']
current.update(version='0.7.0',iteration='APP007',validation_record=prefix+'application-validation.json',build_executable_sha256=v['executable']['sha256'],gui_validation_status=gui,release_verification_status=build)
current['application_tests'].update(passed=138,suites=20,evidence=prefix+'core-tests-final.log',sha256=sha(OUT/'core-tests-final.log'))
current['implemented_scope']=[cpr if x==oldcpr else x for x in current['implemented_scope']]
current['implementation_limits']=[cpr if x==oldcpr else x for x in current['implementation_limits']]
current['evidence']+=proof
steering['next_priorities'][0].update(id='event-rendering-consumer-and-backend-contract',question='How does the concrete event consumer construct and read PAudioSegment gain/fade/loop/source-offset state, and under which actual backend format/rate conditions?',starting_evidence=[prefix+'application-validation.json']+[native+a+'/finding.json' for a in ['segment-consumer','renderer-selection','rate-converter']],action='Trace finite consumer10020f2e8 and caller10020ee24 through PAudioSegment construction and PCM read/application. Establish gain/fade/loop and source-position predicates before promoting imported events. Then implement a versioned supported render contract and independently test real local media. No proprietary target execution.',implementation_gate='Complete original-byte consumer path, exact numeric ordering and source/backend predicates, negative controls, preserved original/report evidence, versioned import semantics, application integration and checked outputs. Conditional selector reachability is not full PCM parity.',historical_compatibility='V1/V2/V3/V4 frozen; attachments stay separate from import baseline. New rendering interpretation requires a new profile.',active_division={'event_rendering':'cubase_evidence','independent_native_review':'target_intake','integration_and_validation':'root'})
save(paths[2],steering)
print(json.dumps({'updated':[str(p.relative_to(ROOT)) for p in paths],'history':str(history.relative_to(ROOT))}))
