import Foundation
import Testing
#if canImport(RebaseCore)
@testable import RebaseCore
#else
@testable import RebasePortable
#endif

/// Authored raw archives exercise publication and historical custody, not a
/// proprietary application's import or playback behavior.
struct SharedCPRImportTests {
    private func workspace(_ body: (URL) throws -> Void) throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("RebaseCPRImport-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false)
        defer { try? FileManager.default.removeItem(at: root) }
        try body(root)
    }

    private func source(at root: URL, name: String = "Authored source.cpr", options: CPRAudioControl.Options = .init()) throws -> (URL, Data, CPRInspection) {
        let url = root.appendingPathComponent(name)
        let bytes = CPRAudioControl.archive(options)
        try bytes.write(to: url, options: .withoutOverwriting)
        return (url, bytes, try CPRProject.inspect(from: url))
    }

    private func requireNoStaging(in root: URL) throws {
        #expect(try !FileManager.default.contentsOfDirectory(atPath: root.path).contains { $0.hasPrefix(".rebase-cpr-") })
    }

    @Test func reviewedAuthoredImportPublishesExactSourceAndReplayedReport() throws {
        try workspace { root in
            let (source, bytes, inspected) = try source(at: root, name: "Café 音源.cpr")
            #expect(inspected.canImport && !inspected.unsupported.isEmpty)
            let destination = root.appendingPathComponent("Imported Café 音源.rebaseproj")
            let result = try CPRProject.importProject(from: source, to: destination,
                allowPartial: true, expectedSHA256: inspected.sourceSHA256)
            #expect(result.report == inspected)
            #expect(result.originalRelativePath == CPRProject.originalRelativePath)
            #expect(result.project == inspected.recoveredProject)
            #expect(result.project.tracks.count == 1 && result.project.unresolvedAudioEvents.count == 1)
            #expect(result.project.tracks.flatMap(\.clips).isEmpty && result.project.cprMediaAttachments.isEmpty)
            #expect(try ProjectStore.load(from: destination) == result.project)
            #expect(try CPRProject.compatibilityReport(from: destination) == inspected)
            #expect(try Data(contentsOf: destination.appendingPathComponent(result.originalRelativePath)) == bytes)
            let encoder = JSONEncoder(); encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            #expect(try Data(contentsOf: destination.appendingPathComponent(CPRProject.reportRelativePath)) == encoder.encode(inspected))
            #expect(try FileManager.default.contentsOfDirectory(atPath: destination.appendingPathComponent("Media").path).isEmpty)
            #expect(try Data(contentsOf: source) == bytes)
            try requireNoStaging(in: root)
        }
    }

