import Foundation
import Testing
#if canImport(RebaseCore)
@testable import RebaseCore
import AVFoundation
#else
@testable import RebasePortable
#endif

enum AudioImportControl {
    static func workspace(_ body: (URL) throws -> Void) throws {
        let checkout = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let parent = ProcessInfo.processInfo.environment["REBASE_TEST_WORK_ROOT"].map { URL(fileURLWithPath: $0) }
            ?? checkout.appendingPathComponent(".local/work/rebase-new-import-20261026/fixtures")
        let directory = parent.appendingPathComponent("audio-import-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        try body(directory)
    }
    static func audio(_ directory: URL, name: String = "Mono", stereo: Bool = false) throws -> URL {
        let mono: [Float] = [0, 0.25, -0.5, 0.75, -0.125, 0]
        let pcm = try PCMBuffer(sampleRate: 48_000, channels: stereo ? [mono, Array(mono.reversed())] : [mono])
        let path = directory.appendingPathComponent(name + ".wav")
        try WAVPCMSource.encode(pcm).write(to: path, options: .withoutOverwriting)
        return path
    }
}

struct SharedAudioImportTests {
    @Test func exclusiveCreationRefusesEveryExistingDestinationAndReturnsReopenableDefaults() throws {
        try AudioImportControl.workspace { directory in
            let root = directory.appendingPathComponent("New.rebaseproj")
            #expect(throws: (any Error).self) { try ProjectStore.createExclusive(at: URL(string: "https://example.invalid/New.rebaseproj")!) }
            #expect(throws: (any Error).self) { try ProjectStore.createExclusive(at: directory.appendingPathComponent("Bad\0.rebaseproj")) }
            try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false)
            #expect(throws: (any Error).self) { try ProjectStore.createExclusive(at: root) }
            #expect(try FileManager.default.contentsOfDirectory(atPath: root.path).isEmpty)
            try FileManager.default.removeItem(at: root)
            try Data([7, 8]).write(to: root)
            #expect(throws: (any Error).self) { try ProjectStore.createExclusive(at: root) }
            #expect(try Data(contentsOf: root) == Data([7, 8]))
            try FileManager.default.removeItem(at: root)
            let project = try ProjectStore.createExclusive(at: root)
            #expect(project.name == "Untitled" && project.tracks.isEmpty && project.sampleRate == 48_000 && project.tempo == 120)
            #expect(try ProjectStore.load(from: root) == project)
            #expect(try FileManager.default.contentsOfDirectory(atPath: directory.path) == ["New.rebaseproj"])
        }
    }

    @Test func monoStereoBatchCopiesExactBytesAndSnapsAsOneReversibleEdit() throws {
        try AudioImportControl.workspace { directory in
            let sources = try [AudioImportControl.audio(directory), AudioImportControl.audio(directory, name: "Stéréo 音", stereo: true)]
            let bytes = try sources.map { try Data(contentsOf: $0) }
            let root = directory.appendingPathComponent("New.rebaseproj")
            let initial = try ProjectStore.createExclusive(at: root)
            let manifest = try Data(contentsOf: root.appendingPathComponent("Project.json"))
            let result = try ProjectStore.importAudioTracks(from: sources, into: root, project: initial, position: 0.7, grid: .quantize(1))
            #expect(result.project.tracks.count == 2 && result.waveformClipIDs.count == 2)
            #expect(result.selection.trackID == result.project.tracks.last?.id)
            #expect(result.selection.clipID == result.project.tracks.last?.clips.first?.id)
            for index in sources.indices {
                let clip = result.project.tracks[index].clips[0]
                #expect(clip.position == 0.5 && clip.sourceOffset == 0 && clip.duration == 6 / 48_000.0)
                let copy = try ProjectStore.resolveMediaURL(clip.mediaPath, projectRoot: root)
                #expect(try Data(contentsOf: copy) == bytes[index])
                #expect(try Data(contentsOf: sources[index]) == bytes[index])
                #expect(try WAVPCMSource(url: copy).channelCount == index + 1)
            }
            #expect(try Data(contentsOf: root.appendingPathComponent("Project.json")) == manifest)
            var history = ProjectEditHistory(); history.record(initial)
            #expect(history.undo(current: result.project) == initial)
            #expect(history.redo(current: initial) == result.project)
            try ProjectStore.save(result.project, to: root)
            #expect(try ProjectStore.load(from: root) == result.project)
        }
    }

