import Foundation
import Testing
@testable import RebaseCore

/// Generated controls are self-authored archive inputs; factory bytes are read
/// from the pinned local reference. Neither is a Reference runtime observation.
final class CPRRecoveryV3Tests {
    private let workspace = PrivateResearchFixtures.root
    private func u16(_ value: UInt16) -> Data { var value = value.bigEndian; return withUnsafeBytes(of: &value) { Data($0) } }
    private func u32(_ value: UInt32) -> Data { var value = value.bigEndian; return withUnsafeBytes(of: &value) { Data($0) } }
    private func u64(_ value: UInt64) -> Data { var value = value.bigEndian; return withUnsafeBytes(of: &value) { Data($0) } }
    private func string(_ value: String) -> Data { u32(UInt32(value.utf8.count + 1)) + Data(value.utf8) + Data([0]) }
    private func object(_ name: String, _ version: UInt16 = 0, _ body: Data) -> Data {
        u32(.max) + string(name) + u16(version) + u32(UInt32(body.count)) + body
    }
    private func integer(_ key: UInt32, _ value: Int64, type: UInt16 = 1) -> Data {
        u32(key) + u16(type) + u64(UInt64(bitPattern: value))
    }
    private func variation(flags: UInt16 = 2, selector: UInt32 = 10, trailing: UInt32 = 0,
                           alternate: Data? = nil, count: UInt32 = 1) -> Data {
        let child = object("MTrackVariation", 0, string("v1") + (alternate ?? u32(0)) + u32(trailing))
        return u32(0x69435654) + u16(0x22) + object("MTrackVariationCollection", 0,
            u32(selector) + u16(flags) + u32(count) + child)
    }
    private func trackAttributes(_ supplied: [Data]? = nil) -> Data {
        let fields = supplied ?? [variation(), integer(0x6b636f4c, 0, type: 0x801), integer(0x73687445, -260498236)]
        return u32(UInt32(fields.count)) + fields.reduce(Data(), +)
    }
    private func score(version: UInt16 = 2, changed: Bool = false, extra: Data = Data(), name: String = "NoteData") -> Data {
        var fields: Data
        if version == 2 {
            fields = u32(.max) + u32(.max) + u16(changed ? 1 : 0) + u16(0) + Data([0])
        } else {
            let values: [(String, Int64)] = [("voiceIndexOnStave", -1), ("staveIndex", -1),
                ("isGraceNote", 0), ("noteNameOptionalIsSet", changed ? 1 : 0), ("noteName", 0)]
            fields = u32(5)
            for (key, value) in values { fields += string(key) + u16(1) + u64(UInt64(bitPattern: value)) }
        }
        let child = object(name, version, fields + extra)
        let collection = object("ScoreEventAttributeContainer", 1, u32(10) + u16(1) + u32(1) + child)
        return u32(1) + u32(0x5343436e) + u16(0x22) + collection
    }
    private typealias Point = (period: Float, seconds: Double, tick: Double, kind: UInt16)
    private var defaultPoints: [Point] { [(0.75, 0, 0, 0), (0.5, 600, 384000, 0)] }
    private func fixture(points supplied: [Point]? = nil, attrs: Data? = nil,
                         itemAttrs: [Data]? = nil, trailing: Data = Data(), fixed: Bool = false) -> Data {
        let points = supplied ?? defaultPoints
        var tempo = u32(UInt32(points.count))
        for point in points {
            tempo += u32(point.period.bitPattern) + u64(point.seconds.bitPattern) + u64(point.tick.bitPattern) + u16(point.kind)
        }
        tempo += u32(Float(126.5).bitPattern) + u16(fixed ? 1 : 0)
        tempo += attrs ?? trackAttributes()
        tempo += (itemAttrs ?? points.map { _ in u32(0) }).reduce(Data(), +)
        tempo += trailing
        let audioNode = object("MListNode", 0, string("Recovered Audio") + u32(1) + u64(0) + u32(0))
        let audio = object("MAudioTrackEvent", 1, Data(repeating: 0, count: 26) + audioNode)
        let node = object("MTrackList", 0, string("") + u32(0) + object("MTempoTrackEvent", 3, tempo)
            + u32(0) + u16(0) + u32(1) + audio)
        let archive = object("PArrangement", 4, object("MRoot", 6, Data(repeating: 0, count: 26) + node))
        func raw(_ value: String) -> Data { u32(UInt32(value.utf8.count)) + Data(value.utf8) }
        func chunk(_ label: String, _ data: Data) -> Data { Data(label.utf8) + u32(UInt32(data.count)) + data }
        let sections = chunk("ROOT", raw("Arrangement1") + raw("PArrangement")) + chunk("ARCH", archive)
        return Data("RIFF".utf8) + u32(UInt32(sections.count)) + Data("NUND".utf8) + sections
    }
    private func recover(_ data: Data) throws -> (recovery: CPRRecoveryResult, clock: NativeTempoClock?) {
        try CPRRecoveryV3(container: CPRProject.readContainer(data)).decode(sourceName: "Control.cpr")
    }
    private func rejectsMap(_ data: Data) throws {
        let result = try recover(data)
        #expect(result.clock == nil)
        #expect(result.recovery.project?.tempoMap.nativeClock == nil)
        #expect(result.recovery.project?.tempoMap.events.first?.bpm == 120)
        #expect(result.recovery.defaults.contains { $0.hasPrefix("120 BPM is an application default") })
        #expect(result.recovery.unsupported.contains { $0.category == "Native jump-tempo map" })
        #expect(!result.recovery.facts.contains { $0.hasPrefix("Recovered 1 native jump") || $0.hasPrefix("Recovered 2 native jump") })
    }

