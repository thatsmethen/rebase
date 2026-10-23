import AVFoundation
import Foundation
import Testing
@testable import RebaseCore

/// Forward-authored graphs test import, source proof and exact PCM composition.
/// Minimal ancillary objects are not native-valid or reference-generated CPRs.
struct CPRSourceTrackOverlapPlaybackTests {
    private let workspace = PrivateResearchFixtures.root
    private var controls: URL { workspace.appendingPathComponent("evidence/application/APP021/overlap-controls-01") }
    private let pins = [
        "equal-crossing": "e2d178848dddc7de95a94c74ca6ad75861bfee760f299a4144af099b594524bf",
        "nested-tail": "4a920c2593392db3b660ea040960eac2ea0b7602d76e7a4fcd04cc65a4d49620",
        "covered-anchor": "2e6db952d129270a179e722c1a5b3d20ed2332c763801c0ce7ff27702ed11255",
        "same-start-ties": "5fa8989adac3105da97519cd10ece5ba5e5a447a9c518cf68e13538ef2989533",
        "signed-earlier-wins": "eef15826335a29280e894688b6252f5fa93862491a7d43b5da176522ee59ab85",
        "signed-later-wins": "4e9b08f918fad105814782a82abbf8a379b591b67041bd46cf7b49c9b919a633",
        "repeated-splits": "b07f5f528e1ed61a9bfb0726c6fcab6f40cf35cfdf127fd2a8249b6b79377ae4",
        "saved32k-original-offset": "4b3037f7084ed3769732523baab3e28e89af3f8d6107fafc990d2a3a7f0132fd",
        "covered-capacity": "fdbae1fb220eca34135aa1ddc4981dd82f65b2fc4804c555d8b69ed1f7728249",
        "reversed-starts": "22a2ace9242a427548ebd036c093c3a981278ca1f744214c86ab9e00add3ba01"
    ]
    private let mediaPins = [
        "0f22730ee27f5803ceefdefe014fa72b0220d2aee98d223873ae8e64c6c30f07",
        "6eada8973e183f835b98413e28d60f729eaa95894b7476e3abb927ca8b915b78",
        "8a1b8380379bb10b42bcccdaee3443f15d31bd29a6ba20916c9cfa6bde176d30",
        "fec09bb1db54441dede767947fbd7fb175a13f921724d434d97fa6c844c52342"
    ]

