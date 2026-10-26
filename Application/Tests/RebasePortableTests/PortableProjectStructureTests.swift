import Foundation
import Testing
@testable import RebasePortable

@Suite struct PortableProjectStructureTests {
    private final class Client {
        let session = PortableSession()
        var id = 0, revision = 0
        func call(_ command: String, _ extra: [String: Any] = [:], expected: Int? = nil) throws -> [String: Any] {
            id += 1
            var request: [String: Any] = ["protocol": 1, "id": id, "command": command, "expectedRevision": expected ?? revision]
            request.merge(extra) { _, next in next }
            let reply = try #require(JSONSerialization.jsonObject(with: session.process(JSONSerialization.data(withJSONObject: request))) as? [String: Any])
            revision = try #require((reply["state"] as? [String: Any])?["revision"] as? Int)
            return reply
        }
    }
    private func workspace(_ body: (URL) throws -> Void) throws {
        let fm = FileManager.default
        let base = ProcessInfo.processInfo.environment["REBASE_TEST_WORK_ROOT"].map { URL(fileURLWithPath: $0) } ?? fm.temporaryDirectory
        let root = base.appendingPathComponent("StructureProtocol-" + UUID().uuidString)
        try fm.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? fm.removeItem(at: root) }
        try body(root)
    }
    private func state(_ reply: [String: Any]) throws -> Data {
        let value = try #require(reply["state"])
        return try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
    }
    private func page(_ reply: [String: Any]) throws -> [String: Any] { try #require(reply["projectStructure"] as? [String: Any]) }
    private func error(_ reply: [String: Any]) -> String? { (reply["error"] as? [String: Any])?["code"] as? String }

    @Test func fullPagedReportRoundTripsWhileDirtyHistoryAndSelectionStayUnchanged() throws {
        try workspace { root in
            var options = BindingControl.Options()
            options.fields = ["OutputBus", "OwnInputBus", "RecorderBus"].map {
                .object($0, [.text("Name", String(repeating: "a\\\"\n", count: 8_000)), .integer("Bus UID", 27)])
            }
            let project = try BindingControl.package(at: root, options: options), client = Client()
            _ = try client.call("open", ["path": root.path])
            _ = try client.call("selectTrack", ["trackID": project.tracks[0].id.uuidString])
            let dirty = try client.call("setGain", ["trackID": project.tracks[0].id.uuidString, "value": -6])
            let firstReply = try client.call("inspectProjectStructure"), first = try page(firstReply)
            #expect(try state(firstReply) == state(dirty))
            let token = try #require(first["reviewID"] as? String)
            let identity = ["reviewID", "revision", "projectID", "projectManifestSHA256", "sourceSHA256", "sourceByteCount", "reportSHA256", "reportByteCount"]
            var joined = Data(), current = first, pages = 0
            while true {
                pages += 1
                let offset = try #require(current["offset"] as? Int)
                #expect(offset == joined.count)
                let base64 = try #require(current["bytesBase64"] as? String)
                let bytes = try #require(Data(base64Encoded: base64))
                #expect(bytes.count <= 65_536 && !bytes.isEmpty)
                joined.append(bytes)
                for key in identity { #expect(String(describing: current[key]!) == String(describing: first[key]!)) }
                guard let next = current["nextOffset"] as? Int else { break }
                #expect(next == joined.count)
                let reply = try client.call("projectStructurePage", ["reviewID": token, "reviewOffset": next])
                #expect(try state(reply) == state(dirty))
                current = try page(reply)
            }
            #expect(pages > 1 && joined.count == first["reportByteCount"] as? Int)
            #expect(cprSHA256(joined) == first["reportSHA256"] as? String)
            let decoded = try JSONDecoder().decode(CPRNativeProjectBindingReport.self, from: joined)
            #expect(try decoded == CPRNativeProjectBindings.inspectPreserved(in: root))
            #expect(decoded.entries.count == 1 && decoded.tracks.count == 1)
            #expect(decoded.tracks.first?.busCandidates.count == 3)
            let closed = try client.call("closeProjectStructure", ["reviewID": token])
            #expect(closed["ok"] as? Bool == true && closed["projectStructure"] == nil)
            #expect(try state(closed) == state(dirty))
            #expect(error(try client.call("projectStructurePage", ["reviewID": token, "reviewOffset": 0])) == "structureToken")
            #expect(try client.call("undo")["ok"] as? Bool == true)
            #expect(try ProjectStore.load(from: root) == project)
        }
    }

    @Test func revisionTokensOffsetsAndProjectSwitchesCannotReuseAReport() throws {
        try workspace { root in
            let project = try BindingControl.package(at: root), client = Client()
            _ = try client.call("open", ["path": root.path])
            let first = try page(client.call("inspectProjectStructure"))
            let second = try page(client.call("inspectProjectStructure")), token = try #require(second["reviewID"] as? String)
            #expect(error(try client.call("projectStructurePage", ["reviewID": first["reviewID"]!, "reviewOffset": 0])) == "structureToken")
            for offset in [-1, 1, Int.max] {
                #expect(error(try client.call("projectStructurePage", ["reviewID": token, "reviewOffset": offset])) == "structureOffset")
            }
            #expect(error(try client.call("projectStructurePage", ["reviewID": token])) == "structureOffset")
            for command in ["inspectProjectStructure", "projectStructurePage", "closeProjectStructure"] {
                #expect(error(try client.call(command, ["reviewID": token, "reviewOffset": 0], expected: 0)) == "staleRevision")
            }
            #expect(try client.call("projectStructurePage", ["reviewID": token, "reviewOffset": 0])["ok"] as? Bool == true)
            _ = try client.call("setGain", ["trackID": project.tracks[0].id.uuidString, "value": -3])
            #expect(error(try client.call("projectStructurePage", ["reviewID": token, "reviewOffset": 0])) == "structureToken")
            let third = try page(client.call("inspectProjectStructure"))
            _ = try client.call("open", ["path": root.path, "discardChanges": true])
            #expect(error(try client.call("projectStructurePage", ["reviewID": third["reviewID"]!, "reviewOffset": 0])) == "structureToken")
        }
    }

    @Test func sourceReportAndManifestTamperingRevokeContinuationWithoutRepair() throws {
        try workspace { root in
            _ = try BindingControl.package(at: root)
            for relative in [ProjectStore.manifestName, CPRProject.originalRelativePath, CPRProject.reportRelativePath] {
                let client = Client(); _ = try client.call("open", ["path": root.path])
                let first = try page(client.call("inspectProjectStructure")), token = first["reviewID"]!
                let file = root.appendingPathComponent(relative), original = try Data(contentsOf: file)
                try Data("changed externally".utf8).write(to: file)
                let reply = try client.call("projectStructurePage", ["reviewID": token, "reviewOffset": 0])
                #expect(reply["ok"] as? Bool == false && reply["projectStructure"] == nil)
                #expect(try Data(contentsOf: file) == Data("changed externally".utf8))
                try original.write(to: file)
                #expect(error(try client.call("projectStructurePage", ["reviewID": token, "reviewOffset": 0])) == "structureToken")
            }
            // Even a semantically valid reserialization changes the preserved
            // report bytes and must revoke an already issued inspection token.
            let client = Client(); _ = try client.call("open", ["path": root.path])
            let first = try page(client.call("inspectProjectStructure")), token = first["reviewID"]!
            let file = root.appendingPathComponent(CPRProject.reportRelativePath)
            let original = try Data(contentsOf: file), changed = original + Data("\n ".utf8)
            try changed.write(to: file)
            #expect(try CPRProject.compatibilityReport(from: root) != nil)
            let reply = try client.call("projectStructurePage", ["reviewID": token, "reviewOffset": 0])
            #expect(reply["ok"] as? Bool == false && reply["projectStructure"] == nil)
            #expect(try Data(contentsOf: file) == changed)
            try original.write(to: file)
            #expect(error(try client.call("projectStructurePage", ["reviewID": token, "reviewOffset": 0])) == "structureToken")
        }
    }

    @Test func noProjectAndOrdinaryProjectHaveNoSavedStructure() throws {
        let client = Client()
        #expect(error(try client.call("inspectProjectStructure")) == "noProject")
        try workspace { root in
            _ = try ProjectStore.create(at: root)
            let opened = try client.call("open", ["path": root.path])
            let refused = try client.call("inspectProjectStructure")
            #expect(refused["ok"] as? Bool == false && refused["projectStructure"] == nil)
            #expect(try state(opened) == state(refused))
        }
    }
}
