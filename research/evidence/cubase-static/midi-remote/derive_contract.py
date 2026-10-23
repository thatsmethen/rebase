#!/usr/bin/env python3
"""Derive a bounded source contract without importing or executing target code."""
import hashlib
import json
import plistlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
APP = ROOT / 'research/targets/full-reference/expanded/Cubase 15.app.pkg/Payload/Cubase 15.app'
SCRIPTS = APP / 'Contents/midiremote_factory_scripts'
REA = OUT / 'rea-static-analysis.json'
data = json.loads(REA.read_text())['data']
n = data['normalized_result']
seal = plistlib.loads((APP / 'Contents/_CodeSignature/CodeResources').read_bytes())

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

sources = []
for rel in n['source_selection']['requested_paths']:
    path = SCRIPTS / rel
    resource = 'midiremote_factory_scripts/' + rel
    expected = seal['files2'][resource]['hash2'].hex()
    actual = digest(path)
    assert actual == expected, resource
    sources.append({'relative_path': rel, 'bytes': path.stat().st_size,
                    'sha256': actual, 'outer_resource_sha256_matches': True})

selected = []
for node in n['semantic_graph']['nodes']:
    ident = node.get('identity', {})
    if (node['kind'] == 'function'
            and ident.get('module_path') == '.api/v1/midiremote_api_v1.js'
            and ident.get('source_range', {}).get('start', {}).get('line') in (1926, 4746, 5176, 7738)):
        selected.append({'node_id': node['node_id'], 'name': node['label'],
                         'source_range': ident['source_range'],
                         'artifact_sha256': ident['artifact_sha256']})
assert len(selected) == 4

finding = {
    'finding_id': 'MIDI-REMOTE-001',
    'evidence_class': 'static source observations and bounded interpretation',
    'target_executed': False,
    'source_scope': 'Three selected files in the complete signed MIDI Remote factory-script tree',
    'sources': sources,
    'rea': {'evidence_id': data['evidence_id'], 'record': str(REA.relative_to(ROOT)),
            'record_sha256': digest(REA), 'root_artifact_sha256': n['root_artifact_sha256'],
            'statistics': n['statistics'], 'graph_coverage': n['graph']['coverage'],
            'unselected_relevant_files': n['source_selection']['unselected_files'],
            'limitations': data['limitations']},
    'declared_example_mapping': {
        'source': 'Public/examplecompany/simpledevice/ExampleCompany_SimpleDevice.js',
        'driver_declaration_line': 9,
        'port_detection_line_ranges': [[17, 19], [21, 23]],
        'surface_knob_declaration_lines': [31, 32, 33, 34],
        'midi_channel_argument': 0,
        'control_change_numbers': [21, 22, 23, 24],
        'cc_binding_lines': [40, 45, 50, 55],
        'page_creation_line': 62,
        'host_selection_line': 65,
        'host_binding_lines': [69, 70, 71, 72],
        'targets_in_knob_order': ['selected track volume', 'selected track send index 0 level',
                                 'selected track send index 1 level', 'selected track send index 2 level'],
        'claim_scope': 'Source declares these calls and arguments; runtime registration, MIDI receipt, host lookup, scaling, takeover and feedback remain unmeasured.'
    },
    'api_file_interpretation': {
        'observation': 'The bundled API JavaScript includes empty increment/decrement bodies, methods returning fresh type objects without using supplied binding arguments, and takeover methods returning this without implementing takeover state.',
        'source_ranges': selected,
        'inference': 'This file serves as a development-facing API shape/stub, not sufficient implementation evidence for the native host behavior.',
        'negative_conclusion_disallowed': 'Empty stub bodies do not establish that Cubase ignores the corresponding actions.',
        'unresolved_boundary': 'The actual runtime module provider, native host bridge, object lifetime and value transformations have not been mapped.'
    },
    'tool_interpretation_correction': {
        'observation': 'REA assigns an electron-main role from package.json main in this selected SDK package.',
        'supporting_node': 'jag_node_86dfd7488140b6d0e05ba5b5e22f30414f616fb3a016a5a791c588ce281877a1',
        'interpretation': 'The retained relation supports a package entrypoint only. It is not evidence that Cubase is an Electron application.'
    },
    'next_discriminating_work': [
        'Trace the native module-provider registration for the literal midiremote_api_v1 before inferring host semantics from the stubs.',
        'In a later runtime phase, test one declared CC binding with recorded track/send selection and explicit takeover mode, preserving MIDI input, feedback and host-value observations.'
    ],
    'reproduction': {
        'analysis': ['sh', 'scripts/rea', 'analyze-javascript-application', str(SCRIPTS),
                     '--artifact-format', 'directory', '--source-path', '.api/v1/package.json',
                     '--source-path', '.api/v1/midiremote_api_v1.js', '--source-path',
                     'Public/examplecompany/simpledevice/ExampleCompany_SimpleDevice.js',
                     '--analysis-timeout-ms', '60000', '--max-heap-mb', '1024', '--format', 'json', '--full-output'],
        'derivation_script': str(Path(__file__).resolve().relative_to(ROOT)),
        'derivation_sha256': digest(Path(__file__))
    }
}
(OUT / 'finding.json').write_text(json.dumps(finding, indent=2) + '\n')
print(json.dumps({'finding_id': finding['finding_id'], 'sealed_sources': len(sources),
                  'rea_evidence': data['evidence_id'], 'source_executed': False}))