    private struct Window {
        let ordinal: Int
        let start: Int64
        let end: Int64
        let source: Int64
    }
    private func temporary() throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }
    private func imported(_ name: String, at directory: URL) throws -> (Project, URL, UUID) {
        let bytes = try Data(contentsOf: controls.appendingPathComponent(name + ".cpr"))
        #expect(cprSHA256(bytes) == pins[name])
        let source = directory.appendingPathComponent("Overlap.cpr")
        let package = directory.appendingPathComponent("Overlap.rebaseproj")
        try bytes.write(to: source)
        var project = try CPRProject.importProject(from: source, to: package, allowPartial: true).project
        let events = project.unresolvedAudioEvents
        let anchor = try #require(events.first?.id)
        for (ordinal, event) in events.enumerated() {
            let media = controls.appendingPathComponent("Overlap Signal \(ordinal).wav")
            #expect(cprSHA256(try Data(contentsOf: media)) == mediaPins[ordinal])
            project = try ProjectStore.attachCPRAudioMedia(from: media, to: event.id, in: project, at: package)
        }
        try ProjectStore.save(project, to: package)
        return (project, package, anchor)
    }
    private func snapshot(_ root: URL) throws -> [String: String] {
        let names = try #require(FileManager.default.enumerator(atPath: root.path)?.allObjects as? [String])
        var result: [String: String] = [:]
        for name in names {
            let file = root.appendingPathComponent(name)
            if try file.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile == true {
                result[name] = cprSHA256(try Data(contentsOf: file))
            }
        }
        return result
    }
    private func rejects(_ work: () throws -> Void) -> Bool {
        do { try work(); return false } catch { return true }
    }
    private func sample(_ frame: Int64, _ channel: Int, _ ordinal: Int) -> UInt32 {
        let raw = ((frame * (channel == 0 ? 7919 : 104729)
            + Int64(channel * 12345 + ordinal * 131071)) & 0xfffff) - 524288
        return (Float(raw) / 8_388_608).bitPattern
    }
    private func check(_ buffer: AVAudioPCMBuffer, at first: Int64, windows: [Window]) {
        var equal = true
        for index in 0..<Int(buffer.frameLength) {
            let position = first + Int64(index)
            let window = windows.first { $0.start <= position && position < $0.end }
            for channel in 0..<2 {
                let expected = window.map { sample($0.source + position - $0.start, channel, $0.ordinal) } ?? Float(0).bitPattern
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
        let seeks = Set([Int64(0), stream.frameCount]
            + windows.flatMap { [$0.start - 1, $0.start, $0.end - 1, $0.end] })
        for seek in seeks where seek >= 0 && seek <= stream.frameCount {
            let cursor = try stream.cursor(from: seek)
            if let buffer = try cursor.nextBuffer(maximumFrames: 8192) { check(buffer, at: seek, windows: windows) }
            else { #expect(seek == stream.frameCount) }
        }
    }
    private func checkCase(_ name: String, windows: [Window], priorities: [Int32]) throws {
        let directory = try temporary(); defer { try? FileManager.default.removeItem(at: directory) }
        let (project, package, anchor) = try imported(name, at: directory)
        let before = try snapshot(package)
        let prepared = try CPRSourceEventPlayback.prepare(eventID: anchor, project: project,
            root: package, mode: .nativeTrackSavedProjectClock)
        let track = try #require(prepared.info.sourceTrack)
        #expect(track.contract == "cpr-15.0.30.287-priority-track-fresh-root-mode0-v1")
        #expect(track.freshRootMode == 0 && track.events.count == priorities.count)
        #expect(track.events.map(\.priority) == priorities)
        #expect(track.events.map(\.sourceOrdinal) == Array(priorities.indices))
        #expect(track.fragments.map(\.sourceOrdinal) == windows.map(\.ordinal))
        #expect(track.snappedEmptyFragmentCount == 0)
        #expect(Set(track.events.map(\.eventID)) == Set(project.unresolvedAudioEvents.map(\.id)))
        #expect(track.events.enumerated().allSatisfy { $0.element.mediaSHA256 == mediaPins[$0.offset] })
        #expect(prepared.info.eventID == anchor && prepared.info.auditionScope == "Source track")
        for event in track.events where event.priority != 1 {
            for mode in [CPRSourceEventPlaybackMode.nativeTimelineSourceRate,
                         .nativeTimelineProjectClock, .nativeTimelineSavedProjectClock] {
                do {
                    _ = try CPRSourceEventPlayback.prepare(eventID: event.eventID,
                        project: project, root: package, mode: mode)
                    Issue.record("Nondefault priority escaped the complete-track normalization context")
                } catch RebaseCoreError.unsupportedAudio(let reason) {
                    #expect(reason.contains("event-priority"))
                }
            }
        }
        let inspection = try CPRSourceAudioInspection.inspect(eventID: anchor, in: project, at: package)
        #expect(inspection.nativeTrackPlaybackUnavailableReason == nil && inspection.nativeTrackEventCount == priorities.count)
        let stream = try #require(prepared.audio.nativeTimelineStream)
        try checkStream(stream, windows: windows)
        #expect(rejects { try project.requireResolvedAudioEvents() })
        #expect(try snapshot(package) == before)
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason)) func equalPriorityCrossingSwitchesToTheLaterContributor() throws {
        try checkCase("equal-crossing", windows: [
            Window(ordinal: 0, start: 66150, end: 198450, source: 88200),
            Window(ordinal: 1, start: 198450, end: 418950, source: 396900)], priorities: [1, 1])
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason)) func nestedWinnerSplitsTheOriginalAndRestoresItsSourceTail() throws {
        try checkCase("nested-tail", windows: [
            Window(ordinal: 0, start: 44100, end: 132300, source: 88200),
            Window(ordinal: 1, start: 132300, end: 220500, source: 529200),
            Window(ordinal: 0, start: 220500, end: 485100, source: 264600)], priorities: [1, 2])
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason)) func coveredAnchorAndSameStartTiesRetainAllOriginalContributors() throws {
        try checkCase("covered-anchor", windows: [
            Window(ordinal: 1, start: 44100, end: 220500, source: 396900)], priorities: [1, 1])
        try checkCase("same-start-ties", windows: [
            Window(ordinal: 2, start: 44100, end: 220500, source: 396900)], priorities: [1, 1, 1])
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason)) func signedPriorityExtremesControlBothOverlapDirections() throws {
        try checkCase("signed-earlier-wins", windows: [
            Window(ordinal: 0, start: 44100, end: 308700, source: 88200),
            Window(ordinal: 1, start: 308700, end: 396900, source: 573300)], priorities: [.max, .min])
        try checkCase("signed-later-wins", windows: [
            Window(ordinal: 0, start: 44100, end: 132300, source: 88200),
            Window(ordinal: 1, start: 132300, end: 396900, source: 396900)], priorities: [.min, .max])
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason)) func repeatedSplitsKeepEachFragmentAttachedToItsOriginalSource() throws {
        try checkCase("repeated-splits", windows: [
            Window(ordinal: 0, start: 44100, end: 132300, source: 44100),
            Window(ordinal: 1, start: 132300, end: 176400, source: 176400),
            Window(ordinal: 0, start: 176400, end: 264600, source: 176400),
            Window(ordinal: 2, start: 264600, end: 352800, source: 396900),
            Window(ordinal: 0, start: 352800, end: 441000, source: 352800),
            Window(ordinal: 3, start: 441000, end: 485100, source: 661500),
            Window(ordinal: 0, start: 485100, end: 573300, source: 485100)], priorities: [0, 1, 2, 3])
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason)) func saved32kSplitProjectsTheOriginalOffsetBeforeReaderQuantization() throws {
        let directory = try temporary(); defer { try? FileManager.default.removeItem(at: directory) }
        let (project, package, anchor) = try imported("saved32k-original-offset", at: directory)
        let before = try snapshot(package)
        var edited = project
        edited.sampleRate = 48000
        edited.tempoMap = TempoMap(events: [TempoEvent(beat: 0, bpm: 37)])
        let prepared = try CPRSourceTrackPlayback.prepare(eventID: anchor, project: edited, root: package)
        #expect(try prepared.setup.supportedSampleRate() == 32000)
        #expect(prepared.track.events.allSatisfy { $0.sourceSampleRate == 44100 })
        #expect(prepared.track.fragments.map(\.sourceOrdinal) == [0, 1, 0])
        // Trimming the already snapped original offset would incorrectly seek39.
        // Fresh projection from original start1/960 and offset1/44100 seeks38.
        let stream = try #require(prepared.audio.nativeTimelineStream)
        try checkStream(stream, windows: [
            Window(ordinal: 0, start: 33, end: 67, source: 1),
            Window(ordinal: 1, start: 67, end: 71, source: 32000),
            Window(ordinal: 0, start: 71, end: 32033, source: 38)])
        #expect(try snapshot(package) == before)
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason)) func coveredContributorStillRequiresMembershipAttachmentAndExactMediaBytes() throws {
        let directory = try temporary(); defer { try? FileManager.default.removeItem(at: directory) }
        let (project, package, anchor) = try imported("covered-anchor", at: directory)
        let before = try snapshot(package)
        let covered = try #require(project.unresolvedAudioEvents.first)
        let winner = try #require(project.unresolvedAudioEvents.last)
        #expect(covered.id == anchor && winner.id != anchor)
        let coveredAttachment = try #require(project.attachedMedia(for: covered))
        let winnerAttachment = try #require(project.attachedMedia(for: winner))
        #expect(coveredAttachment.mediaPath != winnerAttachment.mediaPath)
        #expect(coveredAttachment.mediaSHA256 != winnerAttachment.mediaSHA256)
        var detached = project
        detached.cprMediaAttachments.removeAll { $0.id == coveredAttachment.id }
        #expect(rejects { _ = try CPRSourceTrackPlayback.prepare(eventID: winner.id, project: detached, root: package) })
        var removed = project
        let index = try #require(removed.tracks.firstIndex { $0.unresolvedAudioEvents.contains { $0.id == covered.id } })
        removed.tracks[index].unresolvedAudioEvents.removeAll { $0.id == covered.id }
        removed.removeUnusedCPRMediaAttachments()
        #expect(rejects { _ = try CPRSourceTrackPlayback.prepare(eventID: winner.id, project: removed, root: package) })
        let media = try ProjectStore.resolveMediaURL(coveredAttachment.mediaPath, projectRoot: package)
        let original = try Data(contentsOf: media)
        var changed = original; changed[changed.count - 1] ^= 1
        try changed.write(to: media)
        #expect(rejects { _ = try CPRSourceTrackPlayback.prepare(eventID: winner.id, project: project, root: package) })
        try original.write(to: media)
        #expect(try snapshot(package) == before)
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason)) func coveredInvalidSourceCapacityAndReversedOrderStillRejectTheWholeTrack() throws {
        for name in ["covered-capacity", "reversed-starts"] {
            let directory = try temporary(); defer { try? FileManager.default.removeItem(at: directory) }
            let (project, package, _) = try imported(name, at: directory)
            let before = try snapshot(package)
            let winner = try #require(project.unresolvedAudioEvents.last?.id)
            #expect(rejects { _ = try CPRSourceTrackPlayback.prepare(eventID: winner, project: project, root: package) })
            #expect(try snapshot(package) == before)
        }
    }
}