    @Test func generatedCanonicalMapRetainsExactRecordsAndDisplayProjection() throws {
        let bytes = fixture(), first = try recover(bytes), second = try recover(bytes)
        let clock = try #require(first.clock), records = try #require(clock.mapRecords)
        #expect(clock.contract == NativeTempoClock.mapContract && clock.interpretationProfile == "cpr-static-subset-v3")
        #expect(clock.sourceSHA256 == cprSHA256(bytes))
        #expect(records.map(\.periodBits) == [Float(0.75).bitPattern, Float(0.5).bitPattern])
        #expect(records.map(\.secondsBits) == [0, Double(600).bitPattern])
        #expect(records.map(\.tickBits) == [0, Double(384000).bitPattern])
        #expect(records[1].sourceRecordOffset == records[0].sourceRecordOffset + 22)
        #expect(first.recovery.project == second.recovery.project && first.clock == second.clock)
        let project = try #require(first.recovery.project)
        #expect(project.tracks.count == 1 && project.tracks[0].clips.isEmpty)
        #expect(project.tempoMap.events.map(\.bpm) == [80, 120])
        #expect(project.tempoMap.events.map(\.beat) == [0, 800])
        #expect(try project.tempoMap.seconds(atBeat: 801) == 600.5)
        #expect(!first.recovery.defaults.contains { $0.hasPrefix("120 BPM") })
        #expect(!first.recovery.unsupported.contains { $0.category == "Tempo event map" })
        #expect(first.recovery.objects.contains { $0.className == "MTrackVariation" })
    }

    @Test func defaultNoteDataBothEncodingsAreAllowedButChangedStateIsNot() throws {
        for version: UInt16 in [2, 3] {
            let bytes = fixture(points: [(Float(60)/134, 0, 0, 0)], itemAttrs: [score(version: version)])
            let result = try recover(bytes)
            #expect(result.clock?.mapRecords?.count == 1)
            #expect(result.recovery.objects.contains { $0.className == "NoteData" && $0.version == version })
            try rejectsMap(fixture(points: [(0.5, 0, 0, 0)], itemAttrs: [score(version: version, changed: true)]))
            try rejectsMap(fixture(points: [(0.5, 0, 0, 0)], itemAttrs: [score(version: version, extra: Data([0]))]))
        }
        try rejectsMap(fixture(points: [(0.5, 0, 0, 0)], itemAttrs: [score(version: 4)]))
    }

    @Test func unknownAuxiliaryAndVariationStateRemainExplicitlyUnsupported() throws {
        let lock = integer(0x6b636f4c, 0, type: 0x801)
        for fields in [
            [variation(), lock, integer(0x64696854, 0)], // Visibility callback key.
            [variation(), lock, integer(0x12345678, 0)],
            [variation(), integer(0x6b636f4c, 1, type: 0x801)],
            [variation(), integer(0x6b636f4c, 0, type: 1)],
            [variation(), lock, integer(0x73687445, 0)],
            [variation(flags: 1), lock], [variation(selector: 0), lock],
            [variation(trailing: 1), lock], [variation(count: 2), lock],
            [variation(alternate: object("MDataNode", 0, Data())), lock]
        ] { try rejectsMap(fixture(attrs: trackAttributes(fields))) }
        let duplicate = fixture(attrs: trackAttributes([variation(), lock, lock]))
        #expect(throws: CPRProjectError.self) { try recover(duplicate) }
    }

