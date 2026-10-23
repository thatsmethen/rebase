import Foundation
import Testing
@testable import RebaseCore

/// Independent retained probe records and self-authored structural envelopes.
/// Empty synthetic event bodies test inventory only; they are not playable
/// native objects or claims of Reference execution.
struct CPRTrackContributorArchiveTests {
    private let workspace = PrivateResearchFixtures.root
    private func read(_ bytes: Data) throws -> CPRTrackContributorArchive {
        try CPRTrackContributorArchive.read(container: CPRProject.readContainer(bytes))
    }
    private func rejects(_ body: () throws -> Void) -> Bool {
        do { try body(); return false } catch { return true }
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func allTenFactoryInventoriesMatchThePinnedIndependentCountedProbe() throws {
        let pins = [
            "classic-house": "bc9c6c1ffca9045a5e97a02902ec6f91632a94074add4aff7d6c909a5f8d86f8",
            "lofi-hip-hop": "ea77d245a183b6c8fb81e4db35677c9ee835e15c3fb5fac53fdd4792f56412c0",
            "neo-soul": "0c31a7dcbbc94dc9ac5edc49578d93c64d794c6cee96df6176a28b95ccd2d69b",
            "piano-page-layout": "e88a55333195b4d2d0ea7e173308e7cc042c5dc633cb42238cf46aa62e0b044f",
            "rhythm-section-page-layout": "428fa1c3171b60aebdb7848e5a26b15c2061abc7c0de2fa30f048ac6f5740293",
            "songwriter": "6a07693b834fb4ff8b972a1e2f09275f25f8eb058442dc8507a3d7a2539a58cb",
            "stereo-mastering": "4bf62b24992666564e5aa2b32b20b781f96bc893f9f5d08a45d96ff34c529c8c",
            "string-quartet-page-layout": "2088ac0c4f0f4cf1da7d9379316497c8ff8f62afe383b602e9e2974b8045bb54",
            "symphonic-orchestra": "dfe477489d322866bc4f6403d8d1e6fbb6c9ac49783e8be5b01a0c37d08a5bc7",
            "trap": "a71eea5da01e10354bc4ec2db20e990cd4e3dae8ddbf01a7fe176879ba34cae7"
        ]
        var observedUnknown = 0, observedKnownNonAudio = 0, observedChildren = 0
        for (name, pin) in pins.sorted(by: { $0.key < $1.key }) {
            let probeData = try Data(contentsOf: workspace.appendingPathComponent(
                "evidence/cpr-static/cpr-objects-001/fixtures/\(name)-v09.json"))
            #expect(cprSHA256(probeData) == pin)
            let probe = try #require(JSONSerialization.jsonObject(with: probeData) as? [String: Any])
            let source = try PrivateResearchFixtures.template(recordedPath: #require(probe["source"] as? String))
            let bytes = try Data(contentsOf: source)
            #expect(cprSHA256(bytes) == probe["sha256"] as? String)
            let before = try CPRProject.inspect(from: source)
            let inventory = try read(bytes)
            #expect(inventory.sourceSHA256 == cprSHA256(bytes))
            let roots = try #require(probe["roots"] as? [[String: Any]])
            let arrangement = try #require(roots.first { $0["name"] as? String == "Arrangement1" })
            let decoded = try #require(arrangement["decoded"] as? [String: Any])
            let root = try #require(decoded["root"] as? [String: Any])
            let rootNode = try #require(root["track_list"] as? [String: Any])
            var expectedTrackIDs: [Int] = []
            var traversalOrdinal = 0
            func compare(_ expected: [String: Any], _ actual: CPRTrackContributorNode,
                         ancestors: [Int]) throws {
                #expect(actual.object.identityOffset == expected["size_offset"] as? Int)
                #expect(actual.object.payloadSHA256 == expected["body_sha256"] as? String)
                let fields = try #require(expected["decoded"] as? [String: Any])
                let expectedName = try #require(fields["name"] as? [String: Any])
                #expect(actual.name == expectedName["text"] as? String)
                let children = try #require(fields["children"] as? [[String: Any]])
                #expect(actual.declaredChildCount == fields["count"] as? Int)
                #expect(actual.children.count == children.count)
                observedUnknown += actual.unknownCount
                observedKnownNonAudio += actual.knownNonAudioCount
                observedChildren += children.count
                #expect(actual.audioEventCount + actual.trackCount + actual.knownNonAudioCount + actual.unknownCount == children.count)
                for (ordinal, expectedChild) in children.enumerated() {
                    let child = actual.children[ordinal]
                    #expect(child.ordinal == ordinal && child.traversalOrdinal == traversalOrdinal)
                    traversalOrdinal += 1
                    #expect(child.tokenOffset == expectedChild["offset"] as? Int)
                    #expect(child.object.identityOffset == expectedChild["size_offset"] as? Int)
                    #expect(child.object.className == expectedChild["class"] as? String)
                    #expect(child.object.version == expectedChild["version"] as? Int)
                    #expect(child.object.payloadSHA256 == expectedChild["body_sha256"] as? String)
                    let payload = bytes.subdata(in: child.object.payloadOffset..<(child.object.payloadOffset + child.object.payloadByteCount))
                    #expect(cprSHA256(payload) == child.object.payloadSHA256)
                    if let childNode = expectedChild["node"] as? [String: Any] {
                        #expect(child.classification == .track)
                        let identity = child.object.identityOffset
                        expectedTrackIDs.append(identity)
                        let track = try #require(inventory.tracks.first { $0.track.identityOffset == identity })
                        #expect(track.ancestorTracks.map(\.identityOffset) == ancestors + [identity])
                        #expect(track.traversalOrdinal == child.traversalOrdinal)
                        try compare(childNode, track.node, ancestors: ancestors + [identity])
                    } else if child.object.className == "MAudioEvent" && child.object.version == 6 {
                        #expect(child.classification == .audioEvent)
                    } else if ["MTempoTrackEvent", "MSignatureTrackEvent"].contains(child.object.className) && child.object.version == 3 {
                        #expect(child.classification == .knownNonAudio)
                    } else { #expect(child.classification == .unknown) }
                }
            }
            try compare(rootNode, inventory.rootNode, ancestors: [])
            #expect(inventory.tracks.map { $0.track.identityOffset } == expectedTrackIDs)
            #expect(try read(bytes) == inventory)
            // A fresh read must not alter the V5 interpretation, source bytes,
            // or any historical profile used by compatibility replay.
            #expect(try CPRProject.inspect(from: source) == before)
            #expect(try Data(contentsOf: source) == bytes)
        }
        #expect(observedChildren > 100 && observedUnknown > 0 && observedKnownNonAudio > 0)
    }

    @Test func mixedChildrenKeepExactLocalAndTraversalOrderWithoutPromotion() throws {
        let fixture = ContributorFixture()
        let bytes = fixture.envelope(count: 3) {
            fixture.track("direct", name: "Audio", count: 4) {
                fixture.object("audio", "MAudioEvent", version: 6) {}
                fixture.object("tempo", "MTempoTrackEvent", version: 3) {}
                fixture.object("unknown", "MPatternEvent") { fixture.zeros(9) }
                fixture.object("future", "MAudioEvent", version: 7) {}
            }
            fixture.track("folder", className: "MFolderTrack", version: 0, name: "Folder", count: 1) {
                fixture.track("nested", name: "Nested", count: 1) {
                    fixture.object("nestedAudio", "MAudioEvent", version: 6) {}
                }
            }
            fixture.object("signature", "MSignatureTrackEvent", version: 3) {}
        }
        let result = try read(bytes)
        #expect(result.rootNode.declaredChildCount == 3)
        #expect(result.rootNode.children.map(\.ordinal) == [0, 1, 2])
        #expect(result.rootNode.children.map(\.traversalOrdinal) == [0, 5, 8])
        #expect(result.rootNode.trackCount == 2 && result.rootNode.knownNonAudioCount == 1)
        #expect(result.tracks.map(\.name) == ["Audio", "Folder", "Nested"])
        #expect(result.tracks.map(\.isDirectAudioTrack) == [true, false, false])
        let direct = try #require(result.tracks.first)
        #expect(direct.node.children.map(\.ordinal) == [0, 1, 2, 3])
        #expect(direct.node.children.map(\.traversalOrdinal) == [1, 2, 3, 4])
        #expect(direct.node.children.map(\.classification) == [.audioEvent, .knownNonAudio, .unknown, .unknown])
        #expect(direct.node.audioEventCount == 1 && direct.node.knownNonAudioCount == 1 && direct.node.unknownCount == 2)
        #expect(direct.node.datum == .scalar(tag: 1, bits: Double(1).bitPattern))
        // Inventory recognizes an exact class/version while deliberately not
        // claiming that an empty MAudioEvent body satisfies the audio decoder.
        #expect(rejects { _ = try CPRAudioEventArchive.read(container: CPRProject.readContainer(bytes)) })
    }

    @Test func unknownBodyCannotCreateHiddenTracksAndFutureTrackVersionStaysUnknown() throws {
        let fixture = ContributorFixture()
        let bytes = fixture.envelope(count: 2) {
            fixture.object("opaque", "FutureCollection") {
                fixture.track("hidden", name: "Not counted here", count: 0) {}
            }
            fixture.object("futureTrack", "MAudioTrackEvent", version: 2) { fixture.zeros(26) }
        }
        let result = try read(bytes)
        #expect(result.tracks.isEmpty && result.rootNode.unknownCount == 2)
        #expect(result.rootNode.children.map(\.traversalOrdinal) == [0, 1])
    }

    @Test func repeatedCountedOwnershipAndSharedNodesAreRejected() throws {
        for kind in ["event", "unknown", "track", "node"] {
            let fixture = ContributorFixture()
            let bytes = fixture.envelope(count: 2) {
                if kind == "track" {
                    fixture.track("a", name: "A", count: 0) {}
                    fixture.reference("a")
                } else if kind == "node" {
                    fixture.track("a", name: "A", count: 0) {}
                    fixture.object("b", "MAudioTrackEvent", version: 1) {
                        fixture.zeros(26); fixture.reference("a-node")
                    }
                } else {
                    fixture.object("a", kind == "event" ? "MAudioEvent" : "OpaqueChild", version: kind == "event" ? 6 : 0) {}
                    fixture.reference("a")
                }
            }
            #expect(rejects { _ = try read(bytes) })
        }
    }

    @Test func nullForwardAndCyclicOwnershipCannotYieldPartialInventory() throws {
        for edge in ["nullChild", "nullNode", "unknownReference", "rootCycle", "listCycle", "trackCycle"] {
            let fixture = ContributorFixture()
            let bytes = fixture.envelope(count: 1) {
                switch edge {
                case "nullChild": fixture.u32(0)
                case "unknownReference": fixture.u32(0x123456)
                case "rootCycle": fixture.reference("root")
                default:
                    fixture.object("track", "MAudioTrackEvent", version: 1) {
                        fixture.zeros(26)
                        if edge == "nullNode" { fixture.u32(0) }
                        else { fixture.reference(edge == "listCycle" ? "root-node" : "track") }
                    }
                }
            }
            #expect(rejects { _ = try read(bytes) })
        }
    }

    @Test func countExtentVersionAndDepthBoundsFailBeforeReturningAnyInventory() throws {
        for fault in ["tooMany", "countMismatch", "trailing", "shortHeader", "shortTrack", "nodeVersion", "compatibility"] {
            let fixture = ContributorFixture()
            let count: UInt32 = fault == "tooMany" ? 10_001 : 1
            let bytes = fixture.envelope(count: count,
                rootNodeVersion: fault == "nodeVersion" ? 1 : 0,
                compatibility: fault == "compatibility" ? 1 : 0) {
                switch fault {
                case "tooMany", "countMismatch": fixture.zeros(fault == "tooMany" ? 40_004 : 0)
                case "shortHeader": fixture.u32(.max)
                case "shortTrack": fixture.object("a", "MAudioTrackEvent", version: 1) { fixture.zeros(25) }
                default:
                    fixture.object("a", "OpaqueChild") {}
                    if fault == "trailing" { fixture.u32(0) }
                }
            }
            #expect(rejects { _ = try read(bytes) })
        }
        let fixture = ContributorFixture()
        func nested(_ level: Int) {
            fixture.track("folder\(level)", className: "MFolderTrack", version: 0,
                          name: "Folder", count: level < 33 ? 1 : 0) {
                if level < 33 { nested(level + 1) }
            }
        }
        let deep = fixture.envelope(count: 1) { nested(0) }
        #expect(rejects { _ = try read(deep) })
    }

    @Test func scalarAndInterfaceDatumsKeepBitsWithoutInventingTimingAuthority() throws {
        for tag: Int32 in [1, 10] {
            let fixture = ContributorFixture()
            let bytes = fixture.envelope(count: 1) {
                fixture.track("audio", name: "Audio", count: 0, datum: {
                    fixture.u32(UInt32(bitPattern: tag)); fixture.u64((-0.0).bitPattern)
                }) {}
            }
            #expect(try read(bytes).tracks.first?.node.datum == .scalar(tag: tag, bits: (-0.0).bitPattern))
        }
        for wrong in [false, true] {
            let fixture = ContributorFixture()
            let bytes = fixture.envelope(count: 1) {
                fixture.track("audio", name: "Audio", count: 0, datum: {
                    fixture.u32(17)
                    fixture.object("tempo", wrong ? "MSignatureTrackEvent" : "MTempoTrackEvent", version: 3) {}
                    fixture.u32(0)
                }) {}
            }
            if wrong { #expect(rejects { _ = try read(bytes) }) }
            else {
                let datum = try #require(read(bytes).tracks.first?.node.datum)
                guard case .interfaces(let tag, let tempo, let signature) = datum else {
                    Issue.record("Typed interface datum lost"); continue
                }
                #expect(tag == 17 && tempo?.className == "MTempoTrackEvent" && signature == nil)
            }
        }
        for (tag, scalar) in [(Int32(1), Double.infinity), (Int32(10), Double.nan), (Int32(2), Double(1))] {
            let fixture = ContributorFixture()
            let bytes = fixture.envelope(count: 1) {
                fixture.track("audio", name: "Audio", count: 0, datum: {
                    fixture.u32(UInt32(bitPattern: tag)); fixture.u64(scalar.bitPattern)
                }) {}
            }
            #expect(rejects { _ = try read(bytes) })
        }
    }
}

/// Self-authored counted envelopes only. Opaque payloads intentionally do not
/// satisfy the stricter event/media/track-tail playback readers.
private final class ContributorFixture {
    private var bytes = Data()
    private var identities: [String: Int] = [:]
    private func integer<T: FixedWidthInteger>(_ value: T) {
        var big = value.bigEndian
        bytes.append(withUnsafeBytes(of: &big) { Data($0) })
    }
    func u16(_ value: UInt16) { integer(value) }
    func u32(_ value: UInt32) { integer(value) }
    func u64(_ value: UInt64) { integer(value) }
    func zeros(_ count: Int) { bytes.append(Data(repeating: 0, count: count)) }
    func string(_ value: String) { u32(UInt32(value.utf8.count + 1)); bytes.append(Data(value.utf8)); bytes.append(0) }
    func reference(_ label: String) { u32(UInt32(identities[label]!)) }
    func object(_ label: String, _ name: String, version: UInt16 = 0, body: () -> Void) {
        precondition(identities[label] == nil)
        u32(.max); string(name); u16(version)
        let identity = bytes.count
        identities[label] = identity
        u32(0)
        let start = bytes.count
        body()
        var size = UInt32(bytes.count - start).bigEndian
        bytes.replaceSubrange(identity..<(identity + 4), with: withUnsafeBytes(of: &size) { Data($0) })
    }
    func track(_ label: String, className: String = "MAudioTrackEvent", version: UInt16 = 1,
               name: String, count: UInt32, datum: (() -> Void)? = nil, body: () -> Void) {
        object(label, className, version: version) {
            zeros(26)
            object(label + "-node", "MListNode") {
                string(name)
                if let datum { datum() } else { u32(1); u64(Double(1).bitPattern) }
                u32(count); body()
            }
        }
    }
    func envelope(count: UInt32, rootNodeVersion: UInt16 = 0, compatibility: UInt16 = 0,
                  body: () -> Void) -> Data {
        object("arrangement", "PArrangement", version: 4) {
            object("root", "MRoot", version: 6) {
                zeros(26)
                object("root-node", "MTrackList", version: rootNodeVersion) {
                    string(""); u32(1); u64(Double(1).bitPattern); u16(compatibility); u32(count); body()
                }
            }
        }
        func number(_ value: UInt32) -> Data { var big = value.bigEndian; return withUnsafeBytes(of: &big) { Data($0) } }
        func text(_ value: String) -> Data { number(UInt32(value.utf8.count)) + Data(value.utf8) }
        func chunk(_ tag: String, _ payload: Data) -> Data { Data(tag.utf8) + number(UInt32(payload.count)) + payload }
        let chunks = chunk("ROOT", text("Arrangement1") + text("PArrangement")) + chunk("ARCH", bytes)
        return Data("RIFF".utf8) + number(UInt32(chunks.count)) + Data("NUND".utf8) + chunks
    }
}
