import Foundation

public enum CPRSourceEventPlaybackMode: String, CaseIterable, Equatable, Sendable {
    case sourceRate
    case nativeTimelineSourceRate
    case nativeTimelineProjectClock
    case nativeTimelineSavedProjectClock
    case nativeTrackSavedProjectClock
    case nativeMode0ProjectRate
    case nativeMode1ProjectRate
    case nativeMode2ProjectRate

    public var displayName: String {
        switch self {
        case .sourceRate: return "Stereo audition"
        case .nativeTimelineSourceRate: return "Native timeline reader"
        case .nativeTimelineProjectClock: return "Native project clock · unconverted"
        case .nativeTimelineSavedProjectClock: return "Saved project clock · unconverted"
        case .nativeTrackSavedProjectClock: return "Complete source track · saved clock"
        case .nativeMode0ProjectRate: return "Native mode 0"
        case .nativeMode1ProjectRate: return "Native mode 1"
        case .nativeMode2ProjectRate: return "SoXR mode 2"
        }
    }
}

/// Ephemeral source interpretation; it never overwrites frozen import timing.
public struct CPRSourceEventTimelineRange: Equatable {
    public let contract: String
    public let position: Double
    public let duration: Double
    public let offset: Double
}

public struct CPRSourceEventPlaybackInfo: Equatable {
    public let eventID: UUID
    public let name: String
    public let sampleRate: Double
    public let sourceSampleRate: Double
    public let mode: CPRSourceEventPlaybackMode
    public let frameCount: Int64
    public let sourceSHA256: String
    public let mediaSHA256: String
    public var timelineRange: CPRSourceEventTimelineRange? = nil
    public var savedProjectAudioSetup: CPRProjectAudioSetup? = nil
    /// When present, per-event media hashes cover the complete source
    /// track. eventID/sourceSampleRate/mediaSHA256 still describe its anchor.
    public var sourceTrack: CPRSourceTrackPlaybackInfo? = nil
    public var auditionScope: String { sourceTrack == nil ? "Source event" : "Source track" }
    public var duration: Double { Double(frameCount) / sampleRate }
}

/// Immutable verified source preparation shared by Mac and portable hosts.
/// Each cursor owns its conversion/ring state. Preparing again replays source
/// provenance; neither this API nor its output establishes device behavior.
public enum CPRSourceAudition {
    enum Output {
        case source([Float], CPRTimelineSelection.Segment)
        case timeline(CPRNativeTimelineStream)
        case converted(CPRRateConvertedStream, CPRTimelineSelection.Segment)
    }

    public struct Prepared {
        public let info: CPRSourceEventPlaybackInfo
        public var sampleRate: Double { info.sampleRate }
        public var frameCount: Int64 { info.frameCount }
        let output: Output

        /// Existing application seek policy shared with the macOS scheduler.
        /// Native event selection precedes output-frame rounding; this matters
        /// where converter counts and the saved source duration differ.
        public func startFrame(at seconds: Double) throws -> Int64 {
            let selection: CPRTimelineSelection.Segment?
            switch output {
            case .source(_, let event), .converted(_, let event): selection = event
            case .timeline: selection = nil
            }
            return try CPRSourceAudition.startFrame(sampleRate: sampleRate, frameCount: frameCount,
                nativeEventSelection: selection, at: seconds)
        }

        public func cursor(from outputFrame: Int64) throws -> Cursor {
            guard (0...frameCount).contains(outputFrame) else {
                throw RebaseCoreError.invalidProject("Audition playback position is outside the prepared output.")
            }
            return try Cursor(prepared: self, from: outputFrame)
        }
    }

