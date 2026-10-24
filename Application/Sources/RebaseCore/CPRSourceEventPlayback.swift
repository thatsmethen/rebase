import Foundation
import AVFoundation

/// macOS device-buffer adaptation only. Admission, conversion, timeline reads
/// and playback output-stage operations are owned by CPRSourceAudition.
enum CPRSourceEventPlayback {
    static func prepare(eventID: UUID, project: Project, root: URL,
                        mode: CPRSourceEventPlaybackMode = .sourceRate) throws
        -> (info: CPRSourceEventPlaybackInfo, audio: PreparedProject) {
        let prepared = try CPRSourceAudition.prepare(eventID: eventID, in: project, at: root, mode: mode)
        let format = StereoPCMBlock.audioFormat(sampleRate: prepared.sampleRate)
        let audio: PreparedProject
        switch prepared.output {
        case .timeline(let stream):
            audio = PreparedProject(format: format, frameCount: prepared.frameCount,
                clips: [], nativeTimelineStream: stream)
        case .converted(let stream, let selection):
            audio = PreparedProject(format: format, frameCount: prepared.frameCount,
                clips: [], nativeEventSelection: selection, sourceEventStream: stream)
        case .source(_, let selection):
            let buffer = try AudioPreparation.buffer(format: format, frames: Int(prepared.frameCount))
            let cursor = try prepared.cursor(from: 0)
            var offset = 0
            while let block = try cursor.nextPlaybackBlock() {
                block.copy(to: buffer, at: offset)
                offset += block.frameCount
            }
            guard Int64(offset) == prepared.frameCount else {
                throw RebaseCoreError.invalidProject("The source audition ended at an unexpected frame.")
            }
            audio = PreparedProject(format: format, frameCount: prepared.frameCount,
                clips: [PreparedClip(startFrame: 0, buffer: buffer)], nativeEventSelection: selection)
        }
        return (prepared.info, audio)
    }
}

extension StereoPCMBlock {
    static func audioFormat(sampleRate: Double) -> AVAudioFormat {
        AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: sampleRate,
                      channels: 2, interleaved: false)!
    }
    func audioBuffer(sampleRate: Double) throws -> AVAudioPCMBuffer {
        let buffer = try AudioPreparation.buffer(format: Self.audioFormat(sampleRate: sampleRate), frames: frameCount)
        copy(to: buffer, at: 0)
        return buffer
    }
    fileprivate func copy(to buffer: AVAudioPCMBuffer, at offset: Int) {
        for (channel, samples) in [left, right].enumerated() {
            samples.withUnsafeBufferPointer { source in
                if let base = source.baseAddress {
                    buffer.floatChannelData![channel].advanced(by: offset).update(from: base, count: source.count)
                }
            }
        }
    }
}

// Preserve the existing macOS test/client entry point; all track preparation
// is still performed once by the portable stream builder.
extension CPRSourceTrackPlayback {
    static func prepare(eventID: UUID, project: Project, root: URL) throws
        -> (track: CPRSourceTrackPlaybackInfo, setup: CPRProjectAudioSetup,
            name: String, sourceSHA256: String, audio: PreparedProject) {
        let prepared = try prepareStream(eventID: eventID, project: project, root: root)
        return (prepared.track, prepared.setup, prepared.name, prepared.sourceSHA256,
            PreparedProject(format: prepared.stream.format, frameCount: prepared.stream.frameCount,
                clips: [], nativeTimelineStream: prepared.stream))
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
        let frame = try CPRSourceAudition.startFrame(sampleRate: prepared.format.sampleRate,
            frameCount: prepared.frameCount, nativeEventSelection: prepared.nativeEventSelection, at: seconds)
        if frame == prepared.frameCount { return AudioPlaybackSchedule(startFrame: frame, spans: []) }
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
