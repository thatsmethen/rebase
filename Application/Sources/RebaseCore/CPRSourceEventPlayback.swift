import Foundation
import AVFoundation

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

/// Explicit source audition, independent of project mixer/routing and device output.
/// The source operation is reconstructed; AVAudioEngine transport is an
/// application implementation and does not establish Reference device behavior.
enum CPRSourceEventPlayback {
    static func prepare(eventID: UUID, project: Project, root: URL,
                        mode: CPRSourceEventPlaybackMode = .sourceRate) throws
        -> (info: CPRSourceEventPlaybackInfo, audio: PreparedProject) {
        if mode == .nativeTrackSavedProjectClock {
            let prepared = try CPRSourceTrackPlayback.prepare(eventID: eventID, project: project, root: root)
            guard let anchor = prepared.track.events.first(where: { $0.eventID == eventID }) else {
                throw RebaseCoreError.invalidProject("The track source no longer contains its selected event.")
            }
            var info = CPRSourceEventPlaybackInfo(eventID: eventID, name: prepared.name,
                sampleRate: prepared.audio.format.sampleRate, sourceSampleRate: anchor.sourceSampleRate,
                mode: mode, frameCount: prepared.audio.frameCount, sourceSHA256: prepared.sourceSHA256,
                mediaSHA256: anchor.mediaSHA256)
            info.savedProjectAudioSetup = prepared.setup
            info.timelineRange = anchor.range
            info.sourceTrack = prepared.track
            return (info, prepared.audio)
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
            return (info, PreparedProject(format: stream.format, frameCount: stream.frameCount,
                clips: [], nativeTimelineStream: stream))
        }
        if mode == .sourceRate {
            let source = try CPRSourceEventRenderer.prepareAudition(eventID: eventID, in: project, at: root)
            guard let event = project.unresolvedAudioEvents.first(where: { $0.id == eventID }),
                  let placement = event.placement else {
                throw RebaseCoreError.invalidProject("The selected source event is no longer in this project.")
            }
            let format = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: source.sampleRate,
                                       channels: 2, interleaved: false)!
            let buffer = try AudioPreparation.buffer(format: format, frames: source.frameCount)
            let channels = buffer.floatChannelData!
            for frame in 0..<source.frameCount {
                channels[0][frame] = source.samples[frame * 2]
                channels[1][frame] = source.samples[frame * 2 + 1]
            }
            let info = CPRSourceEventPlaybackInfo(eventID: eventID, name: event.name,
                sampleRate: source.sampleRate, sourceSampleRate: source.sampleRate, mode: mode,
                frameCount: Int64(source.frameCount), sourceSHA256: source.sourceSHA256, mediaSHA256: source.mediaSHA256)
            return (info, PreparedProject(format: format, frameCount: Int64(source.frameCount),
                clips: [PreparedClip(startFrame: 0, buffer: buffer)],
                nativeEventSelection: CPRTimelineSelection.Segment(
                    start: placement.position, length: placement.duration, successor: -1)))
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
        return (info, PreparedProject(format: stream.format, frameCount: stream.frameCount,
            clips: [], nativeEventSelection: CPRTimelineSelection.Segment(
                start: placement.position, length: placement.duration, successor: -1),
            sourceEventStream: stream))
    }
}

/// Application host scheduling policy, shared by project and event transport.
/// Time is clamped before conversion; ties round away from zero. Intervals are
/// half-open in output frames. This is not an inferred Reference live scheduler.
struct AudioPlaybackSchedule {
    struct Span: Equatable {
        let clipIndex: Int
        let sourceOffset: Int
        let frameCount: Int
        let delayFrames: Int64
    }
    let startFrame: Int64
    let spans: [Span]

    static func make(_ prepared: PreparedProject, from seconds: Double) throws -> AudioPlaybackSchedule {
        guard seconds.isFinite, seconds >= 0, prepared.format.sampleRate.isFinite,
              prepared.format.sampleRate > 0, prepared.frameCount >= 0 else {
            throw RebaseCoreError.invalidProject("Playback position must be a finite nonnegative time.")
        }
        let duration = Double(prepared.frameCount) / prepared.format.sampleRate
        if let segment = prepared.nativeEventSelection {
            // Every seek starts with a reset cursor. Selection is a separate
            // recovered operation; frame quantization below is application policy.
            // Clamp to the source end before native-domain validation, allowing
            // arbitrarily large finite UI seeks without arithmetic overflow.
            var cursor = CPRTimelineSelection.Cursor(generation: 0)
            let selected = try CPRTimelineSelection.select([segment], at: min(seconds, duration), generation: 0, cursor: &cursor)
            if selected == nil { return AudioPlaybackSchedule(startFrame: prepared.frameCount, spans: []) }
        }
        if seconds >= duration { return AudioPlaybackSchedule(startFrame: prepared.frameCount, spans: []) }
        guard let converted = Int64(exactly: (seconds * prepared.format.sampleRate).rounded()) else {
            throw RebaseCoreError.invalidProject("Playback position cannot be represented as an audio frame.")
        }
        let frame = min(prepared.frameCount, converted)
        var spans: [Span] = []
        for (index, clip) in prepared.clips.enumerated() {
            let end = clip.startFrame + Int64(clip.buffer.frameLength)
            guard end > frame else { continue }
            let skip = max(0, frame - clip.startFrame)
            spans.append(Span(clipIndex: index, sourceOffset: Int(skip),
                frameCount: Int(clip.buffer.frameLength) - Int(skip), delayFrames: max(0, clip.startFrame - frame)))
        }
        return AudioPlaybackSchedule(startFrame: frame, spans: spans)
    }

    static func buffer(for span: Span, in prepared: PreparedProject) throws -> AVAudioPCMBuffer {
        let source = prepared.clips[span.clipIndex].buffer
        if span.sourceOffset == 0 { return source }
        let output = try AudioPreparation.buffer(format: prepared.format, frames: span.frameCount)
        for channel in 0..<Int(prepared.format.channelCount) {
            output.floatChannelData![channel].update(
                from: source.floatChannelData![channel].advanced(by: span.sourceOffset), count: span.frameCount)
        }
        return output
    }
}
