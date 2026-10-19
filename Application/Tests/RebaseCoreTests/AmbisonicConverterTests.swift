import Testing
import Foundation
import AVFoundation
@testable import RebaseCore

private extension AVAudioPCMBuffer {
    var doublePlanes: [UnsafeMutablePointer<Double>] {
        UnsafeMutableAudioBufferListPointer(mutableAudioBufferList).map {
            $0.mData!.assumingMemoryBound(to: Double.self)
        }
    }
}

// File and buffer bridge tests. C arithmetic is separately checked against
// exact-rational products and tables read from the pinned Mach-O as data.
final class AmbisonicConverterTests {
    private let maps = [[0,3,1,2,6,7,5,8,4,12,13,11,14,10,15,9],
                        [0,2,3,1,8,6,4,5,7,15,13,11,9,10,12,14]]
    private let gains: [Int: [[UInt64]]] = [
        32: [[0x3fb504f3,0x3f800000,0x3f800000,0x3f800000,0x3f800000,0x3f5db3d7,0x3f5db3d7,0x3f5db3d7,
              0x3f5db3d7,0x3f800000,0x4098a61f,0x4098a61f,0x3f3ecfa6,0x3f3ecfa6,0x3fe24630,0x3fe24630],
             [0x3f3504f3,0x3f800000,0x3f800000,0x3f800000,0x3f800000,0x3f93cd3a,0x3f93cd3a,0x3f93cd3a,
              0x3f93cd3a,0x3f800000,0x3e56a99b,0x3e56a99b,0x3fabbae3,0x3fabbae3,0x3f10d0c3,0x3f10d0c3]],
        64: [[0x3ff6a09e667f3bcd,0x3ff0000000000000,0x3ff0000000000000,0x3ff0000000000000,
              0x3ff0000000000000,0x3febb67ae8584caa,0x3febb67ae8584caa,0x3febb67ae8584caa,
              0x3febb67ae8584caa,0x3ff0000000000000,0x401314c3d92a9e91,0x401314c3d92a9e91,
              0x3fe7d9f4cf754635,0x3fe7d9f4cf754635,0x3ffc48c6001f0abf,0x3ffc48c6001f0abf],
             [0x3fe6a09e667f3bcc,0x3ff0000000000000,0x3ff0000000000000,0x3ff0000000000000,
              0x3ff0000000000000,0x3ff279a74590331d,0x3ff279a74590331d,0x3ff279a74590331d,
              0x3ff279a74590331d,0x3ff0000000000000,0x3fcad5336963eefc,0x3fcad5336963eefc,
              0x3ff5775c544ff263,0x3ff5775c544ff263,0x3fe21a1851ff630a,0x3fe21a1851ff630a]]]

