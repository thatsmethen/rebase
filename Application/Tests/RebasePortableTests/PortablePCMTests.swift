import Foundation
import Testing
import RebasePortable

private struct MemoryPCMSource: PCMSourceReader {
    let pcm: PCMBuffer
    var sampleRate: Double { pcm.sampleRate }
    var channelCount: Int { pcm.channels.count }
    var frameCount: Int64 { Int64(pcm.frameCount) }
    func read(from start: Int64, count: Int) throws -> PCMBuffer {
        try PCMBuffer(sampleRate: sampleRate, channels: pcm.channels.map { Array($0[Int(start)..<(Int(start) + count)]) })
    }
}

struct PortablePCMTests {
    private func clip(duration: Double, position: Double = 0, offset: Double = 0) -> Clip {
        Clip(mediaPath: "Media/control.wav", name: "Control", position: position, sourceOffset: offset, duration: duration)
    }

    @Test func trimResamplePanAndTimelineGapUseSharedPolicy() throws {
        let source = MemoryPCMSource(pcm: try PCMBuffer(sampleRate: 24_000, channels: [[0, 0.25, 0.5, 0.75]]))
        let item = clip(duration: 6 / 48_000, position: 2 / 48_000, offset: 1 / 24_000)
        let prepared = try PCMRenderer.prepare(Project(tracks: [Track(name: "Ramp", pan: -1, clips: [item])])) { _ in source }
        let mixed = try PCMRenderer.mix(prepared.clips, sampleRate: 48_000, from: 0, count: 8)
        #expect(prepared.frameCount == 8)
        #expect(mixed.channels[0] == [0, 0, 0.25, 0.375, 0.5, 0.625, 0.75, 0.75])
        #expect(mixed.channels[1] == [Float](repeating: 0, count: 8))
    }

    @Test func soloMuteAndAutomationAreAppliedBeforeMixing() throws {
        let source = MemoryPCMSource(pcm: try PCMBuffer(sampleRate: 48_000, channels: [[0.25, 0.25, 0.25, 0.25]]))
        let item = clip(duration: 4 / 48_000)
        let pan = AutomationLane(parameter: .pan, points: [
            AutomationPoint(time: 0, value: -1, interpolation: .step),
            AutomationPoint(time: 2 / 48_000, value: 1)
        ])
        var muted = item; muted.id = UUID()
        var excluded = item; excluded.id = UUID()
        let project = Project(tracks: [
            Track(name: "Audible", isSolo: true, clips: [item], automation: [pan]),
            Track(name: "Muted", isMuted: true, isSolo: true, clips: [muted]),
            Track(name: "Excluded", clips: [excluded])
        ])
        var reads = 0
        let prepared = try PCMRenderer.prepare(project) { _ in reads += 1; return source }
        let output = try PCMRenderer.mix(prepared.clips, sampleRate: 48_000, from: 0, count: 4)
        #expect(reads == 1)
        #expect(output.channels == [[0.25, 0.25, 0, 0], [0, 0, 0.25, 0.25]])
    }

    @Test func stableFloat32AccumulationAndChunkBoundaries() throws {
        let a = try PCMBuffer(sampleRate: 48_000, channels: [[16_777_216, 0.5], [0, 0]])
        let b = try PCMBuffer(sampleRate: 48_000, channels: [[1, 0.25], [0, 0]])
        let c = try PCMBuffer(sampleRate: 48_000, channels: [[-16_777_216, -0.125], [0, 0]])
        let clips = try [a, b, c].map { try PreparedPCMClip(startFrame: 8191, buffer: $0) }
        let whole = try PCMRenderer.mix(clips, sampleRate: 48_000, from: 8190, count: 4)
        #expect(whole.channels[0] == [0, 0, 0.625, 0])
        let first = try PCMRenderer.mix(clips, sampleRate: 48_000, from: 8190, count: 2)
        let second = try PCMRenderer.mix(clips, sampleRate: 48_000, from: 8192, count: 2)
        #expect(first.channels[0] + second.channels[0] == whole.channels[0])
    }

