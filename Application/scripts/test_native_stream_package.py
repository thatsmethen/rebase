"""Authored package-guard mutation controls; no PE execution or Windows-run claim."""
import argparse
import copy
import hashlib
import json
import os
import stat
from types import SimpleNamespace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import native_stream_package as guard
from test_windows_native_audio_gate import passing_stream_receipt

COMMIT = 'a' * 40
DLL = b'MZ-authored-package-control-not-an-executable'
XML = ('<testsuite><testcase name="native_audio_portable_lifecycle"/>'
       '<testcase name="native_audio_rate_conversion"/><testcase name="native_audio_bounded_stream"/></testsuite>')


def passing_pe():
    return {'machine': 0x8664, 'magic': 0x20b, 'is_dll': True,
            'exports': [{'name': name, 'rva': 4096 + index * 16, 'forwarder': None, 'executable': True}
                        for index, name in enumerate(guard.STREAM_EXPORTS)]}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


class Controls(unittest.TestCase):
    output = None
    scenarios = 0

    def run_case(self, mutate=None, reject=True, pe=None, expected_commit=COMMIT):
        type(self).scenarios += 1
        with tempfile.TemporaryDirectory(prefix='authored-native-package-', dir=self.output) as directory:
            folder = Path(directory)
            stage, native = folder / 'stage', folder / 'native'
            stage.mkdir(); native.mkdir(); (native / 'build').mkdir()
            (stage / 'RebaseWindowsAudio.dll').write_bytes(DLL)
            (native / 'build/RebaseWindowsAudio.dll').write_bytes(DLL)
            stream = passing_stream_receipt()
            endpoint = {'schema': 1, 'suite': 'windows-wasapi-native-probe', 'wasapi_compiled': True,
                        'allow_audio': False, 'playback_attempted': False, 'playback_tested': False,
                        'audible_output_measured': False, 'outcome': 'unavailable-no-endpoint', 'result': 3}
            report = {'schema': 'rebase.windows-native-audio-ci.v1', 'status': 'passed', 'configuration': 'Release',
                      'mode': 'windows-native', 'platform': 'Windows', 'architecture': 'AMD64', 'commit': COMMIT,
                      'native_library_built': True, 'playback_tested': False, 'audible_output_measured': False,
                      'tests': {'count': 3, 'skipped': 0, 'failures': 0}, 'portable_bounded_stream': stream,
                      'endpoint_probe': {'outcome': 'unavailable-no-endpoint', 'exit_code': 77, 'playback_tested': False},
                      'commands': [{'name': name, 'log': name + '.log', 'exit_code': 77 if name == 'endpoint-probe' else 0}
                                   for name in guard.COMMANDS],
                      'build_products': [{'name': name, 'bytes': len(DLL), 'sha256': hashlib.sha256(DLL).hexdigest()}
                                         for name in sorted(guard.PRODUCTS)]}
            for name in guard.COMMANDS: (native / (name + '.log')).write_bytes(b'')
            write_json(native / 'bounded-stream-controls.log', stream)
            write_json(native / 'bounded-stream.json', stream)
            write_json(native / 'endpoint-probe.json', endpoint)
            write_json(native / 'conformance.json', report)
            (native / 'lifecycle.xml').write_text(XML, encoding='utf-8')
            state = {'folder': folder, 'stage': stage, 'native': native, 'report': report, 'stream': stream,
                     'endpoint': endpoint, 'pe': passing_pe() if pe is None else pe}
            if mutate: mutate(state)
            with patch.object(guard, '_inspect_pe', return_value=state['pe']) as inspector:
                if reject:
                    with self.assertRaises((ValueError, OSError, TypeError)):
                        guard.validate_native_stream_package(stage, native, expected_commit)
                else:
                    result = guard.validate_native_stream_package(stage, native, expected_commit)
                    inspector.assert_called_once_with(DLL)
                    self.assertEqual(result['native_dll']['sha256'], hashlib.sha256(DLL).hexdigest())
                    self.assertEqual(result['required_exports'], list(guard.STREAM_EXPORTS))
                    self.assertFalse(result['dll_loaded_by_guard'])
                    self.assertFalse(result['physical_playback_tested'])
                    self.assertNotIn(str(folder), json.dumps(result))
                    return result

    @staticmethod
    def report_change(field, value):
        def change(state):
            state['report'][field] = value
            write_json(state['native'] / 'conformance.json', state['report'])
        return change

    def test_positive_authored_binding_and_silent_logs(self):
        self.run_case(reject=False)

    def test_expected_source_identity_is_mandatory(self):
        for value in (None, '', True, 'a' * 39, 'A' * 40, 'b' * 40):
            with self.subTest(value=value): self.run_case(expected_commit=value)

    def test_source_build_mode_and_claims(self):
        mutations = {'schema': 'other', 'status': 'failed', 'configuration': 'Debug', 'mode': 'portable-lifecycle-only',
                     'platform': 'Darwin', 'architecture': 'arm64', 'commit': 'b' * 40, 'native_library_built': 1,
                     'playback_tested': True, 'audible_output_measured': True, 'error': 'retained failure',
                     'artifact_sanitization_error': 'retained failure'}
        for key, value in mutations.items():
            with self.subTest(field=key): self.run_case(self.report_change(key, value))

    def test_missing_fields_rejected(self):
        for key in ('commit', 'native_library_built', 'tests', 'portable_bounded_stream', 'commands', 'build_products'):
            def mutate(state):
                del state['report'][key]; write_json(state['native'] / 'conformance.json', state['report'])
            with self.subTest(field=key): self.run_case(mutate)

    def test_command_execution_and_paths(self):
        for mutation in ('missing', 'duplicate', 'failed', 'bool', 'timeout', 'path', 'log_missing'):
            def mutate(state):
                commands = state['report']['commands']
                if mutation == 'missing': commands.pop()
                elif mutation == 'duplicate': commands[2] = copy.deepcopy(commands[1])
                elif mutation == 'failed': commands[4]['exit_code'] = 1
                elif mutation == 'bool': commands[4]['exit_code'] = False
                elif mutation == 'timeout': commands[4]['timed_out'] = True
                elif mutation == 'path': commands[4]['log'] = '../outside.log'
                else: (state['native'] / 'build.log').unlink()
                write_json(state['native'] / 'conformance.json', state['report'])
            with self.subTest(mutation=mutation): self.run_case(mutate)

    def test_staged_and_built_byte_identity(self):
        for mutation in ('staged_changed', 'built_changed', 'both_changed', 'missing', 'record_size', 'record_sha', 'duplicate_product', 'missing_product'):
            def mutate(state):
                staged = state['stage'] / 'RebaseWindowsAudio.dll'; built = state['native'] / 'build/RebaseWindowsAudio.dll'
                product = next(item for item in state['report']['build_products'] if item['name'] == 'RebaseWindowsAudio.dll')
                if mutation == 'staged_changed': staged.write_bytes(DLL + b'!')
                elif mutation == 'built_changed': built.write_bytes(DLL + b'!')
                elif mutation == 'both_changed': staged.write_bytes(DLL + b'!'); built.write_bytes(DLL + b'!')
                elif mutation == 'missing': staged.unlink()
                elif mutation == 'record_size': product['bytes'] += 1
                elif mutation == 'record_sha': product['sha256'] = '0' * 64
                elif mutation == 'duplicate_product': state['report']['build_products'][0] = copy.deepcopy(state['report']['build_products'][1])
                elif mutation == 'missing_product': state['report']['build_products'].pop()
                write_json(state['native'] / 'conformance.json', state['report'])
            with self.subTest(mutation=mutation): self.run_case(mutate)

    def test_changed_native_stream_execution(self):
        for mutation in ('missing_gate', 'zero_checks', 'wrong_hash', 'wrong_storage', 'divergent_embedded', 'divergent_log', 'boolean_log'):
            def mutate(state):
                record = copy.deepcopy(state['stream'])
                if mutation == 'missing_gate': record['gates'].pop('snapshot_exact')
                elif mutation == 'zero_checks': record['checks'] = 0
                elif mutation == 'wrong_hash': record['long_fnv1a64'] = '0'
                elif mutation == 'wrong_storage': record['max_pcm_storage_case']['bytes'] += 8
                elif mutation == 'divergent_embedded': state['report']['portable_bounded_stream'] = copy.deepcopy(record); state['report']['portable_bounded_stream']['checks'] += 1
                elif mutation == 'divergent_log': record['checks'] += 1
                elif mutation == 'boolean_log': record['physical_playback_tested'] = 0
                if mutation.endswith('log'): write_json(state['native'] / 'bounded-stream-controls.log', record)
                else: write_json(state['native'] / 'bounded-stream.json', record)
                write_json(state['native'] / 'conformance.json', state['report'])
            with self.subTest(mutation=mutation): self.run_case(mutate)

    def test_native_xml_and_counts(self):
        for mutation in ('empty', 'missing', 'skip', 'failure', 'duplicate', 'summary_bool'):
            def mutate(state):
                xml = XML
                if mutation == 'empty': xml = '<testsuite/>'
                elif mutation == 'missing': xml = xml.replace('<testcase name="native_audio_bounded_stream"/>', '')
                elif mutation == 'skip': xml = xml.replace('native_audio_bounded_stream"/>', 'native_audio_bounded_stream"><skipped/></testcase>')
                elif mutation == 'failure': xml = xml.replace('native_audio_bounded_stream"/>', 'native_audio_bounded_stream"><failure/></testcase>')
                elif mutation == 'duplicate': xml = xml.replace('native_audio_bounded_stream', 'native_audio_rate_conversion')
                elif mutation == 'summary_bool': state['report']['tests']['failures'] = False
                (state['native'] / 'lifecycle.xml').write_text(xml, encoding='utf-8')
                write_json(state['native'] / 'conformance.json', state['report'])
            with self.subTest(mutation=mutation): self.run_case(mutate)

    def test_pe_architecture_and_exports(self):
        for field, value in (('machine', 0x14c), ('magic', 0x10b), ('is_dll', False), ('exports', [])):
            pe = passing_pe(); pe[field] = value
            with self.subTest(field=field): self.run_case(pe=pe)
        for name in guard.STREAM_EXPORTS:
            pe = passing_pe(); pe['exports'] = [row for row in pe['exports'] if row['name'] != name]
            with self.subTest(missing=name): self.run_case(pe=pe)
        for key, value in (('rva', 0), ('rva', True), ('forwarder', 'other.dll.fake'), ('executable', False), ('executable', 1)):
            pe = passing_pe(); pe['exports'][0][key] = value
            with self.subTest(field=key): self.run_case(pe=pe)
        pe = passing_pe(); pe['exports'].append(copy.deepcopy(pe['exports'][0])); self.run_case(pe=pe)

    def test_probe_is_read_only_and_consistent(self):
        for mutation in ('played', 'schema_bool', 'summary_bool', 'wrong_result', 'wrong_exit'):
            def mutate(state):
                if mutation == 'played': state['endpoint']['playback_tested'] = True
                elif mutation == 'schema_bool': state['endpoint']['schema'] = True
                elif mutation == 'summary_bool': state['report']['endpoint_probe']['playback_tested'] = 0
                elif mutation == 'wrong_result': state['endpoint']['result'] = 0
                else: state['report']['commands'][-1]['exit_code'] = 0
                write_json(state['native'] / 'endpoint-probe.json', state['endpoint'])
                write_json(state['native'] / 'conformance.json', state['report'])
            with self.subTest(mutation=mutation): self.run_case(mutate)

    def test_json_duplicate_and_nonfinite_fields(self):
        for raw in ('{"status":"failed","status":"passed"}', '{"value":NaN}', '[]'):
            with self.subTest(raw=raw): self.run_case(lambda state: (state['native'] / 'conformance.json').write_text(raw))

    def test_windows_reparse_attribute_classification(self):
        for mode in (stat.S_IFREG, stat.S_IFDIR):
            type(self).scenarios += 1
            self.assertTrue(guard._redirected(SimpleNamespace(st_mode=mode, st_file_attributes=0x400)))
            self.assertFalse(guard._redirected(SimpleNamespace(st_mode=mode, st_file_attributes=0)))

    @unittest.skipIf(os.name == 'nt', 'Symbolic-link creation privilege is not assumed; Windows reparse attribute controls are separate.')
    def test_symlink_and_irregular_inputs(self):
        for kind in ('dll', 'report', 'ancestor'):
            def mutate(state):
                if kind == 'ancestor':
                    original = state['native'] / 'build'; moved = state['native'] / 'real-build'; original.rename(moved); original.symlink_to(moved, target_is_directory=True)
                else:
                    path = state['stage'] / 'RebaseWindowsAudio.dll' if kind == 'dll' else state['native'] / 'conformance.json'
                    moved = path.with_suffix('.authored-original'); path.rename(moved); path.symlink_to(moved)
            with self.subTest(kind=kind): self.run_case(mutate)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    Controls.output = args.output.resolve()
    with (args.output / 'controls.log').open('w', encoding='utf-8') as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    receipt = {'schema': 'rebase.native-stream-package-authored-controls.v1', 'status': 'passed' if result.wasSuccessful() else 'failed',
               'evidence_class': 'authored-synthetic-build-and-pe-metadata-controls', 'test_methods': result.testsRun,
               'scenarios': Controls.scenarios, 'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped),
               'real_pe_parser_exercised': False, 'windows_execution_tested': False, 'physical_playback_tested': False,
               'guard_sha256': hashlib.sha256(Path(guard.__file__).read_bytes()).hexdigest(),
               'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    write_json(args.output / 'observation.json', receipt)
    print(json.dumps(receipt)); return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
