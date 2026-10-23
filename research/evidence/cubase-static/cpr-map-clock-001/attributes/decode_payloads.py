#!/usr/bin/env python3
"""Exact, read-only MAP-GATE-1 fixture subset; never executes target code.

Reuses the retained bounded archive/attribute readers, then applies a deliberately
narrow allowlist. This is a research instrument, not a general CPR decoder.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
from cpr_probe import Archive, Reader, ProbeError, attributes

MANIFEST = ROOT / 'research/evidence/cubase-static/cpr-audio-timing-001/reviewer-template-state.json'
FIELDS = {'voiceIndexOnStave': -1, 'staveIndex': -1, 'isGraceNote': 0,
          'noteNameOptionalIsSet': 0, 'noteName': 0}
TARGETS = {'voiceIndexOnStave': '0x10', 'staveIndex': '0x0c',
           'isGraceNote': '0x1c', 'noteNameOptionalIsSet': '0x21', 'noteName': '0x20'}


def require(condition, description):
    if not condition:
        raise ProbeError(description)


def enclosing_archive(data, item_start, item_end):
    r = Reader(data, 0, len(data))
    require(r.take(4) == b'RIFF' and r.number('I') == len(data)-12 and
            r.take(4) == b'NUND', 'unsupported envelope')
    found = []
    while r.pos < r.end:
        require(r.take(4) == b'ROOT', 'missing ROOT')
        n = r.number('I'); start = r.pos; r.take(n)
        rr = Reader(data, start, start+n)
        name, kind = rr.string(terminated=False), rr.string(terminated=False)
        require(rr.pos == rr.end and r.take(4) == b'ARCH', 'invalid ROOT/ARCH')
        n = r.number('I'); start = r.pos; r.take(n)
        if start <= item_start < item_end <= r.pos:
            require(name['text'] == 'Arrangement1' and kind['text'] == 'PArrangement',
                    'item outside arrangement archive')
            found.append((start, r.pos))
    require(len(found) == 1, 'ambiguous enclosing archive')
    return found[0]


def decode(data, start, end, archive_start, archive_end):
    a = Archive(data, archive_start, archive_end)
    r = Reader(data, start, end)
    require(r.number('I') == 1, 'only one numeric item attribute supported')
    key_at = r.pos
    require(r.number('I') == 0x5343436e, 'unsupported numeric key')
    require(r.number('H') == 0x22, 'unsupported attribute type')
    obj = a.object(r)
    require(obj.get('class') == 'ScoreEventAttributeContainer' and obj['version'] == 1,
            'unsupported attribute object')
    require(r.pos == r.end, 'trailing item attribute bytes')
    c = a.body(obj)
    index_at = c.pos
    require(c.number('i') == 10, 'unsupported collection index')
    require(c.number('H') == 1, 'unsupported collection flags')
    require(c.number('i') == 1, 'only one NoteData supported')
    note = a.object(c)
    require(note.get('class') == 'NoteData' and note['version'] in (2, 3),
            'unsupported NoteData class/version')
    # The allowlisted encodings use exact raw ASCII class labels. The reusable
    # archive reader is more permissive; reject aliases/BOMs in this instrument.
    for o, label in [(obj, b'ScoreEventAttributeContainer\0'), (note, b'NoteData\0')]:
        d = o['class_declaration_offset']
        q = Reader(data, d, archive_end)
        require(q.number('i') == -1 and q.number('I') == len(label) and q.take(len(label)) == label,
                'class label must be an exact explicit ASCII declaration')
    require(c.pos == c.end, 'trailing container bytes')
    nr = a.body(note)
    fields = []
    if note['version'] == 2:
        for name, fmt in [('voiceIndexOnStave', 'i'), ('staveIndex', 'i'),
                          ('isGraceNote', 'h'), ('noteNameOptionalIsSet', 'H'), ('noteName', 'B')]:
            at = nr.pos; value = nr.number(fmt)
            fields.append(dict(name=name, value=value, value_offset=at, end=nr.pos,
                               encoded_type=fmt, native_object_offset=TARGETS[name]))
    else:
        fields = attributes(nr)
        require(all(f['type_code'] == 1 for f in fields), 'only integer named fields supported')
        require(len(fields) == 5 and {f['name'] for f in fields} == set(FIELDS),
                'unknown/missing NoteData fields')
        for f in fields:
            f['native_object_offset'] = TARGETS[f['name']]
    require(nr.pos == nr.end, 'trailing NoteData bytes')
    require({f['name']: f['value'] for f in fields} == FIELDS,
            'only observed default-valued NoteData state supported')
    for f in fields:
        f['value_bytes_hex'] = data[f['value_offset']:f['end']].hex()
    return dict(item_start=start, item_end=end, numeric_key_offset=key_at,
                numeric_key='0x5343436e', numeric_type='0x22',
                container=obj, container_index_offset=index_at,
                serialized_index=10, native_index=-1, storage_flags=1, object_count=1,
                note=note, fields=fields, consumed_exactly=True,
                body_hex=data[obj['body_offset']:obj['end']].hex(),
                item_bytes_hex=data[start:end].hex(),
                item_sha256=hashlib.sha256(data[start:end]).hexdigest(),
                materialized_defaults={'staveIndex': -1, 'voiceIndexOnStave': -1,
                    'Visibility': 0, 'SuppressPlayback': False, 'isGraceNote': 0,
                    'noteNameOptionalIsSet': False, 'noteName': 0,
                    'spelledForPitch': -1, 'notationOffset': 0},
                materialization_limit='Materialized defaults are native static deductions; no target execution. '
                     'When optional-name is false, serialized noteName is read but not assigned.')


def main():
    manifest_bytes = MANIFEST.read_bytes()
    output = []
    controls = []
    for fixture in json.loads(manifest_bytes)['fixtures']:
        for tempo in fixture['tempo_objects']:
            for item in tempo['item_attributes']:
                if not item['count']:
                    continue
                source = ROOT / fixture['source']; data = source.read_bytes()
                require(hashlib.sha256(data).hexdigest() == fixture['source_sha256'], 'source digest changed')
                lo, hi = enclosing_archive(data, item['offset'], item['end'])
                decoded = decode(data, item['offset'], item['end'], lo, hi)
                old = item['fields'][0]['value']
                require(decoded['container']['body_sha256'] == old['body_sha256'], 'body digest changed')
                output.append(dict(source=fixture['source'], source_sha256=fixture['source_sha256'],
                                   archive_start=lo, archive_end=hi, **decoded))
                # Bounded defect injection: no source files are altered.
                mutations = [('truncated', data, item['end']-1)]
                for label, offset, value in [('wrong_key', item['offset']+4, 0),
                        ('wrong_type', item['offset']+9, 1),
                        ('collection_flags', decoded['container_index_offset']+5, 2),
                        ('changed_note_value', decoded['fields'][0]['value_offset'], 0)]:
                    changed = bytearray(data); changed[offset] = value
                    mutations.append((label, bytes(changed), item['end']))
                for label, changed, end in mutations:
                    try:
                        decode(changed, item['offset'], end, lo, hi)
                    except (ProbeError, UnicodeError) as error:
                        controls.append(dict(source=source.name, control=label, rejected=True, reason=str(error)))
                    else:
                        raise AssertionError('mutation accepted: ' + label)
    require(len(output) == 4, 'expected precisely four nonempty fixture item attributes')
    result = dict(schema_version=1, target_executed=False,
                  scope='Exact four shipped per-item payloads; not arbitrary score attributes or a map acceptance decision.',
                  manifest=str(MANIFEST.relative_to(ROOT)), manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
                  instrument_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  reused_reader='scripts/cpr_probe.py',
                  reused_reader_sha256=hashlib.sha256((ROOT/'scripts/cpr_probe.py').read_bytes()).hexdigest(),
                  fixtures=output, negative_controls=controls)
    (HERE/'decoded-fixtures.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(dict(fixtures=len(output), fully_consumed=len(output), negative_controls=len(controls),
                          output=str(HERE/'decoded-fixtures.json'))))


if __name__ == '__main__':
    main()
