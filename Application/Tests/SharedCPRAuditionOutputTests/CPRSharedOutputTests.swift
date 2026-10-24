import Foundation
import Testing
#if canImport(RebaseCore)
@testable import RebaseCore
#else
@testable import RebasePortable
#endif

/// Authored boundary controls for the platform-neutral output extraction.
/// Converter/kernel reference oracles and native device tests remain separate.
@Suite(.serialized)
struct CPRSharedOutputTests {
    @Test func PlanarCallbackUsesLogicalFramesAndPreservesItsSentinelRules() throws {
        var subnormal = try StereoPCMBlock(left: [0, Float(bitPattern: 1)], right: [0, 0])
        try CPRLiveCallbackAdapter.process(&subnormal)
        #expect(subnormal.left.map(\.bitPattern) == [0x2edbe6ff, 0xaedbe6ff])
        #expect(subnormal.right.map(\.bitPattern) == [0x2edbe6ff, 0xaedbe6ff])
        var invalid = try StereoPCMBlock(left: [1, .infinity], right: [-1, -0.0])
        try CPRLiveCallbackAdapter.process(&invalid)
        #expect(invalid.interleaved.map(\.bitPattern) == [0, 0, 0, 0])
        let left = [Float(bitPattern: 0x80000000), Float(1)]
        let right = [Float(bitPattern: 0x7fc31415), Float(bitPattern: 1)]
        var normal = try StereoPCMBlock(left: left, right: right)
        try CPRLiveCallbackAdapter.process(&normal)
        #expect(normal.left.map(\.bitPattern) == left.map(\.bitPattern))
        #expect(normal.right.map(\.bitPattern) == right.map(\.bitPattern))
        var empty = try StereoPCMBlock(frameCount: 0)
        #expect(throws: RebaseCoreError.self) { try CPRLiveCallbackAdapter.process(&empty) }
        #expect(throws: RebaseCoreError.self) { try StereoPCMBlock(left: [0], right: []) }
    }

    @Test func ConditionalCallbackRestartsAtTheFirstFrameOfEachDeliveredSuffix() throws {
        let raw = [Float(0), 0, Float(bitPattern: 1)]
        var whole = try StereoPCMBlock(left: raw, right: [0, 0, 0])
        var suffix = try StereoPCMBlock(left: Array(raw.dropFirst()), right: [0, 0])
        try CPRLiveCallbackAdapter.process(&whole)
        try CPRLiveCallbackAdapter.process(&suffix)
        #expect(whole.left.map(\.bitPattern) == [0x2edbe6ff, 0xaedbe6ff, 0x2edbe6ff])
        #expect(suffix.left.map(\.bitPattern) == [0x2edbe6ff, 0xaedbe6ff])
        #expect(suffix.left.map(\.bitPattern) != whole.left.dropFirst().map(\.bitPattern))
        // This authored output-stage case does not widen the converter's
        // existing event-gain admission, which rejects such output samples.
        let converted = try CPRRateConvertedStream(source: Array(repeating: Float.leastNormalMagnitude, count: 16),
            sourceRate: 8000, outputRate: 16000, gain: 0.5)
        #expect(throws: RebaseCoreError.self) { try converted.cursor(from: 0).nextPlaybackBlock() }
    }

