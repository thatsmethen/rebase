import Foundation

/// Source-domain peaks shared by the native timelines. Gain, pan, project rate
/// and clip placement do not change this display envelope.
public struct WaveformEnvelope: Equatable {
    public let sampleRate: Double
    public let sourceStartFrame: Int64
    public let sourceFrames: Int64
    public let peaks: [Float]
}

public enum WaveformPeaks {
    public static let maximumBins = 1600

    public static func read(source: any PCMSourceReader, offset: Double,
                            duration: Double) throws -> WaveformEnvelope {
        let rate = source.sampleRate
        let startValue = offset * rate, durationValue = duration * rate
        guard rate.isFinite, rate > 0, (1...2).contains(source.channelCount),
              startValue.isFinite, durationValue.isFinite, startValue >= 0,
              startValue < Double(source.frameCount), startValue < Double(Int64.max),
              durationValue > 0 else {
            throw RebaseCoreError.unsupportedAudio("The waveform source range is invalid.")
        }
        let start = Int64(startValue)
        let boundedCount = min(Double(source.frameCount - start), durationValue)
        guard boundedCount >= 1, boundedCount <= Double(PCMRenderer.maximumClipFrames) else {
            throw RebaseCoreError.unsupportedAudio("The waveform source range exceeds the supported size.")
        }
        let count = Int64(boundedCount), bins = min(maximumBins, Int(count))
        var peaks = [Float](repeating: 0, count: bins)
        var position: Int64 = 0
        while position < count {
            let requested = Int(min(16_384, count - position))
            let buffer = try source.read(from: start + position, count: requested)
            guard buffer.frameCount == requested, buffer.sampleRate == rate,
                  buffer.channels.count == source.channelCount else {
                throw RebaseCoreError.unsupportedAudio("The waveform source changed or ended during decoding.")
            }
            for frame in 0..<requested {
                let bin = Int((position + Int64(frame)) * Int64(bins) / count)
                for channel in buffer.channels {
                    let value = abs(channel[frame])
                    guard value.isFinite else {
                        throw RebaseCoreError.nonFiniteAudio("The waveform source contains nonfinite samples.")
                    }
                    peaks[bin] = max(peaks[bin], value)
                }
            }
            position += Int64(requested)
        }
        return WaveformEnvelope(sampleRate: rate, sourceStartFrame: start,
            sourceFrames: count, peaks: peaks)
    }
}
