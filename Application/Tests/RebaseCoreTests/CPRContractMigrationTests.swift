import Foundation
import Testing
@testable import RebaseCore

struct CPRContractMigrationTests {
    private let sourceHash = String(repeating: "a", count: 64)

    private func record(_ name: String, version: Int) -> CPRObjectRecord {
        CPRObjectRecord(className: name, version: version, declarationOffset: 16,
            objectOffset: 32, identityOffset: 32, payloadOffset: 40,
            payloadByteCount: 8, payloadSHA256: sourceHash)
    }

    private func setup(rate: UInt32 = Float(44100).bitPattern,
                       factor: UInt64 = Double(1).bitPattern) -> CPRProjectAudioSetup {
        CPRProjectAudioSetup(contract: CPRProjectAudioSetup.contractName,
            sourceSHA256: sourceHash, arrangement: record("PArrangement", version: 4),
            root: record("MRoot", version: 6), setup: record("PArrangeSetup", version: 8),
            baseRateBits: rate, factorBits: factor, baseRateOffset: 48, factorOffset: 92)
    }

    private func event(with placement: CPRAudioSourcePlacement) -> UnresolvedCPRAudioEvent {
        UnresolvedCPRAudioEvent(id: UUID(), sourceSHA256: sourceHash,
            event: record("MAudioEvent", version: 6), clip: record("PAudioClip", version: 4),
            cluster: record("AudioCluster", version: 0), name: "Migration control",
            rawStartBits: 0, rawLengthBits: Double(1).bitPattern, rawOffsetBits: 0,
            datumTag: 10, datumScalarBits: Double(1).bitPattern, files: [], segments: [],
            placement: placement, placementStatus: "Synthetic descriptor control")
    }