    public final class Cursor {
        private enum OutputCursor {
            case source(SourceCursor)
            case timeline(CPRNativeTimelineStream.Cursor)
            case converted(CPRRateConvertedStream.Cursor)
        }
        private let output: OutputCursor
        public var deliveredFrames: Int64 {
            switch output {
            case .source(let cursor): return cursor.position
            case .timeline(let cursor): return cursor.deliveredFrames
            case .converted(let cursor): return cursor.deliveredFrames
            }
        }
        public var isAtEnd: Bool {
            switch output {
            case .source(let cursor): return cursor.position == Int64(cursor.samples.count / 2)
            case .timeline(let cursor): return cursor.isAtEnd
            case .converted(let cursor): return cursor.isAtEnd
            }
        }
        fileprivate init(prepared: Prepared, from frame: Int64) throws {
            switch prepared.output {
            case .source(let samples, _): output = .source(SourceCursor(samples: samples, position: frame))
            case .timeline(let stream): output = .timeline(try stream.cursor(from: frame))
            case .converted(let stream, _): output = .converted(try stream.cursor(from: frame))
            }
        }
        /// Returns the existing output-stage partition. In particular converter
        /// blocks are never split before the recovered ring/callback operations.
        public func nextPlaybackBlock() throws -> StereoPCMBlock? {
            switch output {
            case .source(let cursor): return try cursor.nextPlaybackBlock()
            case .timeline(let cursor): return try cursor.nextPlaybackBlock()
            case .converted(let cursor): return try cursor.nextPlaybackBlock()
            }
        }
    }

    private final class SourceCursor {
        let samples: [Float]
        var position: Int64
        init(samples: [Float], position: Int64) { self.samples = samples; self.position = position }
        func nextPlaybackBlock() throws -> StereoPCMBlock? {
            guard position < Int64(samples.count / 2) else { return nil }
            let last = min(Int64(samples.count / 2), position + 4096)
            let block = try StereoPCMBlock(interleaved: samples[(Int(position) * 2)..<(Int(last) * 2)])
            position = last
            return block
        }
    }

    /// Shared application host policy, not an inferred native live scheduler.
    static func startFrame(sampleRate: Double, frameCount: Int64,
                           nativeEventSelection: CPRTimelineSelection.Segment?, at seconds: Double) throws -> Int64 {
        guard seconds.isFinite, seconds >= 0, sampleRate.isFinite,
              sampleRate > 0, frameCount >= 0 else {
            throw RebaseCoreError.invalidProject("Playback position must be a finite nonnegative time.")
        }
        let duration = Double(frameCount) / sampleRate
        if let segment = nativeEventSelection {
            var cursor = CPRTimelineSelection.Cursor(generation: 0)
            let selected = try CPRTimelineSelection.select([segment], at: min(seconds, duration),
                generation: 0, cursor: &cursor)
            if selected == nil { return frameCount }
        }
        if seconds >= duration { return frameCount }
        guard let converted = Int64(exactly: (seconds * sampleRate).rounded()) else {
            throw RebaseCoreError.invalidProject("Playback position cannot be represented as an audio frame.")
        }
        return min(frameCount, converted)
    }

