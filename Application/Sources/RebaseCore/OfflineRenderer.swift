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
                for frame in 0..<frames {
                    let sum = output[channel][destinationStart + frame] + source[channel][sourceStart + frame]
                    guard sum.isFinite else {
                        throw RebaseCoreError.nonFiniteAudio("The mix exceeds the finite audio range. Reduce track gains before playback or export.")
                    }
                    output[channel][destinationStart + frame] = sum
                }
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
}

enum AudioPreparation {
    static let maximumClipFrames: Int64 = 16_000_000
    static let maximumProjectFrames: Int64 = 32_000_000

    static func buffer(format: AVAudioFormat, frames: Int) throws -> AVAudioPCMBuffer {
        guard frames >= 0, frames <= Int(UInt32.max),
              let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(frames)) else {
            throw RebaseCoreError.mediaTooLarge
        }
        buffer.frameLength = AVAudioFrameCount(frames)
        return buffer
    }

    static func prepare(_ project: Project, root: URL) throws -> PreparedProject {
        try project.validate()
        try project.requireResolvedAudioEvents()
        let format = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: project.sampleRate,
                                   channels: 2, interleaved: false)!
        let hasSolo = project.tracks.contains { $0.isSolo }
        var clips: [PreparedClip] = []
        var totalFrames: Int64 = 0
        var end: Int64 = 0
        for track in project.tracks {
            for clip in track.clips {
                let start = Int64((clip.position * project.sampleRate).rounded())
                let frames = Int64((clip.duration * project.sampleRate).rounded())
                end = max(end, start + frames)
                guard !track.isMuted, !hasSolo || track.isSolo, frames > 0 else { continue }
                guard frames <= maximumClipFrames, totalFrames + frames <= maximumProjectFrames else {
                    throw RebaseCoreError.mediaTooLarge
                }
                let url = try ProjectStore.resolveMediaURL(clip.mediaPath, projectRoot: root)
                let audio = try AVAudioFile(forReading: url, commonFormat: .pcmFormatFloat32, interleaved: false)
                let sourceFormat = audio.processingFormat
                guard (1...2).contains(sourceFormat.channelCount), sourceFormat.sampleRate > 0 else {
                    throw RebaseCoreError.unsupportedAudio("Only mono and stereo media can be mixed.")
                }
                try AudioSampleValidation.validateInterval(clip, sampleRate: sourceFormat.sampleRate,
                                                            frameCount: audio.length)
                let sourceStart = clip.sourceOffset * sourceFormat.sampleRate
                let first = Int64(floor(sourceStart))
                let fraction = sourceStart - Double(first)
                let ratio = sourceFormat.sampleRate / project.sampleRate
                let needed = Int64(floor(fraction + Double(frames - 1) * ratio)) + 2
                let readCount = min(needed, audio.length - first)
                guard readCount > 0, readCount <= maximumClipFrames else { throw RebaseCoreError.mediaTooLarge }
                let source = try buffer(format: sourceFormat, frames: Int(readCount))
                audio.framePosition = first
                try audio.read(into: source, frameCount: AVAudioFrameCount(readCount))
                guard source.frameLength == AVAudioFrameCount(readCount) else {
                    throw RebaseCoreError.unsupportedAudio("The source ended while decoding “\(clip.name)”.")
                }
                try AudioSampleValidation.check(source, name: clip.name)
                let output = try buffer(format: format, frames: Int(frames))
                let gainLane = track.automation.first { $0.parameter == .gainDB }
                let panLane = track.automation.first { $0.parameter == .pan }
                let mono = sourceFormat.channelCount == 1
                let samples = source.floatChannelData!
                let destination = output.floatChannelData!
                for frame in 0..<Int(frames) {
                    let time = Double(start + Int64(frame)) / project.sampleRate
                    let gain = gainLane?.value(at: time, fallback: track.gainDB) ?? track.gainDB
                    let pan = panLane?.value(at: time, fallback: track.pan) ?? track.pan
                    let amplitude = pow(10, gain / 20)
                    let left = amplitude * (mono ? sqrt((1 - pan) / 2) : sqrt(min(1, 1 - pan)))
                    let right = amplitude * (mono ? sqrt((1 + pan) / 2) : sqrt(min(1, 1 + pan)))
                    let location = min(fraction + Double(frame) * ratio, Double(readCount - 1))
                    let lower = Int(floor(location))
                    let upper = min(lower + 1, Int(readCount - 1))
                    let blend = location - Double(lower)
                    for channel in 0..<2 {
                        let input = samples[mono ? 0 : channel]
                        let value = Double(input[lower]) + (Double(input[upper]) - Double(input[lower])) * blend
                        let gained = Float(value * (channel == 0 ? left : right))
                        guard gained.isFinite else {
                            throw RebaseCoreError.nonFiniteAudio("Gain processing overflows the audio range in “\(clip.name)”. Reduce the track gain.")
                        }
                        destination[channel][frame] = gained
                    }
                }
                clips.append(PreparedClip(startFrame: start, buffer: output))
                totalFrames += frames
            }
        }
        // Both transport and offline export consume this preparation. Check
        // overlapping ranges before any player node reaches the hardware mixer.
        try validateAccumulation(clips, format: format)
        return PreparedProject(format: format, frameCount: end, clips: clips)
    }

    private static func validateAccumulation(_ clips: [PreparedClip], format: AVAudioFormat) throws {
        guard clips.count > 1 else { return }
        var events: [Int64: Int] = [:]
        for clip in clips {
            events[clip.startFrame, default: 0] += 1
            events[clip.startFrame + Int64(clip.buffer.frameLength), default: 0] -= 1
        }
        let positions = events.keys.sorted()
        let chunk = try buffer(format: format, frames: 8192)
        var active = 0
        for index in 0..<(positions.count - 1) {
            var position = positions[index]
            active += events[position]!
            guard active > 1 else { continue }
            let end = positions[index + 1]
            while position < end {
                chunk.frameLength = AVAudioFrameCount(min(8192, end - position))
                try OfflineRenderer.mix(clips, into: chunk, from: position)
                position += Int64(chunk.frameLength)
            }
        }
    }
}

enum AudioSampleValidation {
    static func validateInterval(_ clip: Clip, sampleRate: Double, frameCount: AVAudioFramePosition) throws {
        let start = clip.sourceOffset * sampleRate
        let end = (clip.sourceOffset + clip.duration) * sampleRate
        guard sampleRate.isFinite, sampleRate > 0, start.isFinite, end.isFinite,
              start >= 0, start < Double(Int64.max) else {
            throw RebaseCoreError.invalidProject("The source position of “\(clip.name)” cannot be represented as an audio frame.")
        }
        guard frameCount > 0, start < Double(frameCount), end <= Double(frameCount) + 0.5 else {
            throw RebaseCoreError.invalidProject("The clip “\(clip.name)” extends beyond its source audio.")
        }
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