    private func workspace<T>(_ body: (URL) throws -> T) throws -> T {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("RebaseAmbi-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        return try body(directory)
    }

    private func append<T: FixedWidthInteger>(_ value: T, to data: inout Data) {
        var little = value.littleEndian
        withUnsafeBytes(of: &little) { data.append(contentsOf: $0) }
    }

    private func sample(_ bits: UInt64, width: Int, to data: inout Data) {
        if width == 32 { append(UInt32(bits), to: &data) } else { append(bits, to: &data) }
    }

    private func wave(channels: Int, width: Int, payload: Data, tag: UInt16 = 3, rate: UInt32 = 96_000) -> Data {
        var data = Data("RIFF".utf8)
        append(UInt32(36 + payload.count), to: &data)
        data.append(Data("WAVEfmt ".utf8))
        append(UInt32(16), to: &data); append(tag, to: &data); append(UInt16(channels), to: &data)
        append(rate, to: &data); append(rate * UInt32(channels * width / 8), to: &data)
        append(UInt16(channels * width / 8), to: &data); append(UInt16(width), to: &data)
        data.append(Data("data".utf8)); append(UInt32(payload.count), to: &data); data.append(payload)
        return data
    }

    private func decoded(_ path: URL) throws -> (Int, Int, Int, Data) {
        let data = try Data(contentsOf: path)
        func number<T: FixedWidthInteger>(_ position: Int, _: T.Type) -> T {
            data.withUnsafeBytes { T(littleEndian: $0.loadUnaligned(fromByteOffset: position, as: T.self)) }
        }
        #expect(data.prefix(4) == Data("RIFF".utf8))
        #expect(data[8..<12] == Data("WAVE".utf8))
        var position = 12, channels = 0, width = 0, rate = 0, payload = Data()
        while position + 8 <= data.count {
            let size = Int(number(position + 4, UInt32.self)), start = position + 8
            guard size <= data.count - start else { throw AmbisonicConversionError.message("Invalid output chunk size") }
            let name = String(data: data[position..<position+4], encoding: .ascii)
            if name == "fmt " {
                guard size >= 16 else { throw AmbisonicConversionError.message("Invalid output format") }
                let tag = number(start, UInt16.self)
                channels = Int(number(start+2, UInt16.self)); rate = Int(number(start+4, UInt32.self))
                width = Int(number(start+14, UInt16.self))
                if tag == 0xfffe {
                    #expect(size >= 40)
                    #expect(number(start+24, UInt16.self) == 3)
                } else { #expect(tag == 3) }
            } else if name == "data" { payload = Data(data[start..<start+size]) }
            position = start + size + (size & 1)
        }
        return (channels, width, rate, payload)
    }

    // Every frame is a channel basis vector scaled by an exact power of two.
    // Expected products change only gain exponent/sign bits: no DSP multiply.
    private func fixture(channels: Int, width: Int, direction: Int, frames: Int = 8209) -> (Data, Data) {
        var input = Data(), expected = Data()
        let fractionBits = width == 32 ? 23 : 52
        let one: UInt64 = width == 32 ? 0x3f800000 : 0x3ff0000000000000
        let sign: UInt64 = UInt64(1) << (width - 1)
        for frame in 0..<frames {
            let active = frame == frames - 1 ? 1 : frame % channels
            let exponent = (frame / channels) % 8
            let negative = frame % 2 != 0
            let zero = frame % 3 == 0 ? sign : 0
            var source = Array(repeating: zero, count: channels)
            var result = Array(repeating: UInt64(0), count: channels)
            // The final sample tests preservation of source mantissa precision.
            source[active] = frame == frames - 1 ? one + 1 : (one - (UInt64(exponent) << fractionBits)) | (negative ? sign : 0)
            for channel in 0..<channels {
                let destination = maps[direction][channel]
                if channel == active {
                    result[destination] = frame == frames - 1 ? one + 1 :
                        (gains[width]![direction][destination] - (UInt64(exponent) << fractionBits)) | (negative ? sign : 0)
                } else { result[destination] = zero }
            }
            for bits in source { sample(bits, width: width, to: &input) }
            for bits in result { sample(bits, width: width, to: &expected) }
        }
        return (wave(channels: channels, width: width, payload: input), expected)
    }

    @Test func allConfigurationsPreserveExactSamplesAndTail() throws {
        try workspace { directory in
            for channels in [4, 9, 16] {
                for width in [32, 64] {
                    for direction in [0, 1] {
                        let (sourceBytes, expected) = fixture(channels: channels, width: width, direction: direction)
                        let source = directory.appendingPathComponent("source-\(channels)-\(width)-\(direction).wav")
                        let output = directory.appendingPathComponent("output-\(channels)-\(width)-\(direction).wav")
                        try sourceBytes.write(to: source)
                        let info = try AmbisonicFileConverter.convert(source: source, destination: output,
                            direction: direction == 0 ? .fumaToAmbix : .ambixToFuma)
                        #expect(info.channels == channels && info.precision == width && info.frames == 8209 && info.sampleRate == 96_000)
                        let actual = try decoded(output)
                        #expect(actual.0 == channels && actual.1 == width && actual.2 == 96_000)
                        let payloadMatches = actual.3 == expected
                        let firstDifference = zip(actual.3, expected).enumerated().first { $0.element.0 != $0.element.1 }?.offset
                        #expect(payloadMatches, "N=\(channels), binary\(width), direction=\(direction), bytes=\(actual.3.count)/\(expected.count), first mismatch=\(String(describing: firstDifference))")
                        let reopened = try AVAudioFile(forReading: output,
                            commonFormat: width == 32 ? .pcmFormatFloat32 : .pcmFormatFloat64, interleaved: false)
                        #expect(reopened.length == 8209 && Int(reopened.fileFormat.streamDescription.pointee.mBitsPerChannel) == width)
                        reopened.framePosition = 8192
                        let tail = try #require(AVAudioPCMBuffer(pcmFormat: reopened.processingFormat, frameCapacity: 17))
                        try reopened.read(into: tail, frameCount: 17)
                        #expect(tail.frameLength == 17)
                        if width == 32 { #expect(tail.floatChannelData![maps[direction][1]][16].bitPattern == 0x3f800001) }
                        else { #expect(tail.doublePlanes[maps[direction][1]][16].bitPattern == 0x3ff0000000000001) }
                        #expect(try Data(contentsOf: source) == sourceBytes)
                    }
                }
            }
        }
    }

    @Test func inPlaceBufferStagesAllChannelsAndBypassCopiesBits() throws {
        for width in [32, 64] {
            for channels in [4, 9, 16] {
                let layout = try #require(AVAudioChannelLayout(layoutTag: kAudioChannelLayoutTag_DiscreteInOrder | UInt32(channels)))
                let format = AVAudioFormat(commonFormat: width == 32 ? .pcmFormatFloat32 : .pcmFormatFloat64,
                                          sampleRate: 48_000, interleaved: false, channelLayout: layout)
                let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 9)!
                buffer.frameLength = 9
                let processor = try AmbisonicProcessor(channels: channels, precision: width, maximumFrames: 9)
                for direction in [0, 1] {
                    for c in 0..<channels { for f in 0..<9 {
                        if width == 32 { buffer.floatChannelData![c][f] = Float(sign: .plus, exponent: -(c+1), significand: 1) }
                        else { buffer.doublePlanes[c][f] = Double(sign: .plus, exponent: -(c+1), significand: 1) }
                    } }
                    let report = try processor.process(input: buffer, output: buffer, direction: direction == 0 ? .fumaToAmbix : .ambixToFuma)
                    #expect(report.staged_all_inputs == 1 && report.disposition == 1)
                    for c in 0..<channels { for f in 0..<9 {
                        let destination = maps[direction][c]
                        let expected = gains[width]![direction][destination] - (UInt64(c+1) << (width == 32 ? 23 : 52))
                        if width == 32 { #expect(UInt64(buffer.floatChannelData![destination][f].bitPattern) == expected) }
                        else { #expect(buffer.doublePlanes[destination][f].bitPattern == expected) }
                    } }
                }
                for c in 0..<channels { for f in 0..<9 {
                    if width == 32 { buffer.floatChannelData![c][f] = Float(bitPattern: f % 2 == 0 ? 1 : 0x80000000) }
                    else { buffer.doublePlanes[c][f] = Double(bitPattern: f % 2 == 0 ? 1 : 0x8000000000000000) }
                } }
                let copied = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 9)!
                let report = try processor.process(input: buffer, output: copied, direction: .ambixToFuma, bypass: true)
                #expect(report.disposition == 2 && report.staged_all_inputs == 0)
                for c in 0..<channels { for f in 0..<9 {
                    if width == 32 { #expect(copied.floatChannelData![c][f].bitPattern == buffer.floatChannelData![c][f].bitPattern) }
                    else { #expect(copied.doublePlanes[c][f].bitPattern == buffer.doublePlanes[c][f].bitPattern) }
                } }
            }
        }
    }

    @Test func failedLateBlockPreservesDestinationAndRemovesTemporary() throws {
        try workspace { directory in
            for width in [32, 64] {
                var (bytes, _) = fixture(channels: 4, width: width, direction: 0)
                let offset = 44 + (8195 * 4 + 2) * (width / 8)
                var invalid = Data(); sample(width == 32 ? 0x7fc00000 : 0x7ff8000000000000, width: width, to: &invalid)
                bytes.replaceSubrange(offset..<offset+invalid.count, with: invalid)
                let source = directory.appendingPathComponent("bad-\(width).wav")
                let output = directory.appendingPathComponent("keep-\(width).wav")
                let prior = Data("existing destination".utf8)
                try bytes.write(to: source); try prior.write(to: output)
                expectThrows(try AmbisonicFileConverter.convert(source: source, destination: output, direction: .fumaToAmbix))
                #expect(try Data(contentsOf: output) == prior)
                #expect(try Data(contentsOf: source) == bytes)
                let absent = directory.appendingPathComponent("absent-\(width).wav")
                expectThrows(try AmbisonicFileConverter.convert(source: source, destination: absent, direction: .fumaToAmbix))
                #expect(!FileManager.default.fileExists(atPath: absent.path))
            }
            #expect(try FileManager.default.contentsOfDirectory(atPath: directory.path).allSatisfy { !$0.hasPrefix(".rebase-") })
        }
    }

    @Test func sameFileLinksMalformedAndUnsupportedCountsAreRejected() throws {
        try workspace { directory in
            let (bytes, _) = fixture(channels: 4, width: 32, direction: 0, frames: 17)
            let source = directory.appendingPathComponent("source.wav")
            try bytes.write(to: source)
            let hard = directory.appendingPathComponent("hard.wav"), symbolic = directory.appendingPathComponent("symbolic.wav")
            try FileManager.default.linkItem(at: source, to: hard)
            try FileManager.default.createSymbolicLink(at: symbolic, withDestinationURL: source)
            for destination in [source, hard, symbolic, directory] {
                expectThrows(try AmbisonicFileConverter.convert(source: source, destination: destination, direction: .ambixToFuma))
                #expect(try Data(contentsOf: source) == bytes)
            }
            let bad = directory.appendingPathComponent("bad.wav"), output = directory.appendingPathComponent("output.wav")
            for badBytes in [Data("not a WAV".utf8), wave(channels: 2, width: 32, payload: Data(repeating: 0, count: 16)),
                             wave(channels: 4, width: 32, payload: Data())] {
                try badBytes.write(to: bad)
                expectThrows(try AmbisonicFileConverter.convert(source: bad, destination: output, direction: .fumaToAmbix))
                #expect(!FileManager.default.fileExists(atPath: output.path))
            }
        }
    }

    @Test func successReplacesExistingOutputAndIntegerPCMConvertsToFloat32() throws {
        try workspace { directory in
            let source = directory.appendingPathComponent("pcm16.wav"), output = directory.appendingPathComponent("out.wav")
            var payload = Data()
            for value: Int16 in [16384, 8192, -4096, 2048] { append(value, to: &payload) }
            try wave(channels: 4, width: 16, payload: payload, tag: 1, rate: 44_100).write(to: source)
            try Data("old output".utf8).write(to: output)
            let info = try AmbisonicFileConverter.convert(source: source, destination: output, direction: .fumaToAmbix)
            #expect(info.precision == 32 && info.frames == 1 && info.sampleRate == 44_100)
            let actual = try decoded(output)
            var expected = Data()
            for bits: UInt32 in [0x3f3504f3, 0xbe000000, 0x3d800000, 0x3e800000] { append(bits, to: &expected) }
            #expect(actual.0 == 4 && actual.1 == 32 && actual.2 == 44_100 && actual.3 == expected)
        }
    }

    @Test func outputSizePreflightRejectsOverflowBeforeProcessing() throws {
        for channels in [4, 9, 16] { for width in [32, 64] {
            let boundary = (Int64(UInt32.max) - 4097) / Int64(channels * (width / 8))
            try AmbisonicFileConverter.validateOutputSize(frames: boundary, channels: channels, precision: width)
            expectThrows(try AmbisonicFileConverter.validateOutputSize(frames: boundary + 1, channels: channels, precision: width))
            expectThrows(try AmbisonicFileConverter.validateOutputSize(frames: Int64.max, channels: channels, precision: width))
        } }
    }
}
