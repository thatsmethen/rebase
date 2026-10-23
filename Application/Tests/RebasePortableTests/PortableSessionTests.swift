import Foundation
import Testing
@testable import RebasePortable

struct PortableSessionTests {
    private func fixture() throws -> (URL, Project) {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("rebase-session-test-" + UUID().uuidString + ".rebaseproj")
        try FileManager.default.createDirectory(at: root.appendingPathComponent("Media"), withIntermediateDirectories: true)
        let pcm = try PCMBuffer(sampleRate: 48_000, channels: [[Float](repeating: 0.25, count: 48_000)])
        try WAVPCMSource.encode(pcm).write(to: root.appendingPathComponent("Media/control.wav"))
        let project = Project(name: "Protocol control", tracks: [Track(name: "Control", clips: [
            Clip(mediaPath: "Media/control.wav", name: "Control", duration: 1)
        ])])
        try ProjectStore.save(project, to: root)
        return (root, project)
    }
    private func request(_ session: PortableSession, _ id: Int, _ command: String, revision: Int = 0,
                         _ extra: [String: Any] = [:]) throws -> [String: Any] {
        var request: [String: Any] = ["protocol": 1, "id": id, "command": command, "expectedRevision": revision]
        request.merge(extra) { _, new in new }
        return try #require(JSONSerialization.jsonObject(with: session.process(JSONSerialization.data(withJSONObject: request))) as? [String: Any])
    }
    private func state(_ reply: [String: Any]) throws -> [String: Any] { try #require(reply["state"] as? [String: Any]) }
    private func project(_ reply: [String: Any]) throws -> Project {
        try JSONDecoder().decode(Project.self, from: JSONSerialization.data(withJSONObject: #require(try state(reply)["project"])))
    }
    private func error(_ reply: [String: Any]) -> String? { (reply["error"] as? [String: Any])?["code"] as? String }

    @Test func editsUseSharedHistoryAndRejectStaleMessagesTransactionally() throws {
        let (root, original) = try fixture(); defer { try? FileManager.default.removeItem(at: root) }
        let session = PortableSession(), clip = original.tracks[0].clips[0].id.uuidString
        #expect(try request(session, 1, "open", ["path": root.path])["ok"] as? Bool == true)
        let moved = try request(session, 2, "moveClip", revision: 1, ["clipID": clip, "value": 0.7, "snap": "quarter"])
        #expect(try project(moved).tracks[0].clips[0].position == 0.5)
        #expect(try state(moved)["revision"] as? Int == 2)
        let stale = try request(session, 3, "deleteEvent", revision: 1, ["clipID": clip])
        #expect(error(stale) == "staleRevision")
        #expect(try project(stale) == project(moved))
        let undo = try request(session, 4, "undo", revision: 2)
        #expect(try project(undo) == original)
        #expect(try state(undo)["dirty"] as? Bool == false)
        let redo = try request(session, 5, "redo", revision: 3)
        #expect(try project(redo) == project(moved))
        #expect(error(try request(session, 5, "state")) == "requestOrder")
        let invalid = try request(session, 6, "setTempo", revision: 4, ["value": 0])
        #expect(invalid["ok"] as? Bool == false)
        #expect(try state(invalid)["revision"] as? Int == 4)
        #expect(try project(invalid) == project(moved))
    }

    @Test func exampleCopySaveAsPreservesOriginalAndSidecarsAndRefusesReplacement() throws {
        let (root, original) = try fixture(); defer { try? FileManager.default.removeItem(at: root) }
        let sidecar = Data([0, 255, 17, 42])
        try sidecar.write(to: root.appendingPathComponent("Opaque.bin"))
        let originalManifest = try Data(contentsOf: root.appendingPathComponent("Project.json"))
        let destination = root.deletingLastPathComponent().appendingPathComponent(UUID().uuidString + ".rebaseproj")
        defer { try? FileManager.default.removeItem(at: destination) }
        let session = PortableSession()
        let opened = try request(session, 1, "open", ["path": root.path, "asCopy": true])
        #expect(try state(opened)["needsSaveAs"] as? Bool == true)
        _ = try request(session, 2, "setGain", revision: 1, ["trackID": original.tracks[0].id.uuidString, "value": -6])
        #expect(error(try request(session, 3, "save", revision: 2)) == "saveAsRequired")
        #expect(error(try request(session, 4, "open", revision: 2, ["path": root.path])) == "unsavedChanges")
        let saved = try request(session, 5, "saveAs", revision: 2, ["path": destination.path])
        #expect(saved["ok"] as? Bool == true)
        #expect(try state(saved)["dirty"] as? Bool == false)
        #expect(try state(saved)["needsSaveAs"] as? Bool == false)
        #expect(try ProjectStore.load(from: destination).tracks[0].gainDB == -6)
        #expect(try Data(contentsOf: destination.appendingPathComponent("Opaque.bin")) == sidecar)
        #expect(try Data(contentsOf: root.appendingPathComponent("Project.json")) == originalManifest)
        let before = try Data(contentsOf: destination.appendingPathComponent("Project.json"))
        #expect(try request(session, 6, "saveAs", revision: 3, ["path": destination.path])["ok"] as? Bool == false)
        #expect(try Data(contentsOf: destination.appendingPathComponent("Project.json")) == before)
    }

    @Test func saveAndRenderRejectExternalManifestChanges() throws {
        let (root, original) = try fixture(); defer { try? FileManager.default.removeItem(at: root) }
        let session = PortableSession()
        _ = try request(session, 1, "open", ["path": root.path])
        _ = try request(session, 2, "setGain", revision: 1, ["trackID": original.tracks[0].id.uuidString, "value": -9])
        var external = original; external.name = "External edit"
        try ProjectStore.save(external, to: root)
        #expect(error(try request(session, 3, "save", revision: 2)) == "externalChange")
        let output = root.deletingLastPathComponent().appendingPathComponent(UUID().uuidString + ".wav")
        #expect(error(try request(session, 4, "render", revision: 2, ["path": output.path])) == "externalChange")
        #expect(!FileManager.default.fileExists(atPath: output.path))
        #expect(try ProjectStore.load(from: root) == external)
    }

    @Test func renderingPublishesOwnedSnapshotAndPreservesExistingFiles() throws {
        let (root, original) = try fixture(); defer { try? FileManager.default.removeItem(at: root) }
        let session = PortableSession()
        _ = try request(session, 1, "open", ["path": root.path])
        let output = root.deletingLastPathComponent().appendingPathComponent(UUID().uuidString + ".wav")
        defer { try? FileManager.default.removeItem(at: output) }
        let rendered = try request(session, 2, "render", revision: 1, ["path": output.path])
        let metadata = try #require(rendered["render"] as? [String: Any])
        let data = try Data(contentsOf: output)
        #expect(metadata["sha256"] as? String == PortableSHA256.hexDigest(data))
        #expect(metadata["frames"] as? Int == 48_000)
        #expect(metadata["revision"] as? Int == 1)
        #expect(try WAVPCMSource(data: data).channelCount == 2)
        #expect((try output.resourceValues(forKeys: [.isSymbolicLinkKey])).isSymbolicLink == false)
        #expect(error(try request(session, 3, "render", revision: 1, ["path": output.path])) == "destination")
        #expect(try Data(contentsOf: output) == data)
        #expect(try project(rendered) == original)
        #expect(try request(session, 4, "saveAs", revision: 1, ["path": root.appendingPathComponent("nested.rebaseproj").path])["ok"] as? Bool == false)
        #expect(!FileManager.default.fileExists(atPath: root.appendingPathComponent("nested.rebaseproj").path))
    }

    @Test func badFramesAndUnknownCommandsDoNotCreateProjectsOrEdits() throws {
        let session = PortableSession()
        #expect(try request(session, 1, "save")["ok"] as? Bool == false)
        let malformed = session.process(Data("{broken".utf8))
        #expect((try JSONSerialization.jsonObject(with: malformed) as? [String: Any])?["ok"] as? Bool == false)
        let oversized = session.process(Data(repeating: 32, count: PortableSession.maximumRequestBytes + 1))
        #expect(error(try #require(JSONSerialization.jsonObject(with: oversized) as? [String: Any])) == "requestTooLarge")
        let wrongVersion = try request(session, 2, "state", ["protocol": 2])
        #expect(error(wrongVersion) == "protocol")
        #expect(try state(wrongVersion)["revision"] as? Int == 0)
    }
}
