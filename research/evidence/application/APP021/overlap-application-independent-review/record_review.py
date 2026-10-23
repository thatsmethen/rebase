"""Record the independent source review after the implementation owner freezes.

Reads application/research artifacts; writes a new review.json exclusively.
It neither builds the shared Swift workspace nor executes proprietary code.
"""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
APP = ROOT / 'Application'
STUDY = ROOT / 'research/evidence/cubase-static/cpr-audio-events-001/track-overlaps'
PREVIOUS = ROOT / 'research/evidence/application/APP020/final-source-snapshot'


def record(path):
    path = Path(path)
    data = path.read_bytes()
    return dict(path=str(path.relative_to(ROOT)), bytes=len(data), sha256=sha256(data).hexdigest())


def source_inventory():
    paths = [APP / 'Package.swift', APP / 'Package.resolved', APP / 'build-app.sh', APP / 'test-app.sh']
    paths += [p for folder in ['Sources', 'Tests'] for p in (APP / folder).rglob('*') if p.is_file()]
    return [record(p) for p in sorted(set(paths))]


source_before = source_inventory()
anchors = {
    STUDY / 'finding.json': '15c8365e3da4410ccfbc443f4bcef8f019c618fabd6347645be978f5de8cfe20',
    STUDY / 'artifact-manifest.json': 'a0643cc0c0c1f14d626da5663765bde844b2ec2b20de15aa8f9fb8d2cf9b35dc',
    STUDY / 'independent-review-01/review.json': '17b2c5ba6db68e3d1e70bf131ebdf059bee0094416d6d02e04739fbc000dec48',
    HERE.parent / 'overlap-kernel-check/result.json': '5511483845e1207c9ae9e299731fcc75b5a32a55c851acda5b47f1385552b6d4',
}
for path, expected in anchors.items():
    assert record(path)['sha256'] == expected, path

kernel = json.loads((HERE.parent / 'overlap-kernel-check/result.json').read_text())
assert kernel['status'] == 'passed' and kernel['target_executed'] is False
assert kernel['native_runtime_comparisons'] == 0 and kernel['live_source_unchanged']
for pin in kernel['source_before'] + kernel['source_after'] + kernel['compiled_sources']:
    assert record(ROOT / pin['path']) == pin, pin['path']

# These are narrow custody/guard checks, separate from the manual semantic
# review below and from the owner's executable test evidence.
placed = (APP / 'Sources/RebaseCore/CPRPlacedSourceEventPlan.swift').read_text()
plan = (APP / 'Sources/RebaseCore/CPRSourceTrackPlan.swift').read_text()
stream = (APP / 'Sources/RebaseCore/CPRNativeTimelineStream.swift').read_text()
view = (APP / 'Sources/Rebase/CPRSourceAudioView.swift').read_text()
banner = (APP / 'Sources/Rebase/RebaseApp.swift').read_text()
assert placed.count('priorityPolicy: .requireDefault') == 2
assert 'priorityPolicy: .normalizedTrack' in plan
assert 'ObjectIdentifier(source.source)' in stream
assert 'Surviving fragments derive their offsets from the original event.' in view
assert '.accessibilityLabel(info.sourceTrack == nil ? "Source event audition mode" : "Source track audition mode")' in banner

changed = []
added = []
missing = []
for p in sorted(PREVIOUS.rglob('*')):
    if not p.is_file():
        continue
    live = APP / p.relative_to(PREVIOUS)
    if not live.exists():
        missing.append(str(live.relative_to(ROOT)))
    elif p.read_bytes() != live.read_bytes():
        changed.append(dict(before=record(p), after=record(live)))
for folder in ['Sources', 'Tests']:
    for live in sorted((APP / folder).rglob('*')):
        if live.is_file() and not (PREVIOUS / live.relative_to(APP)).exists():
            added.append(record(live))
assert not missing

focused = []
for path in sorted(HERE.parent.glob('focused-tests-*.json')):
    item = json.loads(path.read_text())
    log = ROOT / item['log']['path']
    assert record(log) == item['log']
    focused.append(dict(record=record(path), exit_code=item['exit_code'], log=record(log)))
