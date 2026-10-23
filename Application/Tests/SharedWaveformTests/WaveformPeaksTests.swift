import Foundation
import Testing
#if canImport(RebaseCore)
@testable import RebaseCore
#else
@testable import RebasePortable
#endif

struct WaveformPeaksTests {
    private struct Source: PCMSourceReader {
        let channels: [[Float]]
        var sampleRate: Double = 48_000
        var shortRead = false
        var wrongRate = false
        var channelCount: Int { channels.count }
        var frameCount: Int64 { Int64(channels[0].count) }
        func read(from start: Int64, count: Int) throws -> PCMBuffer {
            let end = Int(start) + count - (shortRead ? 1 : 0)
            return try PCMBuffer(sampleRate: wrongRate ? sampleRate + 1 : sampleRate,
                channels: channels.map { Array($0[Int(start)..<end]) })
        }
    }

    @Test func binBoundariesAndChunkEdgesMatchIndependentFrameOracle() throws {
        let count = 33_017
        var left = [Float](repeating: 0, count: count), right = left
        for frame in [0, 19, 20, 21, 16_383, 16_384, 16_385, count - 1] {
            left[frame] = -Float(frame % 13 + 1) / 16
            right[frame] = Float(frame % 17 + 1) / 32
        }
        let actual = try WaveformPeaks.read(source: Source(channels: [left, right]),
            offset: 0, duration: Double(count) / 48_000 + 0.000001)
        var expected = [Float](repeating: 0, count: 1600)
        for bin in 0..<1600 {
            // Invert floor(frame*bins/count) with integer ceiling bounds.
            let first = (bin * count + 1599) / 1600
            let end = ((bin + 1) * count + 1599) / 1600
            expected[bin] = (first..<end).map { max(abs(left[$0]), abs(right[$0])) }.max() ?? 0
        }
        #expect(actual.peaks == expected)
        #expect(actual.sourceFrames == Int64(count))
        #expect(actual.sourceStartFrame == 0)
    }

    @Test func offsetsAndDurationTruncateAtSourceRateAndClampToEOF() throws {
        let source = Source(channels: [[0, -0.1, 0.2, -0.3, 0.4, -0.5]], sampleRate: 44_100)
        let middle = try WaveformPeaks.read(source: source, offset: 1.75 / 44_100, duration: 3.75 / 44_100)
        #expect(middle.sourceStartFrame == 1 && middle.sourceFrames == 3)
        #expect(middle.sampleRate == 44_100)
        #expect(middle.peaks == [0.1, 0.2, 0.3])
        let tail = try WaveformPeaks.read(source: source, offset: 4.25 / 44_100, duration: 10)
        #expect(tail.sourceStartFrame == 4 && tail.sourceFrames == 2)
        #expect(tail.peaks == [0.4, 0.5])
    }

    @Test func shortWrongFormatAndNonfiniteReadsFailWithoutPartialEnvelope() throws {
        let values: [[Float]] = [[0, 0.5, -0.5, 0]]
        #expect(throws: RebaseCoreError.self) {
            try WaveformPeaks.read(source: Source(channels: values, shortRead: true), offset: 0, duration: 1)
        }
        #expect(throws: RebaseCoreError.self) {
            try WaveformPeaks.read(source: Source(channels: values, wrongRate: true), offset: 0, duration: 1)
        }
        #expect(throws: RebaseCoreError.self) {
            try WaveformPeaks.read(source: Source(channels: [[0, .nan]]), offset: 0, duration: 1)
        }
    }

    @Test func invalidOrEmptyRangesAreRejected() throws {
        let source = Source(channels: [[0, 1]])
        for offset in [-1.0, .nan, .infinity, 2.0 / 48_000] {
            #expect(throws: RebaseCoreError.self) { try WaveformPeaks.read(source: source, offset: offset, duration: 1) }
        }
        for duration in [0.0, -1, .nan, .infinity, 0.5 / 48_000] {
            #expect(throws: RebaseCoreError.self) { try WaveformPeaks.read(source: source, offset: 0, duration: duration) }
        }
    }
}