    @Test func invalidSecondFileRollsBackBatchAndPreservesPriorMediaAndManifest() throws {
        try AudioImportControl.workspace { directory in
            let source = try AudioImportControl.audio(directory)
            let root = directory.appendingPathComponent("Existing.rebaseproj")
            let initial = try ProjectStore.createExclusive(at: root)
            let first = try ProjectStore.importAudioTracks(from: [source], into: root, project: initial, position: 0).project
            try ProjectStore.save(first, to: root)
            let baseline = try PortablePackageSnapshot.capture(in: root)
            let bad = directory.appendingPathComponent("Truncated.wav"); try Data("RIFFbad".utf8).write(to: bad)
            #expect(throws: (any Error).self) { try ProjectStore.importAudioTracks(from: [source, bad], into: root, project: first, position: 1) }
            #expect(try PortablePackageSnapshot.capture(in: root) == baseline)
            #expect(try ProjectStore.load(from: root) == first)
        }
    }

    @Test func nonfiniteAndOversizeFilesAndInvalidPositionsLeaveNoAssets() throws {
        try AudioImportControl.workspace { directory in
            let good = try AudioImportControl.audio(directory), root = directory.appendingPathComponent("New.rebaseproj")
            let project = try ProjectStore.createExclusive(at: root), baseline = try PortablePackageSnapshot.capture(in: root)
            var bytes = try Data(contentsOf: good)
            bytes.replaceSubrange((bytes.count - 4)..<bytes.count, with: [0, 0, 0xC0, 0x7F])
            let nan = directory.appendingPathComponent("Nonfinite.wav"); try bytes.write(to: nan)
            let large = directory.appendingPathComponent("Oversize.wav"); try Data().write(to: large)
            let handle = try FileHandle(forWritingTo: large)
            try handle.truncate(atOffset: UInt64(ProjectStore.maximumAudioImportBytes) + 1); try handle.close()
            for source in [nan, large] {
                #expect(throws: (any Error).self) { try ProjectStore.importAudioTracks(from: [good, source], into: root, project: project, position: 0) }
            }
            for position in [Double.nan, .infinity, -1, 86_400] {
                #expect(throws: (any Error).self) { try ProjectStore.importAudioTracks(from: [good], into: root, project: project, position: position) }
            }
            #expect(throws: (any Error).self) { try ProjectStore.importAudioTracks(from: Array(repeating: good, count: 33), into: root, project: project, position: 0) }
            #expect(try PortablePackageSnapshot.capture(in: root) == baseline)
        }
    }

