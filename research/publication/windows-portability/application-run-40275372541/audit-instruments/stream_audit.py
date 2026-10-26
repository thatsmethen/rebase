"""Additional stream/complete-proof checks for the configurable private audit.

The imported validators are extracted from the audited source commit. No
helper, native DLL, endpoint, or GUI is executed by this inspection.
"""
import hashlib
import json
import zipfile


def native_verification_view(context, dll):
    """Use ZIP bytes in a clearly derived view, never invent a raw build binary.

The workflow omits native/build outputs. Bind the ZIP DLL to the original CI
product and final-package receipts first; copy raw evidence bytes unchanged into
a fresh view, then use the production guard against that explicitly derived DLL.
"""
    from audit_context import decode
    from native_stream_package import COMMANDS, _directory, _file
    evidence = _directory(context.evidence/'native')
    raw = {'conformance.json': _file(evidence, 'conformance.json', 1024 * 1024)}
    report = decode(raw['conformance.json'])
    assert report['commit'] == context.commit and report['status'] == 'passed'
    products = report['build_products']
    matching = [row for row in products if row.get('name') == 'RebaseWindowsAudio.dll']
    assert len(matching) == 1, 'Missing or duplicate native DLL build receipt'
    observed = {'name':'RebaseWindowsAudio.dll', 'bytes':len(dll), 'sha256':hashlib.sha256(dll).hexdigest()}
    assert matching[0] == observed, 'Archived native DLL differs from native CI product receipt'
    final = decode((context.evidence/'native-stream-package.json').read_bytes())
    assert final['status'] == 'passed' and final['commit'] == context.commit
    assert final['native_dll'] == observed, 'Archived DLL differs from final CI package guard'
    assert final['native_report_sha256'] == hashlib.sha256(raw['conformance.json']).hexdigest()
    for name in COMMANDS:
        raw[name+'.log'] = _file(evidence, name+'.log', 16 * 1024 * 1024)
    for name, limit in (('lifecycle.xml', 2 * 1024 * 1024), ('bounded-stream.json', 1024 * 1024),
                        ('endpoint-probe.json', 1024 * 1024)):
        raw[name] = _file(evidence, name, limit)
    view = context.output/'native-verification-view'
    view.mkdir(exist_ok=False)
    for name, data in raw.items():
        context.write_once(view/name, data)
    (view/'build').mkdir()
    context.write_once(view/'build/RebaseWindowsAudio.dll', dll)
    provenance = {
        'schema':'rebase.derived-native-audit-view.v1', 'source_commit':context.commit,
        'workflow_id':context.run_id, 'original_downloaded_evidence_modified':False,
        'build_binary_independently_downloaded':False,
        'dll_origin':'Rebase/RebaseWindowsAudio.dll from the audited package ZIP',
        'derived_view_path':'native-verification-view/build/RebaseWindowsAudio.dll',
        'dll':observed,
        'zip_sha256':hashlib.sha256(context.archive.read_bytes()).hexdigest(),
        'native_build_product_receipt_sha256':hashlib.sha256(raw['conformance.json']).hexdigest(),
        'final_ci_package_receipt_sha256':hashlib.sha256((context.evidence/'native-stream-package.json').read_bytes()).hexdigest(),
        'raw_evidence_copies':[{'path':'native/'+name, 'bytes':len(data), 'sha256':hashlib.sha256(data).hexdigest()}
                              for name,data in sorted(raw.items())],
        'boundary':'The derived build-path DLL is copied from the audited ZIP after exact CI product/final-package hash checks. '
                   'It is not an independently downloaded build product. PE exports are reparsed from these archived bytes.'}
    context.write_json('native-verification-view-provenance.json', provenance)
    return view, provenance


