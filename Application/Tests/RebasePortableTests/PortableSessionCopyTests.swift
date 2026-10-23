import Foundation
import Testing
@testable import RebasePortable

struct PortableSessionCopyTests {
    private func fixture() throws -> (URL, URL, Project) {
        let parent = FileManager.default.temporaryDirectory.appendingPathComponent("rebase-copy-test-" + UUID().uuidString)
        let root = parent.appendingPathComponent("Source.rebaseproj")
        let project = try ProjectStore.create(at: root, name: "Copy control")
        return (parent.resolvingSymlinksInPath(), root.resolvingSymlinksInPath(), project)
    }
    private func request(_ session: PortableSession, _ id: Int, _ command: String,
                         revision: Int = 0, _ extra: [String: Any] = [:]) throws -> [String: Any] {
        var frame: [String: Any] = ["protocol": 1, "id": id, "command": command, "expectedRevision": revision]
        frame.merge(extra) { _, new in new }
        return try #require(JSONSerialization.jsonObject(with: session.process(JSONSerialization.data(withJSONObject: frame))) as? [String: Any])
    }
    private func state(_ reply: [String: Any]) throws -> [String: Any] { try #require(reply["state"] as? [String: Any]) }
    private func project(_ reply: [String: Any]) throws -> Project {
        try JSONDecoder().decode(Project.self, from: JSONSerialization.data(withJSONObject: #require(try state(reply)["project"])))
    }

    @Test func legacyDefaultMapsDoNotMasqueradeAsExternalManifestChanges() throws {
        let (parent, root, _) = try fixture(); defer { try? FileManager.default.removeItem(at: parent) }
        let manifest = root.appendingPathComponent(ProjectStore.manifestName)
        var legacy = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: manifest)) as? [String: Any])
        legacy.removeValue(forKey: "tempoMap"); legacy.removeValue(forKey: "signatureMap"); legacy["tempo"] = 96
        let original = try JSONSerialization.data(withJSONObject: legacy, options: [.sortedKeys])
        try original.write(to: manifest)
        let session = PortableSession()
        let opened = try request(session, 1, "open", ["path": root.path])
        #expect(opened["ok"] as? Bool == true)
        #expect(try project(opened).tempo == 96)
        let copy = try request(session, 2, "open", revision: 1, ["path": root.path, "asCopy": true])
        #expect(copy["ok"] as? Bool == true)
        #expect(try state(copy)["needsSaveAs"] as? Bool == true)
        let adopted = try project(copy)
        let destination = parent.appendingPathComponent("Saved.rebaseproj")
        let saved = try request(session, 3, "saveAs", revision: 2, ["path": destination.path])
        #expect(saved["ok"] as? Bool == true)
        #expect(try project(saved) == adopted)
        let reopened = try request(session, 4, "open", revision: 3, ["path": destination.path])
        #expect(reopened["ok"] as? Bool == true)
        #expect(try project(reopened) == adopted)
        #expect(try Data(contentsOf: manifest) == original)
    }

    @Test func bundledLegacyExampleOpensAsAnEditableCopy() throws {
        let application = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let root = application.appendingPathComponent("Examples/Rebase Preview.rebaseproj")
        let manifest = root.appendingPathComponent(ProjectStore.manifestName)
        let original = try Data(contentsOf: manifest)
        let session = PortableSession()
        let opened = try request(session, 1, "open", ["path": root.path, "asCopy": true])
        #expect(opened["ok"] as? Bool == true)
        #expect(try state(opened)["needsSaveAs"] as? Bool == true)
        #expect(try state(opened)["dirty"] as? Bool == false)
        let loaded = try project(opened)
        #expect(loaded.tracks.count == 4 && loaded.tracks.flatMap(\.clips).count == 11)
        #expect(loaded.tempo == 96 && loaded.sampleRate == 48_000 && loaded.duration == 20)
        #expect(try Data(contentsOf: manifest) == original)
    }