    @Test func changedSourceAndChangedSavedManifestAreRejectedBeforePublication() throws {
        try AudioImportControl.workspace { directory in
            let source = try AudioImportControl.audio(directory), root = directory.appendingPathComponent("New.rebaseproj")
            let project = try ProjectStore.createExclusive(at: root), baseline = try PortablePackageSnapshot.capture(in: root)
            let original = try Data(contentsOf: source)
            #expect(throws: (any Error).self) {
                try ProjectStore.importAudioTracks(from: [source], into: root, project: project, position: 0, grid: nil) {
                    try Data([1, 2, 3]).write(to: source)
                }
            }
            #expect(try PortablePackageSnapshot.capture(in: root) == baseline)
            #expect(try Data(contentsOf: source) == Data([1, 2, 3]))
            try original.write(to: source)
            var outside = project; outside.name = "External edit"
            #expect(throws: (any Error).self) {
                try ProjectStore.importAudioTracks(from: [source], into: root, project: project, position: 0, grid: nil) {
                    try ProjectStore.save(outside, to: root)
                }
            }
            #expect(try ProjectStore.load(from: root) == outside)
            #expect(try FileManager.default.contentsOfDirectory(atPath: root.appendingPathComponent("Media").path).isEmpty)
        }
    }

    @Test func emptyProjectWithoutMediaCreatesItOnlyForSuccessfulTransaction() throws {
        try AudioImportControl.workspace { directory in
            let root = directory.appendingPathComponent("Empty.rebaseproj"), project = Project()
            try ProjectStore.save(project, to: root)
            let source = try AudioImportControl.audio(directory)
            enum Injected: Error { case failure }
            #expect(throws: (any Error).self) {
                try ProjectStore.importAudioTracks(from: [source], into: root, project: project, position: 0, grid: nil) { throw Injected.failure }
            }
            #expect(!FileManager.default.fileExists(atPath: root.appendingPathComponent("Media").path))
            let imported = try ProjectStore.importAudioTracks(from: [source], into: root, project: project, position: 0)
            try ProjectStore.save(imported.project, to: root)
            #expect(try ProjectStore.load(from: root) == imported.project)
        }
    }

    @Test func publicationCollisionAndReviewedManifestMismatchNeverReplaceOtherAssets() throws {
        try AudioImportControl.workspace { directory in
            let source = try AudioImportControl.audio(directory), root = directory.appendingPathComponent("New.rebaseproj")
            let project = try ProjectStore.createExclusive(at: root)
            let baseline = try PortablePackageSnapshot.capture(in: root)
            #expect(throws: (any Error).self) {
                try ProjectStore.importAudioTracks(from: [source], into: root, project: project, position: 0,
                    expectedManifestSHA256: String(repeating: "0", count: 64))
            }
            #expect(try PortablePackageSnapshot.capture(in: root) == baseline)
            var collision: URL?
            let sentinel = Data([91, 73, 18])
            #expect(throws: (any Error).self) {
                try ProjectStore.importAudioTracks(from: [source], into: root, project: project, position: 0, grid: nil,
                    publish: { stage, destination in
                        collision = destination
                        try ProjectFileIO.createNewDirectory(destination)
                        try sentinel.write(to: destination.appendingPathComponent("Existing.bin"))
                        try ProjectFileIO.publishNewDirectory(stage, to: destination)
                    }, beforePublication: {})
            }
            let destination = try #require(collision)
            #expect(try Data(contentsOf: destination.appendingPathComponent("Existing.bin")) == sentinel)
            #expect(try FileManager.default.contentsOfDirectory(atPath: root.appendingPathComponent("Media").path) == [destination.lastPathComponent])
            #expect(try ProjectStore.load(from: root) == project)
        }
    }

    #if canImport(RebaseCore)
    @Test func macAdapterKeepsAIFFImportSupportThroughSharedTransaction() throws {
        try AudioImportControl.workspace { directory in
            let source = directory.appendingPathComponent("Authored.aiff")
            let format = try #require(AVAudioFormat(standardFormatWithSampleRate: 48_000, channels: 1))
            let buffer = try #require(AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 4))
            buffer.frameLength = 4
            for index in 0..<4 { buffer.floatChannelData![0][index] = Float(index) / 8 }
            do { let file = try AVAudioFile(forWriting: source, settings: format.settings); try file.write(from: buffer) }
            let root = directory.appendingPathComponent("New.rebaseproj"), project = try ProjectStore.createExclusive(at: root)
            let result = try ProjectStore.importAudioTracks(from: [source], into: root, project: project, position: 0)
            let clip = result.project.tracks[0].clips[0]
            #expect(clip.mediaPath.hasSuffix(".aiff"))
            #expect(try Data(contentsOf: ProjectStore.resolveMediaURL(clip.mediaPath, projectRoot: root)) == Data(contentsOf: source))
            try ProjectStore.save(result.project, to: root)
            #expect(try ProjectStore.load(from: root) == result.project)
        }
    }
    #endif
}
