"""Record the recovered overlap contract; never executes the reference image."""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]


def pin(path):
    data = path.read_bytes()
    return dict(path=str(path.relative_to(ROOT)), bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest())


verification = json.loads((HERE / 'verification.json').read_text())
controls = json.loads((HERE / 'branch-controls.json').read_text())
assert verification['passed'] and controls['passed']
assert verification['target_executed'] is False
assert verification['summary']['canonical_records'] == 40
functions = {row['entry']: row for row in verification['functions']}


def support(*addresses):
    return [dict(entry=hex(address), directory=functions[hex(address)]['directory'],
                 evidence_ids=functions[hex(address)]['evidence_ids']) for address in addresses]


claims = [
    dict(id='TRACK-OVERLAP-1', claim='Saved event priority is a signed 32-bit value; larger priority wins overlaps, with later admitted collector ordinal winning ties.',
         details=['MAudioEvent reader stores serialized priority at +80; virtual getter +1a8 reads the same word. The normalizer uses signed comparisons for priority and ordinal.',
                  'Collector ordinal belongs to admitted traversal order. It matches relative counted order only when every supported plain child passes the explicit fresh filter and collection window.',
                  'Default filtering, collection clipping and the admitted plain segment builder do not reinterpret priority. Other hosted paths and callbacks remain outside the contract.'],
         support=support(0x1000ee164, 0x1000ea130, 0x10020e354, 0x10020e7c8, 0x10020f2e8)),
    dict(id='TRACK-OVERLAP-2', claim='Overlap resolution trims, removes and splits ranges while preserving original event, context and ordinal identities.',
         details=['A stronger current range removes a following range or moves its surviving tail to currentEnd. A stronger following range can retain an earlier prefix and clone the current tail after followingEnd.',
                  'Tail reinsertion scans backward by start and inserts after equal starts. The current-wins branch continues from the saved successor of the removed node, not from the current list head.',
                  'Initial serialized order is not repaired by sorting. This contract accepts chronological finite positive input only.'],
         support=support(0x10020e7c8, 0x1002136ec, 0x103101840, 0x1031022a0, 0x103101e50)),
    dict(id='TRACK-OVERLAP-3', claim='The exact binary64 epsilon and publication watermark govern which short overlaps and remainders survive.',
         details=['Epsilon bits are 3f1a36e2eb1c432d. The overlap branch requires currentEnd >= nextStart and abs(rounded64(currentEnd-nextStart)) >= epsilon; equality enters the branch.',
                  'A surviving cloned or trimmed tail requires an end distance at least epsilon. An earlier prefix additionally requires currentStart < nextStart. Sub-epsilon overlap bypasses priority resolution.',
                  'Publication clamps start to the prior published-end watermark, advances that watermark to the larger end and retains only a positive resulting duration. A small standalone event is not discarded solely because its duration is below epsilon.'],
         support=support(0x10020e7c8)),
    dict(id='TRACK-OVERLAP-4', claim='Each surviving fragment is freshly projected from its original event coordinates before builder and reader quantization.',
         details=['Use original contextOffset + (fragmentStart - originalEventStart), preserving the separate binary64 operations and original event/context identity.',
                  'Intersect the original canonical interval with the normalized fragment, then call the existing native builder projection. Never trim an already rounded range or accumulate offsets through earlier fragments.',
                  'Builder-snapped-empty fragments produce no segment. Every original contributor and media binding must still be accounted for, including fully covered events and a fully covered selected anchor.',
                  'Nil neighbor links, absent explicit fades, effective automatic-fade flags0 and the other existing plain-source gates are required. This finding does not recover crossfades, mixer routing, automation or rate-selection policy.'],
         support=support(0x10020f2e8, 0x1002136ec, 0x1000ea704, 0x1000ea694, 0x100212f3c)),
]

prior = HERE.parent
finding = dict(schema_version=1, finding_id='TRACK-OVERLAPS-001',
    status='bounded static chronological plain-track overlap contract',
    source_sha256=verification['source_sha256'], target_executed=False,
    native_runtime_comparisons=0,
    provider='Pinned rea-agents 6.7.0 with isolated Ghidra arm64 raw imports; original-image instructions authoritative',
    claims=claims, verification=pin(HERE / 'verification.json'),
    analytical_controls=pin(HERE / 'branch-controls.json'),
    analytical_model=pin(HERE / 'normalizer_model.py'),
    control_summary={key: controls[key] for key in [
        'threshold_pair_cases', 'pair_stream_sha256', 'maximum_priority_envelope_cases',
        'envelope_stream_sha256', 'bound_4096_events_passed', 'actions_covered']},
    prior_findings=[pin(prior / directory / 'finding.json') for directory in [
        'track-contributors', 'placed-event-builder', 'placed-event-context', 'project-audio-setup']],
    limits=[
        'Static instruction translation and independent numerical controls are not native runtime equivalence.',
        'Fresh root mode0, nil external predicate and fresh flags/attributes are explicit reconstruction conditions, not observed hosted restoration.',
        'Chronological finite nonnegative positive ranges, at most4096 inputs, within86400 seconds; arbitrary initial source order is unresolved.',
        'The analytical model has a defensive four-million comparison limit. Its4096 chain control does not establish acceptance of every4096-event input; worst cases can exceed that work bound.',
        'Object lifetimes, allocations, callback replacement, dynamic getters, external state and device behavior are not modeled.',
        'Reference code remains unexecuted. App acceptance, release packaging and GUI checks are separate deliverables.',
        'Private original-image readbacks are evidence references, not a redistribution or publication license.'])

with (HERE / 'finding.json').open('x') as output:
    json.dump(finding, output, indent=2)
    output.write('\n')
print(json.dumps(pin(HERE / 'finding.json')))
