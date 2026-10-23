#!/usr/bin/env python3
"""Seal static IComponents host-gate evidence against the pinned original image."""
import hashlib
import json
import struct
import sys
from pathlib import Path

P = Path(__file__).resolve().parent
sys.path.insert(0, str(P.parent / 'attributes'))
import source_tools as s

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def reference(p):
    return {'path': str(p.relative_to(s.ROOT)), 'sha256': digest(p)}

def cstring(a):
    o = s.offset(a)
    b = s.data[o:o + 256].split(b'\0', 1)[0]
    assert len(b) < 256
    return dict(text=b.decode('ascii'), **s.region(a, len(b) + 1))

proof = []
for derivation in sorted(P.glob('pass*/derivation.json')):
    for row in json.loads(derivation.read_text())['derivatives']:
        a = int(row['entry'], 16)
        raw = derivation.parent / row['raw_file']
        b = raw.read_bytes()
        assert b == s.data[s.offset(a, len(b)):s.offset(a, len(b)) + len(b)]
        assert digest(raw) == row['raw_sha256']
        read_path = derivation.parent / f'bytes-{a:x}.json'
        read = json.loads(read_path.read_text())['structuredContent']['raw_result']
        assert read['complete'] and bytes.fromhex(read['bytes_hex']) == b
        dossier = derivation.parent / f'function-{a:x}.json'
        response = json.loads(dossier.read_text())
        assert not response.get('isError')
        pseudo = response['structuredContent']['raw_result']['value']['pseudocode']
        (derivation.parent / f'pseudocode-{a:x}.txt').write_text(pseudo)
        native = derivation.parent / row['original_native_disassembly']
        assert digest(native) == row['native_stdout_sha256']
        proof.append(dict(entry=hex(a), source_offset=s.offset(a, len(b)), length=len(b),
                          raw=reference(raw), native=reference(native), dossier=reference(dossier),
                          REA_read_bytes=reference(read_path), boundary=row['boundary']))

base = 0x1044aced8
slots = []
for off in range(0, 0x58, 8):
    target, = struct.unpack_from('<Q', s.data, s.offset(base + off, 8))
    slots.append(dict(slot=hex(off), target=hex(target), **s.region(base + off, 8)))
assert slots[3]['target'] == '0x1005c0540'
assert slots[2]['target'] == '0x1005c033c'
assert slots[4]['target'] == '0x1005c0548'
assert bytes.fromhex(s.region(0x1005c0540, 8)['bytes_hex']) == bytes.fromhex('00204039c0035fd6')
assert cstring(0x10395cda0)['text'] == 'N9Steinberg4Lego10Components7ContextE'

