import AVFoundation
import Darwin
import Foundation
import Testing
@testable import RebaseCore

/// Wider descriptors are self-authored reader controls. The real CPR admission
/// test separately preserves the frozen zero-origin source interpretation.
@Suite(.serialized)
struct CPRNativeTimelineStreamTests {
    private let workspace = PrivateResearchFixtures.root
    private func rejects(_ body: () throws -> Void) -> Bool {
        do { try body(); return false } catch { return true }
    }
    private func stereo(_ frames: Int, seed: Int) -> [Float] {
        (0..<frames * 2).map { Float(($0 * 37 + seed) % 4095 - 2047) / 4096 }
    }
    private func interleavedBits(_ buffer: AVAudioPCMBuffer) -> [UInt32] {
        (0..<Int(buffer.frameLength) * 2).map {
            buffer.floatChannelData![$0 % 2][$0 / 2].bitPattern
        }
    }
    private func collected(_ cursor: CPRNativeTimelineStream.Cursor, maximum: Int) throws -> [UInt32] {
        var result: [UInt32] = []
        while let buffer = try cursor.nextBuffer(maximumFrames: maximum) {
            #expect(buffer.frameLength > 0 && buffer.frameLength <= maximum)
            result += interleavedBits(buffer)
        }
        #expect(cursor.isAtEnd)
        #expect(try cursor.nextBuffer(maximumFrames: maximum) == nil)
        return result
    }

    @Test func SyntheticPlacementGapsOffsetsAndGainArePartitionAndSeekInvariant() throws {
        // 8192 Hz makes every authored frame coordinate exactly representable.
        // Expected output is a direct integer-indexed construction, not a call
        // to the quantizer, planner, reader or production sample converter.
        let rate = 8192.0
        let rows: [(Int, Int, Int, Float, [Float])] = [
            (3, 8195, 7, 0.5, stereo(8220, seed: 11)),
            (8205, 8193, 3, 2, stereo(8210, seed: 103)),
            (16400, 101, 19, 1, stereo(128, seed: 777))]
        let segments = rows.map { start, length, offset, gain, samples in
            CPRNativeTimelineStream.Segment(start: Double(start) / rate, length: Double(length) / rate,
                offset: Double(offset) / rate, samples: samples, gain: gain, sourceRate: rate)
        }
        var expected = [UInt32](repeating: 0, count: 16501 * 2)
        for (start, length, offset, gain, samples) in rows {
            for frame in 0..<length {
                for channel in 0..<2 {
                    // Multiplication by powers of two is exact in this normal domain.
                    expected[(start + frame) * 2 + channel] = (samples[(offset + frame) * 2 + channel] * gain).bitPattern
                }
            }
        }
        let stream = try CPRNativeTimelineStream(sampleRate: rate, segments: segments)
        #expect(stream.frameCount == 16501 && stream.format.sampleRate == rate)
        #expect(stream.format.channelCount == 2 && !stream.format.isInterleaved)
        for maximum in [1, 257, 4096, 8192, 65536] {
            #expect(try collected(stream.cursor(from: 0), maximum: maximum) == expected)
        }
        for start in [0, 2, 3, 8197, 8198, 8200, 8205, 16397, 16398, 16400, 16500, 16501] {
            let cursor = try stream.cursor(from: Int64(start))
            #expect(cursor.deliveredFrames == Int64(start))
            #expect(try collected(cursor, maximum: 257) == Array(expected.dropFirst(start * 2)))
            #expect(cursor.deliveredFrames == stream.frameCount)
        }
    }

