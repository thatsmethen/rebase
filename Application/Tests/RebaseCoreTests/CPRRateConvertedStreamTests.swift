import AVFoundation
import Foundation
import RebaseTimingDSP
import Testing
@testable import RebaseCore

@Suite(.serialized)
struct CPRRateConvertedStreamTests {
    private func source(frames: Int = 20_003) -> [Float] {
        (0..<frames * 2).map { Float(($0 * 7919 % 65536) - 32768) / 32768 }
    }

    private func collect(_ cursor: CPRRateConvertedStream.Cursor) throws -> [Float] {
        var result: [Float] = []
        while let block = try cursor.nextInterleaved() { result += block }
        return result
    }

    @Test func SeekPrerollAndPendingSuffixPreserveContinuousPCM() throws {
        let stream = try CPRRateConvertedStream(source: source(), sourceRate: 44100, outputRate: 48000, gain: 1)
        let reference = try collect(stream.cursor(from: 0)).map(\.bitPattern)
        #expect(reference.count == Int(stream.frameCount) * 2)
        for offset in [0, 1, 8914, 8915, 8916, 8917, 17831, Int(stream.frameCount) - 1, Int(stream.frameCount)] {
            let cursor = try stream.cursor(from: Int64(offset))
            let suffix = try collect(cursor).map(\.bitPattern)
            #expect(suffix == Array(reference.dropFirst(offset * 2)))
            #expect(cursor.isAtEnd && cursor.deliveredFrames == stream.frameCount)
            #expect(try cursor.nextBuffer() == nil)
        }
        let first = try stream.cursor(from: 0)
        _ = try first.nextBuffer()
        let restarted = try collect(stream.cursor(from: 0)).map(\.bitPattern)
        #expect(restarted == reference)
    }

    @Test func EventGainFollowsConversionAndRejectsInvalidSamplesTransactionally() throws {
        let input: [Float] = [0.12345679, -0.8765432, -0.2345679, 0.7654321, 0.9999999, -0.9999999]
        let gain = Float(0.3)
        let raw = try collect(CPRRateConvertedStream(source: input, sourceRate: 8000, outputRate: 192000, gain: 1).cursor(from: 0))
        let actual = try collect(CPRRateConvertedStream(source: input, sourceRate: 8000, outputRate: 192000, gain: gain).cursor(from: 0))
        // Two binary32 operands multiply exactly in binary64, followed by one
        // binary32 rounding. The converter's independent oracle is separate.
        let after = raw.map { Float(Double($0) * Double(gain)).bitPattern }
        #expect(actual.map(\.bitPattern) == after)
        let beforeInput = input.map { Float(Double($0) * Double(gain)) }
        let before = try collect(CPRRateConvertedStream(source: beforeInput, sourceRate: 8000, outputRate: 192000, gain: 1).cursor(from: 0))
        #expect(before.map(\.bitPattern) != after)
        var invalid: [Float] = [0.25, Float.greatestFiniteMagnitude]
        let original = invalid.map(\.bitPattern)
        #expect(rb_cpr_event_gain_f32(&invalid, invalid.count, Float(2).bitPattern) != 0)
        #expect(invalid.map(\.bitPattern) == original)
    }

    @Test func ConvertedBlocksPassThroughActualOfflinePlayerWithoutExtraTail() throws {
        for outputRate in [48000.0, 32000.0, 16000.0] {
            let stream = try CPRRateConvertedStream(source: source(), sourceRate: 44100, outputRate: outputRate, gain: 1)
            let renderFrames = min(10_003, Int(stream.frameCount))
            let start = stream.frameCount - Int64(renderFrames)
            let expected = try collect(stream.cursor(from: start)).map(\.bitPattern)
            let cursor = try stream.cursor(from: start)
            let engine = AVAudioEngine(), player = AVAudioPlayerNode()
            engine.attach(player); engine.connect(player, to: engine.mainMixerNode, format: stream.format)
            player.volume = 1; engine.mainMixerNode.outputVolume = 1
            try engine.enableManualRenderingMode(.offline, format: stream.format, maximumFrameCount: 256)
            defer { player.stop(); engine.stop(); engine.disableManualRenderingMode() }
            var queued = [AVAudioPCMBuffer]()
            while let buffer = try cursor.nextBuffer() {
                queued.append(buffer); player.scheduleBuffer(buffer, at: nil, options: [])
            }
            #expect(queued.count >= 2)
            try engine.start(); player.play()
            let output = try AudioPreparation.buffer(format: stream.format, frames: 256)
            var position = 0, retries = 0
            while position < renderFrames {
                let request = AVAudioFrameCount(min(256, renderFrames - position))
                let status = try engine.renderOffline(request, to: output)
                if status == .cannotDoInCurrentContext && retries < 16 { retries += 1; continue }
                #expect(status == .success && output.frameLength == request)
                guard status == .success, output.frameLength > 0 else { return }
                var matches = true
                for frame in 0..<Int(output.frameLength) {
                    for channel in 0..<2 {
                        if output.floatChannelData![channel][frame].bitPattern != expected[(position + frame) * 2 + channel] {
                            matches = false
                        }
                    }
                }
                #expect(matches)
                position += Int(output.frameLength)
            }
            #expect(position == renderFrames && cursor.isAtEnd)
            var tailFrames = 0
            while tailFrames < 257 {
                let request = AVAudioFrameCount(min(256, 257 - tailFrames))
                let status = try engine.renderOffline(request, to: output)
                if status == .cannotDoInCurrentContext && retries < 16 { retries += 1; continue }
                try #require(status == .success && output.frameLength == request)
                for channel in 0..<2 {
                    let samples = UnsafeBufferPointer(start: output.floatChannelData![channel], count: Int(request))
                    #expect(samples.allSatisfy { $0 == 0 })
                }
                tailFrames += Int(request)
            }
            #expect(tailFrames == 257)
        }
    }

    @Test func UnsupportedRatesAndSampleDomainsStopWithoutSubstitutingAnotherConverter() throws {
        for rate in [44100.0, 7999, 48000.5, Double.nan, Double.infinity, 192001] {
            #expect(throws: RebaseCoreError.self) {
                try CPRRateConvertedStream(source: source(frames: 8), sourceRate: 44100, outputRate: rate, gain: 1)
            }
        }
        for bad in [Float.nan, Float.infinity, Float.leastNonzeroMagnitude] {
            var samples = source(frames: 8); samples[9] = bad
            let stream = try CPRRateConvertedStream(source: samples, sourceRate: 44100, outputRate: 48000, gain: 1)
            #expect(throws: RebaseCoreError.self) { try stream.cursor(from: 0).nextBuffer() }
        }
    }

    @Test func LargeUpsamplingBlocksAreSplitAcrossTheNativeRingCapacity() throws {
        let stream = try CPRRateConvertedStream(source: source(frames: 8195),
            sourceRate: 8000, outputRate: 192000, gain: 1)
        let expected = try collect(stream.cursor(from: 0)).map(\.bitPattern)
        let cursor = try stream.cursor(from: 0)
        var at = 0, largest = 0
        while let buffer = try cursor.nextBuffer() {
            let frames = Int(buffer.frameLength)
            largest = max(largest, frames)
            var matches = true
            for frame in 0..<frames {
                for channel in 0..<2 {
                    if buffer.floatChannelData![channel][frame].bitPattern != expected[(at + frame) * 2 + channel] {
                        matches = false
                    }
                }
            }
            #expect(matches)
            at += frames
        }
        #expect(largest > 32768 && at == Int(stream.frameCount))
    }
}
