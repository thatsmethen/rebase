import AVFoundation
import Testing
@testable import RebaseCore

/// Adapter checks: shared output bits and partition capacity reach AV buffers
/// unchanged. This is not a separate converter or device behavior oracle.
@Suite(.serialized)
struct CPRSharedOutputMacAdapterTests {
    private func check(_ block: StereoPCMBlock, _ buffer: AVAudioPCMBuffer, rate: Double) {
        #expect(buffer.format.sampleRate == rate && buffer.format.channelCount == 2)
        #expect(!buffer.format.isInterleaved)
        #expect(Int(buffer.frameLength) == block.frameCount && buffer.frameCapacity == buffer.frameLength)
        for (channel, samples) in [block.left, block.right].enumerated() {
            #expect(Array(UnsafeBufferPointer(start: buffer.floatChannelData![channel], count: samples.count))
                .map(\.bitPattern) == samples.map(\.bitPattern))
        }
    }

    @Test func MacConditionalCallbackUsesTheSameFreshSuffixPartition() throws {
        // Direct output-stage input, deliberately outside converter admission.
        // Never relabel it as a converter or reference-runtime observation.
        let raw = [Float(0), 0, Float(bitPattern: 1)]
        var shared = try StereoPCMBlock(left: Array(raw.dropFirst()), right: [0, 0])
        let mac = try shared.audioBuffer(sampleRate: 48000)
        try CPRLiveCallbackAdapter.process(&shared)
        try CPRLiveCallbackAdapter.process(mac)
        check(shared, mac, rate: 48000)
        #expect(shared.left.map(\.bitPattern) == [0x2edbe6ff, 0xaedbe6ff])
    }

    @Test func MacConvertedBuffersAreExactSharedOutputBlocksIncludingSeekSuffixes() throws {
        let input: [Float] = (0..<8193 * 2).map { Float(($0 * 7919 % 65536) - 32768) / 32768 }
        for algorithm: CPRRateConvertedStream.Algorithm in [.nativeMode0, .nativeMode1, .nativeMode2] {
            for rate in [32000.0, 48000.0] {
                let stream = try CPRRateConvertedStream(source: input, sourceRate: 44100,
                    outputRate: rate, gain: 0.5, algorithm: algorithm)
                for start in [Int64(0), 1, stream.frameCount - 1, stream.frameCount] {
                    let shared = try stream.cursor(from: start), mac = try stream.cursor(from: start)
                    while let block = try shared.nextPlaybackBlock() {
                        check(block, try #require(try mac.nextBuffer()), rate: rate)
                    }
                    #expect(try mac.nextBuffer() == nil)
                    #expect(mac.deliveredFrames == shared.deliveredFrames)
                }
            }
        }
    }

    @Test func MacTimelineBuffersPreserveSharedSilenceAndGainedSource() throws {
        let rate = 8192.0
        let stream = try CPRNativeTimelineStream(sampleRate: rate, segments: [
            .init(start: 3 / rate, length: 4 / rate, offset: 1 / rate,
                  samples: [0.25,-0.25,0.5,-0.5,0.75,-0.75,1,-1,0.125,-0.125],
                  gain: 0.5, sourceRate: 8192)
        ])
        for maximum in [1, 3, 4096] {
            let shared = try stream.cursor(from: 0), mac = try stream.cursor(from: 0)
            while let block = try shared.nextPlaybackBlock(maximumFrames: maximum) {
                check(block, try #require(try mac.nextBuffer(maximumFrames: maximum)), rate: rate)
            }
            #expect(try mac.nextBuffer(maximumFrames: maximum) == nil)
        }
    }
}
