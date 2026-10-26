import Foundation
import Testing
@testable import RebasePortable

struct PortableAudioImportTests {
    private final class Client {
        let session = PortableSession()
        var id = 0, revision = 0
        func call(_ command: String, _ fields: [String: Any] = [:], expected: Int? = nil) throws -> [String: Any] {
            id += 1
            var input: [String: Any] = ["protocol": 1, "id": id, "command": command, "expectedRevision": expected ?? revision]
            input.merge(fields) { _, new in new }
            let reply = try #require(JSONSerialization.jsonObject(with: session.process(JSONSerialization.data(withJSONObject: input))) as? [String: Any])
            revision = try #require((reply["state"] as? [String: Any])?["revision"] as? Int)
            return reply
        }
    }
    private func state(_ reply: [String: Any]) throws -> [String: Any] { try #require(reply["state"] as? [String: Any]) }
    private func stateBytes(_ reply: [String: Any]) throws -> Data { try JSONSerialization.data(withJSONObject: state(reply), options: [.sortedKeys]) }
    private func project(_ reply: [String: Any]) throws -> Project {
        try JSONDecoder().decode(Project.self, from: JSONSerialization.data(withJSONObject: #require(try state(reply)["project"])))
    }
    private func error(_ reply: [String: Any]) -> String? { (reply["error"] as? [String: Any])?["code"] as? String }

    @Test func newImportUndoRedoSaveAsReopenUsesOneBatchAndKeepsOwnedMedia() throws {
        try AudioImportControl.workspace { directory in
            let root = directory.appendingPathComponent("Scratch.rebaseproj"), client = Client()
            let created = try client.call("newProject", ["path": root.path])
            #expect(created["ok"] as? Bool == true && client.revision == 1)
            #expect(try state(created)["needsSaveAs"] as? Bool == true)
            #expect(try state(created)["dirty"] as? Bool == false)
            #expect(try state(created)["path"] == nil)
            #expect(try (state(created)["selection"] as? [String: Any])?.isEmpty == true)
            #expect(try project(created).name == "Untitled")
            let sources = try [AudioImportControl.audio(directory), AudioImportControl.audio(directory, name: "Stereo", stereo: true)]
            let sourceBytes = try sources.map { try Data(contentsOf: $0) }
            let imported = try client.call("importAudio", ["paths": sources.map(\.path), "value": 0.7, "snap": "quarter"])
            #expect(imported["ok"] as? Bool == true && client.revision == 2)
            let edited = try project(imported)
            #expect(edited.tracks.count == 2 && edited.tracks.allSatisfy { $0.clips[0].position == 0.5 })
            #expect(try state(imported)["dirty"] as? Bool == true)
            let media = try edited.tracks.map { try ProjectStore.resolveMediaURL($0.clips[0].mediaPath, projectRoot: root) }
            let undo = try client.call("undo")
            #expect(try project(undo) == project(created))
            #expect(try state(undo)["canUndo"] as? Bool == false)
            #expect(try state(undo)["dirty"] as? Bool == false)
            for index in sources.indices { #expect(try Data(contentsOf: media[index]) == sourceBytes[index]) }
            let redo = try client.call("redo")
            #expect(try project(redo) == edited)
            #expect(error(try client.call("save")) == "saveAsRequired")
            let destination = directory.appendingPathComponent("Saved.rebaseproj")
            let saved = try client.call("saveAs", ["path": destination.path])
            #expect(saved["ok"] as? Bool == true)
            #expect(try state(saved)["dirty"] as? Bool == false)
            #expect(try state(saved)["needsSaveAs"] as? Bool == false)
            #expect(try ProjectStore.load(from: destination) == edited)
            let fresh = Client(), reopened = try fresh.call("open", ["path": destination.path])
            #expect(reopened["ok"] as? Bool == true)
            #expect(try project(reopened) == edited)
            for index in sources.indices { #expect(try Data(contentsOf: sources[index]) == sourceBytes[index]) }
        }
    }

    @Test func staleDirtyExistingAndInvalidRequestsPreserveStateHistoryAndFiles() throws {
        try AudioImportControl.workspace { directory in
            let root = directory.appendingPathComponent("Scratch.rebaseproj"), next = directory.appendingPathComponent("Next.rebaseproj"), client = Client()
            _ = try client.call("newProject", ["path": root.path])
            let source = try AudioImportControl.audio(directory)
            let imported = try client.call("importAudio", ["paths": [source.path], "value": 0])
            let before = try stateBytes(imported), snapshot = try PortablePackageSnapshot.capture(in: root)
            #expect(error(try client.call("newProject", ["path": next.path])) == "unsavedChanges")
            #expect(error(try client.call("newProject", ["path": next.path, "discardChanges": true], expected: 0)) == "staleRevision")
            #expect(!FileManager.default.fileExists(atPath: next.path))
            for fields: [String: Any] in [["paths": [], "value": 0], ["paths": [source.path], "value": -1],
                                          ["paths": [source.path], "value": 0, "snap": "unknown"],
                                          ["paths": [source.path, directory.appendingPathComponent("missing.wav").path], "value": 0]] {
                #expect(try client.call("importAudio", fields)["ok"] as? Bool == false)
            }
            #expect(error(try client.call("importAudio", ["paths": [source.path], "value": 0], expected: 0)) == "staleRevision")
            #expect(try stateBytes(client.call("state")) == before)
            #expect(try PortablePackageSnapshot.capture(in: root) == snapshot)
            try FileManager.default.createDirectory(at: next, withIntermediateDirectories: false)
            #expect(try client.call("newProject", ["path": next.path, "discardChanges": true])["ok"] as? Bool == false)
            #expect(try stateBytes(client.call("state")) == before)
            try FileManager.default.removeItem(at: next)
            let replacement = try client.call("newProject", ["path": next.path, "discardChanges": true])
            #expect(replacement["ok"] as? Bool == true)
            #expect(try project(replacement).tracks.isEmpty)
            #expect(try state(replacement)["canUndo"] as? Bool == false)
            #expect(try state(replacement)["canRedo"] as? Bool == false)
        }
    }

    @Test func externallyChangedManifestBlocksNewAndImportWithoutLosingDirtyEdits() throws {
        try AudioImportControl.workspace { directory in
            let root = directory.appendingPathComponent("Scratch.rebaseproj"), client = Client()
            _ = try client.call("newProject", ["path": root.path])
            let source = try AudioImportControl.audio(directory)
            let imported = try client.call("importAudio", ["paths": [source.path], "value": 0])
            let before = try stateBytes(imported)
            var external = try ProjectStore.load(from: root); external.name = "External"
            try ProjectStore.save(external, to: root)
            let snapshot = try PortablePackageSnapshot.capture(in: root)
            #expect(error(try client.call("importAudio", ["paths": [source.path], "value": 1])) == "externalChange")
            let next = directory.appendingPathComponent("Next.rebaseproj")
            #expect(error(try client.call("newProject", ["path": next.path, "discardChanges": true])) == "externalChange")
            #expect(try stateBytes(client.call("state")) == before)
            #expect(try PortablePackageSnapshot.capture(in: root) == snapshot)
            #expect(!FileManager.default.fileExists(atPath: next.path))
        }
    }

    @Test func successfulImportsAndNewRevokeSourceTicketsButFailedBatchDoesNot() throws {
        try AudioImportControl.workspace { directory in
            var options = CPRAuditionModesControl.Options(); options.events[0].frames = 8
            let fixture = try CPRAuditionModesControl.makePackage(in: directory, options: options), client = Client()
            _ = try client.call("open", ["path": fixture.root.path])
            let event = fixture.project.unresolvedAudioEvents[0].id.uuidString
            let ticket = directory.appendingPathComponent("source.ticket")
            #expect(try client.call("prepareSourceStream", ["clipID": event, "path": ticket.path])["ok"] as? Bool == true)
            let ticketBytes = try Data(contentsOf: ticket)
            let source = try AudioImportControl.audio(directory)
            #expect(try client.call("importAudio", ["paths": [source.path, directory.appendingPathComponent("Missing.wav").path], "value": 0])["ok"] as? Bool == false)
            #expect(try Data(contentsOf: ticket) == ticketBytes)
            #expect(try client.call("importAudio", ["paths": [source.path], "value": 0])["ok"] as? Bool == true)
            #expect(!FileManager.default.fileExists(atPath: ticket.path))
            #expect(try client.call("prepareSourceStream", ["clipID": event, "path": ticket.path])["ok"] as? Bool == true)
            let next = directory.appendingPathComponent("Next.rebaseproj")
            #expect(try client.call("newProject", ["path": next.path, "discardChanges": true])["ok"] as? Bool == true)
            #expect(!FileManager.default.fileExists(atPath: ticket.path))
            #expect(try CPRProject.compatibilityReport(from: fixture.root) != nil)
        }
    }
}
