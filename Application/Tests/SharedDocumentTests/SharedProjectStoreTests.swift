import Foundation
import Testing
#if os(Windows)
import WinSDK
#endif
#if canImport(RebaseCore)
@testable import RebaseCore
#else
@testable import RebasePortable
#endif

struct SharedProjectStoreTests {
    private func workspace(_ body: (URL) throws -> Void) throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("RebaseDocument-" + Foundation.UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try body(root)
    }

    private func fixture(at root: URL) throws -> Project {
        var project = try ProjectStore.create(at: root, name: "Shared control")
        let bytes = try WAVPCMSource.encode(PCMBuffer(sampleRate: 48_000, channels: [[0.25, -0.5, 0.75, 0]]))
        try bytes.write(to: root.appendingPathComponent("Media/Control.wav"))
        let clip = Clip(mediaPath: "Media/Control.wav", name: "Control", sourceOffset: 1 / 48_000, duration: 3 / 48_000)
        project.tracks = [Track(name: "Track", clips: [clip])]
        try ProjectStore.save(project, to: root)
        return project
    }

    @Test func sharedEditsSaveReopenAndRetainOpaquePackageFiles() throws {
        try workspace { root in
            var project = try fixture(at: root)
            let media = root.appendingPathComponent("Media/Control.wav")
            let originalMedia = try Data(contentsOf: media)
            let sidecar = root.appendingPathComponent("Compatibility/Opaque.bin")
            try FileManager.default.createDirectory(at: sidecar.deletingLastPathComponent(), withIntermediateDirectories: true)
            let opaque = Data([0, 255, 17, 23, 0, 99])
            try opaque.write(to: sidecar)
            let track = project.tracks[0].id, clip = project.tracks[0].clips[0].id
            let moved = try ProjectEditing.applying(.moveClip(clip, position: 2), to: project)
            project = try #require(moved).project
            project.tracks[0].gainDB = -6
            project.tracks[0].automation = [AutomationLane(parameter: .pan, points: [AutomationPoint(time: 0, value: -0.5)])]
            try ProjectStore.save(project, to: root)
            #expect(try ProjectStore.load(from: root) == project)
            #expect(try ProjectStore.resolveMediaURL("Media/Control.wav", projectRoot: root).lastPathComponent == "Control.wav")
            #expect(try Data(contentsOf: media) == originalMedia)
            #expect(try Data(contentsOf: sidecar) == opaque)
            #expect(project.tracks[0].id == track)
            #expect(throws: (any Error).self) { try ProjectStore.create(at: root, name: "Replacement") }
            #expect(try ProjectStore.load(from: root) == project)
        }
    }

    @Test func invalidAndOversizedSavesPreserveTheLastManifest() throws {
        try workspace { root in
            let original = try fixture(at: root)
            let manifest = root.appendingPathComponent(ProjectStore.manifestName)
            let bytes = try Data(contentsOf: manifest)
            var invalid = original
            invalid.tracks[0].pan = .infinity
            #expect(throws: (any Error).self) { try ProjectStore.save(invalid, to: root) }
            invalid = original; invalid.tracks[0].clips[0].mediaPath = "Media/missing.wav"
            #expect(throws: (any Error).self) { try ProjectStore.save(invalid, to: root) }
            invalid = original; invalid.name = String(repeating: "x", count: ProjectFileIO.maximumManifestBytes)
            #expect(throws: (any Error).self) { try ProjectStore.save(invalid, to: root) }
            #expect(try Data(contentsOf: manifest) == bytes)
            #expect(try ProjectStore.load(from: root) == original)
            #expect(try !FileManager.default.contentsOfDirectory(atPath: root.path).contains { $0.hasPrefix(".rebase-manifest-") })
        }
    }

