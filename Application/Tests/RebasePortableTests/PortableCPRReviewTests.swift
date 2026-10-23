import Foundation
import Testing
@testable import RebasePortable

struct PortableCPRReviewTests {
    private final class Client {
        let session: PortableSession
        var id = 0
        var revision = 0
        init(_ session: PortableSession = PortableSession()) { self.session = session }
        func call(_ command: String, _ extra: [String: Any] = [:], expected: Int? = nil) throws -> [String: Any] {
            id += 1
            var request: [String: Any] = ["protocol": 1, "id": id, "command": command,
                                           "expectedRevision": expected ?? revision]
            request.merge(extra) { _, new in new }
            let reply = try #require(JSONSerialization.jsonObject(with: session.process(JSONSerialization.data(withJSONObject: request))) as? [String: Any])
            revision = try #require((reply["state"] as? [String: Any])?["revision"] as? Int)
            return reply
        }
    }
    private func workspace(_ body: (URL) throws -> Void) throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("RebaseCPRProtocol-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false)
        defer { try? FileManager.default.removeItem(at: root) }
        try body(root)
    }
    private func source(_ directory: URL, name: String = "Authored Café 音源.cpr") throws -> URL {
        let path = directory.appendingPathComponent(name)
        try CPRAudioControl.archive().write(to: path)
        return path
    }
    private func ordinary(_ directory: URL) throws -> (URL, Project) {
        let root = directory.appendingPathComponent("Existing.rebaseproj")
        let project = Project(name: "Existing project", tracks: [Track(name: "Existing track")])
        try ProjectStore.save(project, to: root)
        return (root, project)
    }
    private func state(_ reply: [String: Any]) throws -> [String: Any] { try #require(reply["state"] as? [String: Any]) }
    private func stateBytes(_ reply: [String: Any]) throws -> Data { try JSONSerialization.data(withJSONObject: state(reply), options: [.sortedKeys]) }
    private func review(_ reply: [String: Any]) throws -> [String: Any] { try #require(reply["cprReview"] as? [String: Any]) }
    private func error(_ reply: [String: Any]) -> String? { (reply["error"] as? [String: Any])?["code"] as? String }
    private func arguments(_ review: [String: Any], to destination: URL) throws -> [String: Any] {
        ["reviewID": try #require(review["reviewID"] as? String),
         "sourceSHA256": try #require(review["sourceSHA256"] as? String),
         "path": destination.path, "allowPartial": true]
    }
    private func modified(_ report: CPRInspection, facts: [String]? = nil, metadata: [String]? = nil,
                          tracks: [CPRRecoveredTrack]? = nil, defaults: [String]? = nil,
                          unsupported: [CPRUnsupportedItem]? = nil, schema: Int? = nil, profile: String? = CPRProject.currentInterpretationProfile) -> CPRInspection {
        .init(schemaVersion: schema ?? report.schemaVersion, interpretationProfile: profile, nativeClock: report.nativeClock,
              sourceName: report.sourceName, sourceSHA256: report.sourceSHA256, sourceByteCount: report.sourceByteCount,
              sections: report.sections, recoveredFacts: facts ?? report.recoveredFacts,
              metadataFacts: metadata ?? report.metadataFacts, recoveredTracks: tracks ?? report.recoveredTracks,
              nativeObjects: report.nativeObjects, applicationDefaults: defaults ?? report.applicationDefaults,
              unsupported: unsupported ?? report.unsupported, recoveredProject: report.recoveredProject, audioSetup: report.audioSetup)
    }

    @Test func inspectionAndPagesDoNotChangeDocumentRevisionSelectionOrHistory() throws {
        try workspace { directory in
            let (root, project) = try ordinary(directory), raw = try source(directory), client = Client()
            _ = try client.call("open", ["path": root.path])
            _ = try client.call("selectTrack", ["trackID": project.tracks[0].id.uuidString])
            let edited = try client.call("setGain", ["trackID": project.tracks[0].id.uuidString, "value": -6])
            let inspected = try client.call("inspectCPR", ["path": raw.path]), first = try review(inspected)
            #expect(try stateBytes(inspected) == stateBytes(edited))
            #expect(first["historical"] as? Bool == false && first["canImport"] as? Bool == true)
            #expect(first["sourceName"] as? String == raw.lastPathComponent)
            #expect(first["sourceSHA256"] as? String == PortableSHA256.hexDigest(try Data(contentsOf: raw)))
            #expect(first["recoveredTrackCount"] as? Int == 1 && first["recoveredClipCount"] as? Int == 0)
            #expect(first["unresolvedEventCount"] as? Int == 1)
            let page = try client.call("cprReviewPage", ["reviewID": first["reviewID"]!, "reviewOffset": 0])
            #expect(try stateBytes(page) == stateBytes(edited))
            #expect(try JSONSerialization.data(withJSONObject: review(page), options: [.sortedKeys]) == JSONSerialization.data(withJSONObject: first, options: [.sortedKeys]))
            let cancelled = try client.call("cancelCPRReview", ["reviewID": first["reviewID"]!])
            #expect(try stateBytes(cancelled) == stateBytes(edited))
            #expect(cancelled["cprReview"] == nil)
        }
    }

    @Test func tokensAreSupersededCancelledAndNotAuthorizedByHashAlone() throws {
        try workspace { directory in
            let client = Client(), firstSource = try source(directory), secondSource = try source(directory, name: "Other name.cpr")
            let first = try review(client.call("inspectCPR", ["path": firstSource.path]))
            let second = try review(client.call("inspectCPR", ["path": secondSource.path]))
            #expect(first["sourceSHA256"] as? String == second["sourceSHA256"] as? String)
            #expect(first["reviewID"] as? String != second["reviewID"] as? String)
            let destination = directory.appendingPathComponent("New.rebaseproj")
            #expect(error(try client.call("importCPR", arguments(first, to: destination))) == "reviewToken")
            #expect(error(try client.call("cancelCPRReview", ["reviewID": first["reviewID"]!])) == "reviewToken")
            var bad = try arguments(second, to: destination); bad["reviewID"] = UUID().uuidString
            #expect(error(try client.call("importCPR", bad)) == "reviewToken")
            bad = try arguments(second, to: destination); bad["sourceSHA256"] = String(repeating: "0", count: 64)
            #expect(error(try client.call("importCPR", bad)) == "reviewSource")
            _ = try client.call("cancelCPRReview", ["reviewID": second["reviewID"]!])
            #expect(error(try client.call("importCPR", arguments(second, to: destination))) == "reviewToken")
            #expect(error(try client.call("cprReviewPage", ["reviewID": second["reviewID"]!, "reviewOffset": 0])) == "reviewToken")
            #expect(!FileManager.default.fileExists(atPath: destination.path))
        }
    }

    @Test func allReviewAndImportCommandsRequireExactRevision() throws {
        try workspace { directory in
            let (root, _) = try ordinary(directory), raw = try source(directory), client = Client()
            let opened = try client.call("open", ["path": root.path])
            let current = try review(client.call("inspectCPR", ["path": raw.path]))
            for command in ["inspectCPR", "cprReviewPage", "cancelCPRReview", "cprImportReport", "importCPR"] {
                let reply = try client.call(command, ["path": raw.path, "reviewID": current["reviewID"]!, "reviewOffset": 0], expected: 0)
                #expect(error(reply) == "staleRevision")
                #expect(try stateBytes(reply) == stateBytes(opened))
            }
            #expect(try client.call("cprReviewPage", ["reviewID": current["reviewID"]!, "reviewOffset": 0])["ok"] as? Bool == true)
        }
    }

    @Test func explicitPartialAcceptanceAndNewDestinationAreRequired() throws {
        try workspace { directory in
            let raw = try source(directory), client = Client(), inspected = try review(client.call("inspectCPR", ["path": raw.path]))
            let destination = directory.appendingPathComponent("New.rebaseproj")
            var args = try arguments(inspected, to: destination)
            args.removeValue(forKey: "allowPartial")
            #expect(error(try client.call("importCPR", args)) == "partialImportRequired")
            args["allowPartial"] = false
            #expect(error(try client.call("importCPR", args)) == "partialImportRequired")
            #expect(!FileManager.default.fileExists(atPath: destination.path))
            args = try arguments(inspected, to: directory.appendingPathComponent("wrong.txt"))
            #expect(error(try client.call("importCPR", args)) == "destination")
            for kind in ["file", "directory"] {
                let existing = directory.appendingPathComponent(kind + ".rebaseproj")
                if kind == "file" { try Data("keep".utf8).write(to: existing) }
                else { try FileManager.default.createDirectory(at: existing, withIntermediateDirectories: false) }
                #expect(try client.call("importCPR", arguments(inspected, to: existing))["ok"] as? Bool == false)
                if kind == "file" { #expect(try Data(contentsOf: existing) == Data("keep".utf8)) }
                else { #expect(try FileManager.default.contentsOfDirectory(atPath: existing.path).isEmpty) }
            }
            #expect(try client.call("cprReviewPage", ["reviewID": inspected["reviewID"]!, "reviewOffset": 0])["ok"] as? Bool == true)
        }
    }

    @Test func changedSourceCannotBeImportedAfterItsReview() throws {
        try workspace { directory in
            let raw = try source(directory), client = Client(), inspected = try review(client.call("inspectCPR", ["path": raw.path]))
            var options = CPRAudioControl.Options(); options.gain = 0.5
            let changed = CPRAudioControl.archive(options); try changed.write(to: raw)
            let destination = directory.appendingPathComponent("Changed.rebaseproj")
            let refused = try client.call("importCPR", arguments(inspected, to: destination))
            #expect(refused["ok"] as? Bool == false && client.revision == 0)
            #expect(!FileManager.default.fileExists(atPath: destination.path))
            #expect(try Data(contentsOf: raw) == changed)
            #expect(try FileManager.default.contentsOfDirectory(atPath: directory.path) == [raw.lastPathComponent])
        }
    }

    @Test func importPreservesExactSourceAndReportThenReplacesSessionCleanly() throws {
        try workspace { directory in
            let (root, oldProject) = try ordinary(directory), raw = try source(directory), client = Client()
            _ = try client.call("open", ["path": root.path])
            _ = try client.call("setGain", ["trackID": oldProject.tracks[0].id.uuidString, "value": -9])
            let inspected = try review(client.call("inspectCPR", ["path": raw.path]))
            let destination = directory.appendingPathComponent("Imported.rebaseproj")
            var args = try arguments(inspected, to: destination)
            #expect(error(try client.call("importCPR", args)) == "unsavedChanges")
            #expect(!FileManager.default.fileExists(atPath: destination.path))
            args["discardChanges"] = true
            let imported = try client.call("importCPR", args), state = try state(imported)
            #expect(imported["ok"] as? Bool == true && client.revision == 3)
            #expect(state["dirty"] as? Bool == false && state["canUndo"] as? Bool == false && state["canRedo"] as? Bool == false)
            #expect(state["needsSaveAs"] as? Bool == false)
            let report = try CPRProject.inspect(from: raw)
            #expect(try ProjectStore.load(from: destination) == report.recoveredProject)
            #expect(try CPRProject.compatibilityReport(from: destination) == report)
            let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            #expect(try Data(contentsOf: destination.appendingPathComponent(CPRProject.reportRelativePath)) == encoder.encode(report))
            #expect(try Data(contentsOf: destination.appendingPathComponent(CPRProject.originalRelativePath)) == Data(contentsOf: raw))
            #expect(try ProjectStore.load(from: root) == oldProject)
            #expect(error(try client.call("importCPR", args)) == "reviewToken")
        }
    }

    @Test func savingDirtyDocumentKeepsReviewAuthorizationForLaterImport() throws {
        try workspace { directory in
            for copy in [false, true] {
                let local = directory.appendingPathComponent(copy ? "Copy" : "Direct")
                try FileManager.default.createDirectory(at: local, withIntermediateDirectories: false)
                let (root, project) = try ordinary(local), raw = try source(local), client = Client()
                _ = try client.call("open", ["path": root.path, "asCopy": copy])
                let inspected = try review(client.call("inspectCPR", ["path": raw.path]))
                _ = try client.call("setGain", ["trackID": project.tracks[0].id.uuidString, "value": -6])
                let savedRoot = copy ? local.appendingPathComponent("Saved.rebaseproj") : root
                let saved = try client.call(copy ? "saveAs" : "save", copy ? ["path": savedRoot.path] : [:])
                #expect(saved["ok"] as? Bool == true)
                let imported = try client.call("importCPR", arguments(inspected, to: local.appendingPathComponent("Imported.rebaseproj")))
                #expect(imported["ok"] as? Bool == true)
                #expect(try ProjectStore.load(from: savedRoot).tracks[0].gainDB == -6)
            }
        }
    }

    @Test func historicalReviewIsReadOnlyAndRevalidatesReportAndSource() throws {
        try workspace { directory in
            let raw = try source(directory), client = Client(), initial = try review(client.call("inspectCPR", ["path": raw.path]))
            let destination = directory.appendingPathComponent("History.rebaseproj")
            _ = try client.call("importCPR", arguments(initial, to: destination))
            let project = try ProjectStore.load(from: destination)
            let edited = try client.call("setGain", ["trackID": project.tracks[0].id.uuidString, "value": -3])
            let historicalReply = try client.call("cprImportReport"), historical = try review(historicalReply)
            #expect(try stateBytes(historicalReply) == stateBytes(edited))
            #expect(historical["historical"] as? Bool == true && historical["canImport"] as? Bool == false)
            #expect(error(try client.call("importCPR", arguments(historical, to: directory.appendingPathComponent("Forbidden.rebaseproj")))) == "reviewReadOnly")
            #expect(try client.call("cprReviewPage", ["reviewID": historical["reviewID"]!, "reviewOffset": 0])["ok"] as? Bool == true)
            let reportURL = destination.appendingPathComponent(CPRProject.reportRelativePath)
            let sourceURL = destination.appendingPathComponent(CPRProject.originalRelativePath)
            let reportBytes = try Data(contentsOf: reportURL), originalBytes = try Data(contentsOf: sourceURL)
            var json = try #require(JSONSerialization.jsonObject(with: reportBytes) as? [String: Any]); json["recoveredFacts"] = ["forged"]
            try JSONSerialization.data(withJSONObject: json).write(to: reportURL)
            #expect(try client.call("cprReviewPage", ["reviewID": historical["reviewID"]!, "reviewOffset": 0])["ok"] as? Bool == false)
            #expect(try client.call("cprImportReport")["ok"] as? Bool == false)
            try reportBytes.write(to: reportURL)
            var damaged = originalBytes; damaged[damaged.count - 1] ^= 1; try damaged.write(to: sourceURL)
            let rejected = try client.call("cprImportReport")
            #expect(rejected["ok"] as? Bool == false)
            #expect(try stateBytes(rejected) == stateBytes(edited))
            #expect(try Data(contentsOf: raw) == originalBytes)
            #expect(try Data(contentsOf: reportURL) == reportBytes)
        }
    }

    @Test func unknownOnlySourceCanBeReviewedButNeverImported() throws {
        try workspace { directory in
            func be(_ value: UInt32) -> Data { var v = value.bigEndian; return withUnsafeBytes(of: &v) { Data($0) } }
            func text(_ value: String) -> Data { be(UInt32(value.utf8.count)) + Data(value.utf8) }
            let root = text("Unknown") + text("OpaqueClass")
            let section = Data("ROOT".utf8) + be(UInt32(root.count)) + root + Data("ARCH".utf8) + be(3) + Data([1, 2, 3])
            let bytes = Data("RIFF".utf8) + be(UInt32(section.count)) + Data("NUND".utf8) + section
            let raw = directory.appendingPathComponent("Unknown.cpr"); try bytes.write(to: raw)
            let client = Client(), result = try review(client.call("inspectCPR", ["path": raw.path]))
            #expect(result["canImport"] as? Bool == false && result["totalItems"] as? Int ?? 0 > 0)
            let destination = directory.appendingPathComponent("NoInventedProject.rebaseproj")
            #expect(error(try client.call("importCPR", arguments(result, to: destination))) == "unsupportedCPR")
            #expect(!FileManager.default.fileExists(atPath: destination.path))
        }
    }

    @Test func pagesPreserveEveryItemAndSectionOrderWithinEncodedLimits() throws {
        try workspace { directory in
            let base = try CPRProject.inspect(from: source(directory))
            let facts = (0..<70).map { "Fact \($0)" }, metadata = (0..<45).map { "Tag \($0)" }
            let report = modified(base, facts: facts, metadata: metadata, defaults: ["Default A", "Default B"])
            let snapshot = try PortableCPRReviewSnapshot(report: report, historical: false)
            var offset = 0, items: [PortableCPRReview.Item] = [], pages = 0
            repeat {
                let page = try snapshot.page(offset: offset); pages += 1
                #expect(page.offset == offset && page.items.count <= 32 && !page.items.isEmpty)
                #expect(try JSONEncoder().encode(page).count <= 131_072)
                #expect(page.totalItems == facts.count + metadata.count + report.recoveredTracks.count + report.unsupported.count + 2)
                items += page.items
                guard let next = page.nextOffset else { break }
                #expect(next == offset + page.items.count); offset = next
            } while true
            #expect(pages >= 4)
            #expect(items.filter { $0.section == "recovered" }.map(\.detail) == facts)
            #expect(items.filter { $0.section == "metadata" }.map(\.detail) == metadata)
            let order = ["recovered": 0, "tracks": 1, "unresolved": 2, "defaults": 3, "metadata": 4]
            let sections = items.map { order[$0.section]! }; #expect(sections == sections.sorted())
            #expect(throws: PortableCPRReviewError.self) { try snapshot.page(offset: -1) }
            #expect(throws: PortableCPRReviewError.self) { try snapshot.page(offset: items.count) }
            #expect(throws: PortableCPRReviewError.self) { try snapshot.page(offset: Int.max) }
        }
    }

    @Test func byteBoundsRejectOversizedRowsAndReportsWithoutTruncation() throws {
        try workspace { directory in
            let base = try CPRProject.inspect(from: source(directory))
            // Escaping doubles the encoded bytes; counting Swift characters
            // alone would incorrectly accept this individual row.
            let oversized = modified(base, metadata: [String(repeating: "\"", count: 70_000)])
            #expect(throws: PortableCPRReviewError.self) { try PortableCPRReviewSnapshot(report: oversized, historical: false) }
            let report = modified(base, facts: [String(repeating: "x", count: PortableCPRReviewSnapshot.maximumReportBytes)])
            #expect(throws: PortableCPRReviewError.self) { try PortableCPRReviewSnapshot(report: report, historical: false) }
            let escaped = modified(base, facts: (0..<5).map { _ in String(repeating: "\"", count: 20_000) })
            let snapshot = try PortableCPRReviewSnapshot(report: escaped, historical: false)
            let page = try snapshot.page(offset: 0)
            #expect(page.items.count < 5 && page.nextOffset != nil)
            #expect(try JSONEncoder().encode(page).count <= PortableCPRReviewSnapshot.maximumPageBytes)
        }
    }

    @Test func emptyProjectionAndHistoricalV1ProfileAreExplicit() throws {
        try workspace { directory in
            let base = try CPRProject.inspect(from: source(directory))
            let empty = modified(base, facts: [], metadata: [], tracks: [], defaults: [], unsupported: [], schema: 1, profile: nil)
            let page = try PortableCPRReviewSnapshot(report: empty, historical: true).page(offset: 0)
            #expect(page.totalItems == 0 && page.items.isEmpty && page.nextOffset == nil)
            #expect(page.interpretationProfile == "cpr-static-subset-v1" && page.historical && !page.canImport)
        }
    }

    @Test func publicationReadbackFailurePreservesOldSessionAndRevokesToken() throws {
        try workspace { directory in
            let session = PortableSession(importedSnapshotLoader: { _ in throw CocoaError(.fileReadNoPermission) })
            let client = Client(session), (root, _) = try ordinary(directory), raw = try source(directory)
            let opened = try client.call("open", ["path": root.path])
            let inspected = try review(client.call("inspectCPR", ["path": raw.path]))
            let destination = directory.appendingPathComponent("Published.rebaseproj")
            let args = try arguments(inspected, to: destination)
            let failed = try client.call("importCPR", args)
            #expect(error(failed) == "importPublished")
            #expect(try stateBytes(failed) == stateBytes(opened))
            #expect(try ProjectStore.load(from: destination) == CPRProject.inspect(from: raw).recoveredProject)
            #expect(error(try client.call("importCPR", args)) == "reviewToken")
            #expect((failed["error"] as? [String: Any])?["message"] as? String != nil)
        }
    }

    @Test func publicationReadbackMustMatchImportedModelAndManifest() throws {
        try workspace { directory in
            let session = PortableSession(importedSnapshotLoader: { root in
                let snapshot = try ProjectStore.loadSnapshot(from: root)
                var model = snapshot.project; model.name = "Unverified replacement"
                return (model, snapshot.manifest)
            })
            let client = Client(session), raw = try source(directory), inspected = try review(client.call("inspectCPR", ["path": raw.path]))
            let destination = directory.appendingPathComponent("Published.rebaseproj")
            #expect(error(try client.call("importCPR", arguments(inspected, to: destination))) == "importPublished")
            #expect(client.revision == 0)
            #expect(try ProjectStore.load(from: destination).name != "Unverified replacement")
        }
    }
}
