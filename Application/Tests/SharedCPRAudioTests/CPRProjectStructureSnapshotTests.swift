import Foundation
import Testing
#if canImport(RebaseCore)
@testable import RebaseCore
#else
@testable import RebasePortable
#endif

@Suite struct CPRProjectStructureSnapshotTests {
    private func workspace(_ body: (URL) throws -> Void) throws {
        let fm = FileManager.default
        let base = ProcessInfo.processInfo.environment["REBASE_TEST_WORK_ROOT"].map { URL(fileURLWithPath: $0) } ?? fm.temporaryDirectory
        let root = base.appendingPathComponent("StructureSnapshot-" + UUID().uuidString)
        try fm.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? fm.removeItem(at: root) }
        try body(root)
    }

    @Test func snapshotRetainsCompleteTypedSourceAndPreservesPackageBytes() throws {
        try workspace { root in
            let project = try BindingControl.package(at: root)
            let files = [ProjectStore.manifestName, CPRProject.originalRelativePath, CPRProject.reportRelativePath]
            let before = try files.map { try Data(contentsOf: root.appendingPathComponent($0)) }
            let value = try CPRProjectStructureSnapshot.inspect(in: root, expectedProjectID: project.id,
                expectedManifestSHA256: cprSHA256(before[0]))
            #expect(value.projectID == project.id && value.projectManifestSHA256 == cprSHA256(before[0]))
            #expect(value.reportSHA256 == cprSHA256(value.reportBytes))
            #expect(try JSONDecoder().decode(CPRNativeProjectBindingReport.self, from: value.reportBytes) == value.report)
            #expect(value.report.entries.count == 1 && value.report.tracks.count == 1)
            #expect(value.report.tracks.first?.unresolved.contains("effectiveRoutingUnresolved") == true)
            try value.verify(in: root)
            #expect(try files.map { try Data(contentsOf: root.appendingPathComponent($0)) } == before)
            // An explicit development run can retain this authored package for
            // exercising the real app view. Normal tests leave no fixture.
            if let destination = ProcessInfo.processInfo.environment["REBASE_STRUCTURE_FIXTURE_OUTPUT"] {
                try FileManager.default.copyItem(at: root, to: URL(fileURLWithPath: destination))
            }
        }
    }

    @Test func identityManifestSourceAndImportReportAreRevalidated() throws {
        try workspace { root in
            let project = try BindingControl.package(at: root)
            #expect(throws: CPRProjectError.self) { try CPRProjectStructureSnapshot.inspect(in: root, expectedProjectID: UUID()) }
            #expect(throws: CPRProjectError.self) { try CPRProjectStructureSnapshot.inspect(in: root,
                expectedProjectID: project.id, expectedManifestSHA256: String(repeating: "0", count: 64)) }
            let value = try CPRProjectStructureSnapshot.inspect(in: root, expectedProjectID: project.id)
            for relative in [ProjectStore.manifestName, CPRProject.originalRelativePath, CPRProject.reportRelativePath] {
                let file = root.appendingPathComponent(relative), original = try Data(contentsOf: file)
                try Data("changed externally".utf8).write(to: file)
                #expect(throws: (any Error).self) { try value.verify(in: root) }
                #expect(try Data(contentsOf: file) == Data("changed externally".utf8))
                try original.write(to: file)
            }
            let reportURL = root.appendingPathComponent(CPRProject.reportRelativePath)
            let reportBytes = try Data(contentsOf: reportURL)
            let whitespaceRewrite = reportBytes + Data("\n ".utf8)
            try whitespaceRewrite.write(to: reportURL)
            #expect(try CPRProject.compatibilityReport(from: root) != nil)
            #expect(throws: (any Error).self) { try value.verify(in: root) }
            #expect(try Data(contentsOf: reportURL) == whitespaceRewrite)
            try reportBytes.write(to: reportURL)
            try value.verify(in: root)
        }
    }

    @Test(.enabled(if: ProcessInfo.processInfo.environment["REBASE_SMOKE_PROJECT_STRUCTURE_FIXTURE"] != nil,
                   "Explicit deterministic authored fixture export only"))
    func exportDeterministicWindowsStructureFixtures() throws {
        let path = try #require(ProcessInfo.processInfo.environment["REBASE_SMOKE_PROJECT_STRUCTURE_FIXTURE"])
        let destination = URL(fileURLWithPath: path)
        try exportStructureFixtures(to: destination)
        let original = try fixtureFiles(in: destination)
        // A repeat build must not depend on the filesystem path or UUID defaults.
        try workspace { repeatRoot in
            let repeated = repeatRoot.appendingPathComponent("Repeated")
            try exportStructureFixtures(to: repeated)
            #expect(try fixtureFiles(in: repeated) == original)
        }
        #expect(throws: (any Error).self) { try exportStructureFixtures(to: destination) }
        #expect(try fixtureFiles(in: destination) == original)
    }

    private func fixtureFiles(in root: URL) throws -> [String: Data] {
        let enumerator = try #require(FileManager.default.enumerator(at: root,
            includingPropertiesForKeys: [.isRegularFileKey], options: []))
        var files: [String: Data] = [:]
        for case let file as URL in enumerator where try file.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile == true {
            files[String(file.path.dropFirst(root.path.count + 1))] = try Data(contentsOf: file)
        }
        return files
    }

    private func exportStructureFixtures(to destination: URL) throws {
        let fm = FileManager.default
        guard !fm.fileExists(atPath: destination.path) else {
            throw RebaseCoreError.invalidProject("Authored structure fixture destination already exists.")
        }
        try fm.createDirectory(at: destination, withIntermediateDirectories: false)
        // Preserve a failed generation for diagnosis. Never repair a previous
        // export or change either historical report or preserved source bytes.
        var cases: [[String: Any]] = []
        for (ordinal, name) in ["small", "large"].enumerated() {
            let stem = ordinal == 0 ? "Small" : "Large"
            let root = destination.appendingPathComponent(stem + ".rebaseproj")
            var options = BindingControl.Options()
            if ordinal == 1 {
                options.fields = [.object("OutputBusValue", [.integer("Value", 27)]),
                    .object("Volume", [.number("Value", 1.0.bitPattern)]),
                    .object("OutputBus", [.integer("Bus UID", 11), .integer("Bus Type", 1),
                        .text("Name", "Authored multi-page output"),
                        .list("Child Bus", (0..<3).map { index in
                            [.integer("Bus UID", Int64(27 + index)),
                             .text("Name", String(repeating: "Authored child bus ", count: 1600))]
                        })])]
            }
            _ = try BindingControl.package(at: root, options: options)
            let suffix = ordinal == 0 ? "1" : "2"
            func fixed(_ prefix: String) throws -> UUID {
                try #require(UUID(uuidString: prefix + "-0000-4000-8000-00000000000" + suffix))
            }
            let project = Project(id: try fixed("10000000"), name: "Authored " + name + " structure",
                tracks: [Track(id: try fixed("20000000"), name: "Application track")],
                tempoMap: TempoMap(events: [TempoEvent(id: try fixed("30000000"), beat: 0, bpm: 120)]),
                signatureMap: SignatureMap(events: [SignatureEvent(id: try fixed("40000000"), beat: 0, numerator: 4, denominator: 4)]))
            try ProjectStore.save(project, to: root)
            let files = [ProjectStore.manifestName, CPRProject.originalRelativePath, CPRProject.reportRelativePath]
            let before = try files.map { try Data(contentsOf: root.appendingPathComponent($0)) }
            let snapshot = try CPRProjectStructureSnapshot.inspect(in: root, expectedProjectID: project.id,
                expectedManifestSHA256: cprSHA256(before[0]))
            let roundTrip = try JSONDecoder().decode(CPRNativeProjectBindingReport.self, from: snapshot.reportBytes)
            #expect(roundTrip == snapshot.report)
            #expect(snapshot.report.entries.count == 1 && snapshot.report.tracks.count == 1)
            #expect(snapshot.report.tracks[0].unresolved.contains("effectiveRoutingUnresolved"))
            if ordinal == 0 { try #require(snapshot.reportBytes.count < 65536) }
            else { try #require(snapshot.reportBytes.count > 65536 && snapshot.reportBytes.count < 262144) }
            try snapshot.verify(in: root)
            #expect(try files.map { try Data(contentsOf: root.appendingPathComponent($0)) } == before)
            let reportName = stem + ".structure.json"
            try snapshot.reportBytes.write(to: destination.appendingPathComponent(reportName), options: .withoutOverwriting)
            cases.append(["name": name, "root": stem + ".rebaseproj", "projectID": project.id.uuidString,
                "trackID": try #require(project.tracks.first).id.uuidString,
                "sourceSHA256": snapshot.report.sourceSHA256, "sourceBytes": snapshot.report.sourceByteCount,
                "reportSHA256": snapshot.reportSHA256, "reportBytes": snapshot.reportBytes.count,
                "reportFile": reportName, "manifestSHA256": snapshot.projectManifestSHA256,
                "counts": ["entries": snapshot.report.entries.count, "tracks": snapshot.report.tracks.count,
                    "issues": snapshot.report.issues.count, "lists": snapshot.report.lists.count,
                    "nativeObjects": snapshot.report.nativeObjects.count, "resourceAssociations": snapshot.report.resourceAssociations.count],
                "files": files.enumerated().map { index, path -> [String: Any] in
                    ["path": path, "bytes": before[index].count, "sha256": cprSHA256(before[index])]
                }])
        }
        let here = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let generatorFiles = ["CPRNativeProjectBindingsTests.swift", "CPRProjectStructureSnapshotTests.swift"]
        var generatorSHA256: [String: String] = [:]
        for name in generatorFiles { generatorSHA256[name] = cprSHA256(try Data(contentsOf: here.appendingPathComponent(name))) }
        let expected: [String: Any] = ["schema": "rebase.project-structure-fixtures.v1",
            "evidenceClass": "authored-synthetic-control", "cases": cases, "generatorSHA256": generatorSHA256,
            "scope": "Forward-authored counted inputs and historical replay packages. No reference execution, reference-valid project, effective routing or audio equivalence claim."]
        try JSONSerialization.data(withJSONObject: expected, options: [.prettyPrinted, .sortedKeys])
            .write(to: destination.appendingPathComponent("expected.json"), options: .withoutOverwriting)
    }

    @Test func ordinaryProjectDoesNotAcquireInventedSourceStructure() throws {
        try workspace { root in
            let project = try ProjectStore.create(at: root)
            #expect(throws: CPRProjectError.self) { try CPRProjectStructureSnapshot.inspect(in: root, expectedProjectID: project.id) }
            #expect(!FileManager.default.fileExists(atPath: root.appendingPathComponent("Compatibility").path))
        }
    }

    @Test func oversizedReportIsRefusedRatherThanTruncated() throws {
        try workspace { root in
            var options = BindingControl.Options()
            options.fields = [.object("OutputBus", [.list("Child Bus", (0..<190).map {
                [.integer("Bus UID", Int64($0)), .text("Name", String(repeating: "x", count: 46_000))]
            })])]
            let project = try BindingControl.package(at: root, options: options)
            let inspected = try CPRNativeProjectBindings.inspectPreserved(in: root)
            let report = try #require(inspected)
            #expect(try JSONEncoder().encode(report).count > CPRProjectStructureSnapshot.maximumReportBytes)
            do {
                _ = try CPRProjectStructureSnapshot.inspect(in: root, expectedProjectID: project.id)
                Issue.record("An oversized structure report was accepted")
            } catch {
                #expect(error.localizedDescription.contains("exceeds 8 MiB"))
            }
            #expect(try CPRProject.compatibilityReport(from: root) != nil)
        }
    }
}
