import AVFoundation
import Foundation
import Testing
@testable import RebaseCore

/// Application audition and scheduling tests. Synthetic PCM is attached to a
/// preserved template; neither target execution nor device-output fidelity is tested.
@Suite(.serialized)
struct CPRSourceEventPlaybackTests {
    private let frameCount = 1_058_400
    private let rate = 44_100.0
    private let workspace = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()

    private struct Fixture {
        let temporary: URL
        let package: URL
        let project: Project
        let eventID: UUID
        let media: URL
        let pcm: Data
    }

    private func le<T: FixedWidthInteger>(_ value: T) -> Data {
        var value = value.littleEndian
        return withUnsafeBytes(of: &value) { Data($0) }
    }

    private func fixture() throws -> Fixture {
        let temporary = FileManager.default.temporaryDirectory.appendingPathComponent("SourcePlayback-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: temporary, withIntermediateDirectories: true)
        do {
            let original = workspace.appendingPathComponent("research/targets/full-reference/expanded/Reference 15.app.pkg/Payload/Reference 15.app/Contents/Project Templates/Reference Pro/LoFi Hip Hop.cpr")
            let package = temporary.appendingPathComponent("Source.rebaseproj")
            let imported = try CPRProject.importProject(from: original, to: package, allowPartial: true)
            let event = try #require(imported.project.unresolvedAudioEvents.first)
            let size = frameCount * 6
            var pcm = Data("RIFF".utf8) + le(UInt32(size + 36)) + Data("WAVEfmt ".utf8)
            pcm += le(UInt32(16)) + le(UInt16(1)) + le(UInt16(2)) + le(UInt32(44100))
            pcm += le(UInt32(264600)) + le(UInt16(6)) + le(UInt16(24))
            pcm += Data("data".utf8) + le(UInt32(size)) + Data(repeating: 0, count: size)
            pcm.withUnsafeMutableBytes { raw in
                let bytes = raw.bindMemory(to: UInt8.self)
                for frame in 0..<frameCount {
                    for channel in 0..<2 {
                        let value: Int32
                        if frame == 0 { value = channel == 0 ? -8388608 : 8388607 }
                        else if frame == 1 { value = channel == 0 ? 0 : -1 }
                        else if frame == frameCount - 1 { value = channel == 0 ? 1 : -8388607 }
                        else { value = Int32((frame * (channel == 0 ? 7919 : 104729) + 17 + channel * 12345) & 0xffffff) - 8388608 }
                        let bits = UInt32(bitPattern: value), offset = 44 + (frame * 2 + channel) * 3
                        bytes[offset] = UInt8(truncatingIfNeeded: bits)
                        bytes[offset + 1] = UInt8(truncatingIfNeeded: bits >> 8)
                        bytes[offset + 2] = UInt8(truncatingIfNeeded: bits >> 16)
                    }
                }
            }
            let selected = temporary.appendingPathComponent("Synthetic seek markers.wav")
            try pcm.write(to: selected)
            let project = try ProjectStore.attachCPRAudioMedia(from: selected, to: event.id, in: imported.project, at: package)
            try ProjectStore.save(project, to: package)
            let attachment = try #require(project.cprMediaAttachments.first)
            return Fixture(temporary: temporary, package: package, project: project, eventID: event.id,
                media: try ProjectStore.resolveMediaURL(attachment.mediaPath, projectRoot: package), pcm: pcm)
        } catch {
            try? FileManager.default.removeItem(at: temporary)
            throw error
        }
    }

    private func snapshot(_ root: URL) throws -> [String: Data] {
        let files = try #require(FileManager.default.enumerator(at: root, includingPropertiesForKeys: [.isRegularFileKey]))
        var result: [String: Data] = [:]
        for case let url as URL in files where try url.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile == true {
            result[String(url.path.dropFirst(root.path.count + 1))] = try Data(contentsOf: url)
        }
        return result
    }

    /// Integer-only binary32 encoding of signed24 / 2^23, independent of the C
    /// converter, AVAudioFile, Float arithmetic and the prepared output.
    private func expectedBits(_ pcm: Data) -> [UInt32] {
        pcm.withUnsafeBytes { raw in
            let bytes = raw.bindMemory(to: UInt8.self)
            return (0..<frameCount * 2).map { index in
                let offset = 44 + index * 3
                let packed = UInt32(bytes[offset]) | UInt32(bytes[offset + 1]) << 8 | UInt32(bytes[offset + 2]) << 16
                let value = Int32(packed & 0x7fffff) - Int32(packed & 0x800000)
                guard value != 0 else { return 0 }
                let magnitude = UInt32(value < 0 ? -value : value)
                let top = 31 - magnitude.leadingZeroBitCount
                let exponent = UInt32(top - 23 + 127)
                return (value < 0 ? UInt32(0x80000000) : 0) | exponent << 23
                    | ((magnitude << (23 - top)) & 0x7fffff)
            }
        }
    }

    private func matches(_ buffer: AVAudioPCMBuffer, expected: [UInt32], from first: Int) -> Bool {
        guard buffer.format.channelCount == 2, !buffer.format.isInterleaved,
              let data = buffer.floatChannelData, first + Int(buffer.frameLength) <= frameCount else { return false }
        for frame in 0..<Int(buffer.frameLength) {
            for channel in 0..<2 where data[channel][frame].bitPattern != expected[(first + frame) * 2 + channel] { return false }
        }
        return true
    }

    private func rejects(_ body: () throws -> Void) -> Bool {
        do { try body(); return false } catch { return true }
    }

    @Test func SourceRateAndExactPCMBypassProjectMixerWithoutPromotingTheEvent() throws {
        let f = try fixture(); defer { try? FileManager.default.removeItem(at: f.temporary) }
        let before = try snapshot(f.package)
        var project = f.project
        #expect(project.sampleRate == 48000 && project.duration == 0)
        project.tracks[0].gainDB = 24; project.tracks[0].pan = 1
        project.tracks[0].isMuted = true; project.tracks[0].isSolo = true
        project.tracks[0].automation = [
            AutomationLane(parameter: .gainDB, points: [AutomationPoint(time: 0, value: -96)]),
            AutomationLane(parameter: .pan, points: [AutomationPoint(time: 0, value: -1)])]
        let unchanged = project
        let prepared = try CPRSourceEventPlayback.prepare(eventID: f.eventID, project: project, root: f.package)
        #expect(prepared.info.eventID == f.eventID && prepared.info.sampleRate == rate)
        #expect(prepared.info.frameCount == Int64(frameCount) && prepared.info.duration == 24)
        #expect(prepared.info.sourceSHA256 == project.unresolvedAudioEvents[0].sourceSHA256)
        #expect(prepared.info.mediaSHA256 == cprSHA256(f.pcm))
        #expect(prepared.audio.format.sampleRate == rate && prepared.audio.frameCount == Int64(frameCount))
        #expect(prepared.audio.clips.count == 1 && prepared.audio.clips[0].startFrame == 0)
        #expect(matches(prepared.audio.clips[0].buffer, expected: expectedBits(f.pcm), from: 0))
        #expect(project == unchanged && project.tracks.flatMap(\.clips).isEmpty)
        #expect(rejects { try project.requireResolvedAudioEvents() })
        #expect(rejects { _ = try OfflineRenderer.render(project: project, projectRoot: f.package) })
        let output = f.temporary.appendingPathComponent("Existing.wav"), sentinel = Data("preserve destination".utf8)
        try sentinel.write(to: output)
        #expect(rejects { _ = try OfflineRenderer.export(project: project, projectRoot: f.package, to: output) })
        #expect(try Data(contentsOf: output) == sentinel)
        let exchange = f.temporary.appendingPathComponent("Blocked.dawproject")
        #expect(rejects { try DAWProject.export(project: project, projectRoot: f.package, to: exchange) })
        #expect(!FileManager.default.fileExists(atPath: exchange.path))
        #expect(try snapshot(f.package) == before)
    }

    @Test func EveryCopiedSeekSampleMatchesIndependentPCM24Oracle() throws {
        let f = try fixture(); defer { try? FileManager.default.removeItem(at: f.temporary) }
        let prepared = try CPRSourceEventPlayback.prepare(eventID: f.eventID, project: f.project, root: f.package).audio
        let expected = expectedBits(f.pcm)
        #expect(prepared.nativeEventSelection != nil)
        #expect(Array(expected.prefix(4)) == [0xbf800000, 0x3f7ffffe, 0, 0xb4000000])
        for first in [0, 1, 8191, 8192, 9999, 10000, 10001, frameCount - 2, frameCount - 1] {
            let schedule = try AudioPlaybackSchedule.make(prepared, from: Double(first) / rate)
            #expect(schedule.startFrame == Int64(first) && schedule.spans.count == 1)
            let span = try #require(schedule.spans.first)
            #expect(span.clipIndex == 0 && span.sourceOffset == first)
            #expect(span.frameCount == frameCount - first && span.delayFrames == 0)
            let copied = try AudioPlaybackSchedule.buffer(for: span, in: prepared)
            #expect(copied.frameLength == AVAudioFrameCount(frameCount - first) && copied.format.sampleRate == rate)
            #expect(matches(copied, expected: expected, from: first))
            if first > 0 {
                #expect(copied !== prepared.clips[0].buffer)
                copied.floatChannelData![0][0] = 123
                #expect(prepared.clips[0].buffer.floatChannelData![0][first].bitPattern == expected[first * 2])
            }
        }
        // Exercise the recovered inclusive-end selector and the application's
        // half-open PCM interval together on actual prepared native-event data.
        // Selecting the segment at its end must never schedule one extra frame.
        for seconds in [Double(24), Double(24).nextUp, Double.greatestFiniteMagnitude] {
            let end = try AudioPlaybackSchedule.make(prepared, from: seconds)
            #expect(end.startFrame == 1_058_400 && end.spans.isEmpty)
        }
    }

    @Test func SchedulingClampsBeforeConversionAndDefinesHalfOpenEndpoints() throws {
        let format = try #require(AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: rate, channels: 2, interleaved: false))
        let buffer = try AudioPreparation.buffer(format: format, frames: 4)
        let prepared = PreparedProject(format: format, frameCount: 9,
            clips: [PreparedClip(startFrame: 0, buffer: buffer), PreparedClip(startFrame: 5, buffer: buffer)])
        let half = 0.5 / rate
        for (seconds, expected) in [(0.0, 0), (-0.0, 0), (half.nextDown, 0), (half, 1), (half.nextUp, 1)] {
            #expect(try AudioPlaybackSchedule.make(prepared, from: seconds).startFrame == Int64(expected))
        }
        let gap = try AudioPlaybackSchedule.make(prepared, from: 4 / rate)
        #expect(gap.spans == [AudioPlaybackSchedule.Span(clipIndex: 1, sourceOffset: 0, frameCount: 4, delayFrames: 1)])
        let last = try AudioPlaybackSchedule.make(prepared, from: 8 / rate)
        #expect(last.spans == [AudioPlaybackSchedule.Span(clipIndex: 1, sourceOffset: 3, frameCount: 1, delayFrames: 0)])
        for seconds in [9 / rate, 24, Double.greatestFiniteMagnitude] {
            let end = try AudioPlaybackSchedule.make(prepared, from: seconds)
            #expect(end.startFrame == 9 && end.spans.isEmpty)
        }
        for seconds in [Double.nan, Double.infinity, -Double.infinity, -1, -Double.leastNonzeroMagnitude] {
            #expect(throws: RebaseCoreError.self) { try AudioPlaybackSchedule.make(prepared, from: seconds) }
        }
    }

    @Test func FreshPreparationRejectsChangedMediaSourceAndReportButPreservesSnapshot() throws {
        let f = try fixture(); defer { try? FileManager.default.removeItem(at: f.temporary) }
        let before = try snapshot(f.package)
        let accepted = try CPRSourceEventPlayback.prepare(eventID: f.eventID, project: f.project, root: f.package)
        let expected = expectedBits(f.pcm)
        for path in [f.media, f.package.appendingPathComponent(CPRProject.originalRelativePath),
                     f.package.appendingPathComponent(CPRProject.reportRelativePath)] {
            let original = try Data(contentsOf: path)
            let attributes = try FileManager.default.attributesOfItem(atPath: path.path)
            var changed = original
            changed[path == f.media ? 44 : changed.count - 1] ^= 1
            try changed.write(to: path)
            if let date = attributes[.modificationDate] { try FileManager.default.setAttributes([.modificationDate: date], ofItemAtPath: path.path) }
            #expect(rejects { _ = try CPRSourceEventPlayback.prepare(eventID: f.eventID, project: f.project, root: f.package) })
            #expect(matches(accepted.audio.clips[0].buffer, expected: expected, from: 0))
            try original.write(to: path)
            let recovered = try CPRSourceEventPlayback.prepare(eventID: f.eventID, project: f.project, root: f.package)
            #expect(recovered.info == accepted.info)
        }
        #expect(try snapshot(f.package) == before)
    }

    @Test func ChangedRetainedIdentityPlacementAndSelectionCannotReuseAdmission() throws {
        let f = try fixture(); defer { try? FileManager.default.removeItem(at: f.temporary) }
        let before = try snapshot(f.package)
        _ = try CPRSourceEventPlayback.prepare(eventID: f.eventID, project: f.project, root: f.package)
        #expect(rejects { _ = try CPRSourceEventPlayback.prepare(eventID: UUID(), project: f.project, root: f.package) })
        var removed = f.project
        removed.tracks[0].unresolvedAudioEvents.removeAll(); removed.removeUnusedCPRMediaAttachments()
        #expect(rejects { _ = try CPRSourceEventPlayback.prepare(eventID: f.eventID, project: removed, root: f.package) })
        var moved = f.project; moved.tracks[0].id = UUID()
        #expect(rejects { _ = try CPRSourceEventPlayback.prepare(eventID: f.eventID, project: moved, root: f.package) })
        for key in ["duration", "position"] {
            var encoded = try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(f.project)) as? [String: Any])
            var tracks = try #require(encoded["tracks"] as? [[String: Any]])
            var events = try #require(tracks[0]["unresolvedAudioEvents"] as? [[String: Any]])
            var placement = try #require(events[0]["placement"] as? [String: Any])
            placement[key] = key == "duration" ? 25.0 : 1.0
            events[0]["placement"] = placement; tracks[0]["unresolvedAudioEvents"] = events; encoded["tracks"] = tracks
            let changed = try JSONDecoder().decode(Project.self, from: JSONSerialization.data(withJSONObject: encoded))
            #expect(rejects { _ = try CPRSourceEventPlayback.prepare(eventID: f.eventID, project: changed, root: f.package) })
        }
        #expect(try snapshot(f.package) == before)
    }

    @Test func AVAudioEngineOfflineUnityRoutePreservesThePreparedFinalFrames() throws {
        let f = try fixture(); defer { try? FileManager.default.removeItem(at: f.temporary) }
        let prepared = try CPRSourceEventPlayback.prepare(eventID: f.eventID, project: f.project, root: f.package).audio
        let first = frameCount - 257, expected = expectedBits(f.pcm)
        let schedule = try AudioPlaybackSchedule.make(prepared, from: Double(first) / rate)
        let slice = try AudioPlaybackSchedule.buffer(for: #require(schedule.spans.first), in: prepared)
        let engine = AVAudioEngine(), player = AVAudioPlayerNode()
        engine.attach(player); engine.connect(player, to: engine.mainMixerNode, format: prepared.format)
        player.volume = 1; engine.mainMixerNode.outputVolume = 1
        try engine.enableManualRenderingMode(.offline, format: prepared.format, maximumFrameCount: 256)
        defer { player.stop(); engine.stop(); engine.disableManualRenderingMode() }
        player.scheduleBuffer(slice, at: nil, options: [])
        try engine.start(); player.play()
        let output = try AudioPreparation.buffer(format: engine.manualRenderingFormat, frames: 256)
        var position = 0, retries = 0
        while position < 257 {
            let request = AVAudioFrameCount(min(256, 257 - position))
            let status = try engine.renderOffline(request, to: output)
            if status == .cannotDoInCurrentContext && retries < 16 { retries += 1; continue }
            #expect(status == .success)
            guard status == .success else { return }
            #expect(output.frameLength == request && output.format.sampleRate == rate)
            #expect(matches(output, expected: expected, from: first + position))
            position += Int(output.frameLength)
            guard output.frameLength > 0 else { return }
        }
        #expect(position == 257)
    }
}
