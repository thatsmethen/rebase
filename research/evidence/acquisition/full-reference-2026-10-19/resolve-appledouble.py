#!/usr/bin/env python3
"""One evidence-specific read-only CPIO/AppleDouble comparison; no installation.

Format reference: Apple's copyfile.c, apple_double_header, attr_header, attr_entry:
https://raw.githubusercontent.com/apple-oss-distributions/copyfile/main/copyfile.c
Retrieved 2026-10-19; interpretation is checked against native xattr bytes.
"""
import datetime
import gzip
import hashlib
import json
from pathlib import Path
import stat
import struct
import subprocess
import xml.etree.ElementTree as ET
import zlib

ROOT = Path('/workspace/rebase')
OUT = ROOT / 'research/evidence/acquisition/full-reference-2026-10-19'
PACKAGE = ROOT / 'research/targets/full-reference/mount/Cubase 15.pkg'
ENTRY = 'Cubase 15.app/Contents/VST3/ModScripter.vst3/Contents/Resources/._moduleinfo.json'
OLD = ROOT / 'research/targets/downloads/partial-components-04/components' / ENTRY
NATIVE = ROOT / 'research/targets/full-reference/expanded/Cubase 15.app.pkg/Payload' / ENTRY.replace('/._moduleinfo.json', '/moduleinfo.json')
BLOCK = 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def preserve(path, data):
    if path.exists():
        assert path.read_bytes() == data, 'existing evidence differs'
    else:
        with path.open('xb') as out:
            out.write(data)


class RangeReader:
    def __init__(self, handle, start, length):
        self.handle, self.left = handle, length
        self.digest = hashlib.sha1()
        handle.seek(start)

    def read(self, size=-1):
        size = self.left if size < 0 else min(size, self.left)
        data = self.handle.read(size)
        if len(data) != size:
            raise ValueError('truncated compressed payload')
        self.left -= len(data)
        self.digest.update(data)
        return data


