import AVFoundation
import Testing
@testable import RebaseCore

struct CPRLiveCallbackAdapterTests {
    private func buffer(_ left: [UInt32], _ right: [UInt32]) throws -> AVAudioPCMBuffer {
        let format = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: 48000,
                                   channels: 2, interleaved: false)!
        let output = try AudioPreparation.buffer(format: format, frames: left.count)
        for (channel, words) in [left, right].enumerated() {
            for (index, word) in words.enumerated() {
                output.floatChannelData![channel][index] = Float(bitPattern: word)
            }
        }
        return output
    }

    @Test func AdapterAppliesFirstPlaneSentinelToBothPlanes() throws {
        // The first plane ends subnormal. Native correction is +/-0x2edbe6ff
        // at alternating indexes, independently for each channel.
        let output = try buffer([0, 1], [0, 0])
        try CPRLiveCallbackAdapter.process(output)
        for channel in 0..<2 {
            #expect(output.floatChannelData![channel][0].bitPattern == 0x2edbe6ff)
            #expect(output.floatChannelData![channel][1].bitPattern == 0xaedbe6ff)
        }
        let invalidSentinel = try buffer([0x3f800000, 0x7f800000], [0xbf800000, 0x80000000])
        try CPRLiveCallbackAdapter.process(invalidSentinel)
        for channel in 0..<2 {
            for index in 0..<2 {
                #expect(invalidSentinel.floatChannelData![channel][index].bitPattern == 0)
            }
        }
    }

    @Test func NormalSentinelRetainsOtherPlaneBitsAndSignedZero() throws {
        let left: [UInt32] = [0x80000000, 0x3f800000]
        let right: [UInt32] = [0x7fc31415, 1]
        let output = try buffer(left, right)
        try CPRLiveCallbackAdapter.process(output)
        for (channel, words) in [left, right].enumerated() {
            for (index, word) in words.enumerated() {
                #expect(output.floatChannelData![channel][index].bitPattern == word)
            }
        }
    }

    @Test func EmptyOrNonStereoOutputRejects() throws {
        let output = try buffer([0], [0])
        output.frameLength = 0
        #expect(throws: RebaseCoreError.self) { try CPRLiveCallbackAdapter.process(output) }
        let mono = AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: 48000,
                                 channels: 1, interleaved: false)!
        let monoOutput = try AudioPreparation.buffer(format: mono, frames: 1)
        #expect(throws: RebaseCoreError.self) { try CPRLiveCallbackAdapter.process(monoOutput) }
    }
}
