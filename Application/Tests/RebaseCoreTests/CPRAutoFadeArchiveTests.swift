import Foundation
import Testing
@testable import RebaseCore

struct CPRAutoFadeArchiveTests {
    private let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    private func read(_ data: Data) throws -> CPRSourceAutoFadeArchive {
        try CPRAutoFadeArchive.read(container: CPRProject.readContainer(data))
    }
    private func source(_ name: String) throws -> Data {
        let folder = "research/targets/full-reference/expanded/Reference 15.app.pkg/Payload/Reference 15.app/Contents/Project Templates/Reference Pro/"
        let bytes = try Data(contentsOf: root.appendingPathComponent(folder + name + ".cpr"))
        let pins = ["LoFi Hip Hop": "2795af70cbc6651fbd6aa4cfbcb546d606d25d5970722a6c553384f3d196e495",
                    "Classic House": "28db9a9e6aca3357e0758c4b985c4bbdfb4e1d9268502d53238f0ceb2733e892"]
        #expect(cprSHA256(bytes) == pins[name])
        return bytes
    }
    private func overwrite<T: FixedWidthInteger>(_ value: T, at offset: Int, in bytes: inout Data) {
        var big = value.bigEndian
        bytes.replaceSubrange(offset..<(offset + MemoryLayout<T>.size), with: withUnsafeBytes(of: &big) { Data($0) })
    }
    private func objectMatches(_ actual: CPRObjectRecord, _ expected: [String: Any]) throws {
        #expect(actual.className == expected["class"] as? String)
        #expect(actual.version == expected["version"] as? Int)
        #expect(actual.identityOffset == expected["size_offset"] as? Int)
        #expect(actual.payloadOffset == expected["body_offset"] as? Int)
        #expect(actual.payloadByteCount == expected["body_bytes"] as? Int)
        #expect(actual.payloadSHA256 == expected["body_sha256"] as? String)
    }

