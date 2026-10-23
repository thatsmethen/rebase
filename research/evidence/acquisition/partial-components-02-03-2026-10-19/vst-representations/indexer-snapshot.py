#!/usr/bin/env python3
"""Index recovered VST remote XML, retaining cells/layers and checking resource hashes.

Inputs must be complete recovered regular files. This is a static declaration
index, not a plug-in parameter enumeration, DTD validator, or runtime probe.
CodeDirectory slot checks do not establish certificate trust or notarization.
"""
import argparse
import hashlib
import json
import pathlib
import plistlib
import struct
import sys
import xml.etree.ElementTree as ET


def sha(data):
    return hashlib.sha256(data).hexdigest()


def slot3(raw):
    if len(raw) < 44:
        raise ValueError('truncated CodeDirectory')
    magic, length, _, _, offset, _, special = struct.unpack_from('>7I', raw)
    size, kind = raw[36:38]
    if magic != 0xfade0c02 or length != len(raw) or kind != 2 or size != 32:
        raise ValueError('requires complete SHA-256 CodeDirectory')
    if special < 3 or offset - special * size < 44 or offset > len(raw):
        raise ValueError('invalid CodeDirectory special-slot bounds')
    return raw[offset - 3 * size:offset - 2 * size].hex()


def representation(raw):
    if b'<!ENTITY' in raw.upper():
        raise ValueError('entity declarations unsupported')
    root = ET.fromstring(raw)
    if root.tag != 'vstXML' or len(root.findall('plugin')) != 1:
        raise ValueError('expected vstXML and one plugin declaration')
    result = {'root_attributes': root.attrib, 'plugin': root.find('plugin').attrib,
              'representations': []}
    for rep in root.findall('representation'):
        pages = []
        for page in rep.findall('page'):
            cells = []
            for cell in page.findall('cell'):
                layers = [{'attributes': layer.attrib,
                           'title_names': [n.text or '' for n in layer.findall('titleDisplay/name')]}
                          for layer in cell.findall('layer')]
                cells.append({'attributes': cell.attrib, 'layers': layers})
            pages.append({'attributes': page.attrib, 'cells': cells})
        result['representations'].append({'attributes': rep.attrib, 'pages': pages})
    return result


def analyze(contents, verification):
    sealpath = contents / '_CodeSignature/CodeResources'
    sealraw = sealpath.read_bytes()
    seal = plistlib.loads(sealraw)
    report = {'scope': __doc__, 'contents': str(contents.resolve()),
              'resource_seal_sha256': sha(sealraw),
              'code_directory_resource_bindings': [], 'resources': [], 'xml': [],
              'schema_source': 'https://github.com/steinbergmedia/vst3_pluginterfaces/blob/master/vst/ivstrepresentation.h',
              'dtd_validation_performed': False}
    failures = []
    for path in sorted(verification.glob('*.codedirectory.bin')):
        raw = path.read_bytes()
        expected = slot3(raw)
        matched = expected == sha(sealraw)
        report['code_directory_resource_bindings'].append({
            'path': str(path.resolve()), 'codedirectory_sha256': sha(raw),
            'resource_slot_sha256': expected, 'matched': matched})
        if not matched:
            failures.append(f'resource slot mismatch: {path.name}')
    if not report['code_directory_resource_bindings']:
        failures.append('no CodeDirectory files supplied')
    for name, entry in sorted(seal['files2'].items()):
        relative = pathlib.PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('unsafe resource seal path')
        path = contents / name
        if path.is_symlink():
            raise ValueError('symlink resource unsupported')
        expected = entry.get('hash2')
        if not isinstance(expected, bytes) or len(expected) != 32:
            raise ValueError(f'unsupported resource entry: {name}')
        item = {'path': name, 'expected_sha256': expected.hex(), 'present_complete': path.is_file()}
        if path.is_file():
            raw = path.read_bytes()
            item.update({'bytes': len(raw), 'sha256': sha(raw), 'matched': sha(raw) == expected.hex()})
            if not item['matched']:
                failures.append(f'resource hash mismatch: {name}')
            if name.endswith('.xml'):
                try:
                    parsed = representation(raw)
                    report['xml'].append({'path': name, 'sha256': sha(raw), **parsed})
                except (ValueError, ET.ParseError) as exc:
                    failures.append(f'XML parse failure: {name}: {exc}')
        report['resources'].append(item)
    expectedxml = [r for r in report['resources'] if r['path'].endswith('.xml')]
    report['counts'] = {'sealed_resources': len(report['resources']),
                        'complete_resources': sum(r['present_complete'] for r in report['resources']),
                        'sealed_xml': len(expectedxml), 'parsed_xml': len(report['xml']),
                        'xml_resource_hashes_match': sum(r.get('matched', False) for r in expectedxml),
                        'declared_class_ids': len({x['plugin'].get('classID') for x in report['xml']})}
    report['missing_resources'] = [r['path'] for r in report['resources'] if not r['present_complete']]
    report['failures'] = failures
    report['all_available_resource_hashes_match'] = not any('resource hash mismatch' in f for f in failures)
    report['all_sealed_xml_recovered_and_parsed'] = len(expectedxml) == len(report['xml']) and all(r.get('matched') for r in expectedxml)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('contents', type=pathlib.Path)
    parser.add_argument('--verification', type=pathlib.Path, required=True)
    parser.add_argument('--output', type=pathlib.Path, required=True)
    args = parser.parse_args()
    report = analyze(args.contents, args.verification)
    report['indexer_sha256'] = sha(pathlib.Path(__file__).read_bytes())
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'indexer-snapshot.py').write_bytes(pathlib.Path(__file__).read_bytes())
    (args.output / 'index.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({k: report[k] for k in ('counts', 'missing_resources', 'failures', 'all_sealed_xml_recovered_and_parsed')}, indent=2))
    return int(bool(report['failures']) or not report['all_sealed_xml_recovered_and_parsed'])


if __name__ == '__main__':
    sys.exit(main())
