import Foundation

/// Ephemeral proof of every original contributor and the audible fragments
/// selected by source priority. This is independent of mixer/routed output.
public struct CPRSourceTrackPlaybackInfo: Equatable {
    public static let contractName = "cpr-15.0.30.287-priority-track-fresh-root-mode0-v1"
    public struct Event: Equatable {
        public let eventID: UUID
        public let eventIdentity: Int
        public let sourceOrdinal: Int
        public let priority: Int32
        public let sourceSampleRate: Double
        public let mediaSHA256: String
        public let canonicalStart: Double
        public let canonicalEnd: Double
        /// Original projection, including fully covered events; nil only when
        /// the original interval itself has no builder-produced segment.
        public let range: CPRSourceEventTimelineRange?
    }
    public struct Fragment: Equatable {
        public let eventID: UUID
        public let eventIdentity: Int
        public let sourceOrdinal: Int
        public let range: CPRSourceEventTimelineRange
    }

    public let contract: String
    /// Explicit reconstruction context, not a recovered hosted root mode.
    public let freshRootMode: UInt32
    public let trackIdentity: Int
    public let events: [Event]
    public let fragments: [Fragment]
    public let snappedEmptyFragmentCount: Int
}

/// Entire contributor membership/media verification completes before transport
/// installation, including source events completely covered by stronger events.
enum CPRSourceTrackPlayback {
    static func prepare(eventID: UUID, project: Project, root: URL) throws
        -> (track: CPRSourceTrackPlaybackInfo, setup: CPRProjectAudioSetup,
            name: String, sourceSHA256: String, audio: PreparedProject) {
        let plan = try CPRSourceTrackPlan.make(eventID: eventID, project: project, root: root)
        let rate = try plan.setup.supportedSampleRate()
        var remainingSamples = 32_000_000
        for entry in plan.entries {
            let media = entry.canonical.media
            let count = media.frames * media.channels
            guard count <= remainingSamples else { throw RebaseCoreError.mediaTooLarge }
            remainingSamples -= count
        }
        var sources: [CPRNativeTimelineStream.Source] = []
        var events: [CPRSourceTrackPlaybackInfo.Event] = []
        for entry in plan.entries {
            let canonical = entry.canonical
            let source = try CPRSourceEventRenderer.prepareMedia(plan: canonical.media,
                retained: entry.retained, sourceSHA256: plan.setup.sourceSHA256,
                in: project, at: root)
            sources.append(.init(samples: source.samples, sourceRate: Double(canonical.media.rate)))
            events.append(.init(eventID: entry.retained.id, eventIdentity: entry.retained.event.identityOffset,
                sourceOrdinal: entry.ordinal, priority: entry.priority, sourceSampleRate: Double(canonical.media.rate),
                mediaSHA256: source.mediaSHA256, canonicalStart: canonical.canonicalStart,
                canonicalEnd: canonical.canonicalEnd, range: entry.originalRange))
        }
        var segments: [CPRNativeTimelineStream.Segment] = []
        var fragments: [CPRSourceTrackPlaybackInfo.Fragment] = []
        for fragment in plan.fragments {
            let entry = plan.entries[fragment.entryIndex]
            let placed = fragment.placed
            segments.append(.init(start: placed.range.position, length: placed.range.duration,
                offset: placed.range.offset, source: sources[fragment.entryIndex], gain: placed.media.gain))
            fragments.append(.init(eventID: entry.retained.id, eventIdentity: entry.retained.event.identityOffset,
                sourceOrdinal: entry.ordinal, range: placed.range))
        }
        let stream = try CPRNativeTimelineStream(sampleRate: rate, segments: segments, policy: .normalizedTrack)
        return (CPRSourceTrackPlaybackInfo(contract: CPRSourceTrackPlaybackInfo.contractName,
            freshRootMode: 0, trackIdentity: plan.track.track.identityOffset, events: events,
            fragments: fragments, snappedEmptyFragmentCount: plan.snappedEmptyFragmentCount),
            plan.setup, plan.track.name, plan.setup.sourceSHA256,
            PreparedProject(format: stream.format, frameCount: stream.frameCount,
                clips: [], nativeTimelineStream: stream))
    }
}
