import Foundation
import Testing
@testable import RebaseCore

/// Actual pinned archive bytes plus deliberate mutations, without executing
/// Reference. These test source decoding, not event placement or audible fidelity.
struct CPRAudioEventArchiveTests {
    private let root = PrivateResearchFixtures.root
    private func source(_ name: String) throws -> Data {
        let folder = "templates/"
        let bytes = try Data(contentsOf: root.appendingPathComponent(folder + name + ".cpr"))
        let pins = ["LoFi Hip Hop": "2795af70cbc6651fbd6aa4cfbcb546d606d25d5970722a6c553384f3d196e495",
                    "Classic House": "28db9a9e6aca3357e0758c4b985c4bbdfb4e1d9268502d53238f0ceb2733e892"]
        #expect(cprSHA256(bytes) == pins[name])
        return bytes
    }
    private func read(_ bytes: Data) throws -> [CPRSourceAudioEvent] {
        try CPRAudioEventArchive.read(container: CPRProject.readContainer(bytes))
    }
    private func overwrite<T: FixedWidthInteger>(_ value: T, at offset: Int, in bytes: inout Data) {
        var big = value.bigEndian
        bytes.replaceSubrange(offset..<(offset + MemoryLayout<T>.size), with: withUnsafeBytes(of: &big) { Data($0) })
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func twoPinnedEventsRetainDistinctStoredTimebasesAndExactLinkedObjects() throws {
        for (name, frames, length, eventOffset, fileOffset, segmentOffset) in [
            ("LoFi Hip Hop", UInt64(1_058_400), Double(1_058_400), 197765, 206244, 206306),
            ("Classic House", UInt64(677_376), Double(14_880), 207293, 211609, 211671)
        ] {
            let bytes = try source(name), records = try read(bytes)
            #expect(records.count == 1)
            let event = try #require(records.first)
            #expect(event.root.className == "MRoot" && event.root.version == 6)
            #expect(event.ancestorTracks.last?.identityOffset == event.trackIdentity)
            #expect(event.containingNode.className == "MListNode" && event.containingNode.version == 0)
            #expect(event.event.payloadOffset == eventOffset && event.eventWord == 0)
            #expect(event.startBits == 0 && event.lengthBits == length.bitPattern && event.offsetBits == 0)
            #expect(event.cluster.files.count == 1 && event.cluster.segments.count == 1)
            let file = try #require(event.cluster.files.first), segment = try #require(event.cluster.segments.first)
            #expect(file.object.payloadOffset == fileOffset && file.frameCount == frames)
            #expect(file.sampleRateBits == Float(44_100).bitPattern && file.channels == 2)
            #expect(file.sampleSize == 24 && file.frameSize == 6)
            #expect(segment.object.payloadOffset == segmentOffset && segment.stream == file.object)
            #expect(segment.storedOffset == 0 && segment.storedLength == frames && segment.storedStart == 0)
            #expect(event.path == file.path && file.additionalPath == nil)
            #expect(event.path.directory.hasPrefix("vstsound://"))
            #expect(event.cluster.fileListWord == 2 && event.cluster.segmentListWord == 1)
            if name == "LoFi Hip Hop" {
                #expect(event.trackName == "Vinyl Crackle")
                #expect(event.clipDatum == .scalar(tag: 10, bits: (1.0 / 44_100).bitPattern))
                #expect(event.clipChildren.count == 214)
                #expect(event.path.filename == "Lofi_Ambience_16_Vinyl_Crackle_LD.wav")
                #expect(!event.attributes.contains { $0.name == "Warpscale" })
            } else {
                #expect(event.trackName == "Bongos")
                guard case .interfaces(let tag, let tempo, let signature) = event.clipDatum else {
                    Issue.record("Classic clip must retain its distinct interface datum."); continue
                }
                #expect(tag == 0 && tempo?.identityOffset == 754 && signature?.identityOffset == 1027)
                #expect(event.attributes.contains { $0.name == "Warpscale" })
            }
            #expect(try read(bytes) == records)
        }
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func storedTailAndOpaqueProcessingStateArePreservedWithoutPlaybackPromotion() throws {
        for name in ["LoFi Hip Hop", "Classic House"] {
            let bytes = try source(name), container = try CPRProject.readContainer(bytes)
            let event = try #require(read(bytes).first)
            #expect(event.historyWord == 1 && event.priority == 1)
            #expect(event.fadeIn == nil && event.fadeOut == nil && event.snapPointBits == 0)
            #expect(event.legacyLane == 0 && event.lane == 0 && event.invertedWord == 0)
            #expect(event.volumeBits == Float(1).bitPattern)
            let preset = try #require(event.attributes.first { $0.name == "StretchPreset" })
            guard case .object(let object) = preset.value else { Issue.record("Expected a retained preset object."); continue }
            #expect(object?.className == "ElastiquePreset" && object?.payloadByteCount == 173)
            // The published profile is unchanged. Merely decoding these source
            // fields must not make the source audible or assign guessed seconds.
            let prior = try CPRRecoveryV3(container: container).decode(sourceName: name + ".cpr")
            #expect(prior.recovery.project?.tracks.flatMap(\.clips).isEmpty == true)
        }
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func nonzeroRawFieldsRemainExactInsteadOfBeingConvertedWithGuessedUnits() throws {
        var bytes = try source("LoFi Hip Hop")
        let original = try #require(read(bytes).first)
        let values = [Double(44_100).nextUp, Double(88_200).nextDown, Double(220.5)]
        for (index, value) in values.enumerated() {
            overwrite(value.bitPattern, at: original.event.payloadOffset + 2 + 8 * index, in: &bytes)
        }
        let result = try #require(read(bytes).first)
        #expect([result.startBits, result.lengthBits, result.offsetBits] == values.map(\.bitPattern))
        #expect(result.event.payloadSHA256 != original.event.payloadSHA256)
        #expect(result.cluster == original.cluster)
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func segmentReferenceMustResolveTheActualListedAudioFile() throws {
        let original = try source("LoFi Hip Hop"), event = try #require(read(original).first)
        let segment = try #require(event.cluster.segments.first)
        for token in [UInt32(0), UInt32(1), UInt32(event.path.object.identityOffset - 231)] {
            var bytes = original
            overwrite(token, at: segment.object.payloadOffset, in: &bytes)
            #expect(throws: CPRProjectError.self) { try read(bytes) }
        }
        var bytes = original
        // A segment's final field is preserved exactly, without treating it as
        // an admissible source interval until the consuming contract is bound.
        overwrite(UInt64(123), at: segment.object.payloadOffset + 20, in: &bytes)
        #expect(try read(bytes).first?.cluster.segments.first?.storedStart == 123)
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func nonfiniteAndTruncatedFieldsCannotProducePartialRecords() throws {
        let original = try source("LoFi Hip Hop"), event = try #require(read(original).first)
        let file = try #require(event.cluster.files.first), segment = try #require(event.cluster.segments.first)
        for index in 0..<3 {
            var bytes = original
            overwrite(Double.nan.bitPattern, at: event.event.payloadOffset + 2 + 8 * index, in: &bytes)
            #expect(throws: CPRProjectError.self) { try read(bytes) }
        }
        var badRate = original
        overwrite(Float.infinity.bitPattern, at: file.object.payloadOffset + 14, in: &badRate)
        #expect(throws: CPRProjectError.self) { try read(badRate) }
        var shortSegment = original
        overwrite(UInt32(27), at: segment.object.identityOffset, in: &shortSegment)
        #expect(throws: CPRProjectError.self) { try read(shortSegment) }
        var nonemptyHistory = original
        overwrite(UInt32(1), at: event.clip.payloadOffset + event.clip.payloadByteCount - 4, in: &nonemptyHistory)
        #expect(throws: CPRProjectError.self) { try read(nonemptyHistory) }
    }

    @Test func distinctEventsShareDecodedClipClusterFileAndCurveIdentities() throws {
        let bytes = sharedFixture(), records = try read(bytes)
        #expect(records.count == 4)
        #expect(Set(records.map { $0.event.identityOffset }).count == 4)
        #expect(records.map(\.startBits) == [1.0, 2.0, 3.0, 4.0].map(\.bitPattern))
        let first = try #require(records.first)
        #expect(records[1].clip == first.clip && records[1].cluster == first.cluster)
        #expect(records[2].clip != first.clip && records[2].cluster == first.cluster)
        #expect(records[3].cluster.object != first.cluster.object)
        #expect(records[3].cluster.files == first.cluster.files)
        #expect(records[3].cluster.segments == first.cluster.segments)
        #expect(records.allSatisfy { $0.volumeCurve == first.volumeCurve && $0.volumeCurveDatum == first.volumeCurveDatum })
        // Descriptor and AudioFile paths are deliberately different objects.
        // Sharing must preserve both relationships rather than substitute names.
        #expect(first.path.filename == "descriptor.wav")
        #expect(first.cluster.files.first?.path.filename == "actual-file.wav")
        #expect(first.path.object != first.cluster.files.first?.path.object)
        #expect(first.root.className == "MRoot" && first.root.version == 6)
        #expect(first.ancestorTracks.map(\.className) == ["MFolderTrack", "MAudioTrackEvent"])
        #expect(first.ancestorTracks.last?.identityOffset == first.trackIdentity)
        #expect(first.containingDatum == .scalar(tag: 1, bits: Double(2).bitPattern))
        #expect(records.allSatisfy { $0.containingNode == first.containingNode && $0.ancestorTracks == first.ancestorTracks })
        #expect(try read(bytes) == records)
    }

    @Test func cachedSharingDoesNotAllowDuplicateEventsOrForeignSegmentMembership() throws {
        #expect(throws: CPRProjectError.self) { try read(sharedFixture(reuseEvent: true)) }
        // The segment is already cached from the first cluster. Its Stream
        // still must occur in the new cluster's own file vector.
        #expect(throws: CPRProjectError.self) { try read(sharedFixture(wrongFile: true)) }
    }

    /// Entirely self-authored structural control, not a shipped/runtime result.
    /// Four distinct events share at different graph levels; the AudioFile and
    /// volume-curve bodies contain nested definitions that cannot be registered twice.
    private func sharedFixture(reuseEvent: Bool = false, wrongFile: Bool = false) -> Data {
        let f = AudioArchiveFixture()
        func path(_ label: String, filename: String) {
            f.object(label, "FNPath") {
                f.string(filename); f.u32(0)
                for _ in 0..<3 { f.string("") }
                f.u32(0); f.u16(0); f.string("/unresolved/control/")
            }
        }
        func file(_ label: String, inlinePath: Bool) {
            f.object(label, "AudioFile", version: 1) {
                f.u64(4_800); f.u16(24); f.u16(6); f.u16(2); f.u32(Float(48_000).bitPattern)
                if inlinePath { path("filePath", filename: "actual-file.wav") } else { f.reference("filePath") }
                f.u32(0)
            }
        }
        func cluster(_ label: String, sharedFile: Bool) {
            f.object(label, "AudioCluster") {
                f.u32(0); f.u16(2); f.u32(1)
                if sharedFile {
                    if wrongFile { file("otherFile", inlinePath: false) } else { f.reference("file") }
                } else { file("file", inlinePath: true) }
                f.u16(1); f.u32(1)
                if sharedFile { f.reference("segment") }
                else {
                    f.object("segment", "AClusterSegment") {
                        f.reference("file"); f.u64(7); f.u64(123); f.u64(19)
                    }
                }
            }
        }
        func clip(_ index: Int) {
            if index == 2 { f.reference("clip1"); return }
            f.object("clip\(index)", "PAudioClip", version: 4) {
                f.string("Shared source"); f.u32(10); f.u64((1.0 / 48_000).bitPattern); f.u32(0)
                if index == 1 { path("descriptorPath", filename: "descriptor.wav") }
                else { f.reference("descriptorPath") }
                f.string(""); f.u16(0); f.u32(0); f.u64(0); f.u32(0)
                if index == 1 { cluster("cluster1", sharedFile: false) }
                else if index == 3 { f.reference("cluster1") }
                else { cluster("cluster2", sharedFile: true) }
                f.u16(1); f.u32(0)
            }
        }
        func event(_ index: Int) {
            if index == 2 && reuseEvent { f.reference("event1"); return }
            f.object("event\(index)", "MAudioEvent", version: 6) {
                f.u16(0); f.u64(Double(index).bitPattern); f.u64(Double(123).bitPattern); f.u64(0)
                clip(index)
                f.u32(0); f.u32(1); f.u32(0); f.u32(0); f.u64(0); f.string("")
                f.u32(0); f.u32(Float(1).bitPattern); f.u32(0); f.u16(0)
                if index == 1 {
                    f.object("curve", "VolumeCurveDataNode") {
                        f.string(""); f.u32(0)
                        f.object("curveTempo", "MTempoTrackEvent", version: 3) {}
                        f.u32(0); f.u32(0)
                    }
                } else { f.reference("curve") }
            }
        }
        f.object("arrangement", "PArrangement", version: 4) {
            f.object("root", "MRoot", version: 6) {
                f.zeros(26)
                f.object("rootList", "MTrackList") {
                    f.string(""); f.u32(1); f.u64(0); f.u16(0); f.u32(1)
                    f.object("folder", "MFolderTrack") {
                        f.zeros(26)
                        f.object("folderList", "MListNode") {
                            f.string("Folder"); f.u32(1); f.u64(0); f.u32(1)
                            f.object("audioTrack", "MAudioTrackEvent", version: 1) {
                                f.zeros(26)
                                f.object("audioList", "MListNode") {
                                    f.string("Audio"); f.u32(1); f.u64(Double(2).bitPattern); f.u32(4)
                                    for index in 1...4 { event(index) }
                                }
                            }
                        }
                    }
                }
            }
        }
        return f.container()
    }
}

private final class AudioArchiveFixture {
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
    func container() -> Data {
        func u32(_ value: UInt32) -> Data { var big = value.bigEndian; return withUnsafeBytes(of: &big) { Data($0) } }
        func text(_ value: String) -> Data { u32(UInt32(value.utf8.count)) + Data(value.utf8) }
        func chunk(_ name: String, _ payload: Data) -> Data { Data(name.utf8) + u32(UInt32(payload.count)) + payload }
        let sections = chunk("ROOT", text("Arrangement1") + text("PArrangement")) + chunk("ARCH", bytes)
        return Data("RIFF".utf8) + u32(UInt32(sections.count)) + Data("NUND".utf8) + sections
    }
}
