import Testing
import Foundation
import RebaseCore

/// Synthetic project manifests: these are application validation tests, not
/// observations of Reference or a hardware playback conformance test.
final class InvalidClipIntervalTests: AudioTestCase {
    private func writeManifest(_ project: Project) throws {
        try JSONEncoder().encode(project).write(to: root.appendingPathComponent(ProjectStore.manifestName))
    }

    private func expectInvalidProject(_ operation: () throws -> Void,
                                      sourceLocation: SourceLocation = #_sourceLocation) {
        do {
            try operation()
            Issue.record("Expected invalid source-interval rejection", sourceLocation: sourceLocation)
        } catch RebaseCoreError.invalidProject(_) {
            // A typed validation error, rather than an I/O failure or trap,
            // establishes that a readable media file has an invalid interval.
        } catch { Issue.record(error, sourceLocation: sourceLocation) }
    }

    @Test func testLargeFiniteSourceOffsetsRejectBeforeFrameConversion() throws {
        let original = try importClip([[0.1, 0.2, 0.3, 0.4]])
        for offset in [1e20, Double.greatestFiniteMagnitude] {
            var clip = original
            clip.sourceOffset = offset
            let project = Project(tracks: [Track(name: "Invalid offset", clips: [clip])])
            try writeManifest(project)
            let decoded = try JSONDecoder().decode(Project.self,
                from: Data(contentsOf: root.appendingPathComponent(ProjectStore.manifestName)))
            expectEqual(decoded.tracks[0].clips[0].sourceOffset, offset)
            expectInvalidProject { _ = try ProjectStore.load(from: root) }
            expectInvalidProject { _ = try OfflineRenderer.render(project: project, projectRoot: root) }
        }
    }

    @Test func testLoadedSourceIntervalMustFitActualMedia() throws {
        let original = try importClip([[0.1, 0.2, 0.3, 0.4]])
        for (offset, duration) in [(4 / rate, 1 / rate), (3 / rate, 2 / rate)] {
            var clip = original
            clip.sourceOffset = offset
            clip.duration = duration
            try writeManifest(Project(tracks: [Track(name: "Past end", clips: [clip])]))
            expectInvalidProject { _ = try ProjectStore.load(from: root) }
        }
    }

    @Test func testBoundaryIntervalLoadsAndRendersItsSelectedSamples() throws {
        var clip = try importClip([[0.1, 0.2, 0.3, 0.4]])
        clip.sourceOffset = 2 / rate
        clip.duration = 2 / rate
        let project = Project(tracks: [Track(name: "Valid end", pan: -1, clips: [clip])])
        try writeManifest(project)
        let loaded = try ProjectStore.load(from: root)
        expectEqual(loaded, project)
        let output = try OfflineRenderer.render(project: loaded, projectRoot: root)
        assertPlane(output, channel: 0, equals: [0.3, 0.4])
    }

    @Test func testSharedMediaCacheStillValidatesEveryClip() throws {
        let valid = try importClip([[0.1, 0.2, 0.3, 0.4]])
        var invalid = valid
        invalid.id = UUID()
        invalid.sourceOffset = 1e20
        try writeManifest(Project(tracks: [Track(name: "Shared asset", clips: [valid, invalid])]))
        expectInvalidProject { _ = try ProjectStore.load(from: root) }
    }
}
