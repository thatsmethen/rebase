import Foundation
import Testing
#if canImport(RebaseCore)
@testable import RebaseCore
#else
@testable import RebasePortable
#endif

/// Tiny owned media on long forward-authored timelines. These controls exercise
/// duration independently of storage; they are not captured reference projects.
struct CPRLongTimelineFixtureTests {
    static func options(_ name: String) -> CPRAuditionModesControl.Options {
        var result = CPRAuditionModesControl.Options()
        // 1000.125 seconds is beyond the old 32M-frame Windows export limit at
        // every admitted timeline rate (48k source, 44.1k current, 32k saved).
        let start = (name == "near-day" ? 86_399.0 : 1_000.125) * 960
        if name == "overlap" {
            result.events = [
                .init(frames: 512, startTicks: start, lengthFrames: 360, offsetFrames: 20),
                .init(frames: 512, startTicks: start, lengthFrames: 360, offsetFrames: 40),
                .init(frames: 512, priority: 2, startTicks: start + 2.4, lengthFrames: 120, offsetFrames: 60)
            ]
        } else {
            result.events = [.init(frames: 512, startTicks: start, lengthFrames: 360, offsetFrames: 20)]
        }
        return result
    }

    @Test(arguments: ["boundary", "overlap", "near-day"])
    func boundedTailAndEOF(_ name: String) throws {
        let fm = FileManager.default
        let scratch = fm.temporaryDirectory.appendingPathComponent("rebase-long-control-" + UUID().uuidString)
        try fm.createDirectory(at: scratch, withIntermediateDirectories: false)
        defer { try? fm.removeItem(at: scratch) }
        let fixture = try CPRAuditionModesControl.makePackage(in: scratch, options: Self.options(name))
        let eventID = try #require(fixture.project.unresolvedAudioEvents.first?.id)
        for mode: CPRSourceEventPlaybackMode in [.nativeTimelineSourceRate, .nativeTimelineProjectClock,
            .nativeTimelineSavedProjectClock, .nativeTrackSavedProjectClock] {
            let prepared = try CPRSourceAudition.prepare(eventID: eventID, in: fixture.project, at: fixture.root, mode: mode)
            #expect(prepared.frameCount > 32_000_000)
            if name == "near-day" { #expect(prepared.frameCount > Int64(prepared.sampleRate * 86_398)) }
            #expect(prepared.frameCount <= Int64(prepared.sampleRate * 86_400))
            let start = prepared.frameCount - 1_000
            #expect(try prepared.startFrame(at: Double(start) / prepared.sampleRate) == start)
            let cursor = try prepared.cursor(from: start)
            var emitted: Int64 = 0
            var peakBlock = 0
            var heardSignal = false
            while let block = try cursor.nextPlaybackBlock() {
                peakBlock = max(peakBlock, block.frameCount)
                emitted += Int64(block.frameCount)
                heardSignal = heardSignal || block.left.contains(where: { $0 != 0 }) || block.right.contains(where: { $0 != 0 })
            }
            #expect(emitted == 1_000 && peakBlock <= 4_096 && heardSignal)
            #expect(cursor.deliveredFrames == prepared.frameCount && cursor.isAtEnd)
            let eof = try prepared.cursor(from: prepared.frameCount)
            #expect(try eof.nextPlaybackBlock() == nil && eof.isAtEnd)
            if mode == .nativeTrackSavedProjectClock && name == "overlap" {
                let track = try #require(prepared.info.sourceTrack)
                #expect(track.events.count == 3 && track.fragments.count == 3)
                #expect(!track.fragments.contains(where: { $0.eventID == eventID }))
            }
        }
    }

    @Test(.enabled(if: ProcessInfo.processInfo.environment["REBASE_GENERATE_CPR_LONG_TIMELINES"] != nil,
                   "Explicit new authored fixture generation only"))
    func generateAuthoredLongTimelineFixtures() throws {
        let destination = URL(fileURLWithPath: try #require(ProcessInfo.processInfo.environment["REBASE_GENERATE_CPR_LONG_TIMELINES"]))
        let fm = FileManager.default
        guard !fm.fileExists(atPath: destination.path) else {
            throw RebaseCoreError.invalidProject("Fixture destination already exists.")
        }
        try fm.createDirectory(at: destination, withIntermediateDirectories: false)
        var cases: [[String: Any]] = []
        for name in ["boundary", "overlap", "near-day"] {
            let directory = destination.appendingPathComponent(name)
            try fm.createDirectory(at: directory, withIntermediateDirectories: false)
            let settings = Self.options(name)
            let fixture = try CPRAuditionModesControl.makePackage(in: directory, options: settings)
            let events = fixture.project.unresolvedAudioEvents
            let eventID = try #require(events.first?.id)
            var modes: [[String: Any]] = []
            for mode: CPRSourceEventPlaybackMode in [.nativeTimelineSourceRate, .nativeTimelineProjectClock,
                .nativeTimelineSavedProjectClock, .nativeTrackSavedProjectClock] {
                let prepared = try CPRSourceAudition.prepare(eventID: eventID, in: fixture.project, at: fixture.root, mode: mode)
                let cursor = try prepared.cursor(from: prepared.frameCount - 1_000)
                var tail = Data()
                while let block = try cursor.nextPlaybackBlock() {
                    for sample in block.interleaved {
                        var bits = sample.bitPattern.littleEndian
                        withUnsafeBytes(of: &bits) { tail.append(contentsOf: $0) }
                    }
                }
                #expect(tail.count == 8_000)
                modes.append(["mode": mode.rawValue, "sampleRate": prepared.sampleRate, "totalFrames": prepared.frameCount,
                    "tailFrames": 1_000, "tailPCMSHA256": cprSHA256(tail)])
            }
            cases.append(["name": name, "root": name + "/AuthoredModes.rebaseproj", "anchorID": eventID.uuidString,
                "sourceSHA256": cprSHA256(try Data(contentsOf: fixture.root.appendingPathComponent(CPRProject.originalRelativePath))),
                "reportSHA256": cprSHA256(try Data(contentsOf: fixture.root.appendingPathComponent(CPRProject.reportRelativePath))),
                "manifestSHA256": cprSHA256(try Data(contentsOf: fixture.root.appendingPathComponent(ProjectStore.manifestName))),
                "projectRate": settings.projectRate, "savedRate": try #require(settings.savedRate), "modes": modes,
                "events": try events.enumerated().map { ordinal, event -> [String: Any] in
                    let e = settings.events[ordinal]
                    return ["eventID": event.id.uuidString, "ordinal": ordinal, "priority": e.priority,
                        "frames": e.frames, "rate": e.rate, "gain": Double(e.gain), "startTicks": e.startTicks,
                        "lengthFrames": e.lengthFrames ?? e.frames, "offsetFrames": e.offsetFrames,
                        "mediaSHA256": cprSHA256(try Data(contentsOf: fixture.media[ordinal]))]
                }])
        }
        let here = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        var generators: [String: String] = [:]
        for name in ["CPRAuditionModesControl.swift", "CPRLongTimelineFixtureTests.swift"] {
            generators[name] = cprSHA256(try Data(contentsOf: here.appendingPathComponent(name)))
        }
        let metadata: [String: Any] = ["schemaVersion": 1, "evidenceClass": "authored-synthetic-control",
            "scope": "Tiny media on forward-authored long timelines; not reference-valid projects or observed reference audio. Locked preparation counts are implementation controls.",
            "generatorSHA256": generators, "cases": cases]
        try JSONSerialization.data(withJSONObject: metadata, options: [.prettyPrinted, .sortedKeys])
            .write(to: destination.appendingPathComponent("expected.json"), options: .withoutOverwriting)
    }
}
