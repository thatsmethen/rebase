#!/usr/bin/env python3
"""Read-only verification of the exact downloaded preview; no binary execution."""
import hashlib
import json
import struct
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
import sys
from collections import Counter
from audit_context import load, module, decode, validate_shared_command_exits
CONTEXT = load()
BASE, RUN, ROOT, COMMIT, E, ARCHIVE = (CONTEXT.output, CONTEXT.run_id, CONTEXT.root,
    CONTEXT.commit, CONTEXT.evidence, CONTEXT.archive)
COUNTS = CONTEXT.counts
GATES, GATE_SOURCES = CONTEXT.bind_gates()
import pefile
from windows_automation_gate import require_automation_protocol, require_automation_window, PROTOCOL_GATES, WINDOW_GATES
from cpr_audition_gate import require_cpr_audition, require_cpr_audition_window
from source_stream_gate import require_receipt as require_source_stream
from source_stream_window_gate import require_source_stream_window
from native_stream_package import validate_native_stream_package
WINDOW_GATE = module(GATES/'build-windows-app.py', 'audited_windows_app_gate')

def sha(data):
    return hashlib.sha256(data).hexdigest()

def source(path):
    return CONTEXT.source(path)

def read(name):
    return decode((E/name).read_text())

archive_summary = decode((BASE/'zip-audit/download-summary.json').read_bytes())
assert archive_summary['source_commit'] == COMMIT and archive_summary['archive']['sha256'] == sha(ARCHIVE.read_bytes())
assert archive_summary['privacy_blocker_records'] == 0
workflow = decode(CONTEXT.workflow.read_bytes())
assert workflow['headSha'] == COMMIT and workflow['status'] == 'completed' and workflow['conclusion'] == 'success'
assert len(workflow['jobs']) == 1
assert workflow['databaseId'] == RUN
assert all(j['conclusion'] == 'success' for j in workflow['jobs'])
app = read('application-build.json')
assert app['status'] == 'passed' and app['commit'] == COMMIT
assert all(c['exit_code'] == 0 for c in app['commands'])
assert app['window_smoke_tested'] and app['dependency_closure_checked'] and app['app_local_modules_observed']
assert app['source_fixture_shipped'] is False and app['playback_tested'] is False

