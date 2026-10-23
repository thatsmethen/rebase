import Foundation
import Testing
@testable import RebaseCore

/// Independent source-field controls for the typed saved configuration. No
/// Reference execution or hosted device-state equivalence is claimed by these tests.
@Suite(.serialized)
struct CPRProjectAudioSetupTests {
    private let workspace = PrivateResearchFixtures.root
    private var references: URL {
        workspace.appendingPathComponent("templates")
    }
    private func original() throws -> Data {
        let bytes = try Data(contentsOf: references.appendingPathComponent("LoFi Hip Hop.cpr"))
        #expect(cprSHA256(bytes) == "2795af70cbc6651fbd6aa4cfbcb546d606d25d5970722a6c553384f3d196e495")
        return bytes
    }
    // Existing envelope mechanics locate the typed field independently of the
    // new decoder. No string search or rate-value search establishes ownership.
    private func object(_ bytes: Data) throws -> CPRObjectRecord {
        let container = try CPRProject.readContainer(bytes)
        let section = try #require(container.sections.first { $0.name == "Arrangement1" })
        let archive = CPRArchive(data: bytes, section: section)
        let root = try archive.root(expectedClass: "PArrangement")
        var cursor = archive.body(root)
        #expect(try archive.readObject(&cursor)?.descriptor.className == "MRoot")
        let result = try #require(try archive.readObject(&cursor)).descriptor
        #expect(result.className == "PArrangeSetup" && result.version == 8)
        return result
    }
    private func be<T: FixedWidthInteger>(_ value: T) -> Data {
        var big = value.bigEndian
        return withUnsafeBytes(of: &big) { Data($0) }
    }
    private func put<T: FixedWidthInteger>(_ value: T, _ offset: Int, _ bytes: inout Data) {
        bytes.replaceSubrange(offset..<(offset + MemoryLayout<T>.size), with: be(value))
    }
    private func changed(rate: UInt32 = Float(44100).bitPattern,
                         factor: UInt64 = Double(1).bitPattern) throws -> Data {
        var bytes = try original()
        let descriptor = try object(bytes)
        #expect(descriptor.payloadOffset == 1_291_475 && descriptor.payloadByteCount == 169)
        put(rate, descriptor.payloadOffset + 0x30, &bytes)
        put(factor, descriptor.payloadOffset + 0x5c, &bytes)
        return bytes
    }
    private func rejects(_ work: () throws -> Void) -> Bool {
        do { try work(); return false } catch { return true }
    }
    private func native(_ name: String, version: UInt16, body: Data) -> Data {
        be(UInt32.max) + be(UInt32(name.utf8.count + 1)) + Data(name.utf8) + Data([0])
            + be(version) + be(UInt32(body.count)) + body
    }
    private func envelope(setup: Data, rootClass: String = "MRoot", rootVersion: UInt16 = 6,
                          decoy: Data = Data(), suffix: Data? = nil) throws -> CPRContainer {
        let body = native(rootClass, version: rootVersion, body: decoy) + setup + (suffix ?? Data(repeating: 0, count: 28))
        let archive = native("PArrangement", version: 4, body: body)
        func string(_ value: String) -> Data { be(UInt32(value.utf8.count)) + Data(value.utf8) }
        let root = string("Arrangement1") + string("PArrangement")
        let sections = Data("ROOT".utf8) + be(UInt32(root.count)) + root
            + Data("ARCH".utf8) + be(UInt32(archive.count)) + archive
        return try CPRProject.readContainer(Data("RIFF".utf8) + be(UInt32(sections.count)) + Data("NUND".utf8) + sections)
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason)) func AllTenPinnedTemplatesBindTheDirectSavedRateWithoutChangingV4() throws {
        let inventory = try Data(contentsOf: workspace.appendingPathComponent("evidence/cpr-static/cpr-container-001/inventory.json"))
        #expect(cprSHA256(inventory) == "e50ff515c541c76d857d6c093f4329b5cb53bffcd631a6e22cbc5edf86511b0d")
        let records = try #require((JSONSerialization.jsonObject(with: inventory) as? [String: Any])?["records"] as? [[String: Any]])
        #expect(records.count == 10)
        for record in records {
            let name = try #require(record["name"] as? String), url = references.appendingPathComponent(name)
            let bytes = try Data(contentsOf: url), container = try CPRProject.readContainer(bytes)
            #expect(cprSHA256(bytes) == record["sha256"] as? String)
            let expected = try object(bytes), setup = try CPRProjectAudioSetup.read(container: container)
            #expect(setup.setup == expected && setup.sourceSHA256 == container.sha256)
            #expect(setup.baseRateBits == 0x472c4400 && setup.factorBits == 0x3ff0000000000000)
            #expect(try setup.supportedSampleRate() == 44100)
            let old = try CPRRecoveryV4(container: container).decode(sourceName: name)
            let current = try CPRProject.inspect(from: url)
            #expect(current.interpretationProfile == "cpr-static-subset-v5")
            #expect(current.audioSetup == setup && current.nativeClock == old.clock)
            if var prior = old.recovery.project {
                #expect(prior.sampleRate == 48000)
                prior.sampleRate = 44100
                #expect(current.recoveredProject == prior)
            }
            #expect(current.nativeObjects.contains(expected))
            #expect(try Data(contentsOf: url) == bytes)
        }
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason)) func RawRateAndFactorBoundsCannotBecomeAHostClockByFallback() throws {
        for rate: Float in [10000, 32000, 44100, 48000, 88200, 96000, 192000] {
            let bytes = try changed(rate: rate.bitPattern)
            let setup = try CPRProjectAudioSetup.read(container: CPRProject.readContainer(bytes))
            #expect(setup.baseRateBits == rate.bitPattern)
            #expect(try setup.supportedSampleRate() == Double(rate))
        }
        for rate: Float in [0, -0.0, -1, 8000, 9999, 44100.5, 192001, 1024000, 1024001, .infinity, -.infinity, .nan] {
            let bytes = try changed(rate: rate.bitPattern)
            #expect(rejects {
                _ = try CPRProjectAudioSetup.read(container: CPRProject.readContainer(bytes)).supportedSampleRate()
            })
        }
        for factor in [0.0, -0.0, -1, 0.999, 1.001, 2, Double.infinity, -Double.infinity, Double.nan] {
            let bytes = try changed(factor: factor.bitPattern)
            #expect(rejects {
                _ = try CPRProjectAudioSetup.read(container: CPRProject.readContainer(bytes)).supportedSampleRate()
            })
        }
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason)) func TypedOwnerAndCompleteBodyAreRequiredEvenWhenDecoyRatesExist() throws {
        let bytes = try original(), descriptor = try object(bytes)
        let body = bytes.subdata(in: descriptor.payloadOffset..<(descriptor.payloadOffset + descriptor.payloadByteCount))
        let valid = native("PArrangeSetup", version: 8, body: body)
        #expect(try CPRProjectAudioSetup.read(container: envelope(setup: valid)).supportedSampleRate() == 44100)
        var invalid: [CPRContainer] = []
        invalid.append(try envelope(setup: be(UInt32(0)), decoy: valid))
        invalid.append(try envelope(setup: valid, rootClass: "MListNode"))
        invalid.append(try envelope(setup: valid, rootVersion: 7))
        invalid.append(try envelope(setup: native("OtherSetup", version: 8, body: body)))
        invalid.append(try envelope(setup: be(UInt32(123456))))
        for version: UInt16 in [0, 1, 7, 9, UInt16.max] {
            invalid.append(try envelope(setup: native("PArrangeSetup", version: version, body: body)))
        }
        for length in [0, 47, 51, 91, 99, 168] {
            invalid.append(try envelope(setup: native("PArrangeSetup", version: 8, body: Data(body.prefix(length)))))
        }
        invalid.append(try envelope(setup: native("PArrangeSetup", version: 8, body: body + Data([0]))))
        for container in invalid {
            #expect(rejects { _ = try CPRProjectAudioSetup.read(container: container) })
        }
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason)) func VariableStringsAndEmbeddedDatumBoundsAreParsedForward() throws {
        let bytes = try original(), descriptor = try object(bytes)
        let originalBody = bytes.subdata(in: descriptor.payloadOffset..<(descriptor.payloadOffset + descriptor.payloadByteCount))
        func string(_ value: String) -> Data {
            let bytes = Data(value.utf8) + Data([0,0xef,0xbb,0xbf])
            return be(UInt32(bytes.count)) + bytes
        }
        var body = Data(originalBody.prefix(120))
        body += string("wave") + string("alternative") + string("A longer format display name")
        body += Data("int24\0".utf8) + be(UInt32(0))
        var suffix = Data()
        for index in 0..<7 { suffix += string("Saved text \(index)") }
        let setup = try CPRProjectAudioSetup.read(container: envelope(
            setup:native("PArrangeSetup",version:8,body:body),suffix:suffix))
        #expect(try setup.supportedSampleRate() == 44100)
        #expect(setup.setup.payloadByteCount != 169)
        for position in [8,28,64] {
            for tag:Int32 in [1,10] {
                var altered = body; put(tag,position,&altered)
                #expect(try CPRProjectAudioSetup.read(container:envelope(
                    setup:native("PArrangeSetup",version:8,body:altered))).supportedSampleRate() == 44100)
            }
            for tag:Int32 in [0,17,2,-1] {
                var altered = body; put(tag,position,&altered)
                #expect(rejects { _ = try CPRProjectAudioSetup.read(container:envelope(
                    setup:native("PArrangeSetup",version:8,body:altered))) })
            }
        }
        var malformed = body; put(UInt32.max,120,&malformed)
        #expect(rejects { _ = try CPRProjectAudioSetup.read(container:envelope(
            setup:native("PArrangeSetup",version:8,body:malformed))) })
        #expect(rejects { _ = try CPRProjectAudioSetup.read(container:envelope(
            setup:native("PArrangeSetup",version:8,body:body),suffix:Data(suffix.dropLast()))) })
        #expect(rejects { _ = try CPRProjectAudioSetup.read(container:envelope(
            setup:native("PArrangeSetup",version:8,body:body),suffix:suffix+be(UInt32(0)))) })
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason)) func V5UnsupportedRateRemainsExplicitAndHistoricalV4ReportIsUntouched() throws {
        let temporary = FileManager.default.temporaryDirectory.appendingPathComponent("SavedRate-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: temporary, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporary) }
        for (index, bytes) in try [changed(rate: Float(8000).bitPattern), changed(factor: Double(1.001).bitPattern)].enumerated() {
            let source = temporary.appendingPathComponent("Unsupported\(index).cpr")
            try bytes.write(to: source)
            let report = try CPRProject.inspect(from: source)
            #expect(report.recoveredProject?.sampleRate == 48000)
            #expect(report.audioSetup != nil)
            #expect(report.applicationDefaults.contains { $0.contains("48 kHz") })
            #expect(report.unsupported.contains { $0.detail.lowercased().contains("rate") || $0.detail.lowercased().contains("factor") })
        }
        let source = references.appendingPathComponent("LoFi Hip Hop.cpr")
        let package = temporary.appendingPathComponent("Historical.rebaseproj")
        let imported = try CPRProject.importProject(from: source, to: package, allowPartial: true)
        let bytes = try original(), container = try CPRProject.readContainer(bytes)
        let old = try CPRRecoveryV4(container: container).decode(sourceName: source.lastPathComponent)
        let baseline = old.recovery
        let report = CPRInspection(schemaVersion: 2, interpretationProfile: "cpr-static-subset-v4", nativeClock: old.clock,
            sourceName: source.lastPathComponent, sourceSHA256: container.sha256, sourceByteCount: bytes.count,
            sections: container.sections, recoveredFacts: baseline.facts, metadataFacts: baseline.metadata,
            recoveredTracks: baseline.tracks, nativeObjects: baseline.objects, applicationDefaults: baseline.defaults,
            unsupported: baseline.unsupported, recoveredProject: baseline.project)
        let reportURL = package.appendingPathComponent(CPRProject.reportRelativePath)
        try JSONEncoder().encode(report).write(to: reportURL)
        let project = try #require(baseline.project)
        try ProjectStore.save(project, to: package)
        let paths = ["Project.json", CPRProject.reportRelativePath, CPRProject.originalRelativePath]
        let before = try paths.map { try Data(contentsOf: package.appendingPathComponent($0)) }
        #expect(imported.project.sampleRate == 44100 && project.sampleRate == 48000)
        #expect(try CPRProject.compatibilityReport(from: package) == report)
        let loaded = try ProjectStore.load(from: package), event = try #require(loaded.unresolvedAudioEvents.first)
        let inspection = try CPRSourceAudioInspection.inspect(eventID: event.id, in: loaded, at: package)
        #expect(try inspection.savedProjectAudioSetup?.supportedSampleRate() == 44100)
        #expect(inspection.projectSampleRate == 48000 && inspection.nativeSavedProjectClockRange != nil)
        #expect(inspection.nativeSavedProjectClockPlaybackUnavailableReason?.contains("Attach") == true)
        #expect(try paths.map { try Data(contentsOf: package.appendingPathComponent($0)) } == before)
    }
}