    @Test func SharedPositionRetainsNativeSelectionBeforeFrameRounding() throws {
        let selection = CPRTimelineSelection.Segment(start: 0, length: 0.5, successor: -1)
        #expect(try CPRSourceAudition.startFrame(sampleRate: 8192, frameCount: 8192,
            nativeEventSelection: selection, at: 0.5) == 4096)
        #expect(try CPRSourceAudition.startFrame(sampleRate: 8192, frameCount: 8192,
            nativeEventSelection: selection, at: 0.5.nextUp) == 8192)
        for (time, expected): (Double, Int64) in [(0,0),(0.5/8192,1),(1.5/8192,2),(1,8192),(Double.greatestFiniteMagnitude,8192)] {
            #expect(try CPRSourceAudition.startFrame(sampleRate: 8192, frameCount: 8192,
                nativeEventSelection: nil, at: time) == expected)
        }
        for bad in [-1.0, Double.nan, Double.infinity] {
            #expect(throws: RebaseCoreError.self) { try CPRSourceAudition.startFrame(sampleRate: 8192,
                frameCount: 8192, nativeEventSelection: nil, at: bad) }
        }
    }

    @Test func SharedTimelineKeepsGapsOffsetsTouchingSegmentsAndSeekPartitions() throws {
        let samples = (1...8).flatMap { [Float($0) / 32, -Float($0) / 32] }
        let rate = 8192.0
        let stream = try CPRNativeTimelineStream(sampleRate: rate, segments: [
            .init(start: 3 / rate, length: 5 / rate, offset: 2 / rate,
                  samples: samples, gain: 0.5, sourceRate: 16000),
            .init(start: 8 / rate, length: 3 / rate, offset: 1 / rate,
                  samples: samples, gain: 1, sourceRate: 16000)
        ])
        let expected = [Float](repeating: 0, count: 6)
            + Array(samples[4..<14]).map { $0 * 0.5 } + Array(samples[2..<8])
        #expect(stream.frameCount == 11 && stream.sampleRate == rate)
        for size in [1, 2, 4, 65536] {
            for start: Int64 in [0, 1, 3, 7, 8, 10, 11] {
                let cursor = try stream.cursor(from: start)
                var result = [Float]()
                while let block = try cursor.nextPlaybackBlock(maximumFrames: size) {
                    #expect(block.frameCount > 0 && block.frameCount <= size)
                    result += block.interleaved
                }
                #expect(result.map(\.bitPattern) == expected.dropFirst(Int(start) * 2).map(\.bitPattern))
                #expect(cursor.isAtEnd && cursor.deliveredFrames == 11)
            }
        }
        let cursor = try stream.cursor(from: 3)
        #expect(throws: RebaseCoreError.self) { try cursor.nextPlaybackBlock(maximumFrames: 0) }
        #expect(cursor.deliveredFrames == 3)
    }

    @Test func SharedConvertedOutputKeepsNativePartitionsAndRingTransferAcrossModes() throws {
        let input: [Float] = (0..<16385 * 2).map { Float(($0 * 7919 % 65536) - 32768) / 32768 }
        let cases: [(Double, Double, CPRRateConvertedStream.Algorithm)] = [
            (44100,48000,.nativeMode0), (48000,44100,.nativeMode0),
            (44100,48000,.nativeMode1), (48000,44100,.nativeMode1), (44100,44100,.nativeMode1),
            (44100,48000,.nativeMode2), (48000,44100,.nativeMode2), (44100,44100,.nativeMode2),
            (8000,192000,.nativeMode0)
        ]
        for (sourceRate, outputRate, algorithm) in cases {
            let stream = try CPRRateConvertedStream(source: input, sourceRate: sourceRate,
                outputRate: outputRate, gain: 0.5, algorithm: algorithm)
            for start in [Int64(0), 1, stream.frameCount - 1, stream.frameCount] {
                let raw = try stream.cursor(from: start), playback = try stream.cursor(from: start)
                var largest = 0
                while let samples = try raw.nextInterleaved() {
                    let block = try #require(try playback.nextPlaybackBlock())
                    #expect(block.frameCount * 2 == samples.count)
                    // These authored samples keep the sentinel normal or zero;
                    // separate controls above assert the non-identity branches.
                    let sentinel = samples[samples.count - 2]
                    try #require(sentinel.isNormal || sentinel == 0)
                    #expect(block.interleaved.map(\.bitPattern) == samples.map(\.bitPattern))
                    #expect(raw.deliveredFrames == playback.deliveredFrames)
                    largest = max(largest, block.frameCount)
                }
                #expect(try playback.nextPlaybackBlock() == nil)
                #expect(playback.isAtEnd && playback.deliveredFrames == stream.frameCount)
                if sourceRate == 8000 && start == 0 { #expect(largest > 32768) }
            }
        }
    }
}
