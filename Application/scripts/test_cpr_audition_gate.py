#!/usr/bin/env python3
"""Mutate a real helper receipt and authored UI records to challenge the gate.

Authored PNGs/geometry below test the instrument, not a native window or playback.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import struct
import unittest
import zlib

import cpr_audition_gate as gate


def sha(data):
    return hashlib.sha256(data).hexdigest()


def png(width, height):
    def chunk(tag, body):
        return struct.pack('>I', len(body)) + tag + body + struct.pack('>I', zlib.crc32(tag + body))
    row = b'\0' + bytes(value for x in range(width) for value in (x % 256, (x * 13) % 256, (x * 31) % 256, 255))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(row * height)) + chunk(b'IEND', b''))


class Controls(unittest.TestCase):
    baseline = expected = output = fixture_sha = None

    def setUp(self):
        self.receipt = copy.deepcopy(self.baseline)
        self.work = self.output / self._testMethodName; self.work.mkdir()

    def validate(self):
        return gate.require_cpr_audition(self.receipt, self.expected, self.fixture_sha)

    def rejected(self):
        with self.assertRaises(ValueError): self.validate()

    def test_actual_helper_receipt_admitted(self):
        self.assertEqual(self.validate()['scenarios'], 48)

    def test_failed_status(self): self.receipt['status'] = 'failed'; self.rejected()
    def test_wrong_schema(self): self.receipt['schema'] += '.unexpected'; self.rejected()
    def test_wrong_fixture(self): self.receipt['fixture_manifest_sha256'] = '0' * 64; self.rejected()
    def test_missing_mode(self): self.receipt['scenarios'].pop(); self.rejected()
    def test_duplicate_mode(self): self.receipt['scenarios'][-1] = self.receipt['scenarios'][0]; self.rejected()
    def test_false_gate(self): self.receipt['gates']['covered_media_rejected'] = False; self.rejected()
    def test_numeric_gate(self): self.receipt['gates']['read_only'] = 1; self.rejected()
    def test_device_claim(self): self.receipt['playback_tested'] = True; self.rejected()
    def test_reference_claim(self): self.receipt['reference_execution'] = True; self.rejected()
    def test_wrong_source(self): self.receipt['scenarios'][0]['source_sha256'] = '0' * 64; self.rejected()
    def test_wrong_media(self): self.receipt['scenarios'][0]['media_sha256'] = '0' * 64; self.rejected()
    def test_boolean_frame_count(self): self.receipt['scenarios'][0]['frames'] = True; self.rejected()
    def test_wrong_clock(self): self.receipt['scenarios'][0]['sample_rate'] = 32_000; self.rejected()
    def test_empty_hash(self): self.receipt['scenarios'][0]['wav_sha256'] = ''; self.rejected()
    def test_unknown_metadata_field(self): self.receipt['scenarios'][0]['secret'] = 'unexpected'; self.rejected()
    def test_wrong_eof_digest(self):
        next(r for r in self.receipt['scenarios'] if r['seek'] == 'eof')['pcm_sha256'] = '0' * 64; self.rejected()
    def test_rewind_changed_pcm(self):
        next(r for r in self.receipt['scenarios'] if r['seek'] == 'rewind')['pcm_sha256'] = '0' * 64; self.rejected()
    def test_rewind_changed_proof(self):
        next(r for r in self.receipt['scenarios'] if r['seek'] == 'rewind')['normalized_manifest_sha256'] = '0' * 64; self.rejected()
    def test_inspection_missing_mode(self): self.receipt['inspection'][0]['modes'].pop(); self.rejected()
    def test_inspection_mismatched_extent(self): self.receipt['inspection'][0]['modes'][0]['frames'] += 1; self.rejected()
    def test_inspection_unavailable(self): self.receipt['inspection'][0]['modes'][0]['available'] = False; self.rejected()
    def test_helper_identity_binding(self):
        with self.assertRaises(ValueError): gate.require_cpr_audition(self.receipt, self.expected, self.fixture_sha, '0' * 64)

    def window(self):
        phases = [{'fixture': name, 'revision': n + 1, 'before_sha256': sha(name.encode()), 'after_sha256': sha(name.encode())}
                  for n, name in enumerate(('single', 'overlap'))]
        exports = []
        checks = {'source-modes-all-eight-available', 'source-modes-covered-contributor-retained',
                  'source-modes-existing-export-preserved', 'source-modes-unavailable-reason-and-controls',
                  'source-modes-minimum-layout-captured'}
        for name in ('single', 'overlap'):
            checks.update('source-modes-' + name + '-' + suffix for suffix in
                          ('open-preserves-state', 'owner-close-guarded', 'refresh-read-only', 'close-preserves-state'))
        for row in self.receipt['scenarios']:
            if row['seek'] != 'full' or row['case'] == 'overlap' and row['mode'] != 'nativeTrackSavedProjectClock': continue
            counts = (3, 3) if row['case'] == 'overlap' else (1, 1) if row['mode'] == 'nativeTrackSavedProjectClock' else (0, 0)
            exports.append({k: row[k] for k in ('mode', 'sample_rate', 'frames', 'source_sha256', 'media_sha256', 'wav_sha256')} |
                {'fixture': row['case'], 'manifest_sha256': sha(b'authored-manifest'), 'contributors': counts[0], 'fragments': counts[1],
                 'state_sha256': sha(row['case'].encode())})
            checks.update('source-modes-' + row['case'] + '-' + row['mode'] + '-' + suffix for suffix in ('selection', 'export'))
        unavailable = next(r['mode'] for r in self.receipt['inspection'][1]['modes'] if not r['available'])
        captures = []
        for name, mode in [('converted', 'nativeMode2ProjectRate'), ('track', 'nativeTrackSavedProjectClock'), ('unavailable', unavailable)]:
            filename = 'native-source-modes-' + name + '-visual.png'; data = png(724, 501); (self.work / filename).write_bytes(data)
            controls = [{'name': 'modes', 'x': 12, 'y': 40, 'width': 260, 'height': 300, 'enabled': True}]
            for index, control in enumerate(('refresh', 'export', 'play', 'pause', 'stop', 'close')):
                controls.append({'name': control, 'x': 12 + index * 100, 'y': 450, 'width': 90, 'height': 28,
                                 'enabled': not (name == 'unavailable' and control in ('play', 'export'))})
            captures.append({'file': filename, 'sha256': sha(data), 'frame_excluded': True, 'selected_mode': mode,
                'details': 'Authored layout control, not a native window', 'message': 'Authored reason' if name == 'unavailable' else '',
                'bounds': {'outer_width_dip': 740, 'outer_height_dip': 540, 'width_dip': 724, 'height_dip': 501,
                           'dpi_scale_x': 1, 'dpi_scale_y': 1, 'pixel_width': 724, 'pixel_height': 501}, 'controls': controls})
        record = dict.fromkeys(('tested', 'all_eight_exports_verified', 'complete_track_covered_contributor_verified',
            'inspection_and_export_read_only', 'owner_close_guarded', 'unavailable_controls_guarded', 'existing_export_preserved'), True)
        record.update(dict.fromkeys(('audio_device_playback_tested', 'physical_input_tested', 'native_file_pickers_tested',
                                    'native_frame_visual_tested'), False))
        record.update(exports=exports, phases=phases, captures=captures)
        return {'source_modes': record, 'checks': sorted(checks)}

    def window_rejected(self, smoke):
        with self.assertRaises(ValueError): gate.require_cpr_audition_window(smoke, self.work, self.expected, self.receipt)

    def test_authored_window_gate_baseline(self):
        self.assertEqual(gate.require_cpr_audition_window(self.window(), self.work, self.expected, self.receipt)['exports'], 9)
    def test_window_changed_wav(self):
        smoke = self.window(); smoke['source_modes']['exports'][0]['wav_sha256'] = '0' * 64; self.window_rejected(smoke)
    def test_window_dropped_covered_contributor(self):
        smoke = self.window(); smoke['source_modes']['exports'][-1]['contributors'] = 2; self.window_rejected(smoke)
    def test_window_changed_state(self):
        smoke = self.window(); smoke['source_modes']['phases'][0]['after_sha256'] = '0' * 64; self.window_rejected(smoke)
    def test_window_missing_required_action(self):
        smoke = self.window(); smoke['checks'].remove('source-modes-existing-export-preserved'); self.window_rejected(smoke)
    def test_window_clipped_footer(self):
        smoke = self.window(); smoke['source_modes']['captures'][0]['controls'][-1]['y'] = 510; self.window_rejected(smoke)
    def test_window_unavailable_export_enabled(self):
        smoke = self.window(); smoke['source_modes']['captures'][-1]['controls'][2]['enabled'] = True; self.window_rejected(smoke)
    def test_window_wrong_dpi_bounds(self):
        smoke = self.window(); smoke['source_modes']['captures'][0]['bounds']['dpi_scale_y'] = 2; self.window_rejected(smoke)
    def test_window_truncated_png_even_with_new_hash(self):
        smoke = self.window(); c = smoke['source_modes']['captures'][0]; path = self.work / c['file']
        data = path.read_bytes()[:-10]; path.write_bytes(data); c['sha256'] = sha(data); self.window_rejected(smoke)
    def test_window_corrupt_png_even_with_new_hash(self):
        smoke = self.window(); c = smoke['source_modes']['captures'][0]; path = self.work / c['file']
        data = bytearray(path.read_bytes()); data[-20] ^= 1; path.write_bytes(data); c['sha256'] = sha(data); self.window_rejected(smoke)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    Controls.baseline = json.loads(args.receipt.read_bytes()); Controls.expected = json.loads(args.fixture.read_bytes())
    Controls.fixture_sha = sha(args.fixture.read_bytes()); Controls.output = args.output.absolute()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Controls)
    with (args.output / 'controls.log').open('w') as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    receipt = {'schema': 'rebase.cpr-audition-gate-controls.v1', 'status': 'passed' if result.wasSuccessful() else 'failed',
        'scope': 'Authored rejection controls derived from one actual helper receipt plus synthetic UI geometry/PNGs; not native window or cross-platform evidence',
        'input_receipt_sha256': sha(args.receipt.read_bytes()), 'tests': result.testsRun, 'failures': len(result.failures),
        'errors': len(result.errors), 'skipped': len(result.skipped), 'gate_sha256': sha(Path(gate.__file__).read_bytes()),
        'harness_sha256': sha(Path(__file__).read_bytes()), 'failed_cases': [test.id().split('.')[-1] for test, _ in result.failures + result.errors]}
    (args.output / 'observation.json').write_text(json.dumps(receipt, indent=2) + '\n'); print(json.dumps(receipt))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