    public static func prepare(eventID: UUID, in project: Project, at root: URL,
                        mode: CPRSourceEventPlaybackMode = .sourceRate) throws
        -> Prepared {
        if mode == .nativeTrackSavedProjectClock {
            let prepared = try CPRSourceTrackPlayback.prepareStream(eventID: eventID, project: project, root: root)
            guard let anchor = prepared.track.events.first(where: { $0.eventID == eventID }) else {
                throw RebaseCoreError.invalidProject("The track source no longer contains its selected event.")
            }
            var info = CPRSourceEventPlaybackInfo(eventID: eventID, name: prepared.name,
                sampleRate: prepared.stream.sampleRate, sourceSampleRate: anchor.sourceSampleRate,
                mode: mode, frameCount: prepared.stream.frameCount, sourceSHA256: prepared.sourceSHA256,
                mediaSHA256: anchor.mediaSHA256)
            info.savedProjectAudioSetup = prepared.setup
            info.timelineRange = anchor.range
            info.sourceTrack = prepared.track
            return Prepared(info: info, output: .timeline(prepared.stream))
        }
        if mode == .nativeTimelineSourceRate || mode == .nativeTimelineProjectClock || mode == .nativeTimelineSavedProjectClock {
            let verified = try ProjectStore.verifiedCPRSourceEvent(eventID, in: project, at: root)
            let fades = try CPRAutoFadeArchive.read(container: verified.container)
            let placed: CPRPlacedSourceEventPlan
            let savedSetup: CPRProjectAudioSetup?
            if mode == .nativeTimelineSavedProjectClock {
                let saved = try CPRPlacedSourceEventPlan.makeSavedProjectClock(container: verified.container,
                    source: verified.source, retained: verified.retained, fades: fades)
                placed = saved.plan; savedSetup = saved.setup
            } else {
                placed = try CPRPlacedSourceEventPlan.make(container: verified.container,
                    source: verified.source, retained: verified.retained, fades: fades,
                    timelineRate: mode == .nativeTimelineProjectClock ? project.sampleRate : nil)
                savedSetup = nil
            }
            let source = try CPRSourceEventRenderer.prepareMedia(plan: placed.media, retained: verified.retained,
                sourceSHA256: verified.container.sha256, in: project, at: root)
            let stream = try CPRNativeTimelineStream(sampleRate: placed.timelineRate, segments: [
                .init(start: placed.range.position, length: placed.range.duration, offset: placed.range.offset,
                      samples: source.samples, gain: placed.media.gain, sourceRate: Double(placed.media.rate))
            ])
            var info = CPRSourceEventPlaybackInfo(eventID: eventID, name: verified.retained.name,
                sampleRate: placed.timelineRate, sourceSampleRate: Double(placed.media.rate), mode: mode,
                frameCount: stream.frameCount, sourceSHA256: source.sourceSHA256,
                mediaSHA256: source.mediaSHA256)
            info.timelineRange = placed.range
            info.savedProjectAudioSetup = savedSetup
            return Prepared(info: info, output: .timeline(stream))
        }
        if mode == .sourceRate {
            let source = try CPRSourceEventRenderer.prepareAudition(eventID: eventID, in: project, at: root)
            guard let event = project.unresolvedAudioEvents.first(where: { $0.id == eventID }),
                  let placement = event.placement else {
                throw RebaseCoreError.invalidProject("The selected source event is no longer in this project.")
            }
            let info = CPRSourceEventPlaybackInfo(eventID: eventID, name: event.name,
                sampleRate: source.sampleRate, sourceSampleRate: source.sampleRate, mode: mode,
                frameCount: Int64(source.frameCount), sourceSHA256: source.sourceSHA256, mediaSHA256: source.mediaSHA256)
            return Prepared(info: info, output: .source(source.samples,
                CPRTimelineSelection.Segment(start: placement.position, length: placement.duration, successor: -1)))
        }
        let source = try CPRSourceEventRenderer.prepare(eventID: eventID, in: project, at: root, applyEventGain: false)
        let plan = source.plan
        guard plan.channels == 2 else {
            throw RebaseCoreError.unsupportedAudio("Timeline audition currently requires a stereo source; native mono output routing is unresolved.")
        }
        guard let event = project.unresolvedAudioEvents.first(where: { $0.id == eventID }), let placement = event.placement else {
            throw RebaseCoreError.invalidProject("The selected source event is no longer in this project.")
        }
        let stream = try CPRRateConvertedStream(source: source.samples,
            sourceRate: Double(plan.rate), outputRate: project.sampleRate, gain: plan.gain,
            algorithm: mode == .nativeMode2ProjectRate ? .nativeMode2 :
                mode == .nativeMode1ProjectRate ? .nativeMode1 : .nativeMode0)
        let info = CPRSourceEventPlaybackInfo(eventID: eventID, name: event.name,
            sampleRate: project.sampleRate, sourceSampleRate: Double(plan.rate), mode: mode,
            frameCount: stream.frameCount, sourceSHA256: source.sourceSHA256,
            mediaSHA256: source.mediaSHA256)
        return Prepared(info: info, output: .converted(stream,
            CPRTimelineSelection.Segment(start: placement.position, length: placement.duration, successor: -1)))
    }
}