assert any(item['exit_code'] == 0 for item in focused), 'Owner focused test success must be retained before final review'

review = dict(
    status='no source-level blockers within the bounded overlap admission',
    created_utc=datetime.now(timezone.utc).isoformat(),
    reviewer='independent overlap semantic reviewer; author of the prior sealed independent static overlap review, not author of the application core',
    target_executed=False,
    shared_swift_build_run_by_reviewer=False,
    application_or_gui_executed_by_reviewer=False,
    native_runtime_comparisons=0,
    scope='Read-only review of APP021 application integration against sealed static overlap evidence and APP020 frozen sources. Existing overlap and partial explicit-fade research were not modified. Only this new review directory is owned by this review.',
    evidence_classification={
        'native_semantics': 'Retained exact native readbacks, the sealed finding, and the prior independent semantic review. These are static evidence, not reference runtime observations.',
        'kernel_comparisons': 'Owner executed authored C against analytical models: 24 retained controls and 20000 clustered-epsilon cases, 4096-input quadratic case, 8191 nested fragments, and transactional rejections. This review verifies source pins and reads the result; it does not claim an independently repeated C run.',
        'integration_tests': 'Forward-authored importer graphs and patterned PCM media exercise application plumbing. These are not native-generated or proven native-valid projects.',
        'ui': 'Source-level review only. Native application GUI observation, release packaging, and full-suite execution are separate owner validation duties.'
    },
    sealed_research_and_kernel=[record(p) for p in anchors],
    review_recorder=record(Path(__file__)),
    semantic_checks=[
        {
            'topic': 'Linked-list node identity and exact competition branches',
            'result': 'pass',
            'detail': 'C removes current before competing, preserves the exact following.next pointer before unlink/reinsertion, inserts tails after equal starts, and keeps original sourceIndex/ordinal/priority on clones. Competition uses current.end >= following.start and fabs of one separately rounded binary64 subtraction >= the exact 0x3f1a36e2eb1c432d epsilon. Equality competes. Sub-epsilon overlap bypasses priority and is resolved by publication watermark clamping. Prefix and tail tests retain their respective ordered comparisons and the same rounded-distance threshold. Publication starts from 0xc14b774000000000, clamps start and advances max-end before positive-length retention.'
        },
        {
            'topic': 'Signed priority and original admitted contributor ordinal',
            'result': 'pass',
            'detail': 'Int32 priority comparisons are signed in Swift storage and C. Larger priority wins and equal priority uses larger original collector ordinal. Track admission requires every counted direct child to pass, making counted child order equal to admitted collector order in this restricted context. Source indices are checked against input positions; distinct nonnegative Int32 ordinals are checked without sorting. No new fragment can become a new contributor identity. The sealed native finding supports all Int32 saved priorities here; this is not an arbitrary priority-equals-one restriction.'
        },
        {
            'topic': 'Original canonical placement and reader bounds',
            'result': 'pass',
            'detail': 'Canonical start/end/source offset are recovered once from the preserved CPR clock and scalar datum. Every normalized fragment passes those original values with its new canonical window to the native-builder reconstruction. No rounded parent or previous fragment is used as a new origin. Builder snapping and getter-end reader quantization remain separate. Valid builder-empty fragments are omitted and counted; malformed, incomplete or overlapping quantized reads reject before scheduling. Original full-event projection is metadata and may be nil; it does not impose complete unconverted source-read capacity on a fully covered interval. Original saved trim remains within source capacity for every contributor.'
        },
        {
            'topic': 'Complete contributor and media proof including masked events',
            'result': 'pass',
            'detail': 'Track plan replays the immutable source and checks counted membership, each original object identity, root, containing node, ancestor track chain, retained source hash, clip and cluster. Unknown, nested, removed, duplicated or added contributors reject. Every entry must have an attachment; playback budgets, validates, reads, hashes and decodes every original source before constructing the stream, including completely masked events and the covered anchor. Only the audible fragments become descriptors. Prepare failure cannot install a partially checked track.'
        },
        {
            'topic': 'Resource ownership and gain validation',
            'result': 'pass with explicit application limits',
            'detail': '4096 original contributors and 8192 normalized descriptors are application limits. C uses a count+1 node pool, bounded output buffer, and 4*N*N+N comparison-visit guard; failures leave caller output and count unchanged. Playback counts all original source samples against 32000000 before decode. Immutable Source objects are shared by fragments of the same original contributor. Stream deduplicates with actual ObjectIdentifier rather than a caller-controlled key; distinct original sources remain conservatively counted even if their array backing happens to share. Full source/gain arithmetic checks are cached by actual Source identity plus gain bits. Ordinary callers retain the 4096-segment limit. The comparison guard is policy, not a native limit or a bound on every linked-list operation.'
        },
        {
            'topic': 'Old single-event contract and host scheduling',
            'result': 'pass',
            'detail': 'All existing single-event placement wrappers still use requireDefault; completeMedia defaults to that policy and renderer/converter paths retain that default. Existing contract strings and full-event projection arithmetic remain. Only complete-track preparation requests normalizedTrack. Ancestor timing, stereo PCM24, whole-frame trim, zero fades, no inversion/lanes/warp and saved-root gates remain. The shared stream accessor cache continues to key lifetime to descriptor index, so selecting another fragment resets source state even when its immutable source storage is shared. StudioSession and AudioTransportEngine are unchanged relative to APP020; device scheduling remains application behavior.'
        },
        {
            'topic': 'Metadata and UI describe the actual source audition',
            'result': 'pass after wording correction',
            'detail': 'Track metadata separates all original events from audible fragments and preserves per-original hashes, priorities and collector ordinals; covered anchors stay identifiable. Timeline source audition draws actual fragment reader ranges. Original events with no audible fragment remain selectable with a distinct nonaudible canonical outline and explanation. Inspection/banner distinguish source-event count, fragment count and snapped-empty omissions; track mode has its own accessibility label. Text describes source-derived offsets, saved clock without rate conversion, fresh default filtering, and unresolved project processing. Frozen import placement and unresolved project status remain unchanged.'
        }
    ],
    resolved_review_notes=[
        'The original UI phrase keep their original source offsets was imprecise for trimmed tails. It was changed to derive their offsets from the original event.',
        'The banner originally exposed Source event audition mode in track mode. It now exposes Source track audition mode for a prepared source track.'
    ],
    blockers=[],
    limitations=[
        'No Cubase process, library entrypoint or reference audio output was executed. Full Cubase fidelity is not established.',
        'The admitted context is fresh root mode 0, a complete counted chronological direct all-passing plain track, saved supported whole project rate, accepted source clock, stereo PCM24 media, whole-frame source trim, no explicit/automatic fades, inversion, lanes, warp, mixer, routing, automation or host callbacks.',
        'A track whose every normalized fragment snaps empty is rejected as having no audible frames; this milestone does not install an empty live source track.',
        'Nonempty normalized fragments whose raw source reads would exceed media at the unconverted saved clock remain rejected.',
        'Full-suite fixed-binary checks, release build and native GUI observations are separate milestone acceptance prerequisites. This review is not a replacement for them.',
        'Earlier focused compiler failures are retained below rather than overwritten. Source syntax repairs do not constitute target-behavior measurements.'
    ],
    focused_owner_runs=focused,
    source_changes_from_APP020=changed,
    source_additions_from_APP020=added,
    source_missing_from_APP020=missing,
    source_before=source_before,
)
source_after = source_inventory()
assert source_before == source_after, 'Application source changed during final review recording'
review['source_after'] = source_after
review['source_unchanged_during_recording'] = True
with (HERE / 'review.json').open('x') as f:
    json.dump(review, f, indent=2)
    f.write('\n')
print(json.dumps(record(HERE / 'review.json')))