    @Test func copyVerifiesAllChunksAndCleansAChangedSource() throws {
        let (parent, root, _) = try fixture(); defer { try? FileManager.default.removeItem(at: parent) }
        let sidecar = root.appendingPathComponent("Opaque.bin")
        let original = Data(repeating: 0x31, count: 1_048_583)
        try original.write(to: sidecar)
        let snapshot = try PortablePackageSnapshot.capture(in: root)
        let copy = parent.appendingPathComponent("Copy.rebaseproj")
        _ = try snapshot.copy(from: root, to: copy)
        #expect(try PortablePackageSnapshot.capture(in: copy) == snapshot)
        #expect(try Data(contentsOf: copy.appendingPathComponent("Opaque.bin")) == original)
        // Same-size mutation beyond the first chunk must not pass as a copy.
        var changed = original; changed[1_048_580] = 0x32
        try changed.write(to: sidecar)
        let failed = parent.appendingPathComponent("Changed.rebaseproj")
        #expect(throws: (any Error).self) { try snapshot.copy(from: root, to: failed) }
        #expect(!FileManager.default.fileExists(atPath: failed.path))
        #expect(try Data(contentsOf: sidecar) == changed)
        #expect(try Data(contentsOf: copy.appendingPathComponent("Opaque.bin")) == original)
    }

    @Test func addedAndRemovedEntriesInvalidateTheCopyAndNeverReplaceExistingDirectories() throws {
        let (parent, root, _) = try fixture(); defer { try? FileManager.default.removeItem(at: parent) }
        let snapshot = try PortablePackageSnapshot.capture(in: root)
        let extra = root.appendingPathComponent("Added.bin")
        try Data([1, 2, 3]).write(to: extra)
        let added = parent.appendingPathComponent("Added.rebaseproj")
        #expect(throws: (any Error).self) { try snapshot.copy(from: root, to: added) }
        #expect(!FileManager.default.fileExists(atPath: added.path))
        let withExtra = try PortablePackageSnapshot.capture(in: root)
        try FileManager.default.removeItem(at: extra)
        let removed = parent.appendingPathComponent("Removed.rebaseproj")
        #expect(throws: (any Error).self) { try withExtra.copy(from: root, to: removed) }
        #expect(!FileManager.default.fileExists(atPath: removed.path))
        let existing = parent.appendingPathComponent("Existing.rebaseproj")
        try FileManager.default.createDirectory(at: existing, withIntermediateDirectories: false)
        #expect(throws: (any Error).self) { try snapshot.copy(from: root, to: existing) }
        #expect(try FileManager.default.contentsOfDirectory(atPath: existing.path).isEmpty)
    }

    @Test func sizeBoundsAreCheckedBeforeOpeningTheOversizedFile() throws {
        let (parent, root, _) = try fixture(); defer { try? FileManager.default.removeItem(at: parent) }
        let oversized = root.appendingPathComponent("Oversized.bin")
        try Data().write(to: oversized)
        let handle = try FileHandle(forWritingTo: oversized)
        try handle.truncate(atOffset: UInt64(PortablePackageSnapshot.maximumBytes) + 1)
        try handle.close()
        #expect(throws: (any Error).self) { try PortablePackageSnapshot.capture(in: root) }
        let session = PortableSession()
        let opened = try request(session, 1, "open", ["path": root.path, "asCopy": true])
        #expect(opened["ok"] as? Bool == false)
        #expect(try state(opened)["revision"] as? Int == 0)
    }

