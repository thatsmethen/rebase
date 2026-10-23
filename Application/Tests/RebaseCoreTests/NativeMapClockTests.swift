import Testing
import Foundation
import CryptoKit
@testable import RebaseCore

private let mapWorkspace = PrivateResearchFixtures.root

final class NativeMapClockTests {
    private func records() -> [NativeTempoMapRecord] {
        [NativeTempoMapRecord(periodBits: 0x3f400000, secondsBits: 0, tickBits: 0, kind: 0, sourceRecordOffset: 100),
         NativeTempoMapRecord(periodBits: 0x3f000000, secondsBits: 600.0.bitPattern, tickBits: 384000.0.bitPattern, kind: 0, sourceRecordOffset: 122)]
    }
    private func clock(_ records: [NativeTempoMapRecord]? = nil) throws -> NativeTempoClock {
        try NativeTempoClock(mapRecords: records ?? self.records(), sourceSHA256: String(repeating: "b", count: 64), sourceObjectOffset: 92)
    }
    private func map() throws -> TempoMap {
        let clock = try clock()
        return TempoMap(events: records().map { TempoEvent(beat: $0.beat, bpm: $0.displayBPM) }, nativeClock: clock)
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func swiftClockMatchesIndependentMapOracle() throws {
        let bytes = try Data(contentsOf: mapWorkspace.appendingPathComponent("evidence/cpr-static/cpr-map-clock-001/oracle-iterator/map-clock-goldens.json"))
        #expect(cprSHA256(bytes) == "98b3922f598f57e51e961252a61a6503c67cead5b8d17605024e2bedc202795c")
        let document = try #require(JSONSerialization.jsonObject(with: bytes) as? [String: Any])
        let maps = try #require(document["maps"] as? [String: [[String: Any]]])
        let vectors = try #require(document["vectors"] as? [[String: Any]])
        func bits(_ value: Any?) throws -> UInt64 {
            let text = try #require(value as? String)
            return try #require(UInt64(text.dropFirst(2), radix: 16))
        }
        var checked = 0
        for vector in vectors {
            let name = try #require(vector["map"] as? String)
            let points = try #require(maps[name])
            let records = try points.enumerated().map { index, point in
                NativeTempoMapRecord(periodBits: UInt32(try bits(point["period_f32_bits"])),
                    secondsBits: try bits(point["seconds_f64_bits"]), tickBits: try bits(point["ticks_f64_bits"]),
                    kind: UInt16(try #require(point["kind"] as? Int)), sourceRecordOffset: 100 + index * 22)
            }
            if name == "synthetic-unequal-anchor" {
                // This control distinguishes saved anchors from recomputation.
                // Public descriptors reject it; C-only probes retain it.
                expectThrows(try clock(records)); continue
            }
            let c = try clock(records)
            let input = Double(bitPattern: try bits(vector["input_f64_bits"]))
            let expected = try bits(vector["result_f64_bits"])
            if vector["direction"] as? String == "seconds_to_ticks" {
                #expect(try c.nativeTick(atSeconds: input).bitPattern == expected)
            } else {
                #expect(try c.seconds(atNativeTick: input).bitPattern == expected)
            }
            checked += 1
        }
        #expect(checked > 70)
    }

    @Test func exactDescriptorValidationAndSerialization() throws {
        let c = try clock()
        #expect(try JSONDecoder().decode(NativeTempoClock.self, from: JSONEncoder().encode(c)) == c)
        #expect(c.contract == NativeTempoClock.mapContract && c.interpretationProfile == "cpr-static-subset-v3")
        expectThrows(try c.periodBits())
        let source = try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(c)) as? [String: Any])
        for (key, value): (String, Any) in [("contract", NativeTempoClock.fixedContract), ("fixedBPMBits", 1),
             ("interpretationProfile", "cpr-static-subset-v2"), ("mapRecords", []), ("sourceObjectOffset", 101)] {
            var changed = source; changed[key] = value
            expectThrows(try JSONDecoder().decode(NativeTempoClock.self, from: JSONSerialization.data(withJSONObject: changed)))
        }
        var changed = records()
        changed[1] = NativeTempoMapRecord(periodBits: 0x3f000000, secondsBits: Double(600).nextUp.bitPattern,
            tickBits: 384000.0.bitPattern, kind: 0, sourceRecordOffset: 122)
        expectThrows(try clock(changed))
        changed = records()
        changed[1] = NativeTempoMapRecord(periodBits: 0x3f000000, secondsBits: 600.0.bitPattern,
            tickBits: 384000.0.bitPattern, kind: 1, sourceRecordOffset: 122)
        expectThrows(try clock(changed))
        for input in [Double.nan, .infinity, -1, Double.leastNonzeroMagnitude] {
            expectThrows(try c.nativeTick(atSeconds: input)); expectThrows(try c.seconds(atNativeTick: input))
        }
    }

    @Test func mapProjectionAndExplicitConversionRemainAtomic() throws {
        let native = try map()
        try native.validate()
        #expect(try native.seconds(atBeat: 800) == 600)
        #expect(try native.seconds(atBeat: 804) == 602)
        #expect(try native.beat(atSeconds: 602) == 804)
        var changed = native; changed.events[1].bpm = 119
        expectThrows(try changed.validate())
        changed = native; changed.events.removeLast()
        expectThrows(try changed.validate())
        changed = native; changed.events[1].beat = 801
        expectThrows(try changed.validate())
        var project = Project(tempoMap: native)
        let original = project
        expectThrows(try project.replaceTempoMap(TempoMap(events: native.events)))
        #expect(project == original)
        try project.convertToApplicationTiming()
        #expect(project.tempoMap.nativeClock == nil && project.tempoMap.events == native.events)
    }

    @Test func fixedDescriptorEncodingRemainsUnchanged() throws {
        let c = try NativeTempoClock(fixedBPMBits: 0x42fd0000, sourceSHA256: String(repeating: "a", count: 64), sourceObjectOffset: 758)
        let encoded = try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(c)) as? [String: Any])
        #expect(Set(encoded.keys) == Set(["contract", "fixedBPMBits", "sourceSHA256", "sourceObjectOffset", "interpretationProfile"]))
        #expect(c.mapRecords == nil && c.interpretationProfile == "cpr-static-subset-v2")
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func publishedV2PackagesReplayWithoutRewriting() throws {
        let root = mapWorkspace.appendingPathComponent("evidence/application/APP004")
        for name in ["Classic House Native.rebaseproj", "Concordant Signature Recovery.rebaseproj", "Converted Signature Copy.rebaseproj"] {
            let package = root.appendingPathComponent(name)
            let paths = ["Project.json", CPRProject.reportRelativePath, CPRProject.originalRelativePath].map { package.appendingPathComponent($0) }
            let original = try paths.map { try Data(contentsOf: $0) }
            let report = try JSONDecoder().decode(CPRInspection.self, from: original[1])
            #expect(report.interpretationProfile == "cpr-static-subset-v2")
            #expect(try CPRProject.compatibilityReport(from: package) == report)
            _ = try ProjectStore.load(from: package)
            #expect(try paths.map { try Data(contentsOf: $0) } == original)
        }
    }
}
