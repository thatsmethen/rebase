import Foundation
import RebaseTimingDSP

/// Complete saved direct-track membership and priority-normalized windows. This
/// value is separate from editable project playback and from native routing.
/// The native collector contract is limited to fresh root mode 0, counted
/// chronological MListNode events, and the existing plain-source/fade gates.
struct CPRSourceTrackPlan {
    struct Entry {
        let ordinal: Int
        let retained: UnresolvedCPRAudioEvent
        let priority: Int32
        let canonical: CPRPlacedSourceEventPlan.Canonical
        let originalRange: CPRSourceEventTimelineRange?
    }
    struct Fragment {
        let entryIndex: Int
        let placed: CPRPlacedSourceEventPlan
        let firstFrame: Int64
        let endFrame: Int64
    }

    let track: CPRTrackContributorInventory
    let setup: CPRProjectAudioSetup
    let entries: [Entry]
    let fragments: [Fragment]
    let snappedEmptyFragmentCount: Int

    static func make(eventID: UUID, project: Project, root: URL) throws -> CPRSourceTrackPlan {
        func unsupported(_ message: String) -> RebaseCoreError { .unsupportedAudio(message) }
        // This replays the frozen interpretation and checks every retained
        // event against its original imported track, not just the anchor.
        let verified = try ProjectStore.verifiedCPRSourceEvent(eventID, in: project, at: root)
        let inventory = try CPRTrackContributorArchive.read(container: verified.container)
        guard let track = inventory.tracks.first(where: {
            $0.track.identityOffset == verified.source.trackIdentity
        }), track.isDirectAudioTrack,
              track.node.object == verified.source.containingNode,
              inventory.root == verified.source.root else {
            throw unsupported("Track audition requires a completely inventoried direct audio track.")
        }
        let children = track.node.children
        guard !children.isEmpty, children.count <= 4096,
              track.node.declaredChildCount == children.count,
              children.allSatisfy({ $0.classification == .audioEvent }) else {
            throw unsupported("Every counted track child must be a supported audio event. Unknown, nested or other contributors prevent complete track audition.")
        }
        guard let current = project.tracks.first(where: {
            $0.unresolvedAudioEvents.contains(where: { $0.id == eventID })
        }), current.clips.isEmpty,
              current.unresolvedAudioEvents.count == children.count,
              Set(current.unresolvedAudioEvents.map { $0.event.identityOffset }) ==
                Set(children.map { $0.object.identityOffset }) else {
            throw unsupported("Track audition requires every original source event on its imported track and no added clips. Restore removed events before auditioning the complete saved track.")
        }
        let sources = try CPRAudioEventArchive.read(container: verified.container)
            .filter { $0.trackIdentity == track.track.identityOffset }
        guard sources.count == children.count else {
            throw unsupported("The audio decoder did not account for every counted track contributor.")
        }
        var sourcesByIdentity: [Int: CPRSourceAudioEvent] = [:]
        var retainedByIdentity: [Int: UnresolvedCPRAudioEvent] = [:]
        for source in sources {
            guard sourcesByIdentity.updateValue(source, forKey: source.event.identityOffset) == nil else {
                throw CPRProjectError.invalid("The decoded source contains a repeated contributor identity.")
            }
        }
        for retained in current.unresolvedAudioEvents {
            guard retainedByIdentity.updateValue(retained, forKey: retained.event.identityOffset) == nil else {
                throw CPRProjectError.invalid("The retained track contains a repeated source contributor identity.")
            }
        }
        let fades = try CPRAutoFadeArchive.read(container: verified.container)
        let context = try CPRPlacedSourceEventPlan.savedProjectContext(container: verified.container)
        let setup = context.setup
        let rate = context.rate
        guard setup.root == inventory.root else {
            throw CPRProjectError.invalid("Track inventory and saved audio setup belong to different arrangement roots.")
        }
        var entries: [Entry] = []
        for child in children {
            guard let source = sourcesByIdentity[child.object.identityOffset], source.event == child.object,
                  source.root == inventory.root, source.containingNode == track.node.object,
                  source.ancestorTracks == track.ancestorTracks,
                  let retained = retainedByIdentity[child.object.identityOffset], retained.event == child.object,
                  retained.sourceSHA256 == setup.sourceSHA256,
                  retained.clip == source.clip, retained.cluster == source.cluster.object else {
                throw CPRProjectError.invalid("A counted contributor no longer matches its preserved source event.")
            }
            let canonical = try CPRPlacedSourceEventPlan.savedProjectCanonical(context: context,
                source: source, retained: retained, fades: fades, priorityPolicy: .normalizedTrack)
            guard project.attachedMedia(for: retained) != nil else {
                throw unsupported("Attach matching PCM24 WAV media for every event before auditioning the complete track.")
            }
            let originalRange = try canonical.project(windowStart: canonical.canonicalStart,
                windowEnd: canonical.canonicalEnd, requireCompleteRead: false)?.range
            entries.append(Entry(ordinal: child.ordinal, retained: retained, priority: source.priority,
                canonical: canonical, originalRange: originalRange))
        }
        // Counted child order is also collector order only because every child
        // in this direct track passed the fresh default collector gates. Never
        // sort an arbitrary source order or reuse a fragment's queue position.
        let normalized = try CPRTrackOverlapNormalizer.normalize(entries.enumerated().map { index, entry in
            .init(sourceIndex: index, ordinal: entry.ordinal, priority: entry.priority,
                start: entry.canonical.canonicalStart, end: entry.canonical.canonicalEnd)
        })
        var fragments: [Fragment] = []
        var snappedEmptyCount = 0
        var previousEnd: Int64 = 0
        for window in normalized {
            let entry = entries[window.sourceIndex]
            guard entry.ordinal == window.ordinal, entry.priority == window.priority else {
                throw CPRProjectError.invalid("A normalized fragment lost its original source contributor identity.")
            }
            // This always projects from the original unsnapped source origin;
            // trimming an earlier projected fragment changes sample rounding.
            guard let placed = try entry.canonical.project(windowStart: window.start, windowEnd: window.end) else {
                snappedEmptyCount += 1
                continue
            }
            var first: Int64 = 0, end: Int64 = 0
            guard rb_cpr_timeline_quantize(1 / rate, placed.range.position, &first) == 0,
                  rb_cpr_timeline_quantize(1 / rate,
                    placed.range.position + placed.range.duration, &end) == 0,
                  first >= previousEnd, end > first else {
                throw unsupported("Normalized source fragments do not form supported disjoint native reader windows.")
            }
            fragments.append(Fragment(entryIndex: window.sourceIndex, placed: placed,
                                      firstFrame: first, endFrame: end))
            previousEnd = end
        }
        guard !fragments.isEmpty else {
            throw unsupported("This source track has no audible frames after native segment construction.")
        }
        return CPRSourceTrackPlan(track: track, setup: setup, entries: entries,
            fragments: fragments, snappedEmptyFragmentCount: snappedEmptyCount)
    }
}