    @Test func failedSaveAsPreservesSessionHistoryAndLeavesNoStage() throws {
        let (parent, root, _) = try fixture(); defer { try? FileManager.default.removeItem(at: parent) }
        let session = PortableSession()
        #expect(try request(session, 1, "open", ["path": root.path])["ok"] as? Bool == true)
        let changed = try request(session, 2, "setTempo", revision: 1, ["value": 87])
        let existing = parent.appendingPathComponent("Existing.rebaseproj")
        try FileManager.default.createDirectory(at: existing, withIntermediateDirectories: false)
        let failed = try request(session, 3, "saveAs", revision: 2, ["path": existing.path])
        #expect(failed["ok"] as? Bool == false)
        #expect(try NSDictionary(dictionary: state(failed)) == NSDictionary(dictionary: state(changed)))
        #expect(try FileManager.default.contentsOfDirectory(atPath: parent.path).allSatisfy { !$0.hasPrefix(".rebase-save-") })
        #expect(try FileManager.default.contentsOfDirectory(atPath: existing.path).isEmpty)
        let saved = parent.appendingPathComponent("Saved.rebaseproj")
        #expect(try request(session, 4, "saveAs", revision: 2, ["path": saved.path])["ok"] as? Bool == true)
        #expect(try ProjectStore.load(from: saved).tempoMap.events[0].bpm == 87)
        #expect(try ProjectStore.load(from: root).tempoMap.events[0].bpm == 120)
    }

    @Test func nulPathsAreRejectedByTheDocumentLayerAndProtocol() throws {
        let (parent, root, _) = try fixture(); defer { try? FileManager.default.removeItem(at: parent) }
        #expect(throws: (any Error).self) { try ProjectFileIO.canonicalRoot(URL(fileURLWithPath: root.path + "\0suffix")) }
        let session = PortableSession()
        #expect(try request(session, 1, "open", ["path": root.path + "\0suffix"])["ok"] as? Bool == false)
        #expect(try request(session, 2, "state")["state"] != nil)
    }

    #if !os(Windows)
    @Test func canonicalRootAliasesCopyRealFilesAndUnsafeChildrenDoNotChangeTheSession() throws {
        let (parent, root, original) = try fixture(); defer { try? FileManager.default.removeItem(at: parent) }
        let alias = parent.appendingPathComponent("Alias.rebaseproj")
        try FileManager.default.createSymbolicLink(at: alias, withDestinationURL: root)
        let session = PortableSession()
        let opened = try request(session, 1, "open", ["path": alias.path])
        #expect(opened["ok"] as? Bool == true)
        #expect(try state(opened)["path"] as? String == root.path)
        let copied = try request(session, 2, "open", revision: 1, ["path": alias.path, "asCopy": true])
        #expect(copied["ok"] as? Bool == true)
        #expect(try state(copied)["needsSaveAs"] as? Bool == true)
        let child = root.appendingPathComponent("Redirect")
        try FileManager.default.createSymbolicLink(at: child, withDestinationURL: parent)
        let refused = try request(session, 3, "open", revision: 2, ["path": alias.path, "asCopy": true])
        #expect(refused["ok"] as? Bool == false)
        #expect(try NSDictionary(dictionary: state(refused)) == NSDictionary(dictionary: state(copied)))
        #expect(try ProjectStore.load(from: root) == original)
        let target = parent.appendingPathComponent("Published.rebaseproj")
        #expect(throws: (any Error).self) { try ProjectFileIO.publishNewDirectory(alias, to: target) }
        #expect(!FileManager.default.fileExists(atPath: target.path))
    }

    @Test func unreadableDirectoryCannotBeSilentlySkipped() throws {
        let (parent, root, _) = try fixture(); defer { try? FileManager.default.removeItem(at: parent) }
        let hidden = root.appendingPathComponent("Unreadable")
        try FileManager.default.createDirectory(at: hidden, withIntermediateDirectories: false)
        try Data([4, 2]).write(to: hidden.appendingPathComponent("Evidence.bin"))
        try FileManager.default.setAttributes([.posixPermissions: 0], ofItemAtPath: hidden.path)
        defer { try? FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: hidden.path) }
        // A privileged test process can still read mode-000 directories.
        if !FileManager.default.isReadableFile(atPath: hidden.path) {
            #expect(throws: (any Error).self) { try PortablePackageSnapshot.capture(in: root) }
        }
    }
    #endif
}
