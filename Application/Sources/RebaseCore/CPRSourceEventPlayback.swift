import Foundation
import AVFoundation

public enum CPRSourceEventPlaybackMode: String, CaseIterable, Equatable, Sendable {
    case sourceRate
    case nativeMode0ProjectRate
    case nativeMode2ProjectRate

    public var displayName: String {
        switch self {
        case .sourceRate: return "Stereo audition"
        case .nativeMode0ProjectRate: return "Native mode 0"
        case .nativeMode2ProjectRate: return "SoXR mode 2"
        }
    }
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
    public var duration: Double { Double(frameCount) / sampleRate }
}

/// Event-only audition, independent of project mixer/routing and device output.
/// The source operation is reconstructed; AVAudioEngine transport is an
/// application implementation and does not establish Reference device behavior.
enum CPRSourceEventPlayback {
    static func prepare(eventID: UUID, project: Project, root: URL,
                        mode: CPRSourceEventPlaybackMode = .sourceRate) throws
        -> (info: CPRSourceEventPlaybackInfo, audio: PreparedProject) {
        let source = try CPRSourceEventRenderer.prepare(eventID: eventID, in: project, at: root,
            applyEventGain: mode == .sourceRate)
        let plan = source.plan
        guard plan.channels == 2 else {
            throw RebaseCoreError.unsupportedAudio("Timeline audition currently requires a stereo source; native mono output routing is unresolved.")
        }
        guard let event = project.unresolvedAudioEvents.first(where: { $0.id == eventID }), let placement = event.placement else {
            throw RebaseCoreError.invalidProject("The selected source event is no longer in this project.")
        }
        if mode != .sourceRate {
            let stream = try CPRRateConvertedStream(source: source.samples,
                sourceRate: Double(plan.rate), outputRate: project.sampleRate, gain: plan.gain,
                algorithm: mode == .nativeMode2ProjectRate ? .nativeMode2 : .nativeMode0)
            let info = CPRSourceEventPlaybackInfo(eventID: eventID, name: event.name,
                sampleRate: project.sampleRate, sourceSampleRate: Double(plan.rate), mode: mode,
                frameCount: stream.frameCount, sourceSHA256: source.sourceSHA256,
                mediaSHA256: source.mediaSHA256)
            return (info, PreparedProject(format: stream.format, frameCount: stream.frameCount,
                clips: [], nativeEventSelection: CPRTimelineSelection.Segment(
                    start: placement.position, length: placement.duration, successor: -1),
                sourceEventStream: stream))
        }
        // The source plan admits only a complete, zero-origin segment. Do not
        // pass this audio through Rebase's clip resampler, pan or automation.
        let format = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: Double(plan.rate),
                                   channels: 2, interleaved: false)!
        let buffer = try AudioPreparation.buffer(format: format, frames: plan.frames)
        let channels = buffer.floatChannelData!
        for frame in 0..<plan.frames {
            channels[0][frame] = source.samples[frame * 2]
            channels[1][frame] = source.samples[frame * 2 + 1]
        }
        let info = CPRSourceEventPlaybackInfo(eventID: eventID, name: event.name,
            sampleRate: Double(plan.rate), sourceSampleRate: Double(plan.rate), mode: mode,
            frameCount: Int64(plan.frames),
            sourceSHA256: source.sourceSHA256, mediaSHA256: source.mediaSHA256)
        return (info, PreparedProject(format: format, frameCount: Int64(plan.frames),
                                     clips: [PreparedClip(startFrame: 0, buffer: buffer)],
                                     nativeEventSelection: CPRTimelineSelection.Segment(
                                        start: placement.position, length: placement.duration, successor: -1)))
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