    @Test func TouchingSegmentsAndRoundedDescriptorEndpointsDoNotDuplicateFrames() throws {
        let rate = 8192.0
        let first = stereo(9, seed: 5), second = stereo(9, seed: 701)
        let stream = try CPRNativeTimelineStream(sampleRate: rate, segments: [
            .init(start: 0.25 / rate, length: 3.5 / rate, offset: 1.25 / rate, samples: first, gain: 1, sourceRate: rate),
            .init(start: 4.25 / rate, length: 3.5 / rate, offset: 2.25 / rate, samples: second, gain: 1, sourceRate: rate)])
        // Native independently rounds each concrete start/end getter: [0,4),[4,8).
        let expected = Array(first[2..<10]) + Array(second[4..<12])
        #expect(stream.frameCount == 8)
        #expect(try collected(stream.cursor(from: 0), maximum: 3) == expected.map(\.bitPattern))
        #expect(try collected(stream.cursor(from: 4), maximum: 1) == Array(expected.dropFirst(8)).map(\.bitPattern))
        let a = try stream.cursor(from: 0), b = try stream.cursor(from: 0)
        let output = try #require(try a.nextBuffer(maximumFrames: 2))
        output.floatChannelData![0][0] = 999
        #expect(try collected(b, maximum: 8) == expected.map(\.bitPattern))
    }

    @Test func UnsupportedSourcesAndFailedBlocksDoNotAdvanceCursor() throws {
        let source = stereo(16, seed: 77)
        func segment(start: Double = 0, length: Double = 8 / 8192, offset: Double = 0,
                     gain: Float = 1, samples: [Float]? = nil) -> CPRNativeTimelineStream.Segment {
            .init(start: start, length: length, offset: offset, samples: samples ?? source, gain: gain, sourceRate: 8192)
        }
        for rate in [Double.nan, .infinity, 0, 7999, 8192.5, 192001] {
            #expect(rejects { _ = try CPRNativeTimelineStream(sampleRate: rate, segments: [segment()]) })
        }
        for rows in [
            [], [segment(start: -1)], [segment(start: .nan)], [segment(length: 0)],
            [segment(length: .infinity)], [segment(offset: -1)],
            [segment(offset: 9 / 8192)], [segment(samples: [1])],
            [segment(samples: [])], [segment(gain: 0)], [segment(gain: .infinity)],
            [segment(samples: [Float.nan, 1])],
            [segment(samples: [Float.leastNonzeroMagnitude, 1])],
            [segment(length: 1 / 8192, gain: 2, samples: [.greatestFiniteMagnitude, 1])],
            [segment(), segment(start: 7 / 8192)],
            [segment(start: 10 / 8192), segment()]
        ] {
            #expect(rejects { _ = try CPRNativeTimelineStream(sampleRate: 8192, segments: rows) })
        }
        let stream = try CPRNativeTimelineStream(sampleRate: 8192, segments: [segment()])
        #expect(rejects { _ = try stream.cursor(from: -1) })
        #expect(rejects { _ = try stream.cursor(from: 9) })
        let cursor = try stream.cursor(from: 0)
        for maximum in [0, -1, 65537] {
            #expect(rejects { _ = try cursor.nextBuffer(maximumFrames: maximum) })
            #expect(cursor.deliveredFrames == 0)
        }
        let saved = fegetround()
        defer { _ = fesetround(saved) }
        #expect(fesetround(FE_DOWNWARD) == 0)
        #expect(rejects { _ = try cursor.nextBuffer(maximumFrames: 4) })
        #expect(cursor.deliveredFrames == 0)
        #expect(fesetround(saved) == 0)
        #expect(try collected(cursor, maximum: 3) == Array(source.prefix(16)).map(\.bitPattern))
    }