closure = read('pe-dependency-closure.json')
modules = read('loaded-modules.json')
with zipfile.ZipFile(ARCHIVE) as z:
    manifest = decode(z.read('Rebase/package-manifest.json'))
    files = {f['path']:f for f in manifest['files']}
    pe_paths = {f for f in files if Path(f).suffix.lower() in ('.exe','.dll')}
    images = {i['path']:i for i in closure['images']}
    assert len(images) == len(closure['images']) and set(images) == pe_paths
    local = {Path(f).name.lower(): f for f in files if '/' not in f}
    imports_checked = 0
    for relative, record in images.items():
        data = z.read('Rebase/'+relative)
        pe = pefile.PE(data=data, fast_load=True)
        try:
            pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY[n] for n in ('IMAGE_DIRECTORY_ENTRY_IMPORT','IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT')])
            clr = pe.OPTIONAL_HEADER.DATA_DIRECTORY[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_COM_DESCRIPTOR']]
            flags = struct.unpack('<I', pe.get_data(clr.VirtualAddress+16,4))[0] if clr.VirtualAddress else 0
            assert pe.FILE_HEADER.Machine == 0x8664 or (pe.FILE_HEADER.Machine == 0x14c and flags & 1 and not flags & 2)
            imports = {entry.dll.decode('ascii').lower() for kind in ('DIRECTORY_ENTRY_IMPORT','DIRECTORY_ENTRY_DELAY_IMPORT') for entry in getattr(pe,kind,[])}
        finally:
            pe.close()
        recorded = {i['name']: i['source'] for i in record['imports']}
        assert set(recorded) == imports and len(recorded) == len(record['imports'])
        for name, origin in recorded.items():
            assert Path(name).name == name and ':' not in name and '\\' not in name
            if origin in ('application','visual-cpp-runtime','swift-runtime-6.4.1'):
                assert name in local
            elif origin == 'windows-api-contract':
                assert name.startswith(('api-ms-','ext-ms-'))
            else:
                assert origin == 'windows-system'
                assert not name.startswith(('msvcp1','msvcr1','vcruntime','concrt','vcomp','swift','foundation','dispatch'))
            imports_checked += 1
    for record in closure['copied']:
        assert record['name'].lower() in local
        assert record['source'] in ('visual-cpp-runtime','swift-runtime-6.4.1')
    notices = decode(z.read('Rebase/ThirdPartyNotices/sources.json'))
    assert notices == decode(source('Application/scripts/windows-runtime-license-sources.json'))
    for notice in notices:
        assert sha(z.read('Rebase/ThirdPartyNotices/'+notice['name'])) == notice['sha256']
    assert 'https://visualstudio.microsoft.com/license-terms/' in z.read('Rebase/ThirdPartyNotices/Visual-Cpp-Runtime.txt').decode()
    config = decode(z.read('Rebase/Rebase.runtimeconfig.json'))['runtimeOptions']
    assert {v['name']:v['version'] for v in config['includedFrameworks']} == {'Microsoft.NETCore.App':'10.0.13','Microsoft.WindowsDesktop.App':'10.0.13'}
    assert 'framework' not in config and 'frameworks' not in config
    module_counts = {}
    for group, required in [('process', {'rebase.exe','coreclr.dll','rebasewindowsaudio.dll','soxr.dll'}),('helper',{'rebase-session.exe','swiftcore.dll','soxr.dll'})]:
        names = set()
        for item in modules[group]:
            where = item['location']
            assert where.startswith(('application/','windows/'))
            if where.startswith('application/'):
                relative = where[len('application/'):]
                assert item['sha256'] == files[relative]['sha256']
                assert sha(z.read('Rebase/'+relative)) == item['sha256']
                names.add(item['name'].lower())
        assert required <= names
        module_counts[group] = {'total':len(modules[group]),'app_local':len(names)}


smoke = read('wpf-smoke.json')
review = smoke['cpr_review']
assert smoke['outcome'] == 'passed' and smoke['stage'] == 'completed' and len(smoke['checks']) == len(set(smoke['checks'])) == COUNTS['wpf_checks']
controls = read('host-controls.json')
assert controls['checks'] == COUNTS['host_controls'] and controls['failures'] == 0
conformance = read('shared/conformance.json')
assert conformance['commit'] == COMMIT and conformance['status'] == 'passed'
assert conformance['configuration'] == 'Release' and conformance['platform'] == 'Windows'
assert conformance['architecture'].lower() in ('amd64','x86_64')
validate_shared_command_exits(conformance['commands'])
assert (E/'shared/example-overwrite-refusal.log').read_text().strip() == (
    'rebase-inspect: Choose a new .wav file outside the source project package. Existing files are never replaced.')
tests = ET.parse(E/'shared/tests-swift-testing.xml').getroot().findall('.//testcase')
counts = {'count':len(tests),'executed':sum(t.find('skipped') is None for t in tests),'skipped':sum(t.find('skipped') is not None for t in tests),'failures':sum(t.find('failure') is not None or t.find('error') is not None for t in tests)}
assert counts == {k:conformance['tests'][k] for k in counts} == COUNTS['shared_tests']
subset_counts = {}
for suite, expected_count in COUNTS['shared_subsets'].items():
    members = [t for t in tests if suite in t.attrib.get('classname', '') or suite in t.attrib.get('name', '')]
    assert len(members) == expected_count and all(t.find('skipped') is None and t.find('failure') is None and t.find('error') is None for t in members), suite
    subset_counts[suite] = len(members)
example = decode(source('Application/Examples/Rebase Preview.rebaseproj/Project.json'))
lock = decode(source('Application/scripts/example-render-lock.json'))
example_render = read('shared/example-render.json')
assert example_render['schema'] == 'rebase.portable-render.v1' and example_render['commit'] == COMMIT
assert example_render['configuration'] == 'Release' and example_render['platform'] == 'Windows'
assert example_render['regular_file'] is True and example_render['repeat_render_refused_without_modification'] is True
assert example_render['matches_predeclared_lock'] is True and example_render['mismatched_fields'] == []
assert example_render['expected_render_lock_sha256'] == sha(source('Application/scripts/example-render-lock.json'))
assert all(example_render[key] == lock[key] for key in
           ('frames', 'channels', 'sample_rate', 'bits_per_sample', 'pcm_sha256', 'wav_sha256'))
assert example_render['wav_bytes'] == example_render['frames'] * example_render['channels'] * 4 + 58
assert example_render['cli'] == decode((E/'shared/example-render.log').read_bytes())
assert example_render['cli']['wavBytes'] == example_render['wav_bytes']
expected = decode(source('Application/Tests/Fixtures/SourceAudition/expected.json'))
for name in ('packaged-session-protocol.json','shared/session-protocol.json'):
    p = read(name)
    assert p['status'] == 'passed' and len(p['checks']) == COUNTS['session_checks'] and p['source_journey_tested'] is True
    require_automation_protocol(p, example, lock)
    assert p['automation']['mutation_count'] == 10 and p['automation']['invalid_requests_checked'] == 15
    assert p['automation']['edited_wav_sha256'] == '53445382282de96e9a575ea8910be28146c3916512fdf246fab43a595d598abe'
    assert p['automation']['edited_pcm_sha256'] == 'b924da7269d472b3f710b95207955adea9f63d8e231edb323e22cfcc795712c8'
    assert p['automation']['original_point_count'] == 5
    assert p['wav_sha256'] == '13edfc233369484ff5c88aa4e4ca8a2f013d7c2ac3f21a0c7881e00dc3e457b9'
    assert p['pcm_sha256'] == 'f51a6801100ba715e589fcd9d99be2c0c81f6911972548a4c64fff73ff60c8d4'
    assert p['waveform']['clips_checked'] == 11 and p['waveform']['peak_bins_checked'] == 17600
    assert p['waveform']['float32_peak_words_sha256'] == 'ade8ed5eb493af376b7affbfb5bd0bf3f06aafa51eabe63c48c6657406caba29'
    assert p['ruler']['read_only'] and p['ruler']['stale_revision_rejected'] and p['ruler']['ticks_checked'] == 33
    assert p['ruler']['first_bar_seconds'] == [0,2.5,5,7.5]
    for key in ('sourceSHA256','mediaSHA256','outputSHA256','pcmSHA256','frames','sampleRate','channels'):
        assert p['source'][key] == expected[key]
    imported = p['cpr_import']
    gates = ('tested', 'review_read_only', 'review_bounded', 'cancellation_preserves_state',
             'superseded_review_rejected', 'stale_revision_rejected', 'changed_source_rejected',
             'explicit_partial_required', 'dirty_replacement_guarded', 'existing_destination_preserved',
             'import_published', 'exact_source_and_report_preserved', 'save_reopen_preserves_baseline',
             'historical_read_only', 'tampered_report_rejected', 'tampered_source_rejected')
    assert all(imported[k] is True for k in gates)
    assert imported['sourceSHA256'] == expected['sourceSHA256'] and imported['reportSHA256'] == expected['reportSHA256']
    assert imported['playback_tested'] is False
assert all(review[k] is True for k in ('reviewed','cancelled_without_changes','changed_source_rejected','dirty_guard',
    'destination_cancel_preserved_review','imported','historical_read_only','vertical_scroll_checked'))
assert type(review['error_scrolling_checked']) is bool
assert review['preserved_source_sha256'] == expected['sourceSHA256']
assert all(review[k] is False for k in ('native_frame_visual_tested','native_file_pickers_tested','physical_input_tested'))

# Independently verify the newly shipped public SoXR dependency and source offer.
import io
import stat
from pathlib import PurePosixPath
resampler = read('device-resampler-package.json')
assert resampler == app['device_resampler']
assert resampler['schema'] == 'rebase.windows-soxr-dependency.v1' and resampler['status'] == 'passed'
assert resampler['application_commit'] == COMMIT
assert resampler['source_version'] == '0.1.3' and resampler['source_commit'] == '945b592b70470e29f917f4de89b4281fbbd540c0'
assert resampler['source_manifest_sha256'] == 'faeba8d39aa6eb0c4117291be67a99c207f3e0027bd3f79c1184309eca27a66d'
assert resampler['source_entries_verified'] == 138
assert resampler['build_report_sha256'] == sha((E/'native/soxr/conformance.json').read_bytes())
assert resampler['plumbing_report_sha256'] == sha((E/'native/soxr/soxr-conformance.json').read_bytes())
soxr_build = read('native/soxr/conformance.json')
assert soxr_build['status'] == 'passed' and soxr_build['commit'] == COMMIT
assert soxr_build['platform'] == 'Windows' and soxr_build['architecture'].lower() in ('amd64','x86_64')
assert soxr_build['artifacts'] == resampler['artifacts']
assert len(soxr_build['commands']) == 7 and all(c['exit_code'] == 0 for c in soxr_build['commands'])
assert (E/'native/soxr/probe-build.log').is_file() # A successful compiler may be silent.
plumbing = read('native/soxr/soxr-conformance.json')
assert plumbing == decode((E/'native/soxr/probe.log').read_bytes())
assert plumbing['status'] == 'passed' and plumbing['finite'] is True
assert (plumbing['source_rate'],plumbing['output_rate'],plumbing['input_frames'],plumbing['output_frames']) == (48000,44100,4800,4410)
assert plumbing['energy'] > 0 and 0 < plumbing['peak'] <= 2 and 0 <= plumbing['maximum_channel_error'] < 1e-6
with zipfile.ZipFile(ARCHIVE) as z:
    assert {row['path'] for row in resampler['packaged_files']} == {
        'soxr.dll', *('ThirdPartyNotices/SoXR/'+name for name in ('COPYING.LGPL','LICENCE','AUTHORS',
            'REBUILD-AND-REPLACE.txt','soxr-source-manifest.json','soxr-0.1.3-source.zip'))}
    assert len(resampler['packaged_files']) == 7
    for row in resampler['packaged_files']:
        data = z.read('Rebase/'+row['path'])
        assert len(data) == row['bytes'] and sha(data) == row['sha256']
        assert row == files[row['path']]
    dll = z.read('Rebase/soxr.dll')
    assert {'path':'install/bin/soxr.dll','bytes':len(dll),'sha256':sha(dll)} in resampler['artifacts']
    assert {'name':'soxr.dll','source':'application'} in images['RebaseWindowsAudio.dll']['imports']
    assert {'name':'soxr.dll','source':'application'} in images['rebase-session.exe']['imports']
    assert any(m['name'].lower() == 'soxr.dll' and m['location'] == 'application/soxr.dll'
               and m['sha256'] == sha(dll) for m in modules['process'])
    source_manifest = source('Application/ThirdParty/soxr-source-manifest.json')
    assert z.read('Rebase/ThirdPartyNotices/SoXR/soxr-source-manifest.json') == source_manifest
    rows = decode(source_manifest)['files']
    assert len(rows) == 138
    expected_names = {'soxr-0.1.3/'+row['path'] for row in rows} | {
        'soxr-source-manifest.json','rebuild/build-windows-soxr.py','rebuild/windows-soxr-probe.c'}
    archived = z.read('Rebase/'+resampler['source_archive']['path'])
    assert sha(archived) == resampler['source_archive']['sha256']
    assert resampler['source_archive']['entry_count'] == 141 and resampler['source_archive']['source_entries'] == 138
    with zipfile.ZipFile(io.BytesIO(archived)) as nested:
        assert nested.testzip() is None
        entries = nested.infolist()
        assert len(entries) == 141 and {v.filename for v in entries} == expected_names
        assert len({v.filename.casefold() for v in entries}) == 141
        for info in entries:
            assert not info.is_dir() and not info.flag_bits & 1
            assert stat.S_IFMT(info.external_attr >> 16) == stat.S_IFREG
            assert not PurePosixPath(info.filename).is_absolute() and '..' not in PurePosixPath(info.filename).parts
        for row in rows:
            data = nested.read('soxr-0.1.3/'+row['path'])
            assert data == source('Application/ThirdParty/soxr-0.1.3/'+row['path'])
            if 'symlink' in row: assert data == row['symlink'].encode()
            else: assert len(data) == row['bytes'] and sha(data) == row['sha256']
        assert nested.read('soxr-source-manifest.json') == source_manifest
        for name in ('build-windows-soxr.py','windows-soxr-probe.c'):
            assert nested.read('rebuild/'+name) == source('Application/scripts/'+name)
    assert resampler['source_archive']['symlink_entries'] == [{'path':'inst-check-soxr-lsr','target':'inst-check-soxr','representation':'regular link-text'}]
    for name in ('COPYING.LGPL','LICENCE','AUTHORS'):
        assert z.read('Rebase/ThirdPartyNotices/SoXR/'+name) == source('Application/ThirdParty/soxr-0.1.3/'+name)
    notes = z.read('Rebase/ThirdPartyNotices/SoXR/REBUILD-AND-REPLACE.txt').decode()
    assert COMMIT in notes and resampler['source_commit'] in notes and 'Application/scripts/build-windows-soxr.py' in notes
    assert 'replace soxr.dll' in notes and 'not a proprietary reference library' in notes
    CONTEXT.write_once(BASE/'soxr-0.1.3-source-from-package.zip', archived)

native = read('native/conformance.json')
assert native['commit'] == COMMIT and native['status'] == 'passed' and native['native_library_built'] is True
native_cases = ET.parse(E/'native/lifecycle.xml').getroot().findall('.//testcase')
assert len(native_cases) == 3 and all(c.find('failure') is None and c.find('error') is None and c.find('skipped') is None for c in native_cases)
assert {c.get('name') for c in native_cases} == {'native_audio_portable_lifecycle','native_audio_rate_conversion','native_audio_bounded_stream'}
rate = read('native/rate-conversion.json')
assert rate['failures'] == 0 and rate['checks'] > 0 and rate['soxr_version'] == 'libsoxr-0.1.3'
assert rate['profile'] == {'recipe':6,'channels':2,'linear_phase':True,'runtime_threads':1,'implicit_os_conversion':False}
assert rate['wasapi_compiled'] is False and rate['playback_tested'] is False and rate['audible_output_measured'] is False
case_names = {'identity-bits','44100-to-48000','48000-to-44100','8000-to-192000','192000-to-8000',
 'fractional-frame-count','short-empty-downsample','zero-isolation-tail-drain','seek-phase-preserved',
 'pause-reset-drain','allocation-failure','converter-failure','capacity-rejection','environment-rejection'}
assert len(rate['cases']) == 14 and {c['name'] for c in rate['cases']} == case_names and all(c['failures']==0 for c in rate['cases'])
for case in rate['cases']:
    if case['name'] in {'44100-to-48000','48000-to-44100','8000-to-192000','192000-to-8000','fractional-frame-count'}:
        assert case['endpoint_frames'] == (case['source_frames']*case['endpoint_rate']+case['source_rate']//2)//case['source_rate']
    if case['name'] in {'short-empty-downsample','allocation-failure','converter-failure','capacity-rejection','environment-rejection'}:
        assert case['endpoint_frames'] == 0
controls = read('dependency-controls/observation.json')
assert controls['status']=='passed' and controls['tests']==COUNTS['dependency_tests']['count'] and controls['failures']==0 and controls['errors']==0 and controls['skipped']==COUNTS['dependency_tests']['skipped']
assert controls['helper_sha256'] == sha(source('Application/scripts/windows_soxr_package.py'))
assert controls['harness_sha256'] == sha(source('Application/scripts/test_windows_soxr_package.py'))
endpoint = read('native/endpoint-probe.json')
assert endpoint['wasapi_compiled'] is True and all(endpoint[k] is False for k in ('allow_audio','playback_attempted','playback_tested','audible_output_measured'))
from stream_audit import verify as verify_stream_additions
stream_audit = verify_stream_additions(CONTEXT, app, smoke, files, GATE_SOURCES, WINDOW_GATE)
result = {'schema':'rebase.downloaded-source-stream-runtime-verification.v1', 'stream_audit':stream_audit,'source_commit':COMMIT,'workflow_id':RUN,
 'pe_images_reparsed':len(pe_paths),'pe_imports_matched_to_ci':imports_checked,'dependency_closure_matches_archive':True,
 'runtime_notices_verified':len(notices),'app_local_module_counts':module_counts,'app_local_module_hashes_match_archive':True,
 'soxr_dll_hash_matches_build_manifest_and_loaded_module':True,'public_soxr_source_entries_verified':138,
 'public_soxr_archive_entries_verified':141,'public_soxr_packaged_files_verified':7,'public_soxr_notice_files_verified':3,
 'source_archive_sha256':resampler['source_archive']['sha256'],'upstream_link_stored_as_regular_text':True,
 'exact_rebuild_script_probe_and_manifest_in_source_archive':True,'host_controls':COUNTS['host_controls'],'packaged_helper_checks':COUNTS['session_checks'],
 'shared_release_tests':counts,'shared_release_subset_counts':subset_counts,'native_ctest_count':3,
 'native_conversion_controls':rate['checks'],'native_conversion_cases':14,'dependency_package_controls':COUNTS['dependency_tests'],
 'source_waveform_ruler_and_render_locks_match':True,'shared_example_refusal_and_predeclared_hash_bound':True,'playback_tested':False,'audio_endpoint':endpoint['outcome'],
 'boundary':'Downloaded PE imports/source/archive/module hashes independently verified; actual Windows build and module observations come from exact-source CI. This audit did not execute native binaries or measure device/audio output. Visual review is separate.'}
CONTEXT.write_json('runtime-verification.json', result)
print(json.dumps(result,indent=2))
