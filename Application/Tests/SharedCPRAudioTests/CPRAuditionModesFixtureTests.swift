import Foundation
import Testing
#if canImport(RebaseCore)
@testable import RebaseCore
#else
@testable import RebasePortable
#endif

struct CPRAuditionModesFixtureTests {
    @Test(.enabled(if: ProcessInfo.processInfo.environment["REBASE_GENERATE_CPR_AUDITION_MODES"] != nil,
                   "Explicit authored fixture generation only"))
    func generateAuthoredModeFixtures() throws {
        let destination = URL(fileURLWithPath: try #require(ProcessInfo.processInfo.environment["REBASE_GENERATE_CPR_AUDITION_MODES"]))
        let fm = FileManager.default
        #expect(!fm.fileExists(atPath: destination.path))
        guard !fm.fileExists(atPath: destination.path) else { throw RebaseCoreError.invalidProject("Fixture destination already exists.") }
        try fm.createDirectory(at: destination, withIntermediateDirectories: false)
        // A failed run is retained for diagnosis; this generator never repairs
        // an old fixture or replaces its expected records.
        var cases: [[String: Any]] = []
        var options = CPRAuditionModesControl.Options()
        let single = destination.appendingPathComponent("Single")
        try fm.createDirectory(at: single, withIntermediateDirectories: false)
        let one = try CPRAuditionModesControl.makePackage(in: single, options: options)
        cases.append(try metadata(one, name: "single", relativeRoot: "Single/AuthoredModes.rebaseproj", options: options))

        // The first event is fully covered by the same-start later event; it
        // must still be present and its distinct media verified. A third
        // higher-priority event splits the winner and restores its tail.
        options.events = [
            .init(frames: 24_000, startTicks: 96, lengthFrames: 18_000, offsetFrames: 1_200),
            .init(frames: 24_000, startTicks: 96, lengthFrames: 18_000, offsetFrames: 2_400),
            .init(frames: 24_000, priority: 2, startTicks: 192, lengthFrames: 4_800, offsetFrames: 3_600)
        ]
        let overlap = destination.appendingPathComponent("Overlap")
        try fm.createDirectory(at: overlap, withIntermediateDirectories: false)
        let track = try CPRAuditionModesControl.makePackage(in: overlap, options: options)
        cases.append(try metadata(track, name: "overlap", relativeRoot: "Overlap/AuthoredModes.rebaseproj", options: options))

        let here = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let sources = ["CPRAuditionModesControl.swift", "CPRAuditionModesFixtureTests.swift"]
        var hashes: [String: String] = [:]
        for name in sources { hashes[name] = cprSHA256(try Data(contentsOf: here.appendingPathComponent(name))) }
        let value: [String: Any] = ["schemaVersion": 1, "evidenceClass": "authored-synthetic-control",
            "scope": "Forward-authored structural inputs; not reference-valid projects or observed reference audio. Converted output comparisons are cross-platform implementation checks.",
            "generatorSHA256": hashes, "cases": cases]
        try JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted, .sortedKeys])
            .write(to: destination.appendingPathComponent("expected.json"), options: .withoutOverwriting)
    }

    private func metadata(_ fixture: CPRAuditionModesControl.Fixture, name: String,
                          relativeRoot: String, options: CPRAuditionModesControl.Options) throws -> [String: Any] {
        let events = fixture.project.unresolvedAudioEvents
        let source = try Data(contentsOf: fixture.root.appendingPathComponent(CPRProject.originalRelativePath))
        let report = try Data(contentsOf: fixture.root.appendingPathComponent(CPRProject.reportRelativePath))
        return ["name": name, "root": relativeRoot, "anchorID": try #require(events.first?.id.uuidString),
            "sourceSHA256": cprSHA256(source), "reportSHA256": cprSHA256(report),
            "manifestSHA256": cprSHA256(try Data(contentsOf: fixture.root.appendingPathComponent(ProjectStore.manifestName))),
            "projectRate": options.projectRate, "savedRate": try #require(options.savedRate),
            "events": try events.enumerated().map { ordinal, event -> [String: Any] in
                let settings = options.events[ordinal]
                return ["eventID": event.id.uuidString, "ordinal": ordinal, "priority": settings.priority,
                    "frames": settings.frames, "rate": settings.rate, "gain": Double(settings.gain),
                    "startTicks": settings.startTicks, "lengthFrames": settings.lengthFrames ?? settings.frames,
                    "offsetFrames": settings.offsetFrames,
                    "mediaSHA256": cprSHA256(try Data(contentsOf: fixture.media[ordinal]))]
            }]
    }
}