    @Test func partialRecoveryRequiresExplicitAcceptanceWithoutPublishing() throws {
        try workspace { root in
            let (source, bytes, inspected) = try source(at: root)
            #expect(inspected.canImport && !inspected.unsupported.isEmpty)
            let destination = root.appendingPathComponent("Refused.rebaseproj")
            for acceptance in [false, nil] as [Bool?] {
                #expect(throws: CPRProjectError.self) {
                    if let acceptance {
                        _ = try CPRProject.importProject(from: source, to: destination,
                            allowPartial: acceptance, expectedSHA256: inspected.sourceSHA256)
                    } else {
                        _ = try CPRProject.importProject(from: source, to: destination,
                            expectedSHA256: inspected.sourceSHA256)
                    }
                }
            }
            #expect(try FileManager.default.contentsOfDirectory(atPath: root.path) == [source.lastPathComponent])
            #expect(try Data(contentsOf: source) == bytes)
        }
    }

    @Test func changedSourceAfterReviewIsRejectedBeforePublication() throws {
        try workspace { root in
            let (source, _, inspected) = try source(at: root)
            var options = CPRAudioControl.Options(); options.gain = 0.5
            let replacement = CPRAudioControl.archive(options)
            try replacement.write(to: source)
            let changed = try CPRProject.inspect(from: source)
            #expect(changed.canImport && changed.sourceSHA256 != inspected.sourceSHA256)
            let destination = root.appendingPathComponent("Changed.rebaseproj")
            #expect(throws: CPRProjectError.self) {
                try CPRProject.importProject(from: source, to: destination,
                    allowPartial: true, expectedSHA256: inspected.sourceSHA256)
            }
            #expect(try FileManager.default.contentsOfDirectory(atPath: root.path) == [source.lastPathComponent])
            #expect(try Data(contentsOf: source) == replacement)
        }
    }

    @Test func existingFileAndDirectoryDestinationsAreNeverReplaced() throws {
        try workspace { root in
            let (source, bytes, inspected) = try source(at: root)
            let sentinel = Data("keep existing destination".utf8)
            for kind in ["file", "empty", "populated"] {
                let destination = root.appendingPathComponent(kind + ".rebaseproj")
                if kind == "file" { try sentinel.write(to: destination) }
                else {
                    try FileManager.default.createDirectory(at: destination, withIntermediateDirectories: false)
                    if kind == "populated" { try sentinel.write(to: destination.appendingPathComponent("Keep.bin")) }
                }
                #expect(throws: CPRProjectError.self) {
                    try CPRProject.importProject(from: source, to: destination,
                        allowPartial: true, expectedSHA256: inspected.sourceSHA256)
                }
                if kind == "file" { #expect(try Data(contentsOf: destination) == sentinel) }
                else {
                    #expect(try FileManager.default.contentsOfDirectory(atPath: destination.path) == (kind == "empty" ? [] : ["Keep.bin"]))
                    if kind == "populated" { #expect(try Data(contentsOf: destination.appendingPathComponent("Keep.bin")) == sentinel) }
                }
            }
            #expect(try Data(contentsOf: source) == bytes)
            try requireNoStaging(in: root)
        }
    }

    @Test func savedEditsDoNotRewriteImportBaselineAndTamperingIsRejected() throws {
        try workspace { root in
            let (source, bytes, inspected) = try source(at: root)
            let destination = root.appendingPathComponent("History.rebaseproj")
            let imported = try CPRProject.importProject(from: source, to: destination,
                allowPartial: true, expectedSHA256: inspected.sourceSHA256)
            let reportURL = destination.appendingPathComponent(CPRProject.reportRelativePath)
            let originalURL = destination.appendingPathComponent(CPRProject.originalRelativePath)
            let reportBytes = try Data(contentsOf: reportURL)
            var edited = imported.project; edited.name = "Edited application project"; edited.tracks[0].gainDB = -6
            try ProjectStore.save(edited, to: destination)
            #expect(try ProjectStore.load(from: destination) == edited)
            #expect(try CPRProject.compatibilityReport(from: destination) == imported.report)
            #expect(try Data(contentsOf: reportURL) == reportBytes)
            #expect(try Data(contentsOf: originalURL) == bytes)
            let savedManifest = try Data(contentsOf: destination.appendingPathComponent(ProjectStore.manifestName))
            var json = try #require(JSONSerialization.jsonObject(with: reportBytes) as? [String: Any])
            json["recoveredFacts"] = ["Unverified replacement claim"]
            let forged = try JSONSerialization.data(withJSONObject: json)
            try forged.write(to: reportURL)
            #expect(throws: CPRProjectError.self) { try CPRProject.compatibilityReport(from: destination) }
            #expect(throws: (any Error).self) { try ProjectStore.load(from: destination) }
            #expect(try Data(contentsOf: reportURL) == forged)
            #expect(try Data(contentsOf: destination.appendingPathComponent(ProjectStore.manifestName)) == savedManifest)
            try reportBytes.write(to: reportURL)
            var damaged = bytes; damaged[damaged.count - 1] ^= 1; try damaged.write(to: originalURL)
            #expect(throws: CPRProjectError.self) { try CPRProject.compatibilityReport(from: destination) }
            #expect(try Data(contentsOf: source) == bytes)
            #expect(try Data(contentsOf: reportURL) == reportBytes)
            try requireNoStaging(in: root)
        }
    }

    @Test func failedPublicationCleansOnlyItsStagingAndRetainsSource() throws {
        try workspace { root in
            let (source, bytes, inspected) = try source(at: root)
            // A component longer than APFS/NTFS limits reaches publication only
            // after a fully validated sibling stage; the source remains intact.
            let destination = root.appendingPathComponent(String(repeating: "x", count: 300) + ".rebaseproj")
            #expect(throws: RebaseCoreError.self) {
                try CPRProject.importProject(from: source, to: destination,
                    allowPartial: true, expectedSHA256: inspected.sourceSHA256)
            }
            #expect(try FileManager.default.contentsOfDirectory(atPath: root.path) == [source.lastPathComponent])
            #expect(try Data(contentsOf: source) == bytes)
        }
    }

    #if !os(Windows)
    @Test func danglingDestinationLinkIsNotFollowedOrReplaced() throws {
        try workspace { root in
            let (source, bytes, inspected) = try source(at: root)
            let destination = root.appendingPathComponent("Dangling.rebaseproj")
            let target = root.appendingPathComponent("Absent.rebaseproj")
            try FileManager.default.createSymbolicLink(at: destination, withDestinationURL: target)
            #expect(throws: CPRProjectError.self) {
                try CPRProject.importProject(from: source, to: destination,
                    allowPartial: true, expectedSHA256: inspected.sourceSHA256)
            }
            #expect(try FileManager.default.destinationOfSymbolicLink(atPath: destination.path) == target.path)
            #expect(!FileManager.default.fileExists(atPath: target.path))
            #expect(try Data(contentsOf: source) == bytes)
            try requireNoStaging(in: root)
        }
    }
    #endif
}
