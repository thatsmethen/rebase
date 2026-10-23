#!/usr/bin/env python3
"""Read-only audit of this study's XAR v1/SHA1 package structure.

Checks compressed TOC, archived/extracted data checksums, and gzip Payload
streams. It does not verify signer trust, install files, or execute payloads.
Unsupported encodings fail closed. Native package validation is separate.
"""
import argparse
import bz2
import hashlib
import json
from pathlib import Path
import struct
import xml.etree.ElementTree as ET
import zlib

BLOCK = 1024 * 1024


def chunks(handle, start, length):
    handle.seek(start)
    while length:
        block = handle.read(min(BLOCK, length))
        if not block:
            raise ValueError('truncated archive data')
        yield block
        length -= len(block)


def digest_file(path):
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(BLOCK), b''):
            h.update(block)
    return h.hexdigest()


def bounded_zlib(raw, expected):
    decoder = zlib.decompressobj()
    plain = decoder.decompress(raw, expected + 1)
    if len(plain) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError('TOC decompression length or stream boundary mismatch')
    return plain


def audit(path):
    before = path.stat()
    report = {'scope': __doc__, 'path': str(path.resolve()), 'bytes': before.st_size,
              'sha256': digest_file(path), 'entries': []}
    with path.open('rb') as handle:
        header = handle.read(28)
        if len(header) != 28:
            raise ValueError('truncated XAR header')
        magic, header_size, version, compressed_size, plain_size, checksum_kind = struct.unpack('>4sHHQQI', header)
        if magic != b'xar!' or version != 1 or header_size != 28 or checksum_kind != 1:
            raise ValueError('only XAR v1/28-byte-header/SHA1 TOC supported')
        if compressed_size > 4 * BLOCK or plain_size > 16 * BLOCK:
            raise ValueError('TOC exceeds bounded reader limit')
        compressed = handle.read(compressed_size)
        if len(compressed) != compressed_size:
            raise ValueError('truncated compressed TOC')
        plain = bounded_zlib(compressed, plain_size)
        if b'<!DOCTYPE' in plain.upper() or b'<!ENTITY' in plain.upper():
            raise ValueError('XML DTD/entities unsupported')
        root = ET.fromstring(plain)
        toc = root.find('toc')
        if root.tag != 'xar' or toc is None:
            raise ValueError('unexpected XAR TOC root')
        heap = header_size + compressed_size
        checksum = toc.find('checksum')
        if checksum is None or checksum.get('style') != 'sha1' or checksum.findtext('size') != '20':
            raise ValueError('unsupported TOC checksum declaration')
        offset = int(checksum.findtext('offset'))
        if offset < 0 or heap + offset + 20 > before.st_size:
            raise ValueError('TOC checksum outside file')
        handle.seek(heap + offset)
        expected = handle.read(20).hex()
        actual = hashlib.sha1(compressed).hexdigest()
        if actual != expected:
            raise ValueError('compressed TOC checksum mismatch')
        report['toc'] = {'compressed_bytes': compressed_size, 'plain_bytes': plain_size,
                         'plain_sha256': hashlib.sha256(plain).hexdigest(),
                         'sha1': actual, 'stored_checksum_matches': True}

        def files(node, prefix=''):
            for item in node.findall('file'):
                name = item.findtext('name')
                if not name or '/' in name or name in ('.', '..'):
                    raise ValueError('unsupported XAR filename')
                relative = prefix + name
                if item.find('data') is not None:
                    yield relative, item.find('data')
                yield from files(item, relative + '/')

        for name, data in files(toc):
            offset, length, size = [int(data.findtext(key)) for key in ('offset', 'length', 'size')]
            if min(offset, length, size) < 0 or heap + offset + length > before.st_size:
                raise ValueError(f'data outside archive: {name}')
            if size > 8 * 1024**3:
                raise ValueError(f'entry exceeds 8 GiB decoded bound: {name}')
            encoding = data.find('encoding').get('style')
            if encoding not in ('application/octet-stream', 'application/x-bzip2'):
                raise ValueError(f'unsupported encoding: {encoding}')
            checksums = [data.find(key) for key in ('archived-checksum', 'extracted-checksum')]
            if any(c is None or c.get('style') != 'sha1' for c in checksums):
                raise ValueError('only declared SHA1 entry checksums supported')
            archived, extracted = hashlib.sha1(), hashlib.sha1()
            decoder = bz2.BZ2Decompressor() if encoding == 'application/x-bzip2' else None
            total = 0
            for block in chunks(handle, heap + offset, length):
                archived.update(block)
                if decoder:
                    decoded = decoder.decompress(block, max_length=BLOCK)
                    extracted.update(decoded)
                    total += len(decoded)
                    while not decoder.eof and not decoder.needs_input:
                        decoded = decoder.decompress(b'', max_length=BLOCK)
                        extracted.update(decoded)
                        total += len(decoded)
                        if total > size:
                            raise ValueError(f'decoded size exceeds declaration: {name}')
                else:
                    extracted.update(block)
                    total += len(block)
                if total > size:
                    raise ValueError(f'decoded size exceeds declaration: {name}')
            if decoder and (not decoder.eof or decoder.unused_data):
                raise ValueError(f'incomplete or trailing bzip2 stream: {name}')
            if total != size or archived.hexdigest() != checksums[0].text or extracted.hexdigest() != checksums[1].text:
                raise ValueError(f'entry size or checksum mismatch: {name}')
            record = {'path': name, 'encoding': encoding, 'archived_bytes': length, 'extracted_bytes': total,
                      'archived_sha1': archived.hexdigest(), 'extracted_sha1': extracted.hexdigest(),
                      'both_declared_checksums_match': True}
            if name.endswith('/Payload') or name == 'Payload':
                if encoding != 'application/octet-stream':
                    raise ValueError('Payload stream check requires raw XAR entry')
                handle.seek(heap + offset)
                if handle.read(2) != b'\x1f\x8b':
                    raise ValueError(f'unsupported non-gzip Payload: {name}')
                decoder = zlib.decompressobj(31)
                uncompressed, decoded_hash = 0, hashlib.sha256()
                for block in chunks(handle, heap + offset, length):
                    while block:
                        decoded = decoder.decompress(block, BLOCK)
                        block = decoder.unconsumed_tail
                        uncompressed += len(decoded)
                        decoded_hash.update(decoded)
                        if uncompressed > 8 * 1024**3 or decoder.unused_data:
                            raise ValueError(f'gzip size bound/trailing stream violation: {name}')
                if not decoder.eof:
                    raise ValueError(f'incomplete gzip stream: {name}')
                record['gzip'] = {'stream_complete_and_trailer_checked': True,
                                  'decoded_bytes': uncompressed, 'decoded_sha256': decoded_hash.hexdigest(),
                                  'cpio_structure_checked': False}
            report['entries'].append(record)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise ValueError('archive changed during audit')
    report['all_declared_data_checksums_match'] = True
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = audit(args.package)
    source = Path(__file__).read_bytes()
    report['auditor_sha256'] = hashlib.sha256(source).hexdigest()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'auditor-snapshot.py').write_bytes(source)
    (args.output / 'audit.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'entries_checked': len(report['entries']), 'sha256': report['sha256'], 'output': str(args.output)}))


if __name__ == '__main__':
    main()
