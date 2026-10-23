import Foundation
import Testing
@testable import RebasePortable

struct RebasePortableTests {
    private var applicationRoot: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
    }

    @Test func bundledExampleModelRoundTripsWithoutRewritingItsMedia() throws {
        let root = applicationRoot.appendingPathComponent("Examples/Rebase Preview.rebaseproj")
        let bytes = try Data(contentsOf: root.appendingPathComponent("Project.json"))
        let project = try JSONDecoder().decode(Project.self, from: bytes)
        try project.validate()
        #expect(project.name == "Rebase Preview")
        #expect(project.tracks.count == 4 && project.tracks.flatMap(\.clips).count == 11)
        #expect(project.sampleRate == 48_000 && project.tempo == 96 && project.duration == 20)
        #expect(project.unresolvedAudioEvents.isEmpty && project.cprMediaAttachments.isEmpty)
        #expect(try JSONDecoder().decode(Project.self, from: JSONEncoder().encode(project)) == project)
        let manifest = try JSONDecoder().decode(ExampleManifest.self,
            from: Data(contentsOf: applicationRoot.appendingPathComponent("Examples/example.json")))
        #expect(manifest.files.count == 5)
        for item in manifest.files {
            let data = try Data(contentsOf: root.appendingPathComponent(item.path))
            #expect(data.count == item.bytes)
            #expect(cprSHA256(data) == item.sha256)
        }
        #expect(try Data(contentsOf: root.appendingPathComponent("Project.json")) == bytes)
    }

    @Test func modelEditsPreserveValidationAndAutomationSemantics() throws {
        var project = Project(tempo: 96, tracks: [Track(name: "Control", clips: [
            Clip(mediaPath: "Media/control.wav", name: "Control", position: 1, duration: 2)
        ])])
        project.tracks[0].gainDB = -6
        project.tracks[0].pan = 0.25
        project.tracks[0].clips[0].position = 3
        try project.validate()
        #expect(project.duration == 5)
        #expect(try project.tempoMap.seconds(atBeat: 4) == 2.5)
        let lane = AutomationLane(parameter: .gainDB, points: [
            AutomationPoint(time: 0, value: -12), AutomationPoint(time: 2, value: -6)
        ])
        try lane.validate()
        #expect(lane.value(at: 1, fallback: 0) == -9)
        project.tracks[0].clips[0].duration = -.infinity
        #expect(throws: RebaseCoreError.self) { try project.validate() }
    }

    @Test func authoredCPRControlUsesCurrentRecoveryWithoutSourceMutation() throws {
        try withDirectory { directory in
            let source = directory.appendingPathComponent("Control.cpr")
            let bytes = structuralControl(trackName: Data("Control Audio\0".utf8))
            try bytes.write(to: source)
            let report = try CPRProject.inspect(from: source)
            #expect(report.sourceSHA256 == cprSHA256(bytes))
            #expect(report.sourceByteCount == bytes.count)
            #expect(report.interpretationProfile == CPRProject.currentInterpretationProfile)
            #expect(report.recoveredProject?.tracks.first?.name == "Control Audio")
            #expect(report.recoveredTrackCount == 1 && report.recoveredClipCount == 0)
            #expect(!report.unsupported.isEmpty)
            #expect(try JSONDecoder().decode(CPRInspection.self, from: JSONEncoder().encode(report)) == report)
            #expect(try Data(contentsOf: source) == bytes)
            #expect(try FileManager.default.contentsOfDirectory(atPath: directory.path) == ["Control.cpr"])
        }
    }

    @Test func malformedCPRControlsRemainRejected() throws {
        let valid = structuralControl(trackName: Data("Audio\0".utf8))
        for count in [0, 4, 11, valid.count - 1] {
            #expect(throws: CPRProjectError.self) { try CPRProject.readContainer(Data(valid.prefix(count))) }
        }
        var wrongSize = valid
        wrongSize[7] ^= 1
        #expect(throws: CPRProjectError.self) { try CPRProject.readContainer(wrongSize) }
        let root = section("Arrangement1", "Opaque", Data([1, 2, 3]))
        #expect(throws: CPRProjectError.self) { try CPRProject.readContainer(container(root + root)) }
        try withDirectory { directory in
            let source = directory.appendingPathComponent("Rejected.cpr")
            for name in [Data("Unterminated".utf8), Data([0xef, 0xbb, 0xbf, 0xff, 0])] {
                try structuralControl(trackName: name).write(to: source)
                #expect(throws: CPRProjectError.self) { try CPRProject.inspect(from: source) }
            }
        }
    }

    @Test func preservedReportMustStillMatchItsSourceAndInterpretation() throws {
        try withDirectory { directory in
            let source = directory.appendingPathComponent("Control.cpr")
            let bytes = structuralControl(trackName: Data("Audio\0".utf8))
            try bytes.write(to: source)
            let report = try CPRProject.inspect(from: source)
            let package = directory.appendingPathComponent("Evidence.rebaseproj")
            let original = package.appendingPathComponent(CPRProject.originalRelativePath)
            let reportURL = package.appendingPathComponent(CPRProject.reportRelativePath)
            try FileManager.default.createDirectory(at: original.deletingLastPathComponent(), withIntermediateDirectories: true)
            try bytes.write(to: original)
            try JSONEncoder().encode(report).write(to: reportURL)
            #expect(try CPRProject.compatibilityReport(from: package) == report)
            var changed = bytes
            changed[changed.count - 1] ^= 1
            try changed.write(to: original)
            #expect(throws: CPRProjectError.self) { try CPRProject.compatibilityReport(from: package) }
            try bytes.write(to: original)
            var json = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: reportURL)) as? [String: Any])
            json["sourceName"] = "Changed.cpr"
            json["interpretationProfile"] = "unverified-profile"
            try JSONSerialization.data(withJSONObject: json).write(to: reportURL)
            #expect(throws: CPRProjectError.self) { try CPRProject.compatibilityReport(from: package) }
        }
    }

    @Test func sha256MatchesStandardKnownAnswersAndIndependentPaddingControls() {
        let messages = [
            (Data(), "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
            (Data("abc".utf8), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"),
            (Data("abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq".utf8), "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"),
            (Data(repeating: 97, count: 1_000_000), "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0")
        ]
        for (data, expected) in messages { #expect(cprSHA256(data) == expected) }
        // Independent Python hashlib outputs over bytes(i % 251), not outputs
        // generated by the candidate implementation under test.
        let boundaries = [
            55: "463eb28e72f82e0a96c0a4cc53690c571281131f672aa229e0d45ae59b598b59",
            56: "da2ae4d6b36748f2a318f23e7ab1dfdf45acdc9d049bd80e59de82a60895f562",
            63: "29af2686fd53374a36b0846694cc342177e428d1647515f078784d69cdb9e488",
            64: "fdeab9acf3710362bd2658cdc9a29e8f9c757fcf9811603a8c447cd1d9151108",
            65: "4bfd2c8b6f1eec7a2afeb48b934ee4b2694182027e6d0fc075074f2fabb31781",
            127: "92ca0fa6651ee2f97b884b7246a562fa71250fedefe5ebf270d31c546bfea976",
            128: "471fb943aa23c511f6f72f8d1652d9c880cfa392ad80503120547703e56a2be5",
            129: "5099c6a56203f9687f7d33f4bfdf576d31dc91f6b695ecea38b2770c87631135"
        ]
        for (count, expected) in boundaries {
            #expect(cprSHA256(Data((0..<count).map { UInt8($0 % 251) })) == expected)
        }
    }

    private struct ExampleManifest: Decodable {
        struct Entry: Decodable { let path: String; let bytes: Int; let sha256: String }
        let files: [Entry]
    }
    private func withDirectory(_ body: (URL) throws -> Void) throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("RebasePortable-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try body(root)
    }
    private func be(_ value: UInt32) -> Data {
        var value = value.bigEndian
        return withUnsafeBytes(of: &value) { Data($0) }
    }
    private func be16(_ value: UInt16) -> Data {
        var value = value.bigEndian
        return withUnsafeBytes(of: &value) { Data($0) }
    }
    private func string(_ value: String) -> Data { be(UInt32(value.utf8.count)) + Data(value.utf8) }
    private func record(_ tag: String, _ bytes: Data) -> Data { Data(tag.utf8) + be(UInt32(bytes.count)) + bytes }
    private func section(_ name: String, _ type: String, _ bytes: Data) -> Data {
        record("ROOT", string(name) + string(type)) + record("ARCH", bytes)
    }
    private func container(_ bytes: Data) -> Data { Data("RIFF".utf8) + be(UInt32(bytes.count)) + Data("NUND".utf8) + bytes }
    private func object(_ type: String, _ version: UInt16, _ body: Data) -> Data {
        be(0xffff_ffff) + be(UInt32(type.utf8.count + 1)) + Data(type.utf8) + Data([0]) + be16(version) + be(UInt32(body.count)) + body
    }
    /// Authored counted-structure control, not proprietary application output.
    private func structuralControl(trackName: Data) -> Data {
        let datum = be(1) + Data(repeating: 0, count: 8)
        let trackNode = object("MListNode", 0, be(UInt32(trackName.count)) + trackName + datum + be(0))
        let track = object("MAudioTrackEvent", 1, Data(repeating: 0, count: 26) + trackNode)
        let rootNode = object("MTrackList", 0, be(0) + datum + be16(0) + be(1) + track)
        let root = object("MRoot", 6, Data(repeating: 0, count: 26) + rootNode)
        return container(section("Arrangement1", "PArrangement", object("PArrangement", 4, root)))
    }
}