    @Test func timingBoundariesAndUnconsumedPayloadsDoNotPromoteAClock() throws {
        try rejectsMap(fixture(points: [(0.75, 0, 0, 0), (0.5, Double(600).nextUp, 384000, 0)]))
        try rejectsMap(fixture(points: [(0.75, 0, 0, 0), (0.5, 0, 0, 0)]))
        try rejectsMap(fixture(points: [(0.75, -0.0, 0, 0)]))
        try rejectsMap(fixture(points: [(0.75, 0, 0, 1)]))
        try rejectsMap(fixture(points: [(0.75, 0, 0, 0), (0.5, 600, 384000, 0), (0.5, 601, 384960, 0)]))
        try rejectsMap(fixture(trailing: Data([0])))
        // A truncated body with valid envelope/object lengths must fail bounds,
        // not become a successful prefix parse.
        let truncated = fixture(itemAttrs: [u32(0), Data([0, 0])])
        #expect(throws: CPRProjectError.self) { try recover(truncated) }
    }

    @Test func fixedModeIsExactlyTheFrozenV2Interpretation() throws {
        let bytes = fixture(fixed: true), container = try CPRProject.readContainer(bytes)
        let old = try CPRRecoveryV2(container: container).decode(sourceName: "Control.cpr")
        let new = try recover(bytes)
        #expect(new.clock == old.clock && new.clock?.interpretationProfile == "cpr-static-subset-v2")
        #expect(new.recovery.project == old.recovery.project)
        #expect(new.recovery.facts == old.recovery.facts && new.recovery.defaults == old.recovery.defaults)
        #expect(new.recovery.objects == old.recovery.objects && new.recovery.unsupported == old.recovery.unsupported)
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func tenPinnedFactoryFilesSeparateSixMapClocksFromFourUnchangedFixedClocks() throws {
        let manifestURL = workspace.appendingPathComponent("evidence/cpr-static/cpr-audio-timing-001/reviewer-template-state.json")
        let manifest = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: manifestURL)) as? [String: Any])
        let fixtures = try #require(manifest["fixtures"] as? [[String: Any]])
        var maps = 0, fixed = 0
        for fixture in fixtures {
            let source = try PrivateResearchFixtures.template(recordedPath: #require(fixture["source"] as? String))
            let bytes = try Data(contentsOf: source)
            #expect(cprSHA256(bytes) == fixture["source_sha256"] as? String)
            let container = try CPRProject.readContainer(bytes)
            let result = try CPRRecoveryV3(container: container).decode(sourceName: source.lastPathComponent)
            let clock = try #require(result.clock, "No clock for \(source.lastPathComponent): \(result.recovery.unsupported)")
            if clock.mapRecords != nil {
                maps += 1
                #expect(result.recovery.facts.contains { $0.contains("native jump-tempo point") })
                #expect(!result.recovery.defaults.contains { $0.hasPrefix("120 BPM") })
            } else {
                fixed += 1
                let old = try CPRRecoveryV2(container: container).decode(sourceName: source.lastPathComponent)
                #expect(result.clock == old.clock && result.recovery.project == old.recovery.project)
                #expect(result.recovery.objects == old.recovery.objects && result.recovery.facts == old.recovery.facts)
            }
            #expect(try Data(contentsOf: source) == bytes)
        }
        #expect(fixtures.count == 10 && maps == 6 && fixed == 4)
    }

    @Test func mapImportPersistsProofAndRejectsDescriptorTampering() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("CPRMapImport-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let source = root.appendingPathComponent("Map.cpr"), destination = root.appendingPathComponent("Map.rebaseproj")
        let bytes = fixture(); try bytes.write(to: source)
        let imported = try CPRProject.importProject(from: source, to: destination, allowPartial: true)
        #expect(imported.report.interpretationProfile == CPRProject.currentInterpretationProfile)
        #expect(imported.project.tempoMap.nativeClock?.mapRecords?.count == 2)
        #expect(try ProjectStore.load(from: destination) == imported.project)
        #expect(try CPRProject.compatibilityReport(from: destination) == imported.report)
        #expect(try Data(contentsOf: destination.appendingPathComponent(CPRProject.originalRelativePath)) == bytes)
        let manifest = destination.appendingPathComponent("Project.json")
        let before = try Data(contentsOf: manifest)
        var project = imported.project
        let clock = try #require(project.tempoMap.nativeClock), records = try #require(clock.mapRecords)
        let forged = try NativeTempoClock(mapRecords: records, sourceSHA256: String(repeating: "a", count: 64),
                                          sourceObjectOffset: clock.sourceObjectOffset)
        project.tempoMap = TempoMap(events: project.tempoMap.events, nativeClock: forged)
        #expect(throws: (any Error).self) { try ProjectStore.save(project, to: destination) }
        #expect(try Data(contentsOf: manifest) == before)
        try project.convertToApplicationTiming()
        try ProjectStore.save(project, to: destination)
        #expect(try ProjectStore.load(from: destination).tempoMap.nativeClock == nil)
        #expect(try CPRProject.compatibilityReport(from: destination) == imported.report)
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func realMapPackagesBindCanonicalAlternativeToSourceAndAllowExplicitExchangeConversion() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("CPRFactoryMap-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let reference = workspace.appendingPathComponent("templates")
        let sources = [("LoFi Hip Hop", "2795af70cbc6651fbd6aa4cfbcb546d606d25d5970722a6c553384f3d196e495"),
                       ("Stereo Mastering", "6cde8a5ce37e5f112c79f684ad8c1fc3e308979feba9f046db42bf62ecce3022")]
        for (name, expectedSHA) in sources {
            let source = reference.appendingPathComponent(name + ".cpr")
            let sourceBytes = try Data(contentsOf: source)
            #expect(cprSHA256(sourceBytes) == expectedSHA)
            let destination = root.appendingPathComponent(name + ".rebaseproj")
            let imported = try CPRProject.importProject(from: source, to: destination, allowPartial: true)
            try ProjectStore.save(imported.project, to: destination)
            #expect(try ProjectStore.load(from: destination) == imported.project)
            let reportURL = destination.appendingPathComponent(CPRProject.reportRelativePath)
            let reportBytes = try Data(contentsOf: reportURL)
            let projectURL = destination.appendingPathComponent("Project.json")
            let projectBytes = try Data(contentsOf: projectURL)
            let old = try #require(imported.project.tempoMap.nativeClock)
            let records = try #require(old.mapRecords)
            // This alternative is internally canonical and its display agrees;
            // only preserved-source replay can distinguish it from imported data.
            let alternate = records.map {
                NativeTempoMapRecord(periodBits: Float(1).bitPattern, secondsBits: ($0.tick / 480).bitPattern,
                    tickBits: $0.tickBits, kind: 0, sourceRecordOffset: $0.sourceRecordOffset)
            }
            let forged = try NativeTempoClock(mapRecords: alternate, sourceSHA256: old.sourceSHA256,
                                               sourceObjectOffset: old.sourceObjectOffset)
            var changed = imported.project
            changed.tempoMap = TempoMap(events: alternate.enumerated().map { index, record in
                TempoEvent(id: imported.project.tempoMap.events[index].id, beat: record.beat,
                           bpm: record.displayBPM, curve: .jump)
            }, nativeClock: forged)
            try changed.validate()
            #expect(throws: (any Error).self) { try ProjectStore.save(changed, to: destination) }
            #expect(try Data(contentsOf: projectURL) == projectBytes)
            try JSONEncoder().encode(changed).write(to: projectURL)
            #expect(throws: (any Error).self) { try ProjectStore.load(from: destination) }
            try projectBytes.write(to: projectURL)
            var converted = imported.project
            try converted.convertToApplicationTiming()
            try ProjectStore.save(converted, to: destination)
            let reopened = try ProjectStore.load(from: destination)
            #expect(reopened == converted && reopened.tempoMap.nativeClock == nil)
            let export = root.appendingPathComponent(name + ".dawproject")
            var explicitSubset = reopened
            if !explicitSubset.unresolvedAudioEvents.isEmpty {
                #expect(throws: (any Error).self) { try DAWProject.export(project: explicitSubset, projectRoot: destination, to: export) }
                #expect(!FileManager.default.fileExists(atPath: export.path))
                for index in explicitSubset.tracks.indices { explicitSubset.tracks[index].unresolvedAudioEvents = [] }
            }
            try DAWProject.export(project: explicitSubset, projectRoot: destination, to: export)
            #expect(FileManager.default.fileExists(atPath: export.path))
            #expect(try Data(contentsOf: reportURL) == reportBytes)
            #expect(try Data(contentsOf: destination.appendingPathComponent(CPRProject.originalRelativePath)) == sourceBytes)
            #expect(try CPRProject.compatibilityReport(from: destination) == imported.report)
        }
    }
}
