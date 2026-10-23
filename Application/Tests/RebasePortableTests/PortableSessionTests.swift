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
        #expect(metadata["kind"] as? String == "project")
        #expect(metadata["eventID"] == nil)
        #expect(metadata["sourceSHA256"] == nil)
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

    @Test func sourceCommandsRejectOrdinaryClipsAndStaleStateWithoutSideEffects() throws {
        let (root, original) = try fixture(); defer { try? FileManager.default.removeItem(at: root) }
        let session = PortableSession(), clip = original.tracks[0].clips[0].id.uuidString
        _ = try request(session, 1, "open", ["path": root.path])
        let output = root.deletingLastPathComponent().appendingPathComponent(UUID().uuidString + ".wav")
        let manifest = try Data(contentsOf: root.appendingPathComponent("Project.json"))
        let media = try FileManager.default.contentsOfDirectory(atPath: root.appendingPathComponent("Media").path)
        let source = root.appendingPathComponent("Media/control.wav")
        let rejected = try request(session, 2, "attachSourceMedia", revision: 1,
            ["clipID": clip, "path": source.path])
        #expect(error(rejected) == "selection")
        #expect(try project(rejected) == original)
        #expect(try state(rejected)["revision"] as? Int == 1)
        #expect(try FileManager.default.contentsOfDirectory(atPath: root.appendingPathComponent("Media").path) == media)
        #expect(error(try request(session, 3, "renderSourceEvent", revision: 1,
            ["clipID": clip, "path": output.path])) == "selection")
        #expect(error(try request(session, 4, "renderSourceEvent", revision: 0,
            ["clipID": clip, "path": output.path])) == "staleRevision")
        #expect(!FileManager.default.fileExists(atPath: output.path))
        #expect(try Data(contentsOf: root.appendingPathComponent("Project.json")) == manifest)
    }

    @Test func sourceAuditionRevalidatesAttachedBytesAndRetainsUnresolvedIdentity() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("rebase-source-protocol-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let fixture = try CPRAudioControl.makePackage(in: directory)
        let event = try #require(fixture.project.unresolvedAudioEvents.first)
        let session = PortableSession(), id = event.id.uuidString
        _ = try request(session, 1, "open", ["path": fixture.root.path])
        let missing = directory.appendingPathComponent("missing.wav")
        #expect(try request(session, 2, "renderSourceEvent", revision: 1,
            ["clipID": id, "path": missing.path])["ok"] as? Bool == false)
        #expect(!FileManager.default.fileExists(atPath: missing.path))
        let attached = try request(session, 3, "attachSourceMedia", revision: 1,
            ["clipID": id, "path": fixture.media.path])
        #expect(attached["ok"] as? Bool == true)
        let updated = try project(attached)
        #expect(updated.unresolvedAudioEvents == fixture.project.unresolvedAudioEvents)
        #expect(updated.tracks.flatMap(\.clips).isEmpty)
        #expect(try state(attached)["revision"] as? Int == 2)
        #expect(try state(attached)["dirty"] as? Bool == true)
        let attachment = try #require(updated.cprMediaAttachments.first)
        let output = directory.appendingPathComponent("audition.wav")
        let rendered = try request(session, 4, "renderSourceEvent", revision: 2,
            ["clipID": id, "path": output.path])
        #expect(rendered["ok"] as? Bool == true)
        let metadata = try #require(rendered["render"] as? [String: Any])
        let bytes = try Data(contentsOf: output)
        #expect(metadata["kind"] as? String == "sourceEvent")
        #expect(metadata["eventID"] as? String == id)
        #expect(metadata["sourceSHA256"] as? String == event.sourceSHA256)
        #expect(metadata["mediaSHA256"] as? String == attachment.mediaSHA256)
        #expect(metadata["sha256"] as? String == PortableSHA256.hexDigest(bytes))
        #expect(metadata["sampleRate"] as? Int == 44_100)
        #expect(metadata["frames"] as? Int == 8)
        #expect(metadata["channels"] as? Int == 2)
        #expect(try state(rendered)["revision"] as? Int == 2)
        let pcm = try WAVPCMSource(data: bytes).read(from: 0, count: 8)
        for frame in 0..<8 { for channel in 0..<2 {
            let expected = Float(Double(fixture.samples[frame * 2 + channel]) / 8_388_608 * 0.75)
            #expect(pcm.channels[channel][frame].bitPattern == expected.bitPattern)
        } }
        #expect(try request(session, 5, "renderSourceEvent", revision: 2,
            ["clipID": id, "path": output.path])["ok"] as? Bool == false)
        #expect(try Data(contentsOf: output) == bytes)
        let ordinary = directory.appendingPathComponent("ordinary.wav")
        #expect(try request(session, 6, "render", revision: 2, ["path": ordinary.path])["ok"] as? Bool == false)
        #expect(!FileManager.default.fileExists(atPath: ordinary.path))
        let undone = try request(session, 7, "undo", revision: 2)
        #expect(try project(undone).cprMediaAttachments.isEmpty)
        #expect(try request(session, 8, "renderSourceEvent", revision: 3,
            ["clipID": id, "path": missing.path])["ok"] as? Bool == false)
        _ = try request(session, 9, "redo", revision: 3)
        let media = try ProjectStore.resolveMediaURL(attachment.mediaPath, projectRoot: fixture.root)
        var changed = fixture.mediaBytes; changed[44] ^= 1; try changed.write(to: media)
        let tampered = try request(session, 10, "renderSourceEvent", revision: 4,
            ["clipID": id, "path": missing.path])
        #expect(tampered["ok"] as? Bool == false)
        #expect(try state(tampered)["revision"] as? Int == 4)
        #expect(!FileManager.default.fileExists(atPath: missing.path))
        try fixture.mediaBytes.write(to: media)
        #expect(try request(session, 11, "save", revision: 4)["ok"] as? Bool == true)
        let reopened = PortableSession()
        #expect(try request(reopened, 1, "open", ["path": fixture.root.path])["ok"] as? Bool == true)
        #expect(try request(reopened, 2, "renderSourceEvent", revision: 1,
            ["clipID": id, "path": missing.path])["ok"] as? Bool == true)
        #expect(try Data(contentsOf: missing) == bytes)
    }

    @Test func waveformIsSourceBoundedReadOnlyAndRejectsStaleOrDeletedClips() throws {
        let (root, original) = try fixture(); defer { try? FileManager.default.removeItem(at: root) }
        let session = PortableSession(), clip = original.tracks[0].clips[0].id.uuidString
        _ = try request(session, 1, "open", ["path": root.path])
        let reply = try request(session, 2, "waveform", revision: 1, ["clipID": clip])
        #expect(reply["ok"] as? Bool == true)
        let waveform = try #require(reply["waveform"] as? [String: Any])
        #expect(waveform["revision"] as? Int == 1)
        #expect(waveform["clipID"] as? String == clip)
        #expect(waveform["sampleRate"] as? Int == 48_000)
        #expect(waveform["sourceStartFrame"] as? Int == 0)
        #expect(waveform["sourceFrames"] as? Int == 48_000)
        #expect(waveform["peaks"] as? [Double] == [Double](repeating: 0.25, count: 1600))
        let source = try Data(contentsOf: root.appendingPathComponent("Media/control.wav"))
        #expect(waveform["mediaSHA256"] as? String == PortableSHA256.hexDigest(source))
        #expect(try state(reply)["dirty"] as? Bool == false)
        #expect(try state(reply)["canUndo"] as? Bool == false)
        _ = try request(session, 3, "setGain", revision: 1,
            ["trackID": original.tracks[0].id.uuidString, "value": -24])
        #expect(error(try request(session, 4, "waveform", revision: 1, ["clipID": clip])) == "staleRevision")
        let afterGain = try request(session, 5, "waveform", revision: 2, ["clipID": clip])
        let unchangedPeaks = try #require(afterGain["waveform"] as? [String: Any])
        #expect(unchangedPeaks["peaks"] as? [Double] == waveform["peaks"] as? [Double])
        _ = try request(session, 6, "trimClip", revision: 2, ["clipID": clip, "value": 0.5])
        let trimmed = try request(session, 7, "waveform", revision: 3, ["clipID": clip])
        #expect((trimmed["waveform"] as? [String: Any])?["sourceFrames"] as? Int == 24_000)
        _ = try request(session, 8, "deleteEvent", revision: 3, ["clipID": clip])
        #expect(error(try request(session, 9, "waveform", revision: 4, ["clipID": clip])) == "selection")
    }
}
