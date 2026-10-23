import Foundation

/// Owned planar Float32 audio. Device and file adapters do not define mix semantics.
public struct PCMBuffer {
    public let sampleRate: Double
    public let channels: [[Float]]
    public var frameCount: Int { channels.first?.count ?? 0 }

    public init(sampleRate: Double, channels: [[Float]]) throws {
        guard sampleRate.isFinite, sampleRate > 0, (1...2).contains(channels.count),
              let count = channels.first?.count, count <= Int(PCMRenderer.maximumClipFrames),
              channels.allSatisfy({ $0.count == count }) else {
            throw RebaseCoreError.unsupportedAudio("PCM needs one or two equal-length channels and a finite sample rate.")
        }
        guard channels.allSatisfy({ $0.allSatisfy(\.isFinite) }) else {
            throw RebaseCoreError.nonFiniteAudio("PCM contains NaN or infinite samples.")
        }
        self.sampleRate = sampleRate
        self.channels = channels
    }
}

/// Readers must return exactly the requested finite frames, without changing rate.
/// Source resolution and provenance checks belong to the document/file adapter.
public protocol PCMSourceReader {
    var sampleRate: Double { get }
    var channelCount: Int { get }
    var frameCount: Int64 { get }
    func read(from start: Int64, count: Int) throws -> PCMBuffer
}

public struct PreparedPCMClip {
    public let startFrame: Int64
    public let buffer: PCMBuffer
    public init(startFrame: Int64, buffer: PCMBuffer) throws {
        guard startFrame >= 0, startFrame <= Int64.max - Int64(buffer.frameCount),
              buffer.channels.count == 2 else {
            throw RebaseCoreError.invalidProject("Prepared PCM clips need a representable position and stereo audio.")
        }
        self.startFrame = startFrame; self.buffer = buffer
    }
}

public struct PreparedPCMProject {
    public let sampleRate: Double
    public let frameCount: Int64
    public let clips: [PreparedPCMClip]
}

/// The existing application mix, shared by macOS and Windows. This policy is
/// distinct from the recovered native CPR processing paths.
public enum PCMRenderer {
    public static let maximumClipFrames: Int64 = 16_000_000
    public static let maximumProjectFrames: Int64 = 32_000_000

