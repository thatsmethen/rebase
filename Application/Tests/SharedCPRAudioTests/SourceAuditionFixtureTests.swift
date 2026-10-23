import Foundation
import Testing
#if canImport(RebaseCore)
@testable import RebaseCore
#else
@testable import RebasePortable
#endif

struct SourceAuditionFixtureTests {
    @Test(.enabled(if: ProcessInfo.processInfo.environment["REBASE_GENERATE_SOURCE_AUDITION_FIXTURE"] != nil))
    func generateAuthoredFixtureAtExplicitNewDestination() throws {
        let path = try #require(ProcessInfo.processInfo.environment["REBASE_GENERATE_SOURCE_AUDITION_FIXTURE"])
        try SourceAuditionFixtureGenerator.generate(at: URL(fileURLWithPath: path))
    }

    @Test func checkedInAuthoredFixtureAttachesRendersAndReopensWithoutChangingOriginal() throws {
        let fixture = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Fixtures/SourceAudition")
        let expected = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: fixture.appendingPathComponent("expected.json"))) as? [String: Any])
        let original = fixture.appendingPathComponent("AuthoredSource.rebaseproj")
        let media = fixture.appendingPathComponent("SelectedSource.wav")
        let manifest = try Data(contentsOf: original.appendingPathComponent(ProjectStore.manifestName))
        let report = try Data(contentsOf: original.appendingPathComponent(CPRProject.reportRelativePath))
        let source = try Data(contentsOf: original.appendingPathComponent(CPRProject.originalRelativePath))
        #expect(cprSHA256(manifest) == expected["manifestSHA256"] as? String)
        #expect(cprSHA256(report) == expected["reportSHA256"] as? String)
        #expect(cprSHA256(source) == expected["sourceSHA256"] as? String)
        #expect(cprSHA256(try Data(contentsOf: media)) == expected["mediaSHA256"] as? String)
        let fm = FileManager.default
        let work = fm.temporaryDirectory.appendingPathComponent("CheckedSourceAudition-" + UUID().uuidString)
        try fm.createDirectory(at: work, withIntermediateDirectories: false)
        defer { try? fm.removeItem(at: work) }
        let root = work.appendingPathComponent("Control.rebaseproj")
        try fm.copyItem(at: original, to: root)
        // Git does not retain the generator's empty Media directory. Exercise
        // the same package shape that a fresh Windows checkout receives.
        let emptyMedia = root.appendingPathComponent("Media")
        if fm.fileExists(atPath: emptyMedia.path) {
            #expect(try fm.contentsOfDirectory(atPath: emptyMedia.path).isEmpty)
            try fm.removeItem(at: emptyMedia)
        }
        let loaded = try ProjectStore.load(from: root)
        #expect(loaded.cprMediaAttachments.isEmpty && loaded.sampleRate == 48_000)
        #expect(loaded.unresolvedAudioEvents.count == 1 && loaded.tracks.flatMap(\.clips).isEmpty)
        let event = try #require(loaded.unresolvedAudioEvents.first)
        #expect(event.id.uuidString == expected["eventID"] as? String)
        let attached = try ProjectStore.attachCPRAudioMedia(from: media, to: event.id, in: loaded, at: root)
        try ProjectStore.save(attached, to: root)
        #expect(try ProjectStore.load(from: root) == attached)
        let output = work.appendingPathComponent("Output.wav")
        let rendered = try CPRSourceEventRenderer.renderAudition(eventID: event.id, in: attached, at: root, to: output)
        #expect(rendered.frameCount == expected["frames"] as? Int)
        #expect(Int(rendered.sampleRate) == expected["sampleRate"] as? Int)
        #expect(rendered.channelCount == expected["channels"] as? Int)
        #expect(rendered.outputSHA256 == expected["outputSHA256"] as? String)
        #expect(rendered.sourceSHA256 == expected["sourceSHA256"] as? String)
        #expect(rendered.mediaSHA256 == expected["mediaSHA256"] as? String)
        let outputBytes = try Data(contentsOf: output)
        #expect(outputBytes.count == expected["outputBytes"] as? Int)
        #expect(cprSHA256(outputBytes.dropFirst(58)) == expected["pcmSHA256"] as? String)
        #expect(throws: (any Error).self) { try attached.requireResolvedAudioEvents() }
        #expect(throws: (any Error).self) {
            try CPRSourceEventRenderer.renderAudition(eventID: event.id, in: attached, at: root, to: output)
        }
        #expect(try Data(contentsOf: original.appendingPathComponent(ProjectStore.manifestName)) == manifest)
        #expect(try Data(contentsOf: original.appendingPathComponent(CPRProject.reportRelativePath)) == report)
        #expect(try Data(contentsOf: original.appendingPathComponent(CPRProject.originalRelativePath)) == source)
    }
}
