"""Independent native-xar synthetic controls; these are not Cubase results."""
import gzip
import importlib.util
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zlib

spec = importlib.util.spec_from_file_location('audit_xar', Path(__file__).resolve().parents[1] / 'scripts/audit_xar.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@unittest.skipUnless(shutil.which('xar'), 'requires native xar fixture generator')
class XarControls(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='xar-audit-control-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.payload = bytes(range(256)) * 16384
        (self.root / 'Payload').write_bytes(gzip.compress(self.payload, mtime=0))
        (self.root / 'PackageInfo').write_bytes(b'<pkg-info>' + b'x' * (3 * 1024 * 1024) + b'</pkg-info>')
        self.archive = self.root / 'control.xar'
        self.create_archive()

    def create_archive(self):
        subprocess.run(['xar', '-cf', str(self.archive), '--compression=bzip2', '--no-compress=Payload', 'Payload', 'PackageInfo'],
                       cwd=self.root, check=True, capture_output=True)

    def test_native_archive_and_gzip(self):
        report = module.audit(self.archive)
        self.assertEqual(len(report['entries']), 2)
        payload = next(x for x in report['entries'] if x['path'] == 'Payload')
        self.assertEqual(payload['gzip']['decoded_bytes'], len(self.payload))
        self.assertTrue(payload['gzip']['stream_complete_and_trailer_checked'])
        self.assertTrue(report['all_declared_data_checksums_match'])
        self.assertEqual(next(x for x in report['entries'] if x['path'] == 'PackageInfo')['encoding'], 'application/x-bzip2')

    def test_payload_bit_flip_rejected(self):
        data = bytearray(self.archive.read_bytes())
        _, header, _, compressed, _, _ = struct.unpack('>4sHHQQI', data[:28])
        toc = ET.fromstring(zlib.decompress(data[header:header + compressed])).find('toc')
        payload = next(x for x in toc.findall('file') if x.findtext('name') == 'Payload')
        offset = header + compressed + int(payload.findtext('data/offset'))
        data[offset + 15] ^= 1
        self.archive.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            module.audit(self.archive)

    def test_truncated_archive_rejected(self):
        self.archive.write_bytes(self.archive.read_bytes()[:-7])
        with self.assertRaises(ValueError):
            module.audit(self.archive)

    def test_wrong_toc_length_rejected(self):
        data = bytearray(self.archive.read_bytes())
        length, = struct.unpack_from('>Q', data, 16)
        struct.pack_into('>Q', data, 16, length + 1)
        self.archive.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'TOC decompression length'):
            module.audit(self.archive)

    def test_valid_xar_with_bad_gzip_crc_rejected(self):
        path = self.root / 'Payload'
        data = bytearray(path.read_bytes())
        data[-8] ^= 1
        path.write_bytes(data)
        self.archive.unlink()
        self.create_archive()
        with self.assertRaisesRegex(zlib.error, 'incorrect data check'):
            module.audit(self.archive)


if __name__ == '__main__':
    unittest.main()
