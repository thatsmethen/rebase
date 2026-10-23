import Foundation
import AVFoundation

/// Explicit application mixing policy, independent of the Reference research.
/// Mono uses equal-power pan; stereo uses balance with unity at the center.
/// Sample-rate conversion uses deterministic linear interpolation.
public enum OfflineRenderer {
    public static func render(project: Project, projectRoot: URL) throws -> AVAudioPCMBuffer {
        let prepared = try AudioPreparation.prepare(project, root: projectRoot)
        guard prepared.frameCount > 0 else { throw RebaseCoreError.noAudio }
        guard prepared.frameCount <= AudioPreparation.maximumClipFrames else { throw RebaseCoreError.mediaTooLarge }
        let buffer = try AudioPreparation.buffer(format: prepared.format, frames: Int(prepared.frameCount))
        try mix(prepared.clips, into: buffer, from: 0)
        return buffer
    }

    @discardableResult
    public static func export(project: Project, projectRoot: URL, to destination: URL) throws -> URL {
        guard ["wav", "wave"].contains(destination.pathExtension.lowercased()) else {
            throw RebaseCoreError.unsupportedAudio("Choose a .wav destination for the stereo float export.")
        }
        let target = destination.standardizedFileURL.resolvingSymlinksInPath()
        let media = projectRoot.standardizedFileURL.resolvingSymlinksInPath().appendingPathComponent("Media")
        guard !target.path.hasPrefix(media.path + "/") else {
            throw RebaseCoreError.invalidProject("Export outside the project's Media folder to preserve imported assets.")
        }
        let prepared = try AudioPreparation.prepare(project, root: projectRoot)
        guard prepared.frameCount > 0 else { throw RebaseCoreError.noAudio }
        guard prepared.frameCount * 8 < Int64(UInt32.max) - 4096 else {
            throw RebaseCoreError.unsupportedAudio("This mix exceeds the 4 GB WAV size limit.")
        }
        let manager = FileManager.default
        let temporary = target.deletingLastPathComponent().appendingPathComponent(".rebase-\(UUID().uuidString).wav")
        defer { try? manager.removeItem(at: temporary) }
        try write(prepared, to: temporary)
        if manager.fileExists(atPath: target.path) {
            _ = try manager.replaceItemAt(target, withItemAt: temporary)
        } else {
            try manager.moveItem(at: temporary, to: target)
        }
        return destination
    }

    private static func write(_ prepared: PreparedProject, to url: URL) throws {
        let settings: [String: Any] = [AVFormatIDKey: kAudioFormatLinearPCM,
            AVSampleRateKey: prepared.format.sampleRate, AVNumberOfChannelsKey: 2,
            AVLinearPCMBitDepthKey: 32, AVLinearPCMIsFloatKey: true,
            AVLinearPCMIsBigEndianKey: false, AVLinearPCMIsNonInterleaved: false]
        let file = try AVAudioFile(forWriting: url, settings: settings,
                                   commonFormat: .pcmFormatFloat32, interleaved: false)
        let chunk = try AudioPreparation.buffer(format: prepared.format, frames: 8192)
        var position: Int64 = 0
        while position < prepared.frameCount {
            chunk.frameLength = AVAudioFrameCount(min(8192, prepared.frameCount - position))
            try mix(prepared.clips, into: chunk, from: position)
            try file.write(from: chunk)
            position += Int64(chunk.frameLength)
        }
    }

    static func mix(_ clips: [PreparedClip], into buffer: AVAudioPCMBuffer, from start: Int64) throws {
        let count = Int(buffer.frameLength)
        let output = buffer.floatChannelData!
        for channel in 0..<2 { output[channel].update(repeating: 0, count: count) }
        let end = start + Int64(count)
        // Stable project track/clip order defines accumulation order.
        for clip in clips {
            let overlapStart = max(start, clip.startFrame)
            let overlapEnd = min(end, clip.startFrame + Int64(clip.buffer.frameLength))
            guard overlapEnd > overlapStart else { continue }
            let sourceStart = Int(overlapStart - clip.startFrame)
            let destinationStart = Int(overlapStart - start)
            let frames = Int(overlapEnd - overlapStart)
            let source = clip.buffer.floatChannelData!
            for channel in 0..<2 {
                try PCMRenderer.accumulate(
                    source: UnsafeBufferPointer(start: source[channel] + sourceStart, count: frames),
                    destination: UnsafeMutableBufferPointer(start: output[channel] + destinationStart, count: frames))
            }
        }
    }
}

struct PreparedClip {
    let startFrame: Int64
    let buffer: AVAudioPCMBuffer
}