    private func object<T: Encodable>(_ value: T) throws -> [String: Any] {
        try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(value)) as? [String: Any])
    }

    private func data(_ object: [String: Any]) throws -> Data {
        try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
    }

    private func rejects(_ work: () throws -> Void) -> Bool {
        do { try work(); return false } catch { return true }
    }

    @Test func canonicalDescriptorsRoundTripWithoutChangingFields() throws {
        let fixed = try NativeTempoClock(fixedBPMBits: Float(120).bitPattern,
            sourceSHA256: sourceHash, sourceObjectOffset: 100)
        let map = try NativeTempoClock(mapRecords: [NativeTempoMapRecord(
            periodBits: Float(0.5).bitPattern, secondsBits: 0, tickBits: 0,
            kind: 0, sourceRecordOffset: 108)], sourceSHA256: sourceHash, sourceObjectOffset: 100)
        for clock in [fixed, map] {
            #expect(try JSONDecoder().decode(NativeTempoClock.self, from: JSONEncoder().encode(clock)) == clock)
        }
        let placement = CPRAudioSourcePlacement(contract: CPRAudioSourcePlacement.contractName,
            position: 0, duration: 1, offset: 0)
        #expect(try JSONDecoder().decode(CPRAudioSourcePlacement.self,
            from: JSONEncoder().encode(placement)) == placement)
        try event(with: placement).validate()
        let saved = setup()
        #expect(try JSONDecoder().decode(CPRProjectAudioSetup.self,
            from: JSONEncoder().encode(saved)) == saved)
        #expect(try saved.supportedSampleRate() == 44100)
    }

    @Test func unknownIdentitiesRemainRejectedByExistingDescriptorGates() throws {
        let fixed = try NativeTempoClock(fixedBPMBits: Float(120).bitPattern,
            sourceSHA256: sourceHash, sourceObjectOffset: 100)
        var clock = try object(fixed)
        clock["contract"] = "unknown-clock-contract"
        #expect(rejects { _ = try JSONDecoder().decode(NativeTempoClock.self, from: data(clock)) })
        let originalPlacement = CPRAudioSourcePlacement(contract: CPRAudioSourcePlacement.contractName,
            position: 0, duration: 1, offset: 0)
        var placement = try object(originalPlacement)
        placement["contract"] = "unknown-placement-contract"
        let decodedPlacement = try JSONDecoder().decode(CPRAudioSourcePlacement.self, from: data(placement))
        #expect(decodedPlacement.contract == "unknown-placement-contract")
        #expect(rejects { try event(with: decodedPlacement).validate() })
        var saved = try object(setup())
        saved["contract"] = "unknown-setup-contract"
        let decodedSetup = try JSONDecoder().decode(CPRProjectAudioSetup.self, from: data(saved))
        #expect(decodedSetup.contract == "unknown-setup-contract")
        #expect(rejects { _ = try decodedSetup.supportedSampleRate() })
    }

    @Test func unsupportedSavedValuesRemainLosslessDuringDecoding() throws {
        let original = setup(rate: Float.nan.bitPattern, factor: Double(2).bitPattern)
        let decoded = try JSONDecoder().decode(CPRProjectAudioSetup.self,
            from: JSONEncoder().encode(original))
        #expect(decoded == original)
        #expect(decoded.baseRateBits == original.baseRateBits && decoded.factorBits == original.factorBits)
        #expect(rejects { _ = try decoded.supportedSampleRate() })
    }

    // Historical identifiers come from unchanged private project packages.
    // No alternate spelling is embedded or generated in the published source.
    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func exactHistoricalIdentifiersNormalizeAndNearMissesDoNot() throws {
        let relativePaths = [
            "APP019/Historical V4 QA.rebaseproj/Compatibility/CPR/ImportReport.json",
            "APP019/Saved V5 QA.rebaseproj/Compatibility/CPR/ImportReport.json",
            "APP020/Two Track QA.rebaseproj/Project.json",
            "APP014/LoFi Native Timeline QA.rebaseproj/Project.json"
        ]
        let urls = relativePaths.map {
            PrivateResearchFixtures.root.appendingPathComponent("evidence/application/" + $0)
        }
        let originalBytes = try urls.map { try Data(contentsOf: $0) }
        let objects = try originalBytes.map {
            try #require(JSONSerialization.jsonObject(with: $0) as? [String: Any])
        }
        // The later V4 report deliberately leaves its nonzero events unplaced.
        // Use the preserved zero-origin package for the placement descriptor.
        let tracks = try #require(objects[3]["tracks"] as? [[String: Any]])
        let events = tracks.flatMap { $0["unresolvedAudioEvents"] as? [[String: Any]] ?? [] }
        let placement = try #require(events.compactMap { $0["placement"] as? [String: Any] }.first)
        let tempo = try #require(objects[2]["tempoMap"] as? [String: Any])
        let fixtures = [
            "fixedClock": try #require(tempo["nativeClock"] as? [String: Any]),
            "mapClock": try #require(objects[0]["nativeClock"] as? [String: Any]),
            "placement": placement,
            "audioSetup": try #require(objects[1]["audioSetup"] as? [String: Any])
        ]
        for (key, canonical) in [
            ("fixedClock", NativeTempoClock.fixedContract),
            ("mapClock", NativeTempoClock.mapContract),
            ("placement", CPRAudioSourcePlacement.contractName),
            ("audioSetup", CPRProjectAudioSetup.contractName)
        ] {
            let input = try #require(fixtures[key])
            let historical = try #require(input["contract"] as? String)
            #expect(historical != canonical)
            func decode(_ object: [String: Any]) throws -> [String: Any] {
                switch key {
                case "fixedClock", "mapClock":
                    return try self.object(JSONDecoder().decode(NativeTempoClock.self, from: data(object)))
                case "placement":
                    let value = try JSONDecoder().decode(CPRAudioSourcePlacement.self, from: data(object))
                    try event(with: value).validate()
                    return try self.object(value)
                default:
                    let value = try JSONDecoder().decode(CPRProjectAudioSetup.self, from: data(object))
                    _ = try value.supportedSampleRate()
                    return try self.object(value)
                }
            }
            var expected = input
            expected["contract"] = canonical
            let actual = try decode(input)
            #expect(NSDictionary(dictionary: actual) == NSDictionary(dictionary: expected))
            for nearMiss in [historical + " ", historical.uppercased(), "unknown-contract"] {
                var invalid = input
                invalid["contract"] = nearMiss
                #expect(rejects { _ = try decode(invalid) })
            }
        }
        for (url, before) in zip(urls, originalBytes) {
            #expect(try Data(contentsOf: url) == before)
        }
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func historicalPackagesPassReplayWithoutChangingTheirPreservedFiles() throws {
        for path in ["APP019/Historical V4 QA.rebaseproj", "APP019/Saved V5 QA.rebaseproj",
                     "APP020/Two Track QA.rebaseproj"] {
            let root = PrivateResearchFixtures.root.appendingPathComponent("evidence/application/" + path)
            let urls = [ProjectStore.manifestName, CPRProject.reportRelativePath, CPRProject.originalRelativePath]
                .map { root.appendingPathComponent($0) }
            let before = try urls.map { try Data(contentsOf: $0) }
            let project = try ProjectStore.load(from: root)
            let report = try #require(try CPRProject.compatibilityReport(from: root))
            let clock = try #require(project.tempoMap.nativeClock)
            #expect(clock.contract == (clock.mapRecords == nil ? NativeTempoClock.fixedContract : NativeTempoClock.mapContract))
            #expect(report.nativeClock == clock)
            for event in project.unresolvedAudioEvents {
                if let placement = event.placement {
                    #expect(placement.contract == CPRAudioSourcePlacement.contractName)
                }
            }
            if let setup = report.audioSetup {
                #expect(setup.contract == CPRProjectAudioSetup.contractName)
            }
            let encoded = try JSONEncoder().encode(project)
            #expect(try JSONDecoder().decode(Project.self, from: encoded) == project)
            for (url, bytes) in zip(urls, before) {
                #expect(try Data(contentsOf: url) == bytes)
            }
        }
    }
}
