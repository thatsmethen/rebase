"""Strict receipt boundary for forward-authored shared audition-mode controls."""
import hashlib
import math
import re

MODES = ('sourceRate', 'nativeTimelineSourceRate', 'nativeTimelineProjectClock',
         'nativeTimelineSavedProjectClock', 'nativeTrackSavedProjectClock',
         'nativeMode0ProjectRate', 'nativeMode1ProjectRate', 'nativeMode2ProjectRate')
GATES = ('all_eight_modes', 'read_only', 'explicit_mode', 'seek_fresh_cursor', 'eof_revalidated',
         'complete_track_provenance', 'covered_media_rejected', 'stale_rejected', 'invalid_rejected',
         'new_outputs_only', 'source_unchanged')
SCENARIO_FIELDS = {'case', 'mode', 'seek', 'source_sha256', 'media_sha256', 'sample_rate', 'frames',
                   'start_frame', 'total_frames', 'wav_sha256', 'pcm_sha256', 'normalized_manifest_sha256'}


def require(condition, detail):
    if not condition:
        raise ValueError('CPR audition control: ' + detail)


def digest(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None


def expected_rate(case, mode):
    return (case['events'][0]['rate'] if mode in MODES[:2] else
            case['savedRate'] if mode in MODES[3:5] else case['projectRate'])


def require_cpr_audition(receipt, expected, fixture_sha256, helper_sha256=None):
    require(isinstance(receipt, dict) and receipt.get('schema') == 'rebase.cpr-audition-modes-control.v1'
            and receipt.get('status') == 'passed' and receipt.get('evidence_class') == 'authored-shared-session-control',
            'missing successful authored process receipt')
    require(receipt.get('playback_tested') is False and receipt.get('reference_execution') is False,
            'receipt must preserve device/reference evidence boundaries')
    require(digest(fixture_sha256) and receipt.get('fixture_manifest_sha256') == fixture_sha256,
            'fixture identity differs from the checked-in control')
    require(digest(receipt.get('helper_sha256')) and (helper_sha256 is None or
            digest(helper_sha256) and receipt['helper_sha256'] == helper_sha256), 'helper identity differs')
    gates = receipt.get('gates')
    require(isinstance(gates, dict) and set(gates) == set(GATES) and all(gates[k] is True for k in GATES),
            'one or more required process gates did not pass')
    checks = receipt.get('checks')
    require(isinstance(checks, list) and 1 <= len(checks) <= 8192 and
            all(isinstance(x, str) and 0 < len(x) <= 2048 for x in checks), 'missing bounded executed check inventory')
    require(isinstance(expected, dict) and expected.get('schemaVersion') == 1 and
            expected.get('evidenceClass') == 'authored-synthetic-control', 'unsupported authored fixture schema')
    cases = {case['name']: case for case in expected['cases']}
    require(len(expected['cases']) == 2 and set(cases) == {'single', 'overlap'}, 'fixture cases differ')
    identities = {(case, mode, seek) for case in cases for mode in (MODES if case == 'single' else MODES[1:5])
                  for seek in ('full', 'odd', 'eof', 'rewind')}
    rows = receipt.get('scenarios')
    require(isinstance(rows, list) and len(rows) == len(identities), 'expected exactly 48 complete render scenarios')
    indexed = {}
    for row in rows:
        require(isinstance(row, dict) and set(row) == SCENARIO_FIELDS, 'scenario schema differs')
        identity = tuple(row[k] for k in ('case', 'mode', 'seek'))
        require(all(isinstance(k, str) for k in identity) and identity in identities and identity not in indexed,
                'duplicate or unknown scenario')
        indexed[identity] = row
        case, mode, seek = identity; control = cases[case]
        require(all(digest(row[k]) for k in ('source_sha256', 'media_sha256', 'wav_sha256', 'pcm_sha256',
                                            'normalized_manifest_sha256')), 'missing or malformed scenario digest')
        require(row['source_sha256'] == control['sourceSHA256'] and
                row['media_sha256'] == control['events'][0]['mediaSHA256'], 'source/media identity differs')
        require(type(row['sample_rate']) is int and row['sample_rate'] == expected_rate(control, mode),
                'mode clock differs from its independent fixture rate')
        require(all(type(row[k]) is int and 0 <= row[k] <= 32_000_000 for k in ('frames', 'start_frame', 'total_frames'))
                and row['total_frames'] > 1 and row['start_frame'] + row['frames'] == row['total_frames'],
                'invalid frame counts or start/length relationship')
        if seek in ('full', 'rewind'):
            require(row['start_frame'] == 0 and row['frames'] > 0, 'full/rewind start differs')
        elif seek == 'odd':
            require(row['start_frame'] == 1 and row['frames'] > 0, 'odd seek is not exactly one output frame')
        else:
            require(row['frames'] == 0 and row['start_frame'] == row['total_frames'] and
                    row['pcm_sha256'] == hashlib.sha256(b'').hexdigest(), 'EOF did not preserve an empty complete render')
    for (case, mode, seek), row in indexed.items():
        full = indexed[(case, mode, 'full')]
        require(row['total_frames'] == full['total_frames'], 'fresh seeks changed the available extent')
        if seek == 'rewind':
            require(all(row[k] == full[k] for k in ('frames', 'wav_sha256', 'pcm_sha256', 'normalized_manifest_sha256')),
                    'rewind output or normalized proof differs from the full render')
    inspection = receipt.get('inspection')
    require(isinstance(inspection, list) and len(inspection) == 2, 'expected both mode-availability inspections')
    inspected = set()
    for entry in inspection:
        require(isinstance(entry, dict) and entry.get('case') in cases and entry['case'] not in inspected,
                'duplicate or unknown inspection')
        inspected.add(entry['case']); available = entry.get('modes')
        require(isinstance(available, list) and len(available) == 8 and
                [row.get('mode') if isinstance(row, dict) else None for row in available] == list(MODES),
                'availability must project all eight modes in order')
        for row in available:
            require(type(row.get('available')) is bool, 'availability must be explicit')
            selected = entry['case'] == 'single' or row['mode'] in MODES[1:5]
            if selected:
                full = indexed[(entry['case'], row['mode'], 'full')]
                require(row['available'] is True and type(row.get('frames')) is int and row['frames'] == full['total_frames']
                        and type(row.get('sampleRate')) in (int, float) and math.isfinite(row['sampleRate'])
                        and row['sampleRate'] == full['sample_rate'], 'inspection differs from actual rendered extent')
    return {'fixture_manifest_sha256': fixture_sha256, 'helper_sha256': receipt['helper_sha256'],
            'scenarios': len(rows), 'checks': len(checks), 'gates': dict(gates)}


def require_cpr_audition_window(smoke, evidence, expected, process_receipt):
    """Bind actual WPF export actions/captures to the independently run helper."""
    import struct
    import zlib
    record = smoke.get('source_modes')
    flags = ('tested', 'all_eight_exports_verified', 'complete_track_covered_contributor_verified',
             'inspection_and_export_read_only', 'owner_close_guarded', 'unavailable_controls_guarded', 'existing_export_preserved')
    require(isinstance(record, dict) and all(record.get(k) is True for k in flags), 'native window gates incomplete')
    require(all(record.get(k) is False for k in ('audio_device_playback_tested', 'physical_input_tested',
                                               'native_file_pickers_tested', 'native_frame_visual_tested')),
            'native window evidence scope is unsupported')
    identities = {('single', mode) for mode in MODES} | {('overlap', 'nativeTrackSavedProjectClock')}
    checks = {'source-modes-all-eight-available', 'source-modes-covered-contributor-retained',
              'source-modes-existing-export-preserved', 'source-modes-unavailable-reason-and-controls',
              'source-modes-minimum-layout-captured'}
    for case in ('single', 'overlap'):
        checks.update('source-modes-' + case + '-' + suffix for suffix in
                      ('open-preserves-state', 'owner-close-guarded', 'refresh-read-only', 'close-preserves-state'))
    for case, mode in identities:
        checks.update('source-modes-' + case + '-' + mode + '-' + suffix for suffix in ('selection', 'export'))
    require(checks.issubset(smoke.get('checks', [])), 'native action check inventory incomplete')
    phases = record.get('phases')
    require(isinstance(phases, list) and len(phases) == 2 and [p.get('fixture') for p in phases] == ['single', 'overlap'],
            'missing independent window fixture phases')
    states = {}
    for p in phases:
        require(digest(p.get('before_sha256')) and p.get('before_sha256') == p.get('after_sha256')
                and type(p.get('revision')) is int and p['revision'] > 0, 'window inspection/export changed session state')
        states[p['fixture']] = p['before_sha256']
    rows = record.get('exports')
    require(isinstance(rows, list) and len(rows) == 9, 'expected eight event modes and one complete-track UI export')
    full = {(row['case'], row['mode']): row for row in process_receipt['scenarios'] if row['seek'] == 'full'}
    seen = set()
    for row in rows:
        require(isinstance(row, dict), 'malformed window export')
        identity = (row.get('fixture'), row.get('mode'))
        require(all(isinstance(x, str) for x in identity) and identity in identities and identity not in seen,
                'duplicate or unknown window export')
        seen.add(identity); control = full[identity]
        require(type(row.get('sample_rate')) in (int, float) and math.isfinite(row['sample_rate']) and
                row['sample_rate'] == control['sample_rate'] and type(row.get('frames')) is int and
                row['frames'] == control['frames'] and all(row.get(k) == control[k] for k in
                ('source_sha256', 'media_sha256', 'wav_sha256')) and digest(row.get('manifest_sha256')) and
                row.get('state_sha256') == states[identity[0]], 'window export differs from actual helper output/state')
        counts = (3, 3) if identity[0] == 'overlap' else (1, 1) if identity[1] == 'nativeTrackSavedProjectClock' else (0, 0)
        require(all(type(row.get(k)) is int and row[k] == value for k, value in zip(('contributors', 'fragments'), counts)),
                'complete contributor/fragment projection differs')
    names = {'native-source-modes-converted-visual.png': 'nativeMode2ProjectRate',
             'native-source-modes-track-visual.png': 'nativeTrackSavedProjectClock',
             'native-source-modes-unavailable-visual.png': None}
    captures = record.get('captures')
    require(isinstance(captures, list) and len(captures) == 3, 'missing source-mode visual states')
    captured = set()
    def number(value):
        require(type(value) in (int, float) and math.isfinite(value), 'nonfinite native capture geometry')
        return value
    for capture in captures:
        require(isinstance(capture, dict) and capture.get('file') in names and capture['file'] not in captured,
                'duplicate or unknown source-mode capture')
        name = capture['file']; captured.add(name)
        data = (evidence / name).read_bytes()
        require(len(data) > 1024 and data[:8] == b'\x89PNG\r\n\x1a\n' and sha256(data) == capture.get('sha256'),
                'source-mode PNG missing or changed')
        offset, chunks, image_data = 8, [], bytearray()
        while offset < len(data):
            require(offset + 12 <= len(data), 'truncated PNG chunk')
            size = struct.unpack_from('>I', data, offset)[0]; tag = data[offset + 4:offset + 8]
            require(size <= len(data) - offset - 12, 'truncated PNG payload')
            payload = data[offset + 8:offset + 8 + size]
            require(zlib.crc32(tag + payload) == struct.unpack_from('>I', data, offset + 8 + size)[0], 'PNG CRC mismatch')
            chunks.append(tag)
            if tag == b'IDAT': image_data.extend(payload)
            offset += size + 12
            if tag == b'IEND': break
        require(offset == len(data) and chunks[0] == b'IHDR' and chunks[-1] == b'IEND' and chunks.count(b'IHDR') == 1,
                'PNG envelope incomplete')
        width, height, depth, color, compression, filtering, interlace = struct.unpack_from('>IIBBBBB', data, 16)
        require(0 < width <= 4096 and 0 < height <= 4096 and (depth, color, compression, filtering, interlace) == (8, 6, 0, 0, 0),
                'unsupported bounded WPF PNG format')
        decoded_size = (width * 4 + 1) * height
        decoder = zlib.decompressobj(); decoded = decoder.decompress(image_data, decoded_size + 1)
        require(len(decoded) == decoded_size and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail,
                'PNG pixel stream incomplete')
        require(all(decoded[i * (width * 4 + 1)] in range(5) for i in range(height)), 'PNG row filter invalid')
        bounds = capture.get('bounds', {})
        cw, ch = number(bounds.get('width_dip')), number(bounds.get('height_dip'))
        dx, dy = number(bounds.get('dpi_scale_x')), number(bounds.get('dpi_scale_y'))
        ow, oh = number(bounds.get('outer_width_dip')), number(bounds.get('outer_height_dip'))
        require(0 < cw <= ow <= 740.5 and 0 < ch <= oh <= 540.5 and dx > 0 and dy > 0 and
                (width, height) == (math.ceil(cw * dx), math.ceil(ch * dy)) and
                type(bounds.get('pixel_width')) is int and type(bounds.get('pixel_height')) is int and
                (width, height) == (bounds['pixel_width'], bounds['pixel_height']) and capture.get('frame_excluded') is True,
                'PNG does not match the minimum client capture')
        selected = capture.get('selected_mode')
        require(selected in MODES and (names[name] is None or selected == names[name]), 'capture mode differs')
        if names[name] is None:
            unavailable = next(row for row in process_receipt['inspection'] if row['case'] == 'overlap')['modes']
            require(next(row for row in unavailable if row['mode'] == selected)['available'] is False and
                    isinstance(capture.get('message'), str) and bool(capture['message']), 'unavailable state lacks a real reason')
        require(isinstance(capture.get('details'), str) and bool(capture['details']), 'capture lacks mode details')
        controls = capture.get('controls')
        require(isinstance(controls, list) and len(controls) == 7 and {r.get('name') for r in controls} ==
                {'modes', 'refresh', 'export', 'play', 'pause', 'stop', 'close'}, 'source-mode controls incomplete')
        for row in controls:
            x, y, w, h = (number(row.get(k)) for k in ('x', 'y', 'width', 'height'))
            require(x >= -0.5 and y >= -0.5 and w > 0 and h > 0 and x + w <= cw + 0.5 and y + h <= ch + 0.5
                    and type(row.get('enabled')) is bool, 'source-mode control clipped or state missing')
            if row['name'] == 'modes': require(w >= 220 and h >= 250, 'mode list has no usable viewport')
            if row['name'] in ('export', 'play'):
                require(row['enabled'] is (names[name] is not None), 'available/unavailable action enablement differs')
    return {'exports': len(rows), 'captures': len(captures), 'checks': len(checks), 'read_only': True,
            'wav_hashes_match_independent_helper': True}


def sha256(data):
    return hashlib.sha256(data).hexdigest()