struct PreparedProject {
    let format: AVAudioFormat
    let frameCount: Int64
    let clips: [PreparedClip]
    var nativeEventSelection: CPRTimelineSelection.Segment? = nil
    var sourceEventStream: CPRRateConvertedStream? = nil
    var nativeTimelineStream: CPRNativeTimelineStream? = nil
}

enum AudioPreparation {
    static let maximumClipFrames = PCMRenderer.maximumClipFrames
    static let maximumProjectFrames = PCMRenderer.maximumProjectFrames

    static func buffer(format: AVAudioFormat, frames: Int) throws -> AVAudioPCMBuffer {
        guard frames >= 0, frames <= Int(UInt32.max),
              let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(frames)) else {
            throw RebaseCoreError.mediaTooLarge
        }
        buffer.frameLength = AVAudioFrameCount(frames)
        return buffer
    }

    static func prepare(_ project: Project, root: URL) throws -> PreparedProject {
        let prepared = try PCMRenderer.prepare(project) { clip in
            let url = try ProjectStore.resolveMediaURL(clip.mediaPath, projectRoot: root)
            return try AVPCMSourceReader(url: url)
        }
        let format = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: prepared.sampleRate,
                                   channels: 2, interleaved: false)!
        let clips = try prepared.clips.map { clip in
            let output = try buffer(format: format, frames: clip.buffer.frameCount)
            for channel in 0..<2 {
                clip.buffer.channels[channel].withUnsafeBufferPointer { source in
                    if let base = source.baseAddress {
                        output.floatChannelData![channel].update(from: base, count: source.count)
                    }
                }
            }
            return PreparedClip(startFrame: clip.startFrame, buffer: output)
        }
        return PreparedProject(format: format, frameCount: prepared.frameCount, clips: clips)
    }

}

enum AudioSampleValidation {
    static func validateInterval(_ clip: Clip, sampleRate: Double, frameCount: AVAudioFramePosition) throws {
        try PCMRenderer.validateInterval(clip, sampleRate: sampleRate, frameCount: frameCount)
    }

    static func check(_ buffer: AVAudioPCMBuffer, name: String) throws {
        guard let channels = buffer.floatChannelData else {
            throw RebaseCoreError.unsupportedAudio("Could not decode floating-point samples from “\(name)”.")
        }
        for channel in 0..<Int(buffer.format.channelCount) {
            for frame in 0..<Int(buffer.frameLength) where !channels[channel][frame].isFinite {
                throw RebaseCoreError.nonFiniteAudio("“\(name)” contains NaN or infinite audio samples. Import a file with finite samples.")
            }
        }
    }

    @discardableResult
    static func scan(url: URL, name: String) throws -> (sampleRate: Double, frameCount: AVAudioFramePosition) {
        let file = try AVAudioFile(forReading: url, commonFormat: .pcmFormatFloat32, interleaved: false)
        let buffer = try AudioPreparation.buffer(format: file.processingFormat, frames: 8192)
        while file.framePosition < file.length {
            try file.read(into: buffer, frameCount: AVAudioFrameCount(min(8192, file.length - file.framePosition)))
            guard buffer.frameLength > 0 else {
                throw RebaseCoreError.unsupportedAudio("“\(name)” ended unexpectedly while decoding audio.")
            }
            try check(buffer, name: name)
        }
        return (file.processingFormat.sampleRate, file.length)
    }
}

/// AVFoundation decodes only; shared PCMRenderer owns trim, pan, automation,
/// interpolation, and accumulation policy.
extension WaveformPeaks {
    public static func read(url: URL, offset: Double, duration: Double) throws -> WaveformEnvelope {
        try read(source: AVPCMSourceReader(url: url), offset: offset, duration: duration)
    }
}

private final class AVPCMSourceReader: PCMSourceReader {
    private let audio: AVAudioFile
    var sampleRate: Double { audio.processingFormat.sampleRate }
    var channelCount: Int { Int(audio.processingFormat.channelCount) }
    var frameCount: Int64 { audio.length }
    init(url: URL) throws {
        audio = try AVAudioFile(forReading: url, commonFormat: .pcmFormatFloat32, interleaved: false)
    }
    func read(from start: Int64, count: Int) throws -> PCMBuffer {
        let buffer = try AudioPreparation.buffer(format: audio.processingFormat, frames: count)
        audio.framePosition = start
        try audio.read(into: buffer, frameCount: AVAudioFrameCount(count))
        guard buffer.frameLength == AVAudioFrameCount(count), let planes = buffer.floatChannelData else {
            throw RebaseCoreError.unsupportedAudio("The source ended while decoding audio.")
        }
        let channels = (0..<channelCount).map { Array(UnsafeBufferPointer(start: planes[$0], count: count)) }
        return try PCMBuffer(sampleRate: sampleRate, channels: channels)
    }
}