def main():
    audit = json.loads((OUT / 'xar-audit/audit.json').read_text())
    expected = next(e for e in audit['entries'] if e['path'] == 'Cubase 15.app.pkg/Payload')
    before = PACKAGE.stat()
    with PACKAGE.open('rb') as handle:
        magic, hsize, version, clen, ulen, checksum = struct.unpack('>4sHHQQI', handle.read(28))
        assert (magic, hsize, version, checksum) == (b'xar!', 28, 1, 1)
        toc = zlib.decompress(handle.read(clen))
        assert len(toc) == ulen and sha(toc) == audit['toc']['plain_sha256']
        root = ET.fromstring(toc).find('toc')
        component = next(e for e in root.findall('file') if e.findtext('name') == 'Cubase 15.app.pkg')
        payload = next(e for e in component.findall('file') if e.findtext('name') == 'Payload').find('data')
        assert payload.find('encoding').get('style') == 'application/octet-stream'
        start, compressed_length = hsize + clen + int(payload.findtext('offset')), int(payload.findtext('length'))
        raw = RangeReader(handle, start, compressed_length)
        decoded = gzip.GzipFile(fileobj=raw, mode='rb')
        digest, position = hashlib.sha256(), 0

        def read(n):
            nonlocal position
            data = decoded.read(n)
            if len(data) != n:
                raise ValueError('truncated CPIO record')
            digest.update(data)
            position += len(data)
            if position > 8 * 1024**3:
                raise ValueError('decoded bound exceeded')
            return data

        record, cpio_count = None, 0
        while True:
            offset = position
            header = read(76)
            assert header[:6] == b'070707'
            assert all(x in b'01234567' for x in header[6:])
            mode, namesize, size = int(header[18:24], 8), int(header[59:65], 8), int(header[65:76], 8)
            assert 0 < namesize <= 8192 and size <= 8 * 1024**3
            name = read(namesize)
            assert name.endswith(b'\0') and b'\0' not in name[:-1]
            path = name[:-1].decode('utf-8')
            if path == 'TRAILER!!!':
                assert size == 0
                break
            cpio_count += 1
            selected = path.removeprefix('./') == ENTRY
            data_offset = position
            kept, left = [], size
            while left:
                block = read(min(left, BLOCK))
                if selected:
                    kept.append(block)
                left -= len(block)
            if selected:
                assert record is None and stat.S_ISREG(mode) and size == 656
                data = b''.join(kept)
                record = {'path': path, 'cpio_header_offset': offset,
                          'cpio_data_offset': data_offset, 'bytes': size,
                          'mode': oct(mode), 'sha256': sha(data),
                          'raw_cpio_entry_sha256': sha(header + name + data)}
                preserve(OUT / 'moduleinfo.appledouble', data)
                preserve(OUT / 'moduleinfo.appledouble.cpio-entry', header + name + data)
        padding = 0
        while block := decoded.read(BLOCK):
            assert not any(block), 'nonzero post-trailer CPIO padding'
            digest.update(block)
            position += len(block)
            padding += len(block)
            assert position <= 8 * 1024**3
        assert raw.left == 0 and raw.digest.hexdigest() == expected['archived_sha1']
        assert position == expected['gzip']['decoded_bytes']
        assert digest.hexdigest() == expected['gzip']['decoded_sha256']
        assert record is not None
    after = PACKAGE.stat()
    assert (before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
    data = (OUT / 'moduleinfo.appledouble').read_bytes()
    assert data == OLD.read_bytes()
    magic, version, filler, count = struct.unpack_from('>II16sH', data)
    assert (magic, version, count) == (0x00051607, 0x00020000, 2)
    entries = [dict(zip(('id', 'offset', 'length'), struct.unpack_from('>III', data, 26 + 12*i))) for i in range(count)]
    assert entries == [{'id': 9, 'offset': 50, 'length': 606}, {'id': 2, 'offset': 656, 'length': 0}]
    assert data[50:84] == bytes(34), 'unexpected FinderInfo/padding'
    attr = struct.unpack_from('>8I2H', data, 84)
    assert attr == (0x41545452, 0, 656, 288, 368, 0, 0, 0, 0, 4)
    attributes, cursor = [], 120
    for _ in range(attr[-1]):
        offset, length, flags, nlen = struct.unpack_from('>IIHB', data, cursor)
        assert flags == 0 and 1 < nlen <= 128
        name = data[cursor+11:cursor+11+nlen]
        assert name.endswith(b'\0') and b'\0' not in name[:-1]
        name = name[:-1].decode('utf-8')
        assert (offset == length == 0) or 288 <= offset <= offset + length <= len(data)
        value = data[offset:offset+length]
        result = subprocess.run(['/usr/bin/xattr', '-px', name, str(NATIVE)], capture_output=True, text=True, check=True)
        native_value = bytes.fromhex(result.stdout)
        attributes.append({'name': name, 'offset': offset, 'bytes': length,
                           'sidecar_value_sha256': sha(value), 'native_value_sha256': sha(native_value),
                           'equal_bytes': value == native_value,
                           'native_read': {'argv': result.args, 'returncode': result.returncode,
                                           'stdout': result.stdout, 'stderr': result.stderr}})
        cursor = (cursor + 11 + nlen + 3) & ~3
    assert cursor <= 288 and all(e['equal_bytes'] for e in attributes)
    listing = subprocess.run(['/usr/bin/xattr', str(NATIVE)], capture_output=True, text=True, check=True)
    report = {'scope': 'Resolve exactly one missing regular path using independent full-package raw CPIO recovery and native extended-attribute byte comparison. Native extraction is not modified.',
              'at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'format_source': __doc__.splitlines()[3],
              'source_package': str(PACKAGE), 'source_package_sha256': audit['sha256'],
              'xar_payload': {'path': 'Cubase 15.app.pkg/Payload', 'package_offset': start, 'compressed_bytes': compressed_length,
                              'compressed_sha1': expected['archived_sha1'],
                              'decoded_bytes': position, 'decoded_sha256': digest.hexdigest(),
                              'gzip_eof_and_trailer_checked': True, 'cpio_trailer_seen': True,
                              'cpio_records_before_trailer': cpio_count, 'post_trailer_zero_padding_bytes': padding},
              'raw_entry': record, 'raw_sidecar_path': str(OUT / 'moduleinfo.appledouble'),
              'raw_entry_path': str(OUT / 'moduleinfo.appledouble.cpio-entry'),
              'identical_to_partial_snapshot04_sidecar': True,
              'appledouble_entries': entries, 'finder_info_all_zero': True, 'resource_fork_bytes': 0,
              'native_file': str(NATIVE), 'native_file_sha256': sha(NATIVE.read_bytes()),
              'native_xattr_names': listing.stdout.splitlines(), 'attributes': attributes,
              'all_four_archived_attribute_values_match_native_bytes': True,
              'regular_path_comparison_unchanged': {'identical': 802, 'compared': 803, 'one_missing_appledouble_path': ENTRY},
              'conclusion': 'The missing AppleDouble sidecar is present verbatim in the complete package. Its four named attribute values exactly match native extended attributes on moduleinfo.json; FinderInfo is zero and the resource fork is empty. This resolves the representation difference without changing the 802/803 regular-path result.',
              'limits': ['Additional native com.apple.provenance is not present in the archived sidecar and is not attributed to package content.', 'No target code executed.'],
              'script_sha256': sha(Path(__file__).read_bytes())}
    with (OUT / 'appledouble-resolution.json').open('x') as out:
        json.dump(report, out, indent=2)
        out.write('\n')
    print(json.dumps({'attributes_match': True, 'regular_files_identical': 802, 'compared': 803, 'raw_sidecar_sha256': record['sha256']}))


if __name__ == '__main__':
    main()