helper_dir = P.parent / 'list-review/constructor-context'
reused = [reference(helper_dir / f) for f in ['function-1005c01a8.json', 'native-1005c01a8.txt']]
report = dict(
    schema_version=1,
    source=dict(path=str(s.SOURCE.relative_to(s.ROOT)), sha256=s.PIN, bytes=len(s.data)),
    target_executed=False,
    result='The concrete default host gate can be enabled by initialization. The constructor callback cannot be excluded by the initial zero byte or the nullable global.',
    verification=dict(exact_source_ranges=len(proof), original_bytes=sum(x['length'] for x in proof),
                      all_REA_read_bytes_match_original=True, functions=proof),
    global_slot=dict(address='0x104feeee0', registry_owner_address='0x104feeee8',
                     section='__DATA,__common', file_backed=False,
                     note='The zero-fill section is not read as file bytes and supplies no observed runtime value.'),
    concrete_default=dict(vtable=hex(base),
        RTTI_prefix=s.region(base - 16, 16), type_info=s.region(0x1044acf40, 24),
        type_name=cstring(0x10395cda0), base_type_name=cstring(0x10395cdc6), slots=slots),
    literals=dict(interface_key=cstring(0x104f8647f), callback_parameter=cstring(0x104f86491),
                  packed_key_prefix=s.region(0x10395cd20, 16),
                  packed_key_suffix='Native code appends little-endian u16 0x0073, completing Lego::IComponents plus NUL.'),
    decisive_original_regions=dict(
        allocation_zero=s.region(0x1005bff98, 36), predicate=s.region(0x1005c0540, 8),
        initialize_enable=s.region(0x1005c04a0, 12), reset_disable=s.region(0x1005c0720, 16),
        initialization_call=s.region(0x1005ca9cc, 20), registry_callback=s.region(0x1005c1180, 16)),
    findings=[
        {'id': 'typed-default-registration', 'addresses': ['0x1005bff7c', '0x1005c0250'],
         'statement': 'Registration first queries the supplied registry for typed Lego::IComponents. When absent it allocates112 bytes, writes concrete vtable1044aced8, zeroes the remaining fields including byte8, and passes a typed ownership descriptor to registry+28. Existing providers are retained. Descriptor cleanup/ownership is not treated as proof of destruction.'},
        {'id': 'replaceable-global-binding', 'addresses': ['0x1005c002c', '0x1005c1180'],
         'statement': 'The binder unregisters any prior registry subscription, records the incoming registry at slot+8, then registers a typed key callback through registry+8. The initial returned pair is accepted only after its type-name comparison. Callback1005c1180 stores its supplied pointer in the global slot and conditionally clears the registry owner. The selected service is runtime state, not immutable file data.'},
        {'id': 'concrete-predicate', 'addresses': ['0x1044acef0', '0x1005c0540'],
         'statement': 'The concrete default object is Steinberg::Lego::Components::Context by original RTTI. Its virtual+18 resolves to LDRB W0,[X0,#8]; RET. This getter itself has no writes/calls and receives only its component receiver; it does not receive the track context.'},
        {'id': 'explicit-enable', 'addresses': ['0x1005c033c', '0x1005c04a8', '0x1005ca934', '0x1005ca9dc'],
         'statement': 'Concrete virtual+10 initialization connects several own service slots and, on its normal successful path, stores1 to byte8 at1005c04a8 before returning1. Caller1005ca934 registers the component and then invokes the selected component virtual+10 at1005ca9dc. This establishes an enabled path, not a measurement that every runtime instance uses this default implementation.'},
        {'id': 'explicit-disable', 'addresses': ['0x1005c0548', '0x1005c0728', '0x1005c0158'],
         'statement': 'Concrete virtual+20 detaches own component handles and clears byte8 at1005c0728. Helper1005c0158 calls selected component+20 when the selected component exists and its+18 predicate succeeds. This reset path does not establish the state during CPR loading.'},
        {'id': 'constructor-impact-boundary', 'addresses': ['0x1005c01a8'],
         'statement': 'The retained constructor helper skips only when the selected component is null or its+18 predicate is false. Otherwise it obtains the separately reviewed root-context service and passes TrackLoopHandlerParam with a context containing the track pointer to adjusted virtual+20. The concrete default predicate is read-only, but its successful initialized path permits the service callback; this finding does not establish that callback is harmless.'}
    ],
    scan_evidence=[reference(P / 'locate.py'), reference(P / 'global-xrefs.json'),
                   reference(P / 'initializer-callers.json')],
    reused_evidence=reused,
    open_edges=[
        'The root-context service callback destination and its use of the track context are reviewed separately in list-review/constructor-context. This report does not close that edge.',
        'A supplied or replaced IComponents service can have another implementation. The default vtable binding is conditional on that concrete object being selected.',
        'The entire host initialization call graph, all registry implementations, and service availability at runtime are not established by this bounded branch.'
    ],
    limits=[
        'Static original-byte and control-flow evidence only; no Cubase execution, runtime global observation, or project timing measurement.',
        'The pointer scan locates ADRP-based candidates within a bounded instruction window; it is not proof that no indirect or differently encoded references exist. Reviewed native ranges resolve the listed direct uses.',
        'Raw REA imports omit imports/globals/RTTI/relocations/unwind; original image regions and native disassembly bind those identities here.',
        'Normal successful initialization is analyzed; exceptions/allocation failure and arbitrary replacement providers remain outside this scope.',
        'App tests and synthetic arithmetic vectors do not establish the constructor callback behavior. No app source or fixture was modified by this branch.'
    ])
(P / 'finding.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(dict(report=reference(P / 'finding.json'), functions=len(proof),
                      original_bytes=sum(x['length'] for x in proof))))
