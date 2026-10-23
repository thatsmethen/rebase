import Testing
import Foundation
import CryptoKit
@testable import RebaseCore

private let cprWorkspace = PrivateResearchFixtures.root
private let cprReference = cprWorkspace.appendingPathComponent("templates")
private let cprLegacyEvidence = cprWorkspace.appendingPathComponent("evidence/application/APP003")

final class CPRProjectTests {
    private func be(_ value: UInt32) -> Data {
        var value = value.bigEndian
        return withUnsafeBytes(of: &value) { Data($0) }
    }
    private func string(_ text: String) -> Data { be(UInt32(text.utf8.count)) + Data(text.utf8) }
    private func record(_ tag: String, _ payload: Data) -> Data { Data(tag.utf8) + be(UInt32(payload.count)) + payload }
    private func section(_ name: String, _ type: String = "Opaque", _ archive: Data = Data([0x12, 0x34, 0x56])) -> Data {
        record("ROOT", string(name) + string(type)) + record("ARCH", archive)
    }
    private func container(_ sections: Data) -> Data { Data("RIFF".utf8) + be(UInt32(sections.count)) + Data("NUND".utf8) + sections }
    private func be16(_ value: UInt16) -> Data {
        var value = value.bigEndian
        return withUnsafeBytes(of: &value) { Data($0) }
    }
    private func nativeObject(_ type: String, _ version: UInt16, _ body: Data) -> Data {
        be(0xffff_ffff) + be(UInt32(type.utf8.count + 1)) + Data(type.utf8) + Data([0]) + be16(version) + be(UInt32(body.count)) + body
    }
    /// Self-authored bounded envelope control; not a file produced by Reference.
    private func structuralControl(trackName: Data, childCount: UInt32 = 1,
                                   trackClass: String = "MAudioTrackEvent", tempoBody: Data? = nil,
                                   trackCopies: Int = 1, tempoInTrackNode: Bool = false,
                                   tempoAsSecondDatum: Bool = false,
                                   counterpartClass: String? = nil, counterpartVersion: UInt16 = 3) -> Data {
        let datum = be(1) + Data(repeating: 0, count: 8)
        let tempoDatum = tempoBody.map { body in
            let object = nativeObject("MTempoTrackEvent", 3, body)
            let counterpart = counterpartClass.map { nativeObject($0, counterpartVersion, Data()) } ?? be(0)
            return be(0) + (tempoAsSecondDatum ? counterpart + object : object + counterpart)
        } ?? datum
        let trackNode = nativeObject("MListNode", 0, be(UInt32(trackName.count)) + trackName + (tempoInTrackNode ? tempoDatum : datum) + be(0))
        let track = nativeObject(trackClass, 1, Data(repeating: 0, count: 26) + trackNode)
        let rootDatum = tempoInTrackNode ? datum : tempoDatum
        var children = Data()
        for _ in 0..<trackCopies { children.append(track) }
        let rootNode = nativeObject("MTrackList", 0, be(0) + rootDatum + be16(0) + be(childCount) + children)
        let root = nativeObject("MRoot", 6, Data(repeating: 0, count: 26) + rootNode)
        return container(section("Arrangement1", "PArrangement", nativeObject("PArrangement", 4, root)))
    }
    private func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
    /// Explicit historical interpretation, never a current report with a relabeled profile.
    private func v2Report(from source: URL, version: Int = 2) throws -> CPRInspection {
        let parsed = try CPRProject.readContainer(Data(contentsOf: source))
        let decoded: (recovery: CPRRecoveryResult, clock: NativeTempoClock?)
        switch version {
        case 2: decoded = try CPRRecoveryV2(container: parsed).decode(sourceName: source.lastPathComponent)
        case 3: decoded = try CPRRecoveryV3(container: parsed).decode(sourceName: source.lastPathComponent)
        case 4: decoded = try CPRRecoveryV4(container: parsed).decode(sourceName: source.lastPathComponent)
        default: throw CPRProjectError.invalid("Unsupported historical test profile.")
        }
        let recovered = decoded.recovery
        return CPRInspection(schemaVersion: 2, interpretationProfile: "cpr-static-subset-v\(version)", nativeClock: decoded.clock,
            sourceName: source.lastPathComponent, sourceSHA256: parsed.sha256,
            sourceByteCount: parsed.originalBytes.count, sections: parsed.sections,
            recoveredFacts: recovered.facts, metadataFacts: recovered.metadata,
            recoveredTracks: recovered.tracks, nativeObjects: recovered.objects,
            applicationDefaults: recovered.defaults, unsupported: recovered.unsupported,
            recoveredProject: recovered.project)
    }
    private func workspace<T>(_ body: (URL) throws -> T) throws -> T {
        let path = FileManager.default.temporaryDirectory.appendingPathComponent("CPRTests-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: path, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: path) }
        return try body(path)
    }

    @Test func containerRetainsExactOpaqueBytesAndUnpaddedOddBoundaries() throws {
        let bytes = container(section("First") + section("第二", "OtherClass", Data([0, 0xff])))
        let parsed = try CPRProject.readContainer(bytes)
        #expect(parsed.originalBytes == bytes)
        #expect(parsed.sha256 == digest(bytes))
        #expect(parsed.sections.map(\.name) == ["First", "第二"])
        #expect(parsed.sections[0].archiveByteCount == 3)
        #expect(parsed.sections[1].rootOffset == parsed.sections[0].archiveOffset + 3)
        #expect(parsed.sections[0].archiveSHA256 == digest(Data([0x12, 0x34, 0x56])))
        #expect(parsed.sections[1].archiveSHA256 == digest(Data([0, 0xff])))
    }

    @Test func malformedHeadersAndRecordBoundsRejectWithoutScanning() {
        let valid = container(section("Root"))
        var cases: [Data] = [Data(), Data("RIFF".utf8), container(Data()),
            container(record("ARCH", Data([1]))),
            container(record("ROOT", string("Root") + string("Opaque"))),
            container(record("ROOT", string("Root") + string("Opaque") + Data([0])) + record("ARCH", Data())),
            container(section("Duplicate") + section("Duplicate")),
            container(record("JUNK", section("Nested"))),
            container(record("ROOT", be(0xffff_ffff)) + record("ARCH", Data())),
            container(record("ROOT", be(1) + Data([0xff]) + string("Type")) + record("ARCH", Data())),
            container(record("ROOT", string("N\0ame") + string("Type")) + record("ARCH", Data()))]
        var badLength = valid; badLength.replaceSubrange(4..<8, with: be(UInt32(valid.count - 8))); cases.append(badLength)
        var littleLength = valid; littleLength.replaceSubrange(4..<8, with: Data(be(UInt32(valid.count - 12)).reversed())); cases.append(littleLength)
        var badForm = valid; badForm.replaceSubrange(8..<12, with: Data("WAVE".utf8)); cases.append(badForm)
        var hugeArchive = valid
        let archiveLengthOffset = 12 + 8 + string("Root").count + string("Opaque").count + 4
        hugeArchive.replaceSubrange(archiveLengthOffset..<archiveLengthOffset+4, with: be(0xffff_ffff)); cases.append(hugeArchive)
        for end in 12..<valid.count { cases.append(Data(valid.prefix(end))) }
        for bytes in cases { expectThrows(try CPRProject.readContainer(bytes)) }
    }

    @Test func boundedNamesAndSectionCountsAreEnforced() throws {
        _ = try CPRProject.readContainer(container(section(String(repeating: "x", count: 4096))))
        expectThrows(try CPRProject.readContainer(container(section(String(repeating: "x", count: 4097)))))
        var records = Data()
        for index in 0..<4096 { records.append(section("R\(index)", "O", Data())) }
        #expect(try CPRProject.readContainer(container(records)).sections.count == 4096)
        records.append(section("R4096", "O", Data()))
        expectThrows(try CPRProject.readContainer(container(records)))
    }

    @Test func unknownArchiveIsReportedAndCannotBecomeAnInventedProject() throws {
        try workspace { directory in
            let path = directory.appendingPathComponent("Unknown.cpr")
            let bytes = container(section("UnknownRoot", "OpaqueClass", Data([0x01, 0x02, 0x03])))
            try bytes.write(to: path)
            let report = try CPRProject.inspect(from: path)
            #expect(report.schemaVersion == 2 && report.interpretationProfile == CPRProject.currentInterpretationProfile)
            #expect(report.sourceSHA256 == digest(bytes))
            #expect(!report.canImport && report.recoveredProject == nil && report.recoveredTracks.isEmpty)
            #expect(!report.unsupported.isEmpty && report.applicationDefaults.isEmpty)
            let output = directory.appendingPathComponent("Output.rebaseproj")
            expectThrows(try CPRProject.importProject(from: path, to: output, allowPartial: true, expectedSHA256: report.sourceSHA256))
            #expect(!FileManager.default.fileExists(atPath: output.path))
            expectThrows(try CPRProject.importProject(from: path, to: output, allowPartial: true, expectedSHA256: String(repeating: "0", count: 64)))
            #expect(try Data(contentsOf: path) == bytes)
        }
    }

    @Test func nativeStringMarkersAndCountBoundsDoNotGuessLegacyEncoding() throws {
        try workspace { directory in
            let source = directory.appendingPathComponent("Control.cpr")
            for raw in [Data([0xef, 0xbb, 0xbf]) + Data("Café".utf8) + Data([0]),
                        Data("Café".utf8) + Data([0, 0xef, 0xbb, 0xbf])] {
                try structuralControl(trackName: raw).write(to: source)
                #expect(try CPRProject.inspect(from: source).recoveredProject?.tracks.first?.name == "Café")
            }
            for raw in [Data("Café".utf8) + Data([0]), Data("Not terminated".utf8),
                        Data([0xef, 0xbb, 0xbf, 0xff, 0]), Data([65, 0, 66, 0]),
                        Data(repeating: 65, count: 50_000) + Data([0])] {
                try structuralControl(trackName: raw).write(to: source)
                expectThrows(try CPRProject.inspect(from: source))
            }
            for count: UInt32 in [0, 2, 0xffff_ffff] {
                try structuralControl(trackName: Data("Audio\0".utf8), childCount: count).write(to: source)
                expectThrows(try CPRProject.inspect(from: source))
            }
        }
    }

    @Test func classRegistryKeysDoNotNormalizeUserStringBOMs() throws {
        try workspace { directory in
            let source = directory.appendingPathComponent("ClassControl.cpr")
            let name = Data("Audio\0".utf8)
            try structuralControl(trackName: name).write(to: source)
            #expect(try CPRProject.inspect(from: source).recoveredTrackCount == 1)
            for alteredClass in ["\u{feff}MAudioTrackEvent", "MAudioTrackEvent\0\u{feff}", "MAudio\0TrackEvent"] {
                try structuralControl(trackName: name, trackClass: alteredClass).write(to: source)
                expectThrows(try CPRProject.inspect(from: source))
            }
        }
    }

    @Test func zeroRecordTempoCannotBecomeRecoveredFixedTempo() throws {
        try workspace { directory in
            let source = directory.appendingPathComponent("TempoControl.cpr")
            let name = Data("Audio\0".utf8)
            let fixedSuffix = be(Float(126.5).bitPattern) + be16(1)
            let record = be(Float(0.5).bitPattern) + Data(repeating: 0, count: 16) + be16(0)
            try structuralControl(trackName: name, tempoBody: be(1) + record + fixedSuffix).write(to: source)
            #expect(try CPRProject.inspect(from: source).recoveredProject?.tempo == 126.5)
            // Exactly count=0 + fixed f32 + enabled u16, not a shifted real payload.
            try structuralControl(trackName: name, tempoBody: be(0) + fixedSuffix).write(to: source)
            expectThrows(try CPRProject.inspect(from: source))
            let destination = directory.appendingPathComponent("Rejected.rebaseproj")
            expectThrows(try CPRProject.importProject(from: source, to: destination, allowPartial: true))
            #expect(!FileManager.default.fileExists(atPath: destination.path))
        }
    }

    @Test func oversizedReportCannotPublishAnUnopenableProject() throws {
        try workspace { directory in
            let source = directory.appendingPathComponent("LargeNames.cpr")
            let name = Data(repeating: 65, count: 49_000) + Data([0])
            let bytes = structuralControl(trackName: name, childCount: 100, trackCopies: 100)
            #expect(bytes.count < 5_000_000)
            try bytes.write(to: source)
            let report = try CPRProject.inspect(from: source)
            #expect(report.recoveredTrackCount == 100)
            #expect(try JSONEncoder().encode(report).count > 8_388_608)
            let destination = directory.appendingPathComponent("Unopenable.rebaseproj")
            expectThrows(try CPRProject.importProject(from: source, to: destination, allowPartial: true,
                                                     expectedSHA256: report.sourceSHA256))
            #expect(!FileManager.default.fileExists(atPath: destination.path))
            #expect(try FileManager.default.contentsOfDirectory(atPath: directory.path) == ["LargeNames.cpr"])
            #expect(try Data(contentsOf: source) == bytes)
        }
    }

    @Test func nativeClockRequiresConsistentKnownTrackInterfaceRoles() throws {
        try workspace { directory in
            let source = directory.appendingPathComponent("Role.cpr")
            let record = be(Float(0.5).bitPattern) + Data(repeating: 0, count: 16) + be16(0)
            let body = be(1) + record + be(Float(126.5).bitPattern) + be16(1)
            try structuralControl(trackName: Data("Audio\0".utf8), tempoBody: body).write(to: source)
            let valid = try CPRProject.inspect(from: source)
            #expect(valid.nativeClock?.fixedBPM == 126.5)
            #expect(valid.recoveredProject?.tempoMap.nativeClock == valid.nativeClock)
            for nested in [false, true] {
                try structuralControl(trackName: Data("Audio\0".utf8), tempoBody: body,
                                      tempoInTrackNode: nested).write(to: source)
                let report = try CPRProject.inspect(from: source)
                #expect(report.nativeClock?.fixedBPM == 126.5)
            }
            try structuralControl(trackName: Data("Audio\0".utf8), tempoBody: body,
                                  tempoAsSecondDatum: true).write(to: source)
            let wrongSlot = try CPRProject.inspect(from: source)
            #expect(wrongSlot.nativeClock == nil)
            #expect(wrongSlot.recoveredProject?.tempo == 120)
            #expect(!wrongSlot.recoveredFacts.contains { $0.contains("active fixed tempo") })
            #expect(wrongSlot.applicationDefaults.contains { $0.contains("120 BPM") })
            #expect(wrongSlot.unsupported.contains { $0.category == "Native clock role" })
            for (type, version): (String, UInt16) in [("OpaqueInterface", 3), ("MSignatureTrackEvent", 4)] {
                try structuralControl(trackName: Data("Audio\0".utf8), tempoBody: body,
                                      counterpartClass: type, counterpartVersion: version).write(to: source)
                let report = try CPRProject.inspect(from: source)
                #expect(report.nativeClock == nil && report.recoveredProject?.tempoMap.nativeClock == nil)
                #expect(report.recoveredProject?.tempo == 120)
                #expect(!report.recoveredFacts.contains { $0.contains("active fixed tempo") })
                #expect(report.applicationDefaults.contains { $0.contains("120 BPM") })
                #expect(report.unsupported.contains { $0.category == "Native clock role" })
            }
        }
    }

    @Test func sourceAndDestinationPreflightAreBoundedAndNonDestructive() throws {
        try workspace { directory in
            let oversized = directory.appendingPathComponent("Oversized.cpr")
            FileManager.default.createFile(atPath: oversized.path, contents: Data())
            let file = try FileHandle(forWritingTo: oversized)
            try file.truncate(atOffset: UInt64(CPRProject.maximumFileBytes) + 1)
            try file.close()
            expectThrows(try CPRProject.inspect(from: oversized))
            expectThrows(try CPRProject.inspect(from: directory))
            let path = directory.appendingPathComponent("Source.cpr")
            let bytes = container(section("Opaque")); try bytes.write(to: path)
            let existing = directory.appendingPathComponent("Existing.rebaseproj")
            let sentinel = Data("preserve me".utf8); try sentinel.write(to: existing)
            expectThrows(try CPRProject.importProject(from: path, to: existing, allowPartial: true))
            #expect(try Data(contentsOf: existing) == sentinel)
            let link = directory.appendingPathComponent("Dangling.rebaseproj")
            try FileManager.default.createSymbolicLink(at: link, withDestinationURL: directory.appendingPathComponent("Absent"))
            expectThrows(try CPRProject.importProject(from: path, to: link, allowPartial: true))
            #expect(try FileManager.default.destinationOfSymbolicLink(atPath: link.path).hasSuffix("Absent"))
        }
    }

    @Test func historicalReportVerifiesPreservedBytesAndRejectsRedirection() throws {
        try workspace { directory in
            #expect(try CPRProject.compatibilityReport(from: directory) == nil)
            let source = directory.appendingPathComponent("Source.cpr")
            let bytes = container(section("Opaque")); try bytes.write(to: source)
            let report = try CPRProject.inspect(from: source)
            let package = directory.appendingPathComponent("Stored.rebaseproj")
            let destination = package.appendingPathComponent(CPRProject.originalRelativePath)
            let reportURL = package.appendingPathComponent(CPRProject.reportRelativePath)
            try FileManager.default.createDirectory(at: destination.deletingLastPathComponent(), withIntermediateDirectories: true)
            try bytes.write(to: destination)
            try JSONEncoder().encode(report).write(to: reportURL)
            #expect(try CPRProject.compatibilityReport(from: package)?.sourceSHA256 == digest(bytes))
            var changed = bytes; changed[changed.count - 1] ^= 1; try changed.write(to: destination)
            expectThrows(try CPRProject.compatibilityReport(from: package))
            try FileManager.default.removeItem(at: destination)
            try FileManager.default.createSymbolicLink(at: destination, withDestinationURL: source)
            expectThrows(try CPRProject.compatibilityReport(from: package))
        }
    }

    @Test func reportSchemaAndInterpretationAreValidatedIndependently() throws {
        try workspace { directory in
            let source = directory.appendingPathComponent("Profile.cpr")
            let sourceBytes = structuralControl(trackName: Data("Audio\0".utf8))
            try sourceBytes.write(to: source)
            let output = directory.appendingPathComponent("Profile.rebaseproj")
            let imported = try CPRProject.importProject(from: source, to: output, allowPartial: true)
            #expect(imported.report.schemaVersion == 2)
            #expect(imported.report.interpretationProfile == CPRProject.currentInterpretationProfile)
            let reportURL = output.appendingPathComponent(CPRProject.reportRelativePath)
            let currentProjectBytes = try Data(contentsOf: output.appendingPathComponent("Project.json"))
            let originalReport = try Data(contentsOf: reportURL)
            let originalObject = try #require(JSONSerialization.jsonObject(with: originalReport) as? [String: Any])
            let frozen = try CPRRecoveryV1(container: CPRProject.readContainer(sourceBytes)).decode(sourceName: source.lastPathComponent)
            let frozenV2 = try v2Report(from: source)
            let frozenV3 = try v2Report(from: source, version: 3)
            let frozenV4 = try v2Report(from: source, version: 4)
            for (schema, profile) in [(1, nil as String?), (1, "cpr-static-subset-v1"),
                                      (2, "cpr-static-subset-v1"), (2, "cpr-static-subset-v2"),
                                      (2, "cpr-static-subset-v3"), (2, "cpr-static-subset-v4"), (2, "cpr-static-subset-v5")] {
                // Profile declarations select their real baseline; relabeling a
                // current report must not manufacture a historical interpretation.
                let report = profile == "cpr-static-subset-v5" ? imported.report :
                    profile == "cpr-static-subset-v4" ? frozenV4 :
                    profile == "cpr-static-subset-v3" ? frozenV3 :
                    profile == "cpr-static-subset-v2" ? frozenV2 : CPRInspection(
                    schemaVersion: schema, interpretationProfile: profile, nativeClock: nil,
                    sourceName: imported.report.sourceName, sourceSHA256: imported.report.sourceSHA256,
                    sourceByteCount: sourceBytes.count, sections: imported.report.sections,
                    recoveredFacts: frozen.facts, metadataFacts: frozen.metadata,
                    recoveredTracks: frozen.tracks, nativeObjects: frozen.objects,
                    applicationDefaults: frozen.defaults, unsupported: frozen.unsupported,
                    recoveredProject: frozen.project)
                let bytes = try JSONEncoder().encode(report)
                try bytes.write(to: reportURL)
                let historical = try #require(try CPRProject.compatibilityReport(from: output))
                #expect(historical.schemaVersion == schema && historical.interpretationProfile == profile)
                #expect(historical.recoveredProject == imported.project)
                #expect(try Data(contentsOf: reportURL) == bytes)
            }
            for (schema, profile) in [(1, "unknown-profile" as String?), (2, "unknown-profile"),
                                      (2, nil), (3, "cpr-static-subset-v1"), (0, nil),
                                      (1, "cpr-static-subset-v2"), (1, "cpr-static-subset-v3"), (1, "cpr-static-subset-v4"), (1, "cpr-static-subset-v5")] {
                var object = originalObject
                object["schemaVersion"] = schema
                object["interpretationProfile"] = profile
                let bytes = try JSONSerialization.data(withJSONObject: object)
                try bytes.write(to: reportURL)
                expectThrows(try CPRProject.compatibilityReport(from: output))
                #expect(try Data(contentsOf: reportURL) == bytes)
            }
            #expect(try Data(contentsOf: output.appendingPathComponent("Project.json")) == currentProjectBytes)
            #expect(try Data(contentsOf: output.appendingPathComponent(CPRProject.originalRelativePath)) == sourceBytes)
        }
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func frozenSchemaOneReportsReplayWithoutRewritingEditedProjects() throws {
        let records = [
            ("Classic House Recovery.rebaseproj", "d861662e75cd4fabb2b9248dd150dceac95c760501470f1baa7dae0eed5ce272", "28db9a9e6aca3357e0758c4b985c4bbdfb4e1d9268502d53238f0ceb2733e892", "c6fe832e355c90a27bc3594a9e1bf453cbb626af1a260a01aa94f0dd0bcf9ce7"),
            ("Stereo Mastering Recovery.rebaseproj", "d41ebd025fa211668fac1dad4b851a187b54ab8197766d4497459a702bbed2d3", "6cde8a5ce37e5f112c79f684ad8c1fc3e308979feba9f046db42bf62ecce3022", "53996c0507bd82a7d259cb214e0ce714cd54b66d6e3952066f009a0b1a50d452"),
            ("Stereo Mastering Copy.rebaseproj", "d41ebd025fa211668fac1dad4b851a187b54ab8197766d4497459a702bbed2d3", "6cde8a5ce37e5f112c79f684ad8c1fc3e308979feba9f046db42bf62ecce3022", "e06ab17bcdb1b64ebf1d8013d26b4ac65bfde0668ec36f6d507597bc2dff22a8")]
        try workspace { directory in
            for (name, reportHash, sourceHash, projectHash) in records {
                let original = cprLegacyEvidence.appendingPathComponent(name)
                let relativePaths = [CPRProject.reportRelativePath, CPRProject.originalRelativePath, "Project.json"]
                let before = try relativePaths.map { try Data(contentsOf: original.appendingPathComponent($0)) }
                #expect(before.map(digest) == [reportHash, sourceHash, projectHash])
                let baseline = try JSONDecoder().decode(CPRInspection.self, from: before[0])
                #expect(baseline.schemaVersion == 1 && baseline.interpretationProfile == nil)
                #expect(try CPRProject.compatibilityReport(from: original) == baseline)
                #expect(try relativePaths.map { try Data(contentsOf: original.appendingPathComponent($0)) } == before)

                let copy = directory.appendingPathComponent(name)
                try FileManager.default.copyItem(at: original, to: copy)
                var edited = try ProjectStore.load(from: copy)
                edited.name = "User edit preserved"
                edited.tracks[0].gainDB = -7
                try ProjectStore.save(edited, to: copy)
                let editedBytes = try Data(contentsOf: copy.appendingPathComponent("Project.json"))
                #expect(edited != baseline.recoveredProject)
                #expect(try CPRProject.compatibilityReport(from: copy) == baseline)
                #expect(try ProjectStore.load(from: copy) == edited)
                #expect(try Data(contentsOf: copy.appendingPathComponent("Project.json")) == editedBytes)
                #expect(try Data(contentsOf: copy.appendingPathComponent(CPRProject.reportRelativePath)) == before[0])
                #expect(try Data(contentsOf: copy.appendingPathComponent(CPRProject.originalRelativePath)) == before[1])

                var tampered = try #require(JSONSerialization.jsonObject(with: before[0]) as? [String: Any])
                tampered["applicationDefaults"] = ["Altered historical interpretation"]
                try JSONSerialization.data(withJSONObject: tampered).write(to: copy.appendingPathComponent(CPRProject.reportRelativePath))
                expectThrows(try CPRProject.compatibilityReport(from: copy))
                #expect(try relativePaths.map { try Data(contentsOf: original.appendingPathComponent($0)) } == before)
            }
        }
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func realShippedTemplateContainersMatchPinnedInventory() throws {
        let path = cprWorkspace.appendingPathComponent("evidence/cpr-static/cpr-container-001/inventory.json")
        let bytes = try Data(contentsOf: path)
        #expect(digest(bytes) == "e50ff515c541c76d857d6c093f4329b5cb53bffcd631a6e22cbc5edf86511b0d")
        let inventory = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: Any])
        let records = try #require(inventory["records"] as? [[String: Any]])
        #expect(records.count == 10)
        for record in records {
            let name = try #require(record["name"] as? String)
            let source = try Data(contentsOf: cprReference.appendingPathComponent(name))
            #expect(digest(source) == record["sha256"] as? String)
            #expect(source.count == record["bytes"] as? Int)
            let parsed = try CPRProject.readContainer(source)
            #expect(parsed.sections.map(\.name) == ["Version", "Arrangement1", "ComputerGuid", "Devices", "WindowLayouts", "ProjectLayouts", "Metadata"])
            #expect(parsed.sections.count == 7)
            #expect(parsed.originalBytes == source)
            let inspection = try CPRProject.inspect(from: cprReference.appendingPathComponent(name))
            #expect(inspection.interpretationProfile == CPRProject.currentInterpretationProfile)
            #expect(inspection.sourceSHA256 == digest(source))
            #expect(!inspection.recoveredTracks.isEmpty && !inspection.metadataFacts.isEmpty)
            #expect(inspection.recoveredTracks.filter { $0.kind == "Audio" }.count == inspection.recoveredTrackCount)
            #expect(inspection.recoveredClipCount == 0)
            #expect(inspection.recoveredTracks.filter { $0.kind != "Audio" }.allSatisfy { $0.importedTrackID == nil })
            #expect(inspection.nativeObjects.allSatisfy { $0.payloadOffset >= 0 && $0.payloadOffset + $0.payloadByteCount <= source.count })
            #expect(inspection.recoveredFacts.contains { $0.contains("consistent origin signature 4/4") })
            if let recovered = inspection.recoveredProject {
                #expect(recovered.signatureMap.events.count == 1)
                #expect(recovered.signatureMap.events[0].numerator == 4 && recovered.signatureMap.events[0].denominator == 4)
                #expect(!inspection.applicationDefaults.contains { $0.contains("4/4") })
                #expect(!inspection.applicationDefaults.contains { $0.contains("48 kHz") })
                #expect(recovered.sampleRate == 44100)
            }
            if name == "Stereo Mastering.cpr" {
                #expect(inspection.canImport)
                #expect(inspection.recoveredProject?.tracks.map(\.name) == ["Stereo Master", "Reference Track"])
                #expect(inspection.recoveredTracks.filter { $0.kind == "Audio" }.map(\.sourceOffset) == [2213, 168058])
            }
            if name == "Classic House.cpr" {
                #expect(inspection.metadataFacts.contains { $0.contains("MusicalTempo: 126.5") })
                #expect(inspection.recoveredProject?.tempo == 126.5)
                #expect(inspection.nativeClock?.fixedBPMBits == 0x42fd0000)
                #expect(inspection.nativeClock?.sourceSHA256 == inspection.sourceSHA256)
                #expect(inspection.nativeClock == inspection.recoveredProject?.tempoMap.nativeClock)
                #expect(inspection.recoveredFacts.contains { $0.contains("active fixed tempo: 126.5") })
                #expect(!inspection.applicationDefaults.contains { $0.contains("120 BPM") })
                #expect(inspection.unsupported.contains { $0.category == "Unresolved audio source" && $0.detail.contains("Bongos") && $0.detail.contains("Tech_House_Percussion_Loop_21_125bpm_BODTH.wav") && $0.detail.contains("vstsound://") })
                #expect(inspection.nativeObjects.contains { $0.className == "PAudioClip" && $0.version == 4 })
                #expect(inspection.nativeObjects.contains { $0.className == "FNPath" && $0.version == 0 })
            }
            if name == "Songwriter.cpr" { #expect(inspection.recoveredProject?.tempo == 92) }
            if name == "Neo Soul.cpr" { #expect(inspection.recoveredFacts.contains { $0.contains("active fixed tempo: 70.0") }) }
            if name == "Trap.cpr" { #expect(inspection.recoveredFacts.contains { $0.contains("active fixed tempo: 65.0") }) }
            if name == "LoFi Hip Hop.cpr" {
                #expect(inspection.nativeClock?.contract == NativeTempoClock.mapContract)
                #expect(inspection.nativeClock?.mapRecords?.map(\.periodBits) == [0x3f400000, 0x3f000000])
                #expect(inspection.nativeClock?.mapRecords?.map(\.seconds) == [0, 600])
                #expect(inspection.nativeClock?.mapRecords?.map(\.tick) == [0, 384000])
                #expect(inspection.recoveredProject?.tempo == 80)
                #expect(!inspection.unsupported.contains { $0.category == "Tempo event map" })
                #expect(!inspection.applicationDefaults.contains { $0.contains("120 BPM") })
                let historical = try v2Report(from: cprReference.appendingPathComponent(name))
                #expect(historical.nativeClock == nil && historical.recoveredProject?.tempo == 120)
                #expect(historical.unsupported.contains { $0.category == "Tempo event map" })
                #expect(historical.applicationDefaults.contains { $0.contains("120 BPM") })
                #expect(inspection.unsupported.contains { $0.category == "Unresolved audio source" && $0.detail.contains("Vinyl Crackle") && $0.detail.contains("Lofi_Ambience_16_Vinyl_Crackle_LD.wav") && $0.detail.contains("vstsound://") })
            }
        }
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func fixedTempoUsesFullModeWordAndRejectsMalformedRecords() throws {
        try workspace { directory in
            let original = try Data(contentsOf: cprReference.appendingPathComponent("Classic House.cpr"))
            #expect(digest(original) == "28db9a9e6aca3357e0758c4b985c4bbdfb4e1d9268502d53238f0ceb2733e892")
            let source = directory.appendingPathComponent("Mutation.cpr")
            // Pinned native-backed field offsets; controls mutate copies only.
            var highByteMode = original; highByteMode.replaceSubrange(810..<812, with: be16(0x0100))
            try highByteMode.write(to: source)
            #expect(try CPRProject.inspect(from: source).recoveredProject?.tempo == 126.5)
            var inactive = original; inactive.replaceSubrange(810..<812, with: be16(0))
            try inactive.write(to: source)
            // The historical V2 meaning stays fixed even though V3 can recover this map.
            let mapReport = try v2Report(from: source)
            #expect(mapReport.recoveredProject?.tempo == 120)
            #expect(mapReport.unsupported.contains { $0.category == "Tempo event map" })
            #expect(!mapReport.recoveredFacts.contains { $0.contains("active fixed tempo") })
            let currentMap = try CPRProject.inspect(from: source)
            #expect(currentMap.nativeClock?.contract == NativeTempoClock.mapContract)
            #expect(!currentMap.recoveredFacts.contains { $0.contains("active fixed tempo") })
            for (offset, bytes) in [(758, be(0xffff_ffff)), (762, be(0x7fc0_0000)),
                                    (806, be(0x7f80_0000)), (806, be(Float(500).bitPattern))] {
                var malformed = original; malformed.replaceSubrange(offset..<offset+4, with: bytes)
                try malformed.write(to: source)
                expectThrows(try CPRProject.inspect(from: source))
            }
            #expect(try Data(contentsOf: cprReference.appendingPathComponent("Classic House.cpr")) == original)
        }
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func realAudioTemplateImportsExplicitSubsetAndPreservesOriginal() throws {
        try workspace { directory in
            let source = cprReference.appendingPathComponent("Stereo Mastering.cpr")
            let inspected = try CPRProject.inspect(from: source)
            let output = directory.appendingPathComponent("Imported.rebaseproj")
            expectThrows(try CPRProject.importProject(from: source, to: output, expectedSHA256: inspected.sourceSHA256))
            #expect(!FileManager.default.fileExists(atPath: output.path))
            let imported = try CPRProject.importProject(from: source, to: output, allowPartial: true, expectedSHA256: inspected.sourceSHA256)
            #expect(imported.project.tracks.map(\.name) == ["Stereo Master", "Reference Track"])
            #expect(imported.project.tracks.allSatisfy { $0.clips.isEmpty && $0.gainDB == 0 && $0.pan == 0 })
            #expect(try ProjectStore.load(from: output) == imported.project)
            #expect(try Data(contentsOf: output.appendingPathComponent(imported.originalRelativePath)) == Data(contentsOf: source))
            #expect(try CPRProject.compatibilityReport(from: output) == inspected)
            let reportURL = output.appendingPathComponent(CPRProject.reportRelativePath)
            var report = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: reportURL)) as? [String: Any])
            report["recoveredFacts"] = ["Invented recovery claim"]
            try JSONSerialization.data(withJSONObject: report).write(to: reportURL)
            expectThrows(try CPRProject.compatibilityReport(from: output))
        }
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func realFixedClockImportPersistsCurrentProfileAndRetainsBaselineAfterExplicitConversion() throws {
        try workspace { directory in
            let source = cprReference.appendingPathComponent("Classic House.cpr")
            let inspection = try CPRProject.inspect(from: source)
            #expect(inspection.sourceSHA256 == "28db9a9e6aca3357e0758c4b985c4bbdfb4e1d9268502d53238f0ceb2733e892")
            let output = directory.appendingPathComponent("NativeClock.rebaseproj")
            let result = try CPRProject.importProject(from: source, to: output, allowPartial: true,
                                                      expectedSHA256: inspection.sourceSHA256)
            #expect(result.report.interpretationProfile == CPRProject.currentInterpretationProfile)
            #expect(result.report.nativeClock?.interpretationProfile == "cpr-static-subset-v2")
            var loaded = try ProjectStore.load(from: output)
            #expect(loaded.tempoMap.nativeClock?.fixedBPMBits == 0x42fd0000)
            #expect(try loaded.tempoMap.seconds(atBeat: 1).bitPattern == Double(Float(bitPattern: 0x3ef2d88a)).bitPattern)
            #expect(try CPRProject.compatibilityReport(from: output) == inspection)
            let reportBytes = try Data(contentsOf: output.appendingPathComponent(CPRProject.reportRelativePath))
            let sourceBytes = try Data(contentsOf: output.appendingPathComponent(CPRProject.originalRelativePath))
            try loaded.convertToApplicationTiming()
            try ProjectStore.save(loaded, to: output)
            #expect(try ProjectStore.load(from: output).tempoMap.nativeClock == nil)
            #expect(try CPRProject.compatibilityReport(from: output) == result.report)
            #expect(try Data(contentsOf: output.appendingPathComponent(CPRProject.reportRelativePath)) == reportBytes)
            #expect(try Data(contentsOf: output.appendingPathComponent(CPRProject.originalRelativePath)) == sourceBytes)
        }
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func persistedNativeClockMustMatchReplayedOriginalBeforeLoadOrSave() throws {
        try workspace { directory in
            let source = cprReference.appendingPathComponent("Classic House.cpr")
            let package = directory.appendingPathComponent("Provenance.rebaseproj")
            let imported = try CPRProject.importProject(from: source, to: package, allowPartial: true)
            let original = imported.project
            let clock = try #require(original.tempoMap.nativeClock)
            let manifest = package.appendingPathComponent(ProjectStore.manifestName)
            let originalBytes = try Data(contentsOf: manifest)
            let reportBytes = try Data(contentsOf: package.appendingPathComponent(CPRProject.reportRelativePath))
            let sourceBytes = try Data(contentsOf: package.appendingPathComponent(CPRProject.originalRelativePath))
            let variants = [
                try NativeTempoClock(fixedBPMBits: clock.fixedBPMBits, sourceSHA256: String(repeating: "b", count: 64), sourceObjectOffset: clock.sourceObjectOffset),
                try NativeTempoClock(fixedBPMBits: clock.fixedBPMBits, sourceSHA256: clock.sourceSHA256, sourceObjectOffset: clock.sourceObjectOffset + 1),
                try NativeTempoClock(fixedBPMBits: Float(127).bitPattern, sourceSHA256: clock.sourceSHA256, sourceObjectOffset: clock.sourceObjectOffset)]
            for forged in variants {
                var altered = original
                altered.tempoMap.nativeClock = forged
                altered.tempoMap.events[0].bpm = forged.fixedBPM
                try altered.validate() // Syntax and display consistency alone are insufficient.
                expectThrows(try ProjectStore.save(altered, to: package))
                #expect(try Data(contentsOf: manifest) == originalBytes)
                try JSONEncoder().encode(altered).write(to: manifest)
                expectThrows(try ProjectStore.load(from: package))
                try originalBytes.write(to: manifest)
            }
            let missing = directory.appendingPathComponent("NoProof.rebaseproj")
            expectThrows(try ProjectStore.save(original, to: missing))
            #expect(!FileManager.default.fileExists(atPath: missing.path))
            try FileManager.default.createDirectory(at: missing, withIntermediateDirectories: false)
            try originalBytes.write(to: missing.appendingPathComponent(ProjectStore.manifestName))
            expectThrows(try ProjectStore.load(from: missing))
            #expect(try ProjectStore.load(from: package) == original)
            #expect(try Data(contentsOf: package.appendingPathComponent(CPRProject.reportRelativePath)) == reportBytes)
            #expect(try Data(contentsOf: package.appendingPathComponent(CPRProject.originalRelativePath)) == sourceBytes)
        }
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func signatureRecoveryPreservesV2MeaningAndSurvivesCurrentProfileReopen() throws {
        try workspace { directory in
            let fixtures = cprWorkspace.appendingPathComponent("evidence/application/APP004")
            let controls = [("Synthetic Concordant 7-8.cpr", "3f430d7eecbf89e5e4485a4405b07f379a5cbd95fb784e5f6c1e6959b8881d49", true),
                            ("Synthetic Signature Precedence.cpr", "bf761a0fdca8ea5ec044172abc08b63174180211cf3ab23c55241fc5806e7f8e", false)]
            for (name, hash, concordant) in controls {
                let source = fixtures.appendingPathComponent(name)
                #expect(digest(try Data(contentsOf: source)) == hash)
                let destination = directory.appendingPathComponent(name + ".rebaseproj")
                let imported = try CPRProject.importProject(from: source, to: destination, allowPartial: true, expectedSHA256: hash)
                let historical = try v2Report(from: source)
                let frozenV3 = try v2Report(from: source, version: 3)
                #expect(historical.recoveredProject == frozenV3.recoveredProject)
                #expect(historical.recoveredFacts == frozenV3.recoveredFacts)
                #expect(historical.nativeObjects == frozenV3.nativeObjects)
                // V4 adds the source audio event while the independently
                // recovered fixed clock and signature interpretation stay exact.
                let frozenV4 = try v2Report(from: source, version: 4)
                var priorSubset = try #require(frozenV4.recoveredProject)
                #expect(priorSubset.unresolvedAudioEvents.count == 1)
                #expect(priorSubset.unresolvedAudioEvents[0].placement == nil)
                for index in priorSubset.tracks.indices { priorSubset.tracks[index].unresolvedAudioEvents = [] }
                #expect(historical.recoveredProject == priorSubset)
                #expect(historical.recoveredFacts == frozenV4.recoveredFacts.filter { !$0.hasPrefix("Recovered 1 unresolved audio event") })
                var expectedV5 = try #require(frozenV4.recoveredProject)
                #expect(expectedV5.sampleRate == 48000)
                expectedV5.sampleRate = 44100
                #expect(imported.project == expectedV5)
                #expect(historical.nativeObjects.allSatisfy { imported.report.nativeObjects.contains($0) })
                let loaded = try ProjectStore.load(from: destination)
                #expect(loaded.tempoMap.nativeClock?.fixedBPMBits == 0x42fd0000)
                #expect(loaded.signatureMap.events[0].numerator == (concordant ? 7 : 4))
                #expect(loaded.signatureMap.events[0].denominator == (concordant ? 8 : 4))
                #expect(loaded.signatureMap.events[0].beat == 0)
                #expect(imported.report.applicationDefaults.contains { $0.contains("4/4") } == !concordant)
                #expect(imported.report.recoveredFacts.contains { $0.contains("consistent origin signature") } == concordant)
                if !concordant {
                    #expect(imported.report.unsupported.contains { $0.category == "Signature state" && $0.detail.contains("disagree") })
                }
                #expect(try CPRProject.compatibilityReport(from: destination) == imported.report)
                #expect(digest(try Data(contentsOf: source)) == hash)
            }
        }
    }
}