    #if os(Windows)
    @Test func deniedWindowsReplacementRetainsTheSavedDocumentAndCleansStaging() throws {
        try workspace { root in
            let original = try fixture(at: root)
            let manifest = root.appendingPathComponent(ProjectStore.manifestName)
            let before = try Data(contentsOf: manifest)
            let path = try manifest.withUnsafeFileSystemRepresentation { pointer in
                let pointer = try #require(pointer)
                return Array(String(cString: pointer).utf16) + [0]
            }
            let handle = path.withUnsafeBufferPointer {
                CreateFileW($0.baseAddress, DWORD(GENERIC_READ), DWORD(FILE_SHARE_READ), nil,
                            DWORD(OPEN_EXISTING), DWORD(FILE_ATTRIBUTE_NORMAL), nil)
            }
            #expect(handle != INVALID_HANDLE_VALUE)
            guard handle != INVALID_HANDLE_VALUE else { return }
            defer { _ = CloseHandle(handle) }
            var edited = original; edited.name = "Must not replace"
            #expect(throws: (any Error).self) { try ProjectStore.save(edited, to: root) }
            #expect(try Data(contentsOf: manifest) == before)
            #expect(try ProjectStore.load(from: root) == original)
            #expect(try !FileManager.default.contentsOfDirectory(atPath: root.path).contains { $0.hasPrefix(".rebase-manifest-") })
        }
    }
    #endif

    @Test func everySourceIntervalAndAllSamplesAreCheckedOnLoad() throws {
        try workspace { root in
            var project = try fixture(at: root)
            let manifest = root.appendingPathComponent(ProjectStore.manifestName)
            var invalid = project.tracks[0].clips[0]
            invalid.id = Foundation.UUID(); invalid.sourceOffset = 4 / 48_000; invalid.duration = 1 / 48_000
            project.tracks[0].clips.append(invalid)
            project.tracks[0].isMuted = true
            try JSONEncoder().encode(project).write(to: manifest)
            #expect(throws: (any Error).self) { try ProjectStore.load(from: root) }
            project.tracks[0].clips.removeLast()
            project.tracks[0].clips[0].sourceOffset = 0
            project.tracks[0].clips[0].duration = 1 / 48_000
            try JSONEncoder().encode(project).write(to: manifest)
            let media = root.appendingPathComponent("Media/Control.wav")
            var bytes = try Data(contentsOf: media)
            bytes.replaceSubrange((bytes.count - 4)..<bytes.count, with: [0, 0, 0xc0, 0x7f])
            try bytes.write(to: media)
            #expect(throws: (any Error).self) { try ProjectStore.load(from: root) }
        }
    }

    @Test func mediaContainmentRejectsTraversalAlternateStreamsAndRedirectedDirectories() throws {
        try workspace { directory in
            let root = directory.appendingPathComponent("Project.rebaseproj")
            _ = try fixture(at: root)
            let outside = directory.appendingPathComponent("Outside.wav")
            let sentinel = Data([1, 2, 3]); try sentinel.write(to: outside)
            for path in ["../Outside.wav", "Media/../Project.json", "Media//Control.wav", "Media/./Control.wav",
                         "Media\\Control.wav", "Media/Control.wav:secret", "Media/C:/Outside.wav", "Media", "Media/missing.wav"] {
                #expect(throws: (any Error).self) { try ProjectStore.resolveMediaURL(path, projectRoot: root) }
            }
            let escape = root.appendingPathComponent("Media/Escape.wav")
            try FileManager.default.createSymbolicLink(at: escape, withDestinationURL: outside)
            #expect(throws: (any Error).self) { try ProjectStore.resolveMediaURL("Media/Escape.wav", projectRoot: root) }
            let redirected = directory.appendingPathComponent("Redirected.rebaseproj")
            try FileManager.default.createDirectory(at: redirected, withIntermediateDirectories: false)
            try FileManager.default.createSymbolicLink(at: redirected.appendingPathComponent("Media"), withDestinationURL: root.appendingPathComponent("Media"))
            #expect(throws: (any Error).self) { try ProjectStore.resolveMediaURL("Media/Control.wav", projectRoot: redirected) }
            #expect(try Data(contentsOf: outside) == sentinel)
        }
    }

