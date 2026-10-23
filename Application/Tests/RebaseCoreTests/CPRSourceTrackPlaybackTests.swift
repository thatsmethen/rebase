import AVFoundation
import Foundation
import Testing
@testable import RebaseCore

/// Forward-authored parser graphs and exact integer PCM controls. Their opaque
/// ancillary bodies are scaffolding, not native-valid or Reference-generated CPRs.
struct CPRSourceTrackPlaybackTests {
    private let workspace = PrivateResearchFixtures.root
    private var controls: URL { workspace.appendingPathComponent("evidence/application/APP020/track-controls-01") }
    private let pins = [
        "two-events": "bad521c4fcf152c745312495b2e967355ae8b474f142377e8d86b4bfb0a998c3",
        "three-events": "045a18e1185ec174e060058658537aab4d1c0dc603dcfa347b3a520c7deb278c",
        "unknown-child": "c952fb147ffdfe1205378118f75735620350578e342b3f4af4d76f55e34d74a6",
        "reverse-order": "e2f282a2a818209181f4d38c89321adf80c39fa493529f9a9ecbc271526cc53f",
        "overlap": "1a1e2c82825f23adc54b254b0a28ae2065e723a52d147ea6b61ce786d30290d2",
        "touching": "fcfb26c05e7ef8505545e674b3bbd32b2dbb1d1098e025736de7d14703d5bf7d",
        "missing-counted-event": "213b824d23659bccd7e150837fba8f9fbaa0492d6b0111c8488aa1c87b05d9cc"
    ]
    private func bytes(_ name: String) throws -> Data {
        let bytes = try Data(contentsOf: controls.appendingPathComponent(name + ".cpr"))
        #expect(cprSHA256(bytes) == pins[name])
        return bytes
    }
    private func rejects(_ body: () throws -> Void) -> Bool {
        do { try body(); return false } catch { return true }
    }
    private func temporary() throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }
    private func imported(_ bytes: Data, at directory: URL) throws -> (Project, URL, UUID) {
        let source = directory.appendingPathComponent("Control.cpr")
        let package = directory.appendingPathComponent("Control.rebaseproj")
        try bytes.write(to: source)
        let result = try CPRProject.importProject(from: source, to: package, allowPartial: true)
        var project = result.project
        let anchor = try #require(project.unresolvedAudioEvents.first?.id)
        let media = controls.appendingPathComponent("Symbolic Track Signal.wav")
        #expect(cprSHA256(try Data(contentsOf: media)) == "0f22730ee27f5803ceefdefe014fa72b0220d2aee98d223873ae8e64c6c30f07")
        project = try ProjectStore.attachCPRAudioMedia(from: media, to: anchor, in: project, at: package)
        try ProjectStore.save(project, to: package)
        return (project, package, anchor)
    }
    private func snapshot(_ root: URL) throws -> [String: String] {
        let names = try #require(FileManager.default.enumerator(atPath: root.path)?.allObjects as? [String])
        var result: [String: String] = [:]
        for name in names {
            let url = root.appendingPathComponent(name)
            if try url.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile == true {
                result[name] = cprSHA256(try Data(contentsOf: url))
            }
        }
        return result
    }
    private struct Window {
        let start: Int64
        let end: Int64
        let source: Int64
    }
    private func sample(_ frame: Int64, _ channel: Int) -> UInt32 {
        let value = ((frame * (channel == 0 ? 7919 : 104729) + Int64(channel * 12345)) & 0xfffff) - 524288
        return (Float(value) / 8_388_608).bitPattern
    }
    private func check(_ buffer: AVAudioPCMBuffer, at first: Int64, windows: [Window]) {
        var equal = true
        for index in 0..<Int(buffer.frameLength) {
            let position = first + Int64(index)
            let window = windows.first { $0.start <= position && position < $0.end }
            for channel in 0..<2 {
                let expected = window.map { sample($0.source + position - $0.start, channel) } ?? Float(0).bitPattern
                if buffer.floatChannelData![channel][index].bitPattern != expected { equal = false }
            }
        }
        #expect(equal)
    }
    private func checkStream(_ stream: CPRNativeTimelineStream, windows: [Window]) throws {
        #expect(stream.frameCount == windows.last?.end)
        let cursor = try stream.cursor(from: 0)
        let partitions = [1, 257, 4096, 3, 65536]
        var position: Int64 = 0, block = 0
        while let buffer = try cursor.nextBuffer(maximumFrames: partitions[block % partitions.count]) {
            check(buffer, at: position, windows: windows)
            position += Int64(buffer.frameLength); block += 1
        }
        #expect(position == stream.frameCount && cursor.isAtEnd)
        let seeks = Set([Int64(0), stream.frameCount] + windows.flatMap { [$0.start - 1, $0.start, $0.end - 1, $0.end] })
        for seek in seeks where seek >= 0 && seek <= stream.frameCount {
            let cursor = try stream.cursor(from: seek)
            if let buffer = try cursor.nextBuffer(maximumFrames: 8192) { check(buffer, at: seek, windows: windows) }
            else { #expect(seek == stream.frameCount) }
        }
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason)) func completeTwoAndThreeEventTracksKeepExactPCMThroughGapsAndSeeks() throws {
        for count in [2, 3] {
            let directory = try temporary(); defer { try? FileManager.default.removeItem(at: directory) }
            let (project, package, anchor) = try imported(bytes(count == 2 ? "two-events" : "three-events"), at: directory)
            let before = try snapshot(package)
            #expect(project.unresolvedAudioEvents.count == count && project.tracks.flatMap(\.clips).isEmpty)
            let prepared = try CPRSourceEventPlayback.prepare(eventID: anchor, project: project,
                root: package, mode: .nativeTrackSavedProjectClock)
            let track = try #require(prepared.info.sourceTrack)
            #expect(track.events.count == count)
            #expect(track.contract == "cpr-15.0.30.287-priority-track-fresh-root-mode0-v1" && track.freshRootMode == 0)
            #expect(prepared.info.eventID == anchor && prepared.info.auditionScope == "Source track")
            #expect(prepared.info.sampleRate == 44100 && prepared.info.savedProjectAudioSetup != nil)
            #expect(track.events.map(\.sourceOrdinal) == Array(0..<count))
            #expect(Set(track.events.map(\.eventID)) == Set(project.unresolvedAudioEvents.map(\.id)))
            #expect(track.events.allSatisfy { $0.mediaSHA256 == "0f22730ee27f5803ceefdefe014fa72b0220d2aee98d223873ae8e64c6c30f07" })
            let inspection = try CPRSourceAudioInspection.inspect(eventID: anchor, in: project, at: package)
            #expect(inspection.nativeTrackPlaybackUnavailableReason == nil && inspection.nativeTrackEventCount == count)
            #expect(prepared.audio.clips.isEmpty && prepared.audio.sourceEventStream == nil)
            let all = [Window(start: 66150, end: 242550, source: 88200),
                Window(start: 352800, end: 573300, source: 396900),
                Window(start: 705600, end: 793800, source: 793800)]
            let stream = try #require(prepared.audio.nativeTimelineStream)
            try checkStream(stream, windows: Array(all.prefix(count)))
            #expect(rejects { try project.requireResolvedAudioEvents() })
            #expect(try snapshot(package) == before)
        }
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason)) func unknownMissingOrReversedContributorsCannotBecomePartialTrackPlayback() throws {
        for name in ["unknown-child", "reverse-order"] {
            let directory = try temporary(); defer { try? FileManager.default.removeItem(at: directory) }
            let (project, package, anchor) = try imported(bytes(name), at: directory)
            let before = try snapshot(package)
            #expect(rejects { _ = try CPRSourceTrackPlayback.prepare(eventID: anchor, project: project, root: package) })
            let inspection = try CPRSourceAudioInspection.inspect(eventID: anchor, in: project, at: package)
            #expect(inspection.nativeTrackPlaybackUnavailableReason != nil && inspection.nativeTrackEventCount == nil)
            // The deliberately narrower selected-event operation is unchanged.
            #expect(try CPRSourceEventPlayback.prepare(eventID: anchor, project: project, root: package,
                mode: .nativeTimelineSavedProjectClock).info.eventID == anchor)
            #expect(try snapshot(package) == before)
        }
        let missing = try CPRProject.readContainer(bytes("missing-counted-event"))
        #expect(rejects { _ = try CPRTrackContributorArchive.read(container: missing) })
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason)) func touchingEventsHaveSeparateSourceAccessorsAtTheExactBoundary() throws {
        let directory = try temporary(); defer { try? FileManager.default.removeItem(at: directory) }
        let (project, package, anchor) = try imported(bytes("touching"), at: directory)
        let prepared = try CPRSourceTrackPlayback.prepare(eventID: anchor, project: project, root: package)
        let stream = try #require(prepared.audio.nativeTimelineStream)
        try checkStream(stream, windows: [
            Window(start: 66150, end: 242550, source: 88200),
            Window(start: 242550, end: 463050, source: 396900)])
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason)) func completeTrackUsesSavedClockAndRawSourceFramesDespiteApplicationEdits() throws {
        let directory = try temporary(); defer { try? FileManager.default.removeItem(at: directory) }
        let source = try Data(contentsOf: workspace.appendingPathComponent(
            "evidence/application/APP020/track-controls-saved32k/two-events-saved32k.cpr"))
        #expect(cprSHA256(source) == "bc74b4fbcfbce1bdacd9f26df1bffd734268140cc1bfcd07200ceb097121669b")
        let (project, package, anchor) = try imported(source, at: directory)
        let before = try snapshot(package)
        #expect(project.sampleRate == 32000)
        var edited = project
        edited.sampleRate = 48000
        edited.tempoMap = TempoMap(events: [TempoEvent(beat: 0, bpm: 37)])
        let prepared = try CPRSourceTrackPlayback.prepare(eventID: anchor, project: edited, root: package)
        #expect(try prepared.setup.supportedSampleRate() == 32000)
        #expect(prepared.audio.format.sampleRate == 32000)
        #expect(prepared.track.events.allSatisfy { $0.sourceSampleRate == 44100 })
        let stream = try #require(prepared.audio.nativeTimelineStream)
        try checkStream(stream, windows: [Window(start: 48000, end: 176000, source: 64000),
            Window(start: 256000, end: 416000, source: 288000)])
        #expect(try snapshot(package) == before)
        #expect(rejects { try edited.requireResolvedAudioEvents() })
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason)) func retainedDeletionMissingAttachmentAndChangedMediaAreRecheckedForTheWholeTrack() throws {
        let directory = try temporary(); defer { try? FileManager.default.removeItem(at: directory) }
        let (project, package, anchor) = try imported(bytes("two-events"), at: directory)
        let before = try snapshot(package)
        var removed = project
        let index = try #require(removed.tracks.firstIndex { $0.unresolvedAudioEvents.contains { $0.id == anchor } })
        removed.tracks[index].unresolvedAudioEvents.removeLast()
        #expect(try CPRSourceEventPlayback.prepare(eventID: anchor, project: removed, root: package,
            mode: .nativeTimelineSavedProjectClock).info.eventID == anchor)
        #expect(rejects { _ = try CPRSourceTrackPlayback.prepare(eventID: anchor, project: removed, root: package) })
        var detached = project; detached.cprMediaAttachments.removeAll()
        #expect(rejects { _ = try CPRSourceTrackPlayback.prepare(eventID: anchor, project: detached, root: package) })
        let attachment = try #require(project.cprMediaAttachments.first)
        let media = try ProjectStore.resolveMediaURL(attachment.mediaPath, projectRoot: package)
        let original = try Data(contentsOf: media)
        var changed = original; changed[changed.count - 1] ^= 1
        try changed.write(to: media)
        #expect(rejects { _ = try CPRSourceTrackPlayback.prepare(eventID: anchor, project: project, root: package) })
        try original.write(to: media)
        #expect(try snapshot(package) == before)
    }
}