    @Test func invalidBuffersRangesAndAccumulationReject() throws {
        #expect(throws: (any Error).self) { try PCMBuffer(sampleRate: .nan, channels: [[0]]) }
        #expect(throws: (any Error).self) { try PCMBuffer(sampleRate: 48_000, channels: [[0], []]) }
        #expect(throws: (any Error).self) { try PCMBuffer(sampleRate: 48_000, channels: [[.infinity]]) }
        let pcm = try PCMBuffer(sampleRate: 48_000, channels: [[Float.greatestFiniteMagnitude], [0]])
        let prepared = try PreparedPCMClip(startFrame: 0, buffer: pcm)
        #expect(throws: (any Error).self) { try PCMRenderer.mix([prepared, prepared], sampleRate: 48_000, from: 0, count: 1) }
        #expect(throws: (any Error).self) { try PCMRenderer.mix([prepared], sampleRate: 44_100, from: 0, count: 1) }
        #expect(throws: (any Error).self) { try PCMRenderer.mix([], sampleRate: 48_000, from: Int64.max, count: 1) }
    }

    @Test func wavFloatRoundTripPreservesBitPatternsIncludingNegativeZero() throws {
        let values: [Float] = [0, -0.0, Float.leastNonzeroMagnitude, -1, 1, 0.25, Float.greatestFiniteMagnitude]
        let pcm = try PCMBuffer(sampleRate: 48_000, channels: [values, values.reversed()])
        let bytes = try WAVPCMSource.encode(pcm)
        let source = try WAVPCMSource(data: bytes)
        let decoded = try source.read(from: 0, count: values.count)
        #expect(source.channelCount == 2 && source.frameCount == 7 && source.sampleRate == 48_000)
        for channel in 0..<2 { #expect(decoded.channels[channel].map(\.bitPattern) == pcm.channels[channel].map(\.bitPattern)) }
        #expect(try WAVPCMSource.encode(decoded) == bytes)
        // Data slices can have a nonzero startIndex; parsing must normalize them.
        var prefix = Data([1, 2, 3]); prefix.append(bytes)
        #expect(try WAVPCMSource(data: prefix.dropFirst(3)).frameCount == 7)
    }

    @Test func integerWavDecodesSignedExtremesAndStereoOrdering() throws {
        let cases: [(Int, [UInt8], [Float])] = [
            (16, [0, 128, 0, 0, 255, 127, 0, 64], [-1, 0, 32_767 / 32_768, 0.5]),
            (24, [0, 0, 128, 0, 0, 0, 255, 255, 127, 0, 0, 64], [-1, 0, 8_388_607 / 8_388_608, 0.5]),
            (32, [0, 0, 0, 128, 0, 0, 0, 0, 255, 255, 255, 127, 0, 0, 0, 64], [-1, 0, 1, 0.5])
        ]
        for (bits, payload, expected) in cases {
            let source = try WAVPCMSource(data: integerWAV(bits: bits, payload: payload))
            let decoded = try source.read(from: 0, count: 2)
            #expect(decoded.channels == [[expected[0], expected[2]], [expected[1], expected[3]]])
            #expect(try source.read(from: 1, count: 1).channels == [[expected[2]], [expected[3]]])
            #expect(throws: (any Error).self) { try source.read(from: 2, count: 1) }
        }
    }

    @Test func malformedWavBoundsMetadataAndNonfiniteSamplesReject() throws {
        let pcm = try PCMBuffer(sampleRate: 48_000, channels: [[0.25], [-0.25]])
        let valid = try WAVPCMSource.encode(pcm)
        for length in [0, 4, 11, 12, 19, 37, valid.count - 1] {
            #expect(throws: (any Error).self) { try WAVPCMSource(data: valid.prefix(length)) }
        }
        // Byte rate, block alignment, and format code are independently checked.
        for offset in [20, 28, 32] {
            var invalid = valid; invalid[offset] = 0xff
            #expect(throws: (any Error).self) { try WAVPCMSource(data: invalid) }
        }
        var nonfinite = valid
        nonfinite.replaceSubrange(58..<62, with: [0, 0, 128, 127]) // +infinity
        let source = try WAVPCMSource(data: nonfinite)
        #expect(throws: (any Error).self) { try source.read(from: 0, count: 1) }
    }

    private func integerWAV(bits: Int, payload: [UInt8]) -> Data {
        var data = Data()
        func tag(_ s: String) { data.append(contentsOf: s.utf8) }
        func u16(_ n: Int) { data.append(UInt8(truncatingIfNeeded: n)); data.append(UInt8(truncatingIfNeeded: n >> 8)) }
        func u32(_ n: Int) { for shift in stride(from: 0, to: 32, by: 8) { data.append(UInt8(truncatingIfNeeded: n >> shift)) } }
        tag("RIFF"); u32(36 + payload.count); tag("WAVE"); tag("fmt "); u32(16)
        u16(1); u16(2); u32(48_000); u32(48_000 * 2 * bits / 8); u16(2 * bits / 8); u16(bits)
        tag("data"); u32(payload.count); data.append(contentsOf: payload)
        return data
    }
}
