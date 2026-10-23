import Testing
import Foundation
import CryptoKit
@testable import RebaseCore

private let cprWorkspace = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
private let cprReference = cprWorkspace.appendingPathComponent("research/targets/full-reference/expanded/Cubase 15.app.pkg/Payload/Cubase 15.app/Contents/Project Templates/Cubase Pro")

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
    /// Self-authored bounded envelope control; not a file produced by Cubase.
    private func structuralControl(trackName: Data, childCount: UInt32 = 1,
                                   trackClass: String = "MAudioTrackEvent", tempoBody: Data? = nil) -> Data {
        let datum = be(1) + Data(repeating: 0, count: 8)
        let trackNode = nativeObject("MListNode", 0, be(UInt32(trackName.count)) + trackName + datum + be(0))
        let track = nativeObject(trackClass, 1, Data(repeating: 0, count: 26) + trackNode)
        let rootDatum = tempoBody.map { be(0) + nativeObject("MTempoTrackEvent", 3, $0) + be(0) } ?? datum
        let rootNode = nativeObject("MTrackList", 0, be(0) + rootDatum + be16(0) + be(childCount) + track)
        let root = nativeObject("MRoot", 6, Data(repeating: 0, count: 26) + rootNode)
        return container(section("Arrangement1", "PArrangement", nativeObject("PArrangement", 4, root)))
    }
    private func digest(_ data: Data) -> String { SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() }
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
            #expect(report.schemaVersion == 1 && report.sourceSHA256 == digest(bytes))
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

    @Test(.enabled(if: FileManager.default.fileExists(atPath: cprReference.path), "Requires the locally acquired pinned Cubase template fixtures; no download or target execution."))
    func realShippedTemplateContainersMatchPinnedInventory() throws {
        let path = cprWorkspace.appendingPathComponent("research/evidence/cubase-static/cpr-container-001/inventory.json")
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
            #expect(inspection.sourceSHA256 == digest(source))
            #expect(!inspection.recoveredTracks.isEmpty && !inspection.metadataFacts.isEmpty)
            #expect(inspection.recoveredTracks.filter { $0.kind == "Audio" }.count == inspection.recoveredTrackCount)
            #expect(inspection.recoveredClipCount == 0)
            #expect(inspection.recoveredTracks.filter { $0.kind != "Audio" }.allSatisfy { $0.importedTrackID == nil })
            #expect(inspection.nativeObjects.allSatisfy { $0.payloadOffset >= 0 && $0.payloadOffset + $0.payloadByteCount <= source.count })
            if name == "Stereo Mastering.cpr" {
                #expect(inspection.canImport)
                #expect(inspection.recoveredProject?.tracks.map(\.name) == ["Stereo Master", "Reference Track"])
                #expect(inspection.recoveredTracks.filter { $0.kind == "Audio" }.map(\.sourceOffset) == [2213, 168058])
            }
            if name == "Classic House.cpr" {
                #expect(inspection.metadataFacts.contains { $0.contains("MusicalTempo: 126.5") })
                #expect(inspection.recoveredProject?.tempo == 126.5)
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
                #expect(inspection.unsupported.contains { $0.category == "Tempo event map" })
                #expect(inspection.applicationDefaults.contains { $0.contains("120 BPM") })
                #expect(inspection.unsupported.contains { $0.category == "Unresolved audio source" && $0.detail.contains("Vinyl Crackle") && $0.detail.contains("Lofi_Ambience_16_Vinyl_Crackle_LD.wav") && $0.detail.contains("vstsound://") })
            }
        }
    }

    @Test(.enabled(if: FileManager.default.fileExists(atPath: cprReference.path), "Requires the locally acquired pinned CPR reference."))
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
            let mapReport = try CPRProject.inspect(from: source)
            #expect(mapReport.recoveredProject?.tempo == 120)
            #expect(mapReport.unsupported.contains { $0.category == "Tempo event map" })
            #expect(!mapReport.recoveredFacts.contains { $0.contains("active fixed tempo") })
            for (offset, bytes) in [(758, be(0xffff_ffff)), (762, be(0x7fc0_0000)),
                                    (806, be(0x7f80_0000)), (806, be(Float(500).bitPattern))] {
                var malformed = original; malformed.replaceSubrange(offset..<offset+4, with: bytes)
                try malformed.write(to: source)
                expectThrows(try CPRProject.inspect(from: source))
            }
            #expect(try Data(contentsOf: cprReference.appendingPathComponent("Classic House.cpr")) == original)
        }
    }

    @Test(.enabled(if: FileManager.default.fileExists(atPath: cprReference.path), "Requires the locally acquired pinned CPR reference."))
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
}