    private func le<T: FixedWidthInteger>(_ value: T) -> Data {
        var value = value.littleEndian
        return withUnsafeBytes(of: &value) { Data($0) }
    }
    private func pcm24(frames: Int) -> Data {
        let size = frames * 6
        var data = Data("RIFF".utf8) + le(UInt32(size + 36)) + Data("WAVEfmt ".utf8)
        data += le(UInt32(16)) + le(UInt16(1)) + le(UInt16(2)) + le(UInt32(44100))
        data += le(UInt32(264600)) + le(UInt16(6)) + le(UInt16(24))
        data += Data("data".utf8) + le(UInt32(size)) + Data(repeating: 0, count: size)
        data.withUnsafeMutableBytes { raw in
            let bytes = raw.bindMemory(to: UInt8.self)
            for frame in 0..<frames {
                for channel in 0..<2 {
                    let bits = UInt32(bitPattern: sample(frame, channel))
                    let offset = 44 + (frame * 2 + channel) * 3
                    bytes[offset] = UInt8(truncatingIfNeeded: bits)
                    bytes[offset + 1] = UInt8(truncatingIfNeeded: bits >> 8)
                    bytes[offset + 2] = UInt8(truncatingIfNeeded: bits >> 16)
                }
            }
        }
        return data
    }
    private func sample(_ frame: Int, _ channel: Int) -> Int32 {
        Int32((frame * (channel == 0 ? 7919 : 104729) + channel * 12345) & 0xffffff) - 8388608
    }
    private func expectedBits(_ value: Int32) -> UInt32 {
        guard value != 0 else { return 0 }
        let magnitude = UInt32(value < 0 ? -value : value)
        let top = 31 - magnitude.leadingZeroBitCount
        return (value < 0 ? UInt32(0x80000000) : 0) | UInt32(top - 23 + 127) << 23
            | ((magnitude << (23 - top)) & 0x7fffff)
    }
    private func snapshot(_ root: URL) throws -> [String: Data] {
        let files = try #require(FileManager.default.enumerator(at: root, includingPropertiesForKeys: [.isRegularFileKey]))
        var result: [String: Data] = [:]
        for case let url as URL in files where try url.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile == true {
            result[String(url.path.dropFirst(root.path.count + 1))] = try Data(contentsOf: url)
        }
        return result
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func RealSourceReaderMatchesEveryPCMFrameAndKeepsProofAndProjectBarriers() throws {
        let temporary = FileManager.default.temporaryDirectory.appendingPathComponent("NativeTimeline-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: temporary, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporary) }
        let original = workspace.appendingPathComponent("templates/LoFi Hip Hop.cpr")
        let originalData = try Data(contentsOf: original)
        #expect(cprSHA256(originalData) == "2795af70cbc6651fbd6aa4cfbcb546d606d25d5970722a6c553384f3d196e495")
        let package = temporary.appendingPathComponent("Source.rebaseproj")
        let imported = try CPRProject.importProject(from: original, to: package, allowPartial: true)
        let event = try #require(imported.project.unresolvedAudioEvents.first)
        let pcm = pcm24(frames: 1_058_400), media = temporary.appendingPathComponent("Synthetic.wav")
        try pcm.write(to: media)
        let project = try ProjectStore.attachCPRAudioMedia(from: media, to: event.id, in: imported.project, at: package)
        try ProjectStore.save(project, to: package)
        let before = try snapshot(package)
        let prepared = try CPRSourceEventPlayback.prepare(eventID: event.id, project: project, root: package,
                                                          mode: .nativeTimelineSourceRate)
        #expect(prepared.info.mode == .nativeTimelineSourceRate)
        #expect(prepared.info.frameCount == 1_058_400 && prepared.info.duration == 24)
        #expect(prepared.info.sampleRate == 44100 && prepared.info.sourceSampleRate == 44100)
        #expect(prepared.info.sourceSHA256 == cprSHA256(originalData) && prepared.info.mediaSHA256 == cprSHA256(pcm))
        #expect(prepared.audio.clips.isEmpty && prepared.audio.sourceEventStream == nil)
        #expect(project.tracks.flatMap(\.clips).isEmpty && project.unresolvedAudioEvents == imported.project.unresolvedAudioEvents)
        let stream = try #require(prepared.audio.nativeTimelineStream)
        let cursor = try stream.cursor(from: 0)
        var first = 0
        while let output = try cursor.nextBuffer(maximumFrames: 4093) {
            let channels = try #require(output.floatChannelData)
            var equal = true
            for frame in 0..<Int(output.frameLength) {
                for channel in 0..<2 where channels[channel][frame].bitPattern != expectedBits(sample(first + frame, channel)) {
                    equal = false
                }
            }
            #expect(equal)
            first += Int(output.frameLength)
        }
        #expect(first == 1_058_400)
        for seek in [1, 4093, 8192, 1_058_399, 1_058_400] {
            let seekCursor = try stream.cursor(from: Int64(seek))
            if let output = try seekCursor.nextBuffer(maximumFrames: 7) {
                for frame in 0..<Int(output.frameLength) {
                    for channel in 0..<2 {
                        #expect(output.floatChannelData![channel][frame].bitPattern == expectedBits(sample(seek + frame, channel)))
                    }
                }
            } else { #expect(seek == 1_058_400) }
        }
        #expect(rejects { try project.requireResolvedAudioEvents() })
        #expect(rejects { _ = try OfflineRenderer.render(project: project, projectRoot: package) })
        let destination = temporary.appendingPathComponent("Blocked.wav")
        try Data("unchanged".utf8).write(to: destination)
        #expect(rejects { _ = try OfflineRenderer.export(project: project, projectRoot: package, to: destination) })
        #expect(try Data(contentsOf: destination) == Data("unchanged".utf8))
        let boundMedia = try ProjectStore.resolveMediaURL(project.cprMediaAttachments[0].mediaPath, projectRoot: package)
        for path in [boundMedia, package.appendingPathComponent(CPRProject.originalRelativePath),
                     package.appendingPathComponent(CPRProject.reportRelativePath)] {
            let bytes = try Data(contentsOf: path)
            var changed = bytes
            changed[path == boundMedia ? 44 : changed.count - 1] ^= 1
            try changed.write(to: path)
            #expect(rejects {
                _ = try CPRSourceEventPlayback.prepare(eventID: event.id, project: project, root: package,
                                                      mode: .nativeTimelineSourceRate)
            })
            try bytes.write(to: path)
        }
        #expect(try snapshot(package) == before)
        #expect(try Data(contentsOf: original) == originalData)
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func SourceBackedNonzeroCPRControlStaysUnplacedAndRequiresMedia() throws {
        let temporary = FileManager.default.temporaryDirectory.appendingPathComponent("TimelineUnplaced-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: temporary, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporary) }
        let original = workspace.appendingPathComponent("templates/LoFi Hip Hop.cpr")
        let originalData = try Data(contentsOf: original)
        #expect(cprSHA256(originalData) == "2795af70cbc6651fbd6aa4cfbcb546d606d25d5970722a6c553384f3d196e495")
        // Known pinned event MEvent prefix: u16 then start/length/offset f64BE.
        // This is a derived CPR input with its own replayed digest, not a forged
        // Project.json placement or a mutation of the reference template.
        var derived = originalData
        let startOffset = 197_765 + 2
        #expect(derived[startOffset..<startOffset + 8].allSatisfy { $0 == 0 })
        var start = Double(44100).bitPattern.bigEndian
        withUnsafeBytes(of: &start) { derived.replaceSubrange(startOffset..<startOffset + 8, with: $0) }
        let source = temporary.appendingPathComponent("Derived nonzero.cpr")
        try derived.write(to: source)
        let package = temporary.appendingPathComponent("Derived.rebaseproj")
        let imported = try CPRProject.importProject(from: source, to: package, allowPartial: true)
        let event = try #require(imported.project.unresolvedAudioEvents.first)
        #expect(event.sourceSHA256 == cprSHA256(derived) && event.rawStartBits == Double(44100).bitPattern)
        #expect(event.placement == nil && imported.project.tracks.flatMap(\.clips).isEmpty)
        // Frozen V4 remains unplaced. Playback still needs an explicit media
        // attachment; APP015 separately tests admitted nonzero attached events.
        #expect(rejects {
            _ = try CPRSourceEventPlayback.prepare(eventID: event.id, project: imported.project, root: package,
                                                  mode: .nativeTimelineSourceRate)
        })
        #expect(try Data(contentsOf: package.appendingPathComponent(CPRProject.originalRelativePath)) == derived)
        #expect(try Data(contentsOf: original) == originalData)
    }
}
