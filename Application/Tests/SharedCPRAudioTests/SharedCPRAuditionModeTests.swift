import Foundation
import Testing
#if canImport(RebaseCore)
@testable import RebaseCore
#else
@testable import RebasePortable
#endif

/// Forward-authored CPR/media controls. No proprietary project, library or
/// runtime output supplies the expected samples or admission decisions.
struct SharedCPRAuditionModeTests {
    private func workspace(_ body: (URL) throws -> Void) throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("SharedAuditionModes-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try body(root)
    }
    private func rendered(_ prepared: CPRSourceAudition.Prepared, from frame: Int64 = 0) throws -> [UInt32] {
        let cursor = try prepared.cursor(from: frame)
        var bits: [UInt32] = []
        while let block = try cursor.nextPlaybackBlock() {
            #expect(block.frameCount > 0)
            let finite = block.interleaved.allSatisfy { $0.isFinite }
            #expect(finite)
            bits += block.interleaved.map(\.bitPattern)
        }
        #expect(cursor.isAtEnd && cursor.deliveredFrames == prepared.frameCount)
        #expect(Int64(bits.count / 2) == prepared.frameCount - frame)
        #expect(try cursor.nextPlaybackBlock() == nil)
        return bits
    }
    private func preserved(_ root: URL) throws -> [Data] {
        try [ProjectStore.manifestName, CPRProject.originalRelativePath, CPRProject.reportRelativePath].map {
            try Data(contentsOf: root.appendingPathComponent($0))
        }
    }

    @Test func allEightModesPrepareDistinctClockContractsAndPreserveSource() throws {
        try workspace { directory in
            let fixture = try CPRAuditionModesControl.makePackage(in: directory)
            let event = try #require(fixture.project.unresolvedAudioEvents.first)
            let before = try preserved(fixture.root)
            #expect(CPRSourceEventPlaybackMode.allCases.count == 8)
            let expected = fixture.samples[0].map { (Float($0) * (1 / Float(8_388_608)) * Float(0.0625)).bitPattern }
            for mode in CPRSourceEventPlaybackMode.allCases {
                let prepared = try CPRSourceAudition.prepare(eventID: event.id, in: fixture.project, at: fixture.root, mode: mode)
                let samples = try rendered(prepared)
                #expect(prepared.info.mode == mode && prepared.info.eventID == event.id)
                #expect(prepared.info.sourceSampleRate == 48_000 && prepared.info.sourceSHA256 == event.sourceSHA256)
                #expect(prepared.frameCount > 0)
                switch mode {
                case .sourceRate, .nativeTimelineSourceRate:
                    #expect(prepared.sampleRate == 48_000 && prepared.frameCount == 16_403)
                    #expect(samples == expected)
                case .nativeTimelineProjectClock:
                    #expect(prepared.sampleRate == 44_100 && prepared.info.timelineRange?.contract == CPRPlacedSourceEventPlan.projectClockContract)
                    #expect(samples == Array(expected.prefix(samples.count)))
                case .nativeTimelineSavedProjectClock, .nativeTrackSavedProjectClock:
                    #expect(prepared.sampleRate == 32_000 && prepared.info.savedProjectAudioSetup != nil)
                    #expect(samples == Array(expected.prefix(samples.count)))
                case .nativeMode0ProjectRate, .nativeMode1ProjectRate, .nativeMode2ProjectRate:
                    #expect(prepared.sampleRate == 44_100 && prepared.info.timelineRange == nil)
                    #expect(samples != Array(expected.prefix(samples.count)))
                }
                #expect(try preserved(fixture.root) == before)
            }
        }
    }

    @Test func savedClockIgnoresEditedProjectRateAndTempoButCurrentClockChanges() throws {
        try workspace { directory in
            let fixture = try CPRAuditionModesControl.makePackage(in: directory)
            let event = try #require(fixture.project.unresolvedAudioEvents.first)
            let saved = try CPRSourceAudition.prepare(eventID: event.id, in: fixture.project, at: fixture.root, mode: .nativeTimelineSavedProjectClock)
            let current = try CPRSourceAudition.prepare(eventID: event.id, in: fixture.project, at: fixture.root, mode: .nativeTimelineProjectClock)
            var edited = fixture.project
            edited.sampleRate = 24_000
            edited.tempoMap = TempoMap(events: [TempoEvent(beat: 0, bpm: 73)])
            try ProjectStore.save(edited, to: fixture.root)
            let afterSaved = try CPRSourceAudition.prepare(eventID: event.id, in: edited, at: fixture.root, mode: .nativeTimelineSavedProjectClock)
            let afterCurrent = try CPRSourceAudition.prepare(eventID: event.id, in: edited, at: fixture.root, mode: .nativeTimelineProjectClock)
            let afterSamples = try rendered(afterSaved), beforeSamples = try rendered(saved)
            #expect(afterSaved.info == saved.info && afterSamples == beforeSamples)
            #expect(afterCurrent.sampleRate == 24_000 && afterCurrent.frameCount < current.frameCount)
            #expect(afterCurrent.info.sourceSHA256 == current.info.sourceSHA256)
        }
    }

