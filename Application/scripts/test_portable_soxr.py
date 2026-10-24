#!/usr/bin/env python3
"""Authored dependency/staging controls; no native Windows execution claim."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

import portable_soxr as dependency


def sha(data):
    return hashlib.sha256(data).hexdigest()


class RuntimeControls(unittest.TestCase):
    output = None

    def setUp(self):
        self.work = self.output / self._testMethodName
        self.work.mkdir()
        self.runtime = self.work / 'input/soxr.dll'
        self.runtime.parent.mkdir()
        self.data = b'Authored runtime identity control; not executable'
        self.runtime.write_bytes(self.data)
        self.destination = self.work / 'products/release'

    def stage(self, digest=None):
        return dependency.stage_windows_runtime(self.runtime, self.destination, digest or sha(self.data))

    def test_stage_exact_bytes_and_path_free_receipt(self):
        result = self.stage()
        self.assertEqual((self.destination / 'soxr.dll').read_bytes(), self.data)
        self.assertEqual(result['sha256'], sha(self.data))
        self.assertNotIn(str(self.work), json.dumps(result))

    def test_identical_second_stage_is_idempotent(self):
        self.assertEqual(self.stage(), self.stage())

    def test_existing_other_runtime_preserved(self):
        self.destination.mkdir(parents=True)
        path = self.destination / 'soxr.dll'; path.write_bytes(b'other')
        with self.assertRaises(RuntimeError): self.stage()
        self.assertEqual(path.read_bytes(), b'other')

    def test_changed_runtime_before_stage(self):
        self.runtime.write_bytes(b'changed')
        with self.assertRaises(RuntimeError): self.stage()
        self.assertFalse(self.destination.exists())

    def test_missing_runtime(self):
        self.runtime.unlink()
        with self.assertRaises(OSError): self.stage()
        self.assertFalse(self.destination.exists())

    def test_malformed_digest(self):
        for value in (True, 'a' * 63, 'A' * 64, 'a' * 65):
            with self.subTest(value=str(value)):
                with self.assertRaises(RuntimeError): self.stage(value)
        self.assertFalse(self.destination.exists())

    def test_directory_runtime_rejected(self):
        self.runtime.unlink(); self.runtime.mkdir()
        with self.assertRaises(RuntimeError): self.stage()

    @unittest.skipIf(os.name == 'nt', 'Link privilege is not assumed; Windows reparse checks are source reviewed')
    def test_runtime_symlink_rejected(self):
        actual = self.work / 'actual.dll'; actual.write_bytes(self.data)
        self.runtime.unlink(); self.runtime.symlink_to(actual)
        with self.assertRaises(RuntimeError): self.stage()

    @unittest.skipIf(os.name == 'nt', 'Link privilege is not assumed; Windows reparse checks are source reviewed')
    def test_existing_destination_symlink_rejected(self):
        self.destination.mkdir(parents=True)
        (self.destination / 'soxr.dll').symlink_to(self.runtime)
        with self.assertRaises(RuntimeError): self.stage()

    @unittest.skipIf(os.name == 'nt', 'Link privilege is not assumed; Windows reparse checks are source reviewed')
    def test_redirected_destination_ancestor_rejected(self):
        actual = self.work / 'actual'; actual.mkdir()
        self.destination.parent.symlink_to(actual, target_is_directory=True)
        with self.assertRaises(RuntimeError): self.stage()
        self.assertFalse((actual / 'release/soxr.dll').exists())


@unittest.skipIf(os.name == 'nt', 'Authored macOS manifest controls use POSIX symbolic links')
class MacControls(unittest.TestCase):
    output = None

    def setUp(self):
        self.work = self.output / self._testMethodName; self.work.mkdir()
        self.app = self.work / 'Application'; self.app.mkdir()
        self.build = self.work / 'build'; self.build.mkdir()
        self.lib = self.build / 'install/lib'; self.lib.mkdir(parents=True)
        (self.build / 'cmake').mkdir()
        self.rows = [{'path': 'src/' + name, 'bytes': 1, 'sha256': sha(b'x'), 'mode': '0o644'}
                     for name in sorted(dependency.MAC_UNITS)]
        source = {row['path']: b'x' for row in self.rows}
        self.patch = patch.object(dependency, '_source', return_value=(json.dumps({'files': self.rows}).encode(), source, []))
        self.patch.start(); self.addCleanup(self.patch.stop)
        library = bytearray(32); library[:4] = b'\xcf\xfa\xed\xfe'; struct.pack_into('<I', library, 4, 0x0100000c)
        (self.lib / 'libsoxr.0.1.2.dylib').write_bytes(library)
        (self.lib / 'libsoxr.0.dylib').symlink_to('libsoxr.0.1.2.dylib')
        (self.lib / 'libsoxr.dylib').symlink_to('libsoxr.0.dylib')
        self.commands = []
        for name in sorted(dependency.MAC_UNITS):
            path = self.app / 'ThirdParty/soxr-0.1.3/src' / name
            self.commands.append({'file': str(path), 'command': f'clang -O3 -DNDEBUG -fno-fast-math -ffp-contract=off -c "{path}"'})
        self.header = ''.join(f'#define {key} {value}\n' for key, value in dependency.FEATURES.items())
        self.manifest = {'commit': dependency.SOURCE_COMMIT, 'source_version': dependency.SOURCE_VERSION,
            'upstream_dylib_abi_version': '0.1.2', 'architecture': 'arm64', 'minimum_macos': '14.0',
            'options': {'optimization': '-O3 -DNDEBUG', 'fast_math': False, 'fp_contract': 'off', 'CR32': True,
                'CR64': True, 'SIMD': False, 'VR32': False, 'PFFFT': False, 'AVFFT': False, 'OpenMP': False,
                'high_precision_clock': True, 'float_standard_precision_clock': False, 'developer_trace': False,
                'LSR_bindings': False},
            'source': [{key: ('soxr-0.1.3/' + value if key == 'path' else value)
                        for key, value in row.items() if key != 'mode'} for row in self.rows]}
        self.save()

    def save(self):
        (self.build / 'cmake/compile_commands.json').write_text(json.dumps(self.commands))
        (self.build / 'cmake/soxr-config.h').write_text(self.header)
        for key, relative in [('library', 'install/lib/libsoxr.0.1.2.dylib'),
                              ('compile_commands', 'cmake/compile_commands.json'), ('configured_header', 'cmake/soxr-config.h')]:
            data = (self.build / relative).read_bytes()
            self.manifest[key] = {'bytes': len(data), 'sha256': sha(data)}
        (self.build / 'build-manifest.json').write_text(json.dumps(self.manifest))

    def validate(self):
        return dependency.verify_macos(self.app, self.build, '1' * 40)

    def test_valid_authored_manifest(self):
        receipt, path = self.validate()
        self.assertEqual(receipt['status'], 'passed')
        self.assertEqual(receipt['application_commit'], '1' * 40)
        self.assertEqual(path, self.lib)
        self.assertNotIn(str(self.work), json.dumps(receipt))

    def test_recorded_source_tamper(self):
        self.manifest['source'][0]['sha256'] = '0' * 64; self.save()
        with self.assertRaises(RuntimeError): self.validate()

    def test_wrong_architecture(self):
        self.manifest['architecture'] = 'x86_64'; self.save()
        with self.assertRaises(RuntimeError): self.validate()

    def test_boolean_profile_not_numeric(self):
        self.manifest['options']['CR32'] = 1; self.save()
        with self.assertRaises(RuntimeError): self.validate()

    def test_duplicate_json_field(self):
        path = self.build / 'build-manifest.json'; path.write_text(path.read_text()[:-1] + ',"architecture":"arm64"}')
        with self.assertRaises(RuntimeError): self.validate()

    def test_missing_compile_unit(self):
        self.commands.pop(); self.save()
        with self.assertRaises(RuntimeError): self.validate()

    def test_duplicate_compile_unit(self):
        self.commands[-1] = copy.deepcopy(self.commands[0]); self.save()
        with self.assertRaises(RuntimeError): self.validate()

    def test_ambient_compile_source(self):
        self.commands[0]['file'] = '/ambient/src/soxr.c'; self.save()
        with self.assertRaises(RuntimeError): self.validate()

    def test_profile_override_rejected(self):
        self.commands[0]['command'] += ' -ffast-math -O0'; self.save()
        with self.assertRaises(RuntimeError): self.validate()

    def test_feature_tamper_with_updated_hash(self):
        self.header = self.header.replace('#define WITH_CR32 1', '#define WITH_CR32 0'); self.save()
        with self.assertRaises(RuntimeError): self.validate()

    def test_library_changed_after_manifest(self):
        with (self.lib / 'libsoxr.0.1.2.dylib').open('ab') as stream: stream.write(b'changed')
        with self.assertRaises(RuntimeError): self.validate()

    def test_link_name_redirect(self):
        path = self.lib / 'libsoxr.dylib'; path.unlink(); path.symlink_to('elsewhere.dylib')
        with self.assertRaises(RuntimeError): self.validate()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=False)
    RuntimeControls.output = MacControls.output = args.output.absolute()
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(cls) for cls in (RuntimeControls, MacControls))
    with (args.output / 'controls.log').open('w') as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    receipt = {'schema': 'rebase.portable-soxr-controls.v1', 'status': 'passed' if result.wasSuccessful() else 'failed',
        'scope': 'Authored validator/runtime-staging controls; synthetic library bytes; no native Windows execution',
        'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped),
        'helper_sha256': sha(Path(dependency.__file__).read_bytes()), 'harness_sha256': sha(Path(__file__).read_bytes()),
        'failed_cases': [test.id().split('.')[-1] for test, _ in result.failures + result.errors]}
    (args.output / 'observation.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