    @Test func redirectedAndOversizedManifestsCannotBeOpenedOrOverwritten() throws {
        try workspace { directory in
            let root = directory.appendingPathComponent("Project.rebaseproj")
            try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false)
            let outside = directory.appendingPathComponent("Outside.json")
            let bytes = try JSONEncoder().encode(Project(name: "Sentinel")); try bytes.write(to: outside)
            let manifest = root.appendingPathComponent(ProjectStore.manifestName)
            try FileManager.default.createSymbolicLink(at: manifest, withDestinationURL: outside)
            #expect(throws: (any Error).self) { try ProjectStore.load(from: root) }
            #expect(throws: (any Error).self) { try ProjectStore.save(Project(), to: root) }
            #expect(throws: (any Error).self) { try ProjectStore.create(at: root) }
            #expect(try Data(contentsOf: outside) == bytes)
            try FileManager.default.removeItem(at: manifest)
            try Data(repeating: 0, count: ProjectFileIO.maximumManifestBytes + 1).write(to: manifest)
            #expect(throws: (any Error).self) { try ProjectStore.load(from: root) }
        }
    }

    @Test func publicationNeverReplacesExistingFilesOrDirectories() throws {
        try workspace { root in
            let staging = root.appendingPathComponent("Stage"), destination = root.appendingPathComponent("Saved.rebaseproj")
            try FileManager.default.createDirectory(at: staging, withIntermediateDirectories: false)
            let bytes = Data([1, 3, 5]); try bytes.write(to: staging.appendingPathComponent("Opaque.bin"))
            try FileManager.default.createDirectory(at: destination, withIntermediateDirectories: false)
            #expect(throws: (any Error).self) { try ProjectFileIO.publishNewDirectory(staging, to: destination) }
            #expect(try Data(contentsOf: staging.appendingPathComponent("Opaque.bin")) == bytes)
            #expect(try FileManager.default.contentsOfDirectory(atPath: destination.path).isEmpty)
            try FileManager.default.removeItem(at: destination)
            try ProjectFileIO.publishNewDirectory(staging, to: destination)
            #expect(!FileManager.default.fileExists(atPath: staging.path))
            #expect(try Data(contentsOf: destination.appendingPathComponent("Opaque.bin")) == bytes)
            let source = root.appendingPathComponent("Stage.wav"), target = root.appendingPathComponent("Mix.wav")
            try bytes.write(to: source)
            let sentinel = Data([9, 7]); try sentinel.write(to: target)
            #expect(throws: (any Error).self) { try ProjectFileIO.publishNewFile(source, to: target) }
            #expect(try Data(contentsOf: target) == sentinel)
            try FileManager.default.removeItem(at: target)
            try ProjectFileIO.publishNewFile(source, to: target)
            try FileManager.default.removeItem(at: source)
            #expect(try Data(contentsOf: target) == bytes)
            #expect(try target.resourceValues(forKeys: [.isSymbolicLinkKey]).isSymbolicLink == false)
        }
    }

    @Test func nativeClockReplayAndFailedSavesPreserveTheSourceAndReport() throws {
        try workspace { root in
            _ = try ProjectStore.create(at: root)
            let source = root.appendingPathComponent(CPRProject.originalRelativePath)
            let reportURL = root.appendingPathComponent(CPRProject.reportRelativePath)
            try FileManager.default.createDirectory(at: source.deletingLastPathComponent(), withIntermediateDirectories: true)
            let sourceBytes = fixedClockControl()
            try sourceBytes.write(to: source)
            let report = try CPRProject.inspect(from: source)
            let clock = try #require(report.nativeClock)
            var project = try #require(report.recoveredProject)
            let reportBytes = try JSONEncoder().encode(report)
            try reportBytes.write(to: reportURL)
            project.name = "Retained source"
            try ProjectStore.save(project, to: root)
            #expect(try ProjectStore.load(from: root) == project)
            let manifest = root.appendingPathComponent(ProjectStore.manifestName)
            let saved = try Data(contentsOf: manifest)
            var forged = project
            forged.tempoMap.nativeClock = try NativeTempoClock(fixedBPMBits: clock.fixedBPMBits,
                sourceSHA256: String(repeating: "b", count: 64), sourceObjectOffset: clock.sourceObjectOffset)
            try forged.validate()
            #expect(throws: (any Error).self) { try ProjectStore.save(forged, to: root) }
            #expect(try Data(contentsOf: manifest) == saved)
            #expect(try Data(contentsOf: source) == sourceBytes)
            #expect(try Data(contentsOf: reportURL) == reportBytes)
            var damaged = sourceBytes; damaged[damaged.count - 1] ^= 1
            try damaged.write(to: source)
            #expect(throws: (any Error).self) { try ProjectStore.load(from: root) }
            #expect(throws: (any Error).self) { try ProjectStore.save(project, to: root) }
            #expect(try Data(contentsOf: manifest) == saved)
            #expect(try Data(contentsOf: source) == damaged)
            #expect(try Data(contentsOf: reportURL) == reportBytes)
            try sourceBytes.write(to: source)
            #expect(try ProjectStore.load(from: root) == project)
        }
    }

    #if !canImport(RebaseCore)
    @Test func portableAttachmentValidationRefusesUncheckedAssociations() throws {
        let digest = String(repeating: "a", count: 64)
        let attachment = CPRAudioMediaAttachment(id: Foundation.UUID(), association: "user-selected", sourceSHA256: digest,
            sourceFileIdentity: 10, mediaPath: "Media/Control.wav", mediaSHA256: digest, selectedFilename: "Control.wav",
            frameCount: 4, sampleRate: 48_000, channels: 1, bitsPerSample: 32, bytesPerFrame: 4)
        try workspace { root in
            let original = try fixture(at: root)
            let manifest = root.appendingPathComponent(ProjectStore.manifestName)
            let before = try Data(contentsOf: manifest)
            var project = original; project.cprMediaAttachments = [attachment]
            #expect(throws: RebaseCoreError.self) { try ProjectStore.validateCPRAudioMedia(project, at: root) }
            #expect(throws: (any Error).self) { try ProjectStore.save(project, to: root) }
            #expect(try Data(contentsOf: manifest) == before)
        }
    }
    #endif

    /// Authored structure control, not output from a proprietary application.
    private func fixedClockControl() -> Data {
        func be(_ value: UInt32) -> Data { var value = value.bigEndian; return withUnsafeBytes(of: &value) { Data($0) } }
        func be16(_ value: UInt16) -> Data { var value = value.bigEndian; return withUnsafeBytes(of: &value) { Data($0) } }
        func string(_ value: String) -> Data { be(UInt32(value.utf8.count)) + Data(value.utf8) }
        func record(_ tag: String, _ bytes: Data) -> Data { Data(tag.utf8) + be(UInt32(bytes.count)) + bytes }
        func object(_ type: String, _ version: UInt16, _ body: Data) -> Data {
            be(0xffff_ffff) + be(UInt32(type.utf8.count + 1)) + Data(type.utf8) + Data([0]) + be16(version) + be(UInt32(body.count)) + body
        }
        let datum = be(1) + Data(repeating: 0, count: 8)
        let tempoRecord = be(Float(0.5).bitPattern) + Data(repeating: 0, count: 16) + be16(0)
        let tempo = object("MTempoTrackEvent", 3, be(1) + tempoRecord + be(Float(126.5).bitPattern) + be16(1))
        let name = Data("Control\0".utf8)
        let trackNode = object("MListNode", 0, be(UInt32(name.count)) + name + datum + be(0))
        let track = object("MAudioTrackEvent", 1, Data(repeating: 0, count: 26) + trackNode)
        let rootNode = object("MTrackList", 0, be(0) + be(0) + tempo + be(0) + be16(0) + be(1) + track)
        let root = object("MRoot", 6, Data(repeating: 0, count: 26) + rootNode)
        let sections = record("ROOT", string("Arrangement1") + string("PArrangement")) + record("ARCH", object("PArrangement", 4, root))
        return Data("RIFF".utf8) + be(UInt32(sections.count)) + Data("NUND".utf8) + sections
    }
}