    @Test func freshCursorsAndBoundarySeeksDoNotShareConversionState() throws {
        try workspace { directory in
            let fixture = try CPRAuditionModesControl.makePackage(in: directory)
            let event = try #require(fixture.project.unresolvedAudioEvents.first)
            for mode in CPRSourceEventPlaybackMode.allCases {
                let prepared = try CPRSourceAudition.prepare(eventID: event.id, in: fixture.project, at: fixture.root, mode: mode)
                let first = try prepared.cursor(from: 0)
                _ = try first.nextPlaybackBlock()
                for frame in [Int64(0), 1, 4095, 8191, prepared.frameCount - 1, prepared.frameCount] where frame <= prepared.frameCount {
                    let a = try rendered(prepared, from: frame)
                    let b = try rendered(prepared, from: frame)
                    #expect(a == b)
                }
                #expect(throws: (any Error).self) { try prepared.cursor(from: -1) }
                #expect(throws: (any Error).self) { try prepared.cursor(from: prepared.frameCount + 1) }
            }
        }
    }

    @Test func equalRateDoesNotFallbackModeZeroAndSavedSetupIsRequired() throws {
        try workspace { directory in
            var options = CPRAuditionModesControl.Options()
            options.projectRate = 48_000; options.savedRate = nil
            let fixture = try CPRAuditionModesControl.makePackage(in: directory, options: options)
            let event = try #require(fixture.project.unresolvedAudioEvents.first)
            for mode in [CPRSourceEventPlaybackMode.nativeMode0ProjectRate, .nativeTimelineSavedProjectClock, .nativeTrackSavedProjectClock] {
                #expect(throws: (any Error).self) { try CPRSourceAudition.prepare(eventID: event.id, in: fixture.project, at: fixture.root, mode: mode) }
            }
            for mode in [CPRSourceEventPlaybackMode.sourceRate, .nativeMode1ProjectRate, .nativeMode2ProjectRate] {
                let prepared = try CPRSourceAudition.prepare(eventID: event.id, in: fixture.project, at: fixture.root, mode: mode)
                #expect(prepared.sampleRate == 48_000 && prepared.frameCount > 0)
                _ = try rendered(prepared)
            }
        }
    }

    @Test func fullyCoveredContributorStillRequiresItsVerifiedMediaAndMembership() throws {
        try workspace { directory in
            var options = CPRAuditionModesControl.Options()
            options.events = [.init(priority: .min), .init(priority: .max)]
            let fixture = try CPRAuditionModesControl.makePackage(in: directory, options: options)
            let events = fixture.project.unresolvedAudioEvents
            let anchor = try #require(events.first)
            let prepared = try CPRSourceAudition.prepare(eventID: anchor.id, in: fixture.project, at: fixture.root, mode: .nativeTrackSavedProjectClock)
            let track = try #require(prepared.info.sourceTrack)
            #expect(track.events.count == 2 && track.events.map(\.priority) == [Int32.min, Int32.max])
            #expect(track.fragments.count == 1 && track.fragments[0].eventID == events[1].id)
            let samples = try rendered(prepared)
            let expected = fixture.samples[1].prefix(samples.count).map { (Float($0) * (1 / Float(8_388_608)) * Float(0.0625)).bitPattern }
            #expect(samples == expected)
            var removed = fixture.project
            removed.tracks[0].unresolvedAudioEvents.removeAll { $0.id == anchor.id }
            #expect(throws: (any Error).self) { try CPRSourceAudition.prepare(eventID: events[1].id, in: removed, at: fixture.root, mode: .nativeTrackSavedProjectClock) }
            let attachment = try #require(fixture.project.cprMediaAttachments.first { $0.mediaSHA256 == track.events[0].mediaSHA256 })
            let media = try ProjectStore.resolveMediaURL(attachment.mediaPath, projectRoot: fixture.root)
            var bytes = try Data(contentsOf: media); bytes[bytes.count - 1] ^= 1
            try bytes.write(to: media)
            #expect(throws: (any Error).self) { try CPRSourceAudition.prepare(eventID: events[1].id, in: fixture.project, at: fixture.root, mode: .nativeTrackSavedProjectClock) }
        }
    }
}