    public static func validateInterval(_ clip: Clip, sampleRate: Double, frameCount: Int64) throws {
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

    public static func prepare(_ project: Project,
                               openSource: (Clip) throws -> any PCMSourceReader) throws -> PreparedPCMProject {
        try project.validate()
        try project.requireResolvedAudioEvents()
        let hasSolo = project.tracks.contains { $0.isSolo }
        var clips: [PreparedPCMClip] = []
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
                let reader = try openSource(clip)
                guard (1...2).contains(reader.channelCount), reader.sampleRate.isFinite, reader.sampleRate > 0 else {
                    throw RebaseCoreError.unsupportedAudio("Only mono and stereo media can be mixed.")
                }
                try validateInterval(clip, sampleRate: reader.sampleRate, frameCount: reader.frameCount)
                let sourceStart = clip.sourceOffset * reader.sampleRate
                let first = Int64(floor(sourceStart))
                let fraction = sourceStart - Double(first)
                let ratio = reader.sampleRate / project.sampleRate
                let neededValue = floor(fraction + Double(frames - 1) * ratio)
                guard neededValue.isFinite, neededValue >= 0, neededValue < Double(Int64.max - 2) else {
                    throw RebaseCoreError.mediaTooLarge
                }
                let needed = Int64(neededValue) + 2
                let readCount = min(needed, reader.frameCount - first)
                guard readCount > 0, readCount <= maximumClipFrames else { throw RebaseCoreError.mediaTooLarge }
                let source = try reader.read(from: first, count: Int(readCount))
                guard source.frameCount == Int(readCount), source.sampleRate == reader.sampleRate,
                      source.channels.count == reader.channelCount else {
                    throw RebaseCoreError.unsupportedAudio("The source changed format or ended while decoding “\(clip.name)”.")
                }
                let gainLane = track.automation.first { $0.parameter == .gainDB }
                let panLane = track.automation.first { $0.parameter == .pan }
                let mono = reader.channelCount == 1
                var destination = Array(repeating: [Float](repeating: 0, count: Int(frames)), count: 2)
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
                        let input = source.channels[mono ? 0 : channel]
                        let value = Double(input[lower]) + (Double(input[upper]) - Double(input[lower])) * blend
                        let gained = Float(value * (channel == 0 ? left : right))
                        guard gained.isFinite else {
                            throw RebaseCoreError.nonFiniteAudio("Gain processing overflows the audio range in “\(clip.name)”. Reduce the track gain.")
                        }
                        destination[channel][frame] = gained
                    }
                }
                let buffer = try PCMBuffer(sampleRate: project.sampleRate, channels: destination)
                clips.append(try PreparedPCMClip(startFrame: start, buffer: buffer))
                totalFrames += frames
            }
        }
        try validateAccumulation(clips, sampleRate: project.sampleRate)
        return PreparedPCMProject(sampleRate: project.sampleRate, frameCount: end, clips: clips)
    }

    public static func mix(_ clips: [PreparedPCMClip], sampleRate: Double,
                           from start: Int64, count: Int) throws -> PCMBuffer {
        guard start >= 0, count >= 0, count <= maximumClipFrames,
              start <= Int64.max - Int64(count), clips.allSatisfy({ $0.buffer.sampleRate == sampleRate }) else {
            throw RebaseCoreError.invalidProject("The mix range or sample rate is invalid.")
        }
        var output = Array(repeating: [Float](repeating: 0, count: count), count: 2)
        let end = start + Int64(count)
        // Stable project track/clip order defines Float32 accumulation order.
        for clip in clips {
            let overlapStart = max(start, clip.startFrame)
            let overlapEnd = min(end, clip.startFrame + Int64(clip.buffer.frameCount))
            guard overlapEnd > overlapStart else { continue }
            let sourceStart = Int(overlapStart - clip.startFrame)
            let destinationStart = Int(overlapStart - start)
            let frames = Int(overlapEnd - overlapStart)
            for channel in 0..<2 {
                try clip.buffer.channels[channel].withUnsafeBufferPointer { source in
                    try output[channel].withUnsafeMutableBufferPointer { destination in
                        try accumulate(
                            source: UnsafeBufferPointer(rebasing: source[sourceStart..<(sourceStart + frames)]),
                            destination: UnsafeMutableBufferPointer(rebasing: destination[destinationStart..<(destinationStart + frames)]))
                    }
                }
            }
        }
        return try PCMBuffer(sampleRate: sampleRate, channels: output)
    }

    static func accumulate(source: UnsafeBufferPointer<Float>, destination: UnsafeMutableBufferPointer<Float>) throws {
        precondition(source.count == destination.count)
        for frame in source.indices {
            let sum = destination[frame] + source[frame]
            guard sum.isFinite else {
                throw RebaseCoreError.nonFiniteAudio("The mix exceeds the finite audio range. Reduce track gains before playback or export.")
            }
            destination[frame] = sum
        }
    }

    private static func validateAccumulation(_ clips: [PreparedPCMClip], sampleRate: Double) throws {
        guard clips.count > 1 else { return }
        var events: [Int64: Int] = [:]
        for clip in clips {
            events[clip.startFrame, default: 0] += 1
            events[clip.startFrame + Int64(clip.buffer.frameCount), default: 0] -= 1
        }
        let positions = events.keys.sorted()
        var active = 0
        for index in 0..<(positions.count - 1) {
            var position = positions[index]
            active += events[position]!
            guard active > 1 else { continue }
            let end = positions[index + 1]
            while position < end {
                let count = Int(min(8192, end - position))
                _ = try mix(clips, sampleRate: sampleRate, from: position, count: count)
                position += Int64(count)
            }
        }
    }
}