    @Test func pinnedFactoriesMatchIndependentForwardProbeAndInheritExactZeroFlags() throws {
        let url = root.appendingPathComponent("research/evidence/cpr-static/cpr-audio-events-001/autofade-source/source-forward-probe.json")
        let probe = try Data(contentsOf: url)
        #expect(cprSHA256(probe) == "946f5ce59e3f3e977b9da1a4a5a8b1a040aa6dde90b9b0698f92eb3d91acb456")
        let document = try #require(JSONSerialization.jsonObject(with: probe) as? [String: Any])
        let fixtures = try #require(document["fixtures"] as? [[String: Any]])
        #expect(fixtures.count == 2)
        for fixture in fixtures {
            let name = try #require(fixture["fixture"] as? String), bytes = try source(name), result = try read(bytes)
            #expect(result.root.identityOffset == fixture["root_identity"] as? Int)
            #expect(result.root.payloadOffset + result.root.payloadByteCount == fixture["root_parsed_end"] as? Int)
            #expect(result.objectListWord == 0 && result.rootObjects.isEmpty && result.loudness == nil)
            let expectedProject = try #require(fixture["project"] as? [String: Any])
            let expectedSetting = try #require(expectedProject["setting"] as? [String: Any])
            let setting = try #require(result.projectSetting)
            try objectMatches(setting.object, #require(expectedSetting["object"] as? [String: Any]))
            #expect(setting.flags == 0 && setting.durationBits == 0x3f847ae147ae147b)
            let expectedCurves = try #require(expectedSetting["interpolators"] as? [[String: Any]])
            #expect(setting.interpolators.count == expectedCurves.count && expectedCurves.count == 4)
            for (actual, expected) in zip(setting.interpolators, expectedCurves) {
                try objectMatches(#require(actual), expected)
            }
            let expectedTracks = try #require(fixture["tracks"] as? [[String: Any]])
            #expect(result.tracks.count == 1 && expectedTracks.count == 1)
            for expected in expectedTracks {
                let identity = try #require(expected["track_identity"] as? Int)
                let track = try #require(result.tracks[identity])
                #expect(track.localSetting == nil && track.localSettingTokenOffset + 4 == track.track.payloadOffset + track.track.payloadByteCount)
                #expect(track.trackWord == 46 && track.numberBits == 0)
                #expect(track.automation.className == "MAutomationNode" && track.automation.version == 1)
                #expect(track.automation.payloadByteCount == 156)
                try objectMatches(track.resource, #require(expected["resource"] as? [String: Any]))
                let attributes = try #require(expected["attribute_tail"] as? [String: Any])
                let fields = try #require(attributes["fields"] as? [[String: Any]])
                #expect(track.attributes.count == fields.count && fields.count == 6)
                for (actual, expected) in zip(track.attributes, fields) {
                    #expect(actual.offset == expected["offset"] as? Int)
                    #expect(actual.key == UInt32(try #require(expected["key"] as? String), radix: 16))
                    #expect(Int(actual.type) == expected["type"] as? Int)
                    switch actual.value {
                    case .integer(let value): #expect(value == (expected["value"] as? NSNumber)?.int64Value)
                    case .object(let value): try objectMatches(#require(value), #require(expected["value"] as? [String: Any]))
                    }
                }
                #expect(!track.attributes.contains { $0.key == 0x46706d49 })
                #expect(result.effectiveSetting(forTrackIdentity: identity) == setting)
            }
            #expect(result.effectiveSetting(forTrackIdentity: -1) == nil)
            for record in result.records {
                let payload = bytes.subdata(in: record.payloadOffset..<(record.payloadOffset + record.payloadByteCount))
                #expect(cprSHA256(payload) == record.payloadSHA256)
            }
        }
    }

    @Test func nonnullLocalZeroOverridesEnabledProjectAndMissingProjectStaysUnknown() throws {
        for (projectFlags, localFlags, expected): (UInt16?, UInt16?, UInt16?) in [
            (7, 0, 0), (0, 2, 2), (5, nil, 5), (nil, nil, nil), (nil, 0, 0)
        ] {
            let result = try read(fixture(project: projectFlags, local: localFlags))
            let track = try #require(result.tracks.values.first)
            #expect(result.projectSetting?.flags == projectFlags && track.localSetting?.flags == localFlags)
            #expect(result.effectiveSetting(forTrackIdentity: track.track.identityOffset)?.flags == expected)
        }
    }

    @Test func sharedPositiveSettingReferencePreservesIdentityAndOpaqueCurves() throws {
        let result = try read(fixture(project: 0, local: 0, sharedSetting: true, curveBytes: Data([0xff, 0, 0x12, 0x34])))
        let track = try #require(result.tracks.values.first), local = try #require(track.localSetting)
        #expect(result.projectSetting == local)
        #expect(local.interpolators.count == 4 && local.interpolators[0]?.payloadByteCount == 4)
        #expect(local.interpolators.dropFirst().allSatisfy { $0 == nil })
        #expect(result.records.filter { $0.className == "MAutoFadeSetting" }.count == 1)
        // Finite values retain their bits; no smoothing/clamping is inferred.
        for bits: UInt64 in [0, 0x8000000000000000, Double(0.01).nextUp.bitPattern] {
            let raw = try read(fixture(project: 0, durationBits: bits))
            #expect(raw.projectSetting?.durationBits == bits)
        }
    }

    @Test func nonfiniteDurationsRejectAsExplicitApplicationPolicy() throws {
        for bits: UInt64 in [0x7ff8000000000012, 0x7ff0000000000001,
                            0x7ff0000000000000, 0xfff0000000000000] {
            for flags: UInt16 in [0, 1] {
                #expect(throws: CPRProjectError.self) { try read(fixture(project: flags, durationBits: bits)) }
                #expect(throws: CPRProjectError.self) { try read(fixture(project: nil, local: flags, durationBits: bits)) }
            }
        }
    }

    @Test func keyedRootRequiresCountedEventTypeAndLoudnessRemainsNullOnly() throws {
        for target in ["path", "pool", "automation", "resource"] {
            #expect(throws: CPRProjectError.self) { try read(fixture(keyedTarget: target)) }
            #expect(throws: CPRProjectError.self) { try read(fixture(loudnessTarget: target)) }
        }
        // A correct-looking event class introduced only in the ancillary root
        // list cannot manufacture membership in the counted arrangement.
        #expect(throws: CPRProjectError.self) { try read(fixture(keyedTarget: "outsideTrack")) }
        #expect(throws: CPRProjectError.self) { try read(fixture(loudnessTarget: "audio")) }
        let control = try read(fixture())
        #expect(control.keyedEvents.count == 1 && control.loudness == nil)
    }

    @Test func baseVersionsAreResolvedFromHeadersNotPayloadStrings() throws {
        for (event, track): (UInt16, UInt16) in [(0, 2), (1, 1), (2, 2), (1, 3)] {
            #expect(throws: CPRProjectError.self) { try read(fixture(eventVersion: event, trackVersion: track)) }
        }
        #expect(throws: CPRProjectError.self) { try read(fixture(curveBytes: Data("MEvent\0MTrackEvent\0".utf8), omitBases: true)) }
        #expect(throws: CPRProjectError.self) { try read(fixture(settingVersion: 1)) }
        #expect(throws: CPRProjectError.self) { try read(fixture(curveVersion: 1)) }
    }

    @Test func typedNumericAttributesRemainOpaqueAndUnknownRepresentationsReject() throws {
        for type: UInt16 in [1, 0x801, 2, 0x12, 0x22, 0x92, 8] {
            let result = try read(fixture(attributeType: type))
            let attribute = try #require(result.tracks.values.first?.attributes.first)
            #expect(attribute.key == 0x46706d49 && attribute.type == type)
            if type == 1 || type == 0x801 { #expect(attribute.value == .integer(-123)) }
        }
        for type: UInt16 in [0, 3, 4, 0x42, 0xffff] {
            #expect(throws: CPRProjectError.self) { try read(fixture(attributeType: type)) }
        }
        #expect(throws: CPRProjectError.self) { try read(fixture(attributeType: 1, duplicateAttribute: true)) }
    }

    @Test func ExactTailsAndRootClockIdentityRejectFalseForwardInterpretations() throws {
        for extra in ["track", "root", "setting"] {
            #expect(throws: CPRProjectError.self) { try read(fixture(extraTail: extra)) }
        }
        #expect(throws: CPRProjectError.self) { try read(fixture(wrongRootTempo: true)) }
        #expect(throws: CPRProjectError.self) { try read(fixture(negativeKeyCount: true)) }
        #expect(throws: CPRProjectError.self) { try read(fixture(duplicateEventKey: true)) }
        let original = try source("LoFi Hip Hop"), decoded = try read(original)
        let track = try #require(decoded.tracks.values.first), setting = try #require(decoded.projectSetting)
        var forward = original
        // A positive object reference cannot point forward to the project
        // setting before its definition is entered.
        overwrite(UInt32(setting.object.identityOffset - 231), at: track.localSettingTokenOffset, in: &forward)
        #expect(throws: CPRProjectError.self) { try read(forward) }
        var short = original
        overwrite(UInt32(setting.object.payloadByteCount - 1), at: setting.object.identityOffset, in: &short)
        #expect(throws: CPRProjectError.self) { try read(short) }
        var unknown = original
        overwrite(UInt16(4), at: track.attributes[0].offset + 4, in: &unknown)
        #expect(throws: CPRProjectError.self) { try read(unknown) }
    }

    private func fixture(project: UInt16? = 0, local: UInt16? = nil, sharedSetting: Bool = false,
                         durationBits: UInt64 = 0x3f847ae147ae147b, curveBytes: Data = Data([0, 1]),
                         eventVersion: UInt16 = 1, trackVersion: UInt16 = 2, omitBases: Bool = false,
                         settingVersion: UInt16 = 0, curveVersion: UInt16 = 0,
                         attributeType: UInt16? = nil, duplicateAttribute: Bool = false,
                         extraTail: String = "", wrongRootTempo: Bool = false,
                         negativeKeyCount: Bool = false, duplicateEventKey: Bool = false,
                         keyedTarget: String = "audio", loudnessTarget: String? = nil) -> Data {
        let f = AutoFadeFixture()
        func setting(_ label: String, _ flags: UInt16?) {
            guard let flags else { f.u32(0); return }
            f.object(label, "MAutoFadeSetting", version: settingVersion) {
                f.u16(flags); f.u64(durationBits)
                f.object(label + "curve", "MLinearInterpolator", version: curveVersion) { f.raw(curveBytes) }
                f.u32(0); f.u32(0); f.u32(0)
                if extraTail == "setting" { f.u16(0) }
            }
        }
        f.object("arrangement", "PArrangement", version: 4) {
            if !omitBases { f.base("MEvent", eventVersion); f.base("MTrackEvent", trackVersion) }
            f.object("root", "MRoot", version: 6) {
                f.zeros(26)
                f.object("rootList", "MTrackList") {
                    f.string(""); f.u32(0)
                    f.object("tempo", "MTempoTrackEvent", version: 3) {}
                    f.object("signature", "MSignatureTrackEvent", version: 3) {}
                    f.u16(0); f.u32(1)
                    f.object("audio", "MAudioTrackEvent", version: 1) {
                        f.zeros(26)
                        f.object("audioList", "MListNode") { f.string("Audio"); f.u32(1); f.u64(Double(1).bitPattern); f.u32(0) }
                        f.u32(attributeType == nil ? 0 : duplicateAttribute ? 2 : 1)
                        if let type = attributeType {
                            for index in 0..<(duplicateAttribute ? 2 : 1) {
                                f.u32(0x46706d49); f.u16(type)
                                switch type {
                                case 1, 0x801: f.u64(UInt64(bitPattern: -123))
                                case 8: f.object("text\(index)", "CmString") { f.string("opaque") }
                                default: f.u32(0)
                                }
                            }
                        }
                        f.object("resource", "MAudioTrack") {}
                        f.u32(46); f.u64(0)
                        f.object("automation", "MAutomationNode", version: 1) { f.raw(Data([0x11, 0x22])) }
                        setting("local", local)
                        if extraTail == "track" { f.u16(0) }
                    }
                }
                f.u32(0); f.u16(0); f.u32(keyedTarget == "outsideTrack" ? 1 : 0)
                if keyedTarget == "outsideTrack" { f.object("outsideTrack", "MAudioTrackEvent", version: 1) {} }
                f.object("path", "FNPath") {}
                f.object("pool", "PPool", version: 5) {}
                f.u32(0)
                f.reference(wrongRootTempo ? "signature" : "tempo"); f.reference("signature")
                if sharedSetting { f.reference("local") } else { setting("project", project) }
                f.u16(negativeKeyCount ? 0xffff : duplicateEventKey ? 2 : 1)
                f.u16(1); f.reference(keyedTarget)
                if duplicateEventKey { f.u16(1); f.reference("audio") }
                if let loudnessTarget { f.reference(loudnessTarget) } else { f.u32(0) }
                if extraTail == "root" { f.u16(0) }
            }
        }
        return f.container()
    }
}

private final class AutoFadeFixture {
    private var data = Data()
    private var identities: [String: Int] = [:]
    private func integer<T: FixedWidthInteger>(_ value: T) {
        var value = value.bigEndian; data.append(withUnsafeBytes(of: &value) { Data($0) })
    }
    func u16(_ value: UInt16) { integer(value) }
    func u32(_ value: UInt32) { integer(value) }
    func u64(_ value: UInt64) { integer(value) }
    func raw(_ bytes: Data) { data.append(bytes) }
    func zeros(_ count: Int) { raw(Data(repeating: 0, count: count)) }
    func string(_ text: String) { u32(UInt32(text.utf8.count + 1)); raw(Data(text.utf8)); raw(Data([0])) }
    func base(_ name: String, _ version: UInt16) { u32(0xffff_fffe); string(name); u16(version) }
    func reference(_ label: String) { u32(UInt32(identities[label]!)) }
    func object(_ label: String, _ name: String, version: UInt16 = 0, body: () -> Void) {
        u32(.max); string(name); u16(version)
        let identity = data.count; identities[label] = identity; u32(0)
        let start = data.count; body()
        var count = UInt32(data.count - start).bigEndian
        data.replaceSubrange(identity..<(identity + 4), with: withUnsafeBytes(of: &count) { Data($0) })
    }
    func container() -> Data {
        func u32(_ n: UInt32) -> Data { var n = n.bigEndian; return withUnsafeBytes(of: &n) { Data($0) } }
        func text(_ value: String) -> Data { u32(UInt32(value.utf8.count)) + Data(value.utf8) }
        func chunk(_ name: String, _ body: Data) -> Data { Data(name.utf8) + u32(UInt32(body.count)) + body }
        let sections = chunk("ROOT", text("Arrangement1") + text("PArrangement")) + chunk("ARCH", data)
        return Data("RIFF".utf8) + u32(UInt32(sections.count)) + Data("NUND".utf8) + sections
    }
}