def verify(context, app, smoke, files, gates, window_gate):
    from audit_context import decode
    from cpr_audition_gate import require_cpr_audition, require_cpr_audition_window
    from source_stream_gate import require_receipt
    from source_stream_window_gate import require_source_stream_window
    from documents_window_gate import require_documents_window
    from windows_automation_gate import require_automation_window
    from native_stream_package import validate_native_stream_package

    def sha(data): return hashlib.sha256(data).hexdigest()
    def read(name): return decode((context.evidence / name).read_bytes())
    counts = context.counts
    expected = decode(context.source('Application/Tests/Fixtures/SourceAudition/expected.json'))
    short_bytes = context.source('Application/Tests/Fixtures/SourceAuditionModes/expected.json')
    long_bytes = context.source('Application/Tests/Fixtures/SourceStreamTimelines/expected.json')
    short, long = decode(short_bytes), decode(long_bytes)
    example_bytes = context.source('Application/Examples/Rebase Preview.rebaseproj/Project.json')
    example = decode(example_bytes)
    render_lock = decode(context.source('Application/scripts/example-render-lock.json'))
    helper_hash = files['rebase-session.exe']['sha256']
    worker_records, mode_records = [], []
    for prefix, mode_name, stream_name, helper in (
        ('packaged', 'packaged-cpr-audition-modes.json', 'packaged-source-stream.json', helper_hash),
        ('shared', 'shared/cpr-audition-modes.json', 'shared/source-stream.json', None),
    ):
        modes, stream = read(mode_name), read(stream_name)
        mode_summary = require_cpr_audition(modes, short, sha(short_bytes), helper)
        stream_summary = require_receipt(stream, short, long, sha(short_bytes), sha(long_bytes), helper, modes)
        assert len(modes['checks']) == counts['audition_checks']
        assert len(modes['scenarios']) == counts['audition_scenarios']
        assert len(stream['checks']) == counts['stream_checks']
        assert len(stream['scenarios']) == counts['stream_scenarios']
        assert modes['helper_sha256'] == stream['helper_sha256']
        mode_records.append(modes); worker_records.append(stream)
        if prefix == 'packaged':
            mode_summary['receipt_sha256'] = sha((context.evidence / mode_name).read_bytes())
            stream_summary['receipt_sha256'] = sha((context.evidence / stream_name).read_bytes())
            assert app['cpr_audition_control'] == mode_summary
            assert app['source_stream_control'] == stream_summary
        else:
            shared = read('shared/conformance.json')
            mode_summary['receipt_sha256'] = sha((context.evidence / mode_name).read_bytes())
            stream_summary['receipt_sha256'] = sha((context.evidence / stream_name).read_bytes())
            assert shared['cpr_audition_control'] == mode_summary
            assert shared['source_stream_control'] == stream_summary
    # Independently compare the two separately built helper observations,
    # including observed logical-block ordering, not only final PCM equality.
    stream_fields = ('mode', 'sample_rate', 'start_frame', 'total_frames', 'frames', 'pcm_sha256',
                     'normalized_proof_sha256', 'observed_logical_blocks',
                     'observed_peak_logical_frames', 'logical_blocks_sha256')
    indexed = [{row['case']: row for row in receipt['scenarios']} for receipt in worker_records]
    assert set(indexed[0]) == set(indexed[1])
    for key, row in indexed[0].items():
        assert all(row[field] == indexed[1][key][field] for field in stream_fields), 'Shared/packaged stream output differs'
    indexed_modes = [{(row['case'], row['mode'], row['seek']): row for row in receipt['scenarios']} for receipt in mode_records]
    assert indexed_modes[0] == indexed_modes[1], 'Shared/packaged snapshot output differs'

    window_gate.require_pinned_header_scroll(smoke)
    window_gate.require_musical_ruler(smoke)
    window_gate.require_workspace_layout(smoke, context.evidence, expected)
    window_gate.require_top_rows(smoke, context.evidence, sha(example_bytes), expected)
    require_automation_window(smoke, context.evidence, example, render_lock)
    modes_window = require_cpr_audition_window(smoke, context.evidence, short, mode_records[0])
    stream_window = require_source_stream_window(smoke, context.evidence, long, worker_records[0], sha(long_bytes))
    assert app['source_modes_window_control'] == modes_window
    assert app['source_stream_window_control'] == stream_window
    example_manifest = context.source('Application/Examples/example.json')
    documents_window = require_documents_window(smoke, context.evidence, example_manifest, helper_hash)
    assert app['documents_window_control'] == documents_window
    assert documents_window['native_checks'] == counts['documents_window_checks']
    assert documents_window['phases'] == counts['documents_phases']
    document_controls = read('documents-window-controls/observation.json')
    assert document_controls == app['documents_window_gate_controls']
    assert document_controls['schema'] == 'rebase.documents-window-gate-controls.v1'
    assert document_controls['outcome'] == 'passed'
    assert document_controls['evidence_class'] == 'authored-receipt-and-pixel-mutation-controls'
    assert document_controls['control_count'] == len(document_controls['checks']) == counts['documents_gate_checks']
    assert all(row['passed'] is True and row['expected'] == row['observed'] for row in document_controls['checks'])
    assert len({row['name'] for row in document_controls['checks']}) == len(document_controls['checks'])
    assert document_controls['example_manifest_sha256'] == sha(example_manifest)
    assert document_controls['gate_sha256'] == sha(context.source('Application/scripts/documents_window_gate.py'))
    assert document_controls['instrument_sha256'] == sha(context.source('Application/scripts/test_documents_window_gate.py'))
    assert document_controls['controls_log_sha256'] == sha((context.evidence/'documents-window-controls/controls.log').read_bytes())
    assert all(document_controls[key] is False for key in
               ('native_wpf_executed', 'helper_executed', 'physical_input_tested', 'playback_tested'))
    # Both committed gates independently decode CRC/DPI/alpha, compare the
    # recorded histogram and preserve the measured near-opaque254 policy.
    for record in (smoke['source_stream_window']['capture'], smoke['documents']['capture']):
        diagnostic = read(record['file'].removesuffix('.png') + '-alpha.json')
        assert set(diagnostic) == {'screenshot', 'png_sha256', 'alpha_coverage'}
        assert diagnostic == {'screenshot': record['file'], 'png_sha256': record['sha256'],
                              'alpha_coverage': record['alpha_coverage']}
        assert record['alpha_coverage']['root_background_alpha'] == 255
        assert record['alpha_coverage']['alpha_below_254_pixels'] == 0
    bounds = smoke['window_bounds']
    for name in ('native-app-visual.png', 'native-source-visual.png', 'native-timeline-scroll-visual.png'):
        window_gate.require_window_visual(context.evidence / name, bounds)
    review = smoke['cpr_review']
    window_gate.require_cpr_review_layout(context.evidence/'native-cpr-review-visual.png',
                                         review['window_bounds'], review['capture_layout'])
    window_gate.require_cpr_review_layout(context.evidence/'native-cpr-review-minimum-error-visual.png',
                                         review['minimum_error_bounds'], review['minimum_error_layout'], minimum_error=True)

    reader = read('managed-source-stream-reader.json')
    assert reader['suite'] == 'actual-shared-helper-managed-stream-reader'
    assert reader['checks'] == counts['managed_reader_checks'] and reader['failures'] == 0
    assert reader['helper_responsive_after_cancellation'] is True
    assert reader['device_playback_tested'] is False and reader['wpf_runtime_tested'] is False
    assert reader['project_open'] == 'explicit-private-copy'
    records = reader['records']
    pairs = {(case['name'], point) for case in long['cases'] for point in ('tail', 'eof', 'cancel')}
    assert len(records) == counts['managed_reader_workers'] == len(pairs)
    assert {(row['fixture'], row['point']) for row in records} == pairs
    for row in records:
        case = next(case for case in long['cases'] if case['name'] == row['fixture'])
        mode = next(mode for mode in case['modes'] if mode['mode'] == 'nativeTrackSavedProjectClock')
        total, point = mode['totalFrames'], row['point']
        start = total - 1000 if point == 'tail' else total if point == 'eof' else 0
        assert row['first'] == start and row['total'] == total and row['worker_joined'] is True
        assert type(row['frames']) is int and type(row['peak_payload_frames']) is int
        assert 0 <= row['peak_payload_frames'] <= 65536
        if point == 'tail': assert row['frames'] == 1000 and row['pcm_sha256'] == mode['tailPCMSHA256']
        elif point == 'eof': assert row['frames'] == 0 and row['pcm_sha256'] == sha(b'')
        else: assert 0 < row['frames'] <= 65536
    assert app['managed_source_stream_reader'] == {
        'receipt_sha256': sha((context.evidence/'managed-source-stream-reader.json').read_bytes()),
        'workers': len(records), 'checks': reader['checks'], 'helper_sha256': helper_hash, 'device_playback_tested': False}
    controls = read('source-stream-window-controls/observation.json')
    assert controls['schema'] == 'rebase.source-stream-window-gate-controls.v1' and controls['outcome'] == 'passed'
    assert controls['check_count'] == len(controls['checks']) == counts['window_gate_checks']
    assert len(controls['real_workers']) == counts['window_gate_workers']
    assert controls['process_receipt_sha256'] == sha((context.evidence/'packaged-source-stream.json').read_bytes())
    assert controls['helper_sha256'] == helper_hash and controls['fixture_sha256'] == sha(long_bytes)
    assert controls['controls_log_sha256'] == sha((context.evidence/'source-stream-window-controls/controls.log').read_bytes())
    assert controls['gate_sha256'] == sha(context.source('Application/scripts/source_stream_window_gate.py'))
    assert controls['instrument_sha256'] == sha(context.source('Application/scripts/test_source_stream_window_gate.py'))
    assert all(controls[key] is False for key in ('native_wpf_executed', 'physical_input_tested',
                                                 'audio_device_playback_measured', 'reference_execution'))
    assert app['source_stream_window_gate_controls'] == controls

    # The workflow omits build binaries. Preserve all downloaded records and
    # explicitly disclose the provenance of the derived guard input.
    stage = context.output / 'native-stage'
    stage.mkdir(exist_ok=False)
    with zipfile.ZipFile(context.archive) as package:
        dll = package.read('Rebase/RebaseWindowsAudio.dll')
    view, provenance = native_verification_view(context, dll)
    context.write_once(stage/'RebaseWindowsAudio.dll', dll)
    native = validate_native_stream_package(stage, view, context.commit)
    assert native == read('native-stream-package.json') == app['native_stream_package']
    native_controls = read('native-package-controls/observation.json')
    assert native_controls == app['native_stream_package_gate_controls']
    assert native_controls['schema'] == 'rebase.native-stream-package-authored-controls.v1'
    assert native_controls['status'] == 'passed' and native_controls['test_methods'] == 13
    assert native_controls['scenarios'] == 80 and native_controls['skipped'] == 1
    assert native_controls['failures'] == native_controls['errors'] == 0
    assert native_controls['real_pe_parser_exercised'] is False
    assert native_controls['windows_execution_tested'] is False and native_controls['physical_playback_tested'] is False
    assert native_controls['guard_sha256'] == sha(context.source('Application/scripts/native_stream_package.py'))
    assert native_controls['harness_sha256'] == sha(context.source('Application/scripts/test_native_stream_package.py'))
    return {'host_controls': counts['host_controls'], 'native_window_checks': counts['wpf_checks'],
            'snapshot_checks': counts['audition_checks'], 'snapshot_scenarios': counts['audition_scenarios'],
            'stream_checks': counts['stream_checks'], 'stream_scenarios': counts['stream_scenarios'],
            'managed_reader_checks': reader['checks'], 'managed_reader_workers': len(records),
            'window_gate_checks': controls['check_count'], 'window_gate_real_workers': len(controls['real_workers']),
            'documents_gate_checks': document_controls['control_count'], 'documents_window': documents_window,
            'capture_alpha_diagnostics_match_decoded_pixels': True,
            'packaged_and_shared_output_and_logical_order_match': True,
            'full_window_proofs_and_capture_bounds_validated': True,
            'long_fixture_sha256': sha(long_bytes), 'short_fixture_sha256': sha(short_bytes),
            'native_stream_package': native, 'native_verification_view':provenance,
            'build_binary_independently_downloaded':False, 'source_gate_files': gates,
            'physical_input_tested_by_audit': False, 'device_playback_tested_by_audit': False,
            'binaries_executed_by_audit': False, 'pixel_content_human_review': 'separate'}
