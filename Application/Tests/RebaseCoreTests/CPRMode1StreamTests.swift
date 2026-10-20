import AVFoundation
import Foundation
import Testing
@testable import RebaseCore

/// Application composition controls for the reconstructed mode 1 filter.
/// Instruction-derived coefficient and history oracles are tested separately;
/// these checks do not execute the Reference reference.
@Suite(.serialized)
struct CPRMode1StreamTests {
    private func source(frames: Int = 20_003) -> [Float] {
        (0..<frames * 2).map { Float(($0 * 7919 % 65536) - 32768) / 32768 }
    }

    private func collect(_ cursor: CPRRateConvertedStream.Cursor) throws -> [Float] {
        var values = [Float]()
        while let block = try cursor.nextInterleaved() { values.append(contentsOf: block) }
        return values
    }

    private func stream(rate: Double, gain: Float = 1) throws -> CPRRateConvertedStream {
        try CPRRateConvertedStream(source: source(), sourceRate: 44100, outputRate: rate,
            gain: gain, algorithm: .nativeMode1)
    }

    @Test func FreshCursorsAndPrerollPreserveOutputAcrossBothRatesAndEqualRate() throws {
        for rate in [48000.0, 32000.0, 16000.0, 44100.0] {
            let converted = try stream(rate: rate)
            let firstCursor = try converted.cursor(from: 0)
            let first = try collect(firstCursor).map(\.bitPattern)
            #expect(first.count == Int(converted.frameCount) * 2 && firstCursor.isAtEnd)
            #expect(first.contains { $0 & 0x7fffffff != 0 })
            let second = try collect(converted.cursor(from: 0)).map(\.bitPattern)
            #expect(second == first)
            for offset in [1, 2047, 2048, 4095, Int(converted.frameCount) - 1, Int(converted.frameCount)] {
                let cursor = try converted.cursor(from: Int64(offset))
                #expect(try collect(cursor).map(\.bitPattern) == Array(first.dropFirst(offset * 2)))
                #expect(cursor.isAtEnd && cursor.deliveredFrames == converted.frameCount)
                #expect(try cursor.nextBuffer() == nil)
            }
        }
    }

    @Test func GainIsAppliedAfterFilteringAndRingTransferPreservesStereo() throws {
        for rate in [48000.0, 32000.0] {
            let raw = try collect(stream(rate: rate).cursor(from: 0))
            let gain = Float(0.3)
            let converted = try stream(rate: rate, gain: gain)
            let expected = raw.map { Float(Double($0) * Double(gain)).bitPattern }
            let cursor = try converted.cursor(from: 0)
            var at = 0
            while let buffer = try cursor.nextBuffer() {
                #expect(buffer.format.sampleRate == rate && buffer.format.channelCount == 2)
                #expect(!buffer.format.isInterleaved)
                var matches = true
                for frame in 0..<Int(buffer.frameLength) {
                    for channel in 0..<2 {
                        if buffer.floatChannelData![channel][frame].bitPattern != expected[(at + frame) * 2 + channel] {
                            matches = false
                        }
                    }
                }
                #expect(matches)
                at += Int(buffer.frameLength)
            }
            #expect(at == Int(converted.frameCount))
            let changedInput = source().map { Float(Double($0) * Double(gain)) }
            let before = try CPRRateConvertedStream(source: changedInput, sourceRate: 44100,
                outputRate: rate, gain: 1, algorithm: .nativeMode1)
            #expect(try collect(before.cursor(from: 0)).map(\.bitPattern) != expected)
        }
    }

    @Test func OfflinePlayerDeliversMode1TailAndThenSilence() throws {
        for rate in [48000.0, 32000.0] {
            let converted = try stream(rate: rate)
            let frames = min(9001, Int(converted.frameCount))
            let start = converted.frameCount - Int64(frames)
            let expected = try collect(converted.cursor(from: start)).map(\.bitPattern)
            let cursor = try converted.cursor(from: start)
            let engine = AVAudioEngine(), player = AVAudioPlayerNode()
            engine.attach(player); engine.connect(player, to: engine.mainMixerNode, format: converted.format)
            player.volume = 1; engine.mainMixerNode.outputVolume = 1
            try engine.enableManualRenderingMode(.offline, format: converted.format, maximumFrameCount: 256)
            defer { player.stop(); engine.stop(); engine.disableManualRenderingMode() }
            var buffers = [AVAudioPCMBuffer]()
            while let buffer = try cursor.nextBuffer() {
                buffers.append(buffer); player.scheduleBuffer(buffer, at: nil, options: [])
            }
            try engine.start(); player.play()
            let output = try AudioPreparation.buffer(format: converted.format, frames: 256)
            var position = 0, retries = 0
            while position < frames + 257 {
                let request = AVAudioFrameCount(min(256, frames + 257 - position))
                let status = try engine.renderOffline(request, to: output)
                if status == .cannotDoInCurrentContext && retries < 16 { retries += 1; continue }
                try #require(status == .success && output.frameLength == request)
                var matches = true
                for frame in 0..<Int(request) {
                    for channel in 0..<2 {
                        let value = output.floatChannelData![channel][frame]
                        let absolute = position + frame
                        if absolute < frames {
                            if value.bitPattern != expected[absolute * 2 + channel] { matches = false }
                        } else if value != 0 { matches = false }
                    }
                }
                #expect(matches)
                position += Int(request)
            }
            #expect(cursor.isAtEnd && position == frames + 257)
        }
    }

    @Test func InvalidDomainsRejectWithoutSelectingAnotherAlgorithm() throws {
        for rate in [7999.0, 192001.0, 48000.5, Double.infinity, Double.nan] {
            #expect(throws: RebaseCoreError.self) { try stream(rate: rate) }
        }
        for bad in [Float.nan, Float.infinity, Float.leastNonzeroMagnitude] {
            var input = source(); input[2] = bad
            let converted = try CPRRateConvertedStream(source: input, sourceRate: 44100,
                outputRate: 48000, gain: 1, algorithm: .nativeMode1)
            #expect(throws: RebaseCoreError.self) { try converted.cursor(from: 0).nextBuffer() }
        }
        let converted = try stream(rate: 48000)
        #expect(throws: RebaseCoreError.self) { try converted.cursor(from: -1) }
        #expect(throws: RebaseCoreError.self) { try converted.cursor(from: converted.frameCount + 1) }
    }
}
