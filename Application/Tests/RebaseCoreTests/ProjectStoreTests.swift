import Testing
import Foundation
import RebaseCore

final class ProjectStoreTests: AudioTestCase {
    @Test func testSaveLoadPreservesEditsAndImportedMediaSurvivesSourceRemoval() throws {
        let source = try writeAudio([[0.125, -0.25, 0.5, -0.75]], name: "Original")
        let originalBytes = try Data(contentsOf: source)
        let imported = try ProjectStore.importAudio(from: source, into: root)
        expectEqual(imported.name, "Original")
        expectEqual(imported.channelCount, 1)
        expectEqual(imported.sampleRate, rate)
        expectEqual(imported.duration, 4 / rate)
        expectTrue(imported.mediaPath.hasPrefix("Media/"))
        let clip = Clip(mediaPath: imported.mediaPath, name: "Edited clip", position: 2 / rate,
                        sourceOffset: 1 / rate, duration: 3 / rate)
        let project = Project(name: "Saved edits", tempo: 137.5, sampleRate: 96_000,
                              tracks: [Track(name: "Voice", gainDB: -9.25, pan: -0.3,
                                             isMuted: true, isSolo: true, clips: [clip])])
        try ProjectStore.save(project, to: root)
        try FileManager.default.removeItem(at: source)
        expectEqual(try ProjectStore.load(from: root), project)
        let copied = try ProjectStore.resolveMediaURL(imported.mediaPath, projectRoot: root)
        expectEqual(try Data(contentsOf: copied), originalBytes)
        expectThrows(try ProjectStore.create(at: root, name: "Overwrite"))
        expectEqual(try ProjectStore.load(from: root), project)
    }

    @Test func testMalformedAndEscapingMediaReferencesAreRejected() throws {
        let clip = try importClip([[0.25]])
        expectNoThrow(try ProjectStore.resolveMediaURL(clip.mediaPath, projectRoot: root))
        let outside = try writeAudio([[0.5]], name: "outside")
        let escape = root.appendingPathComponent("Media/escape.wav")
        try FileManager.default.createSymbolicLink(at: escape, withDestinationURL: outside)
        for path in [outside.path, "../outside.wav", "Media/../Project.json", "Media//missing.wav",
                     "Media/./missing.wav", "Media\\missing.wav", "Media/escape.wav", "Media/missing.wav", "Media"] {
            expectThrows(try ProjectStore.resolveMediaURL(path, projectRoot: root), path)
        }
        var project = Project(tracks: [Track(name: "Invalid", clips: [clip])])
        project.tracks[0].clips[0].mediaPath = "Media/escape.wav"
        // Bypass the writer to represent an edited project received from elsewhere.
        try JSONEncoder().encode(project).write(to: root.appendingPathComponent(ProjectStore.manifestName))
        expectThrows(try ProjectStore.load(from: root))
    }

    @Test func testMediaDirectorySymlinkCannotRedirectImports() throws {
        let external = temporary.appendingPathComponent("External", isDirectory: true)
        try FileManager.default.createDirectory(at: external, withIntermediateDirectories: true)
        let media = root.appendingPathComponent("Media")
        try FileManager.default.removeItem(at: media)
        try FileManager.default.createSymbolicLink(at: media, withDestinationURL: external)
        let source = try writeAudio([[0.25]])
        expectThrows(try ProjectStore.importAudio(from: source, into: root))
        expectEqual(try FileManager.default.contentsOfDirectory(atPath: external.path), [])
    }

    @Test func testInvalidSaveLeavesPreviouslySavedProjectReadable() throws {
        let original = try ProjectStore.load(from: root)
        var invalid = original
        invalid.tracks = [Track(name: "Bad pan", pan: .infinity)]
        expectThrows(try ProjectStore.save(invalid, to: root))
        expectEqual(try ProjectStore.load(from: root), original)
        let duplicate = Track(name: "Repeated identity")
        invalid.tracks = [duplicate, duplicate]
        expectThrows(try ProjectStore.save(invalid, to: root))
        expectEqual(try ProjectStore.load(from: root), original)
    }
}
