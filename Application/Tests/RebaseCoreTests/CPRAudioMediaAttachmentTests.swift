import Foundation
import Testing
@testable import RebaseCore

/// Self-authored PCM assets are associated explicitly with preserved source
/// references. Neither matching metadata nor these tests prove original media
/// identity, target execution, or restored native playback processing.
struct CPRAudioMediaAttachmentTests {
    private let workspace = PrivateResearchFixtures.root
    private func temporary() throws -> URL {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("CPRAttachment-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        return root
    }
    private func imported(at root: URL) throws -> (URL, CPRImportResult) {
        let source = workspace.appendingPathComponent("templates/LoFi Hip Hop.cpr")
        let expected = "2795af70cbc6651fbd6aa4cfbcb546d606d25d5970722a6c553384f3d196e495"
        #expect(cprSHA256(try Data(contentsOf: source)) == expected)
        let package = root.appendingPathComponent("Source.rebaseproj")
        return (package, try CPRProject.importProject(from: source, to: package, allowPartial: true, expectedSHA256: expected))
    }
    private func pcm(at url: URL, frames: Int = 1_058_400, rate: UInt32 = 44_100,
                     channels: UInt16 = 2, bits: UInt16 = 24, marker: UInt8 = 1) throws -> Data {
        func le<T: FixedWidthInteger>(_ value: T) -> Data {
            var value = value.littleEndian
            return withUnsafeBytes(of: &value) { Data($0) }
        }
        let frameSize = channels * (bits / 8), payload = frames * Int(frameSize)
        var bytes = Data("RIFF".utf8) + le(UInt32(36 + payload)) + Data("WAVEfmt ".utf8)
        bytes += le(UInt32(16)) + le(UInt16(1)) + le(channels) + le(rate)
        bytes += le(rate * UInt32(frameSize)) + le(frameSize) + le(bits)
        bytes += Data("data".utf8) + le(UInt32(payload))
        bytes += Data(repeating: 0, count: payload)
        if payload > 0 { bytes[44] = marker; bytes[bytes.count - Int(frameSize)] = marker }
        try bytes.write(to: url)
        return bytes
    }
    private func mediaFiles(_ package: URL) throws -> Set<String> {
        Set(try FileManager.default.contentsOfDirectory(atPath: package.appendingPathComponent("Media").path))
    }
    private func retainedBytes(_ package: URL) throws -> [Data] {
        try [CPRProject.originalRelativePath, CPRProject.reportRelativePath].map {
            try Data(contentsOf: package.appendingPathComponent($0))
        }
    }
    private func attach(_ project: Project, package: URL, source: URL) throws -> Project {
        let id = try #require(project.unresolvedAudioEvents.first?.id)
        return try ProjectStore.attachCPRAudioMedia(from: source, to: id, in: project, at: package)
    }
    private func mutateAttachment(_ project: Project, _ change: (inout [String: Any]) throws -> Void) throws -> Project {
        var json = try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(project)) as? [String: Any])
        var attachments = try #require(json["cprMediaAttachments"] as? [[String: Any]])
        try change(&attachments[0]); json["cprMediaAttachments"] = attachments
        return try JSONDecoder().decode(Project.self, from: JSONSerialization.data(withJSONObject: json))
    }
    private func unresolvedError(_ body: () throws -> Void) {
        do { try body(); Issue.record("Unresolved native processing unexpectedly passed the playback/export barrier.") }
        catch RebaseCoreError.invalidProject(let message) { #expect(message.contains("unresolved Reference audio events")) }
        catch { Issue.record("Wrong failure instead of the unresolved-audio barrier: \(error)") }
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func explicitMatchingAssociationCopiesExactBytesAndPreservesFrozenBaseline() throws {
        let root = try temporary(); defer { try? FileManager.default.removeItem(at: root) }
        let (package, baseline) = try imported(at: root), preserved = try retainedBytes(package)
        let source = root.appendingPathComponent("Self Authored LoFi Format.wav")
        let bytes = try pcm(at: source)
        let project = try attach(baseline.project, package: package, source: source)
        let attachment = try #require(project.cprMediaAttachments.first), event = try #require(project.unresolvedAudioEvents.first)
        #expect(project.cprMediaAttachments.count == 1 && attachment.association == "user-selected")
        #expect(attachment.sourceSHA256 == baseline.report.sourceSHA256)
        #expect(attachment.sourceFileIdentity == event.files.first?.object.identityOffset)
        #expect(attachment.selectedFilename == source.lastPathComponent)
        #expect(attachment.frameCount == 1_058_400 && attachment.sampleRate == 44_100)
        #expect(attachment.channels == 2 && attachment.bitsPerSample == 24 && attachment.bytesPerFrame == 6)
        #expect(attachment.mediaSHA256 == cprSHA256(bytes))
        let copied = try ProjectStore.resolveMediaURL(attachment.mediaPath, projectRoot: package)
        #expect(copied != source)
        #expect(try Data(contentsOf: copied) == bytes)
        #expect(try mediaFiles(package) == [copied.lastPathComponent])
        #expect(project.unresolvedAudioEvents == baseline.project.unresolvedAudioEvents)
        #expect(project.tracks.flatMap(\.clips).isEmpty && project.attachedMedia(for: event) == attachment)
        #expect(baseline.project.cprMediaAttachments.isEmpty)
        try ProjectStore.save(project, to: package)
        #expect(try ProjectStore.load(from: package) == project)
        let copy = root.appendingPathComponent("Copy.rebaseproj")
        try FileManager.default.copyItem(at: package, to: copy)
        #expect(try ProjectStore.load(from: copy) == project)
        #expect(try retainedBytes(package) == preserved && retainedBytes(copy) == preserved)
        #expect(try CPRProject.compatibilityReport(from: package) == baseline.report)
        #expect(baseline.report.recoveredProject?.cprMediaAttachments.isEmpty == true)
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func changedOrMissingCopiedMediaFailsLoadAndSaveBeforeManifestWrites() throws {
        let root = try temporary(); defer { try? FileManager.default.removeItem(at: root) }
        let (package, baseline) = try imported(at: root), source = root.appendingPathComponent("Match.wav")
        let bytes = try pcm(at: source), project = try attach(baseline.project, package: package, source: source)
        try ProjectStore.save(project, to: package)
        let manifest = package.appendingPathComponent("Project.json"), before = try Data(contentsOf: manifest)
        let attachment = try #require(project.cprMediaAttachments.first)
        let copied = try ProjectStore.resolveMediaURL(attachment.mediaPath, projectRoot: package)
        var altered = bytes; altered[44] ^= 1; try altered.write(to: copied)
        #expect(throws: RebaseCoreError.self) { try ProjectStore.load(from: package) }
        #expect(throws: RebaseCoreError.self) { try ProjectStore.save(project, to: package) }
        #expect(try Data(contentsOf: manifest) == before)
        try bytes.write(to: copied)
        #expect(try ProjectStore.load(from: package) == project)
        try FileManager.default.removeItem(at: copied)
        #expect(throws: RebaseCoreError.self) { try ProjectStore.load(from: package) }
        #expect(throws: RebaseCoreError.self) { try ProjectStore.save(project, to: package) }
        #expect(try Data(contentsOf: manifest) == before)
        #expect(try Data(contentsOf: source) == bytes)
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func incompatibleFormatAndFrameCountsLeaveNoAssociationOrCopiedAsset() throws {
        let root = try temporary(); defer { try? FileManager.default.removeItem(at: root) }
        let (package, baseline) = try imported(at: root), preserved = try retainedBytes(package)
        let manifest = package.appendingPathComponent("Project.json"), before = try Data(contentsOf: manifest)
        for (index, frames, rate, channels, bits) in [
            (0, 1_058_399, UInt32(44_100), UInt16(2), UInt16(24)),
            (1, 1_058_401, UInt32(44_100), UInt16(2), UInt16(24)),
            (2, 1_058_400, UInt32(48_000), UInt16(2), UInt16(24)),
            (3, 1_058_400, UInt32(44_100), UInt16(1), UInt16(24)),
            (4, 1_058_400, UInt32(44_100), UInt16(2), UInt16(16))
        ] {
            let source = root.appendingPathComponent("Wrong-\(index).wav")
            _ = try pcm(at: source, frames: frames, rate: rate, channels: channels, bits: bits)
            #expect(throws: RebaseCoreError.self) { try attach(baseline.project, package: package, source: source) }
            #expect(try mediaFiles(package).isEmpty)
            #expect(try Data(contentsOf: manifest) == before)
        }
        let directory = root.appendingPathComponent("Directory.wav")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false)
        #expect(throws: RebaseCoreError.self) { try attach(baseline.project, package: package, source: directory) }
        #expect(try mediaFiles(package).isEmpty && retainedBytes(package) == preserved)
        #expect(baseline.project.cprMediaAttachments.isEmpty)
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func replacementKeepsOneAssociationAndExplicitRemovalPrunesIt() throws {
        let root = try temporary(); defer { try? FileManager.default.removeItem(at: root) }
        let (package, baseline) = try imported(at: root), preserved = try retainedBytes(package)
        let first = root.appendingPathComponent("First.wav"), second = root.appendingPathComponent("Second.wav")
        _ = try pcm(at: first, marker: 1); let replacementBytes = try pcm(at: second, marker: 7)
        let original = try attach(baseline.project, package: package, source: first)
        let old = try #require(original.cprMediaAttachments.first)
        let replaced = try attach(original, package: package, source: second)
        let new = try #require(replaced.cprMediaAttachments.first)
        #expect(replaced.cprMediaAttachments.count == 1 && old.id != new.id && old.mediaPath != new.mediaPath)
        #expect(new.mediaSHA256 == cprSHA256(replacementBytes) && new.mediaSHA256 != old.mediaSHA256)
        try ProjectStore.save(replaced, to: package)
        #expect(try ProjectStore.load(from: package) == replaced)
        let files = try mediaFiles(package), manifest = try Data(contentsOf: package.appendingPathComponent("Project.json"))
        let wrong = root.appendingPathComponent("Wrong.wav"); _ = try pcm(at: wrong, frames: 1)
        #expect(throws: RebaseCoreError.self) { try attach(replaced, package: package, source: wrong) }
        #expect(try mediaFiles(package) == files)
        #expect(try Data(contentsOf: package.appendingPathComponent("Project.json")) == manifest)
        var removed = replaced
        for index in removed.tracks.indices { removed.tracks[index].unresolvedAudioEvents = [] }
        #expect(throws: RebaseCoreError.self) { try removed.validate() }
        removed.removeUnusedCPRMediaAttachments()
        #expect(removed.cprMediaAttachments.isEmpty)
        try ProjectStore.save(removed, to: package)
        #expect(try ProjectStore.load(from: package) == removed)
        #expect(try retainedBytes(package) == preserved)
        #expect(try CPRProject.compatibilityReport(from: package)?.recoveredProject?.unresolvedAudioEvents.count == 1)
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func attachmentManifestTamperingAndMissingSourceProofCannotPersist() throws {
        let root = try temporary(); defer { try? FileManager.default.removeItem(at: root) }
        let (package, baseline) = try imported(at: root), source = root.appendingPathComponent("Match.wav")
        _ = try pcm(at: source); let project = try attach(baseline.project, package: package, source: source)
        try ProjectStore.save(project, to: package)
        let manifest = package.appendingPathComponent("Project.json"), before = try Data(contentsOf: manifest)
        let changes: [(inout [String: Any]) -> Void] = [
            { $0["mediaSHA256"] = String(repeating: "a", count: 64) },
            { $0["sourceSHA256"] = String(repeating: "b", count: 64) },
            { $0["sourceFileIdentity"] = 1 },
            { $0["frameCount"] = 1_058_399 },
            { $0["sampleRate"] = 48_000 },
            { $0["association"] = "verified-original" },
            { $0["mediaPath"] = "Media/../Match.wav" }
        ]
        for change in changes {
            let altered = try mutateAttachment(project, change)
            #expect(throws: (any Error).self) { try ProjectStore.save(altered, to: package) }
            #expect(try Data(contentsOf: manifest) == before)
            try JSONEncoder().encode(altered).write(to: manifest)
            #expect(throws: (any Error).self) { try ProjectStore.load(from: package) }
            try before.write(to: manifest)
        }
        let original = package.appendingPathComponent(CPRProject.originalRelativePath), originalBytes = try Data(contentsOf: original)
        var forgedSource = originalBytes; forgedSource[forgedSource.count - 1] ^= 1; try forgedSource.write(to: original)
        let files = try mediaFiles(package)
        #expect(throws: CPRProjectError.self) { try attach(project, package: package, source: source) }
        #expect(try mediaFiles(package) == files)
        try originalBytes.write(to: original)
        let reportURL = package.appendingPathComponent(CPRProject.reportRelativePath)
        let report = try Data(contentsOf: reportURL); try FileManager.default.removeItem(at: reportURL)
        #expect(throws: (any Error).self) { try ProjectStore.save(project, to: package) }
        #expect(throws: (any Error).self) { try ProjectStore.load(from: package) }
        try report.write(to: reportURL)
        #expect(try ProjectStore.load(from: package) == project)
    }

    @Test(.enabled(if: PrivateResearchFixtures.isConfigured, PrivateResearchFixtures.reason))
    func attachedMediaStillCannotRenderOrExportNativeEvents() throws {
        let root = try temporary(); defer { try? FileManager.default.removeItem(at: root) }
        let (package, baseline) = try imported(at: root), source = root.appendingPathComponent("Match.wav")
        _ = try pcm(at: source)
        var project = try attach(baseline.project, package: package, source: source)
        try project.convertToApplicationTiming()
        try ProjectStore.save(project, to: package)
        let wav = root.appendingPathComponent("Existing.wav"), marker = Data("unchanged output".utf8)
        try marker.write(to: wav)
        let exchange = root.appendingPathComponent("Blocked.dawproject")
        unresolvedError { _ = try OfflineRenderer.render(project: project, projectRoot: package) }
        unresolvedError { _ = try OfflineRenderer.export(project: project, projectRoot: package, to: wav) }
        unresolvedError { try DAWProject.export(project: project, projectRoot: package, to: exchange) }
        #expect(try Data(contentsOf: wav) == marker && !FileManager.default.fileExists(atPath: exchange.path))
        #expect(project.tracks.flatMap(\.clips).isEmpty && project.unresolvedAudioEvents.count == 1)
        #expect(try ProjectStore.load(from: package).cprMediaAttachments.count == 1)
    }

    @Test func legitimateSharedSourceChecksEveryEventBeforeAcceptingOrKeepingCopy() throws {
        let root = try temporary(); defer { try? FileManager.default.removeItem(at: root) }
        let source = root.appendingPathComponent("Shared.wav"); _ = try pcm(at: source)
        for exceedsSource in [false, true] {
            let archive = sharedSourceFixture(secondLength: exceedsSource ? 1_058_401 : 1_058_400)
            let cpr = root.appendingPathComponent(exceedsSource ? "Beyond.cpr" : "Valid.cpr")
            try archive.write(to: cpr)
            let package = root.appendingPathComponent(exceedsSource ? "Beyond.rebaseproj" : "Valid.rebaseproj")
            let baseline = try CPRProject.importProject(from: cpr, to: package, allowPartial: true, expectedSHA256: cprSHA256(archive))
            #expect(baseline.project.unresolvedAudioEvents.count == 2)
            #expect(try CPRProject.compatibilityReport(from: package) == baseline.report)
            let events = baseline.project.unresolvedAudioEvents
            #expect(events[0].files[0].object == events[1].files[0].object)
            #expect(events[0].segments[0].storedLength == 1_058_400)
            let before = try Data(contentsOf: package.appendingPathComponent("Project.json"))
            if exceedsSource {
                // The selected first event is admissible. A second, genuinely
                // source-backed event makes the shared association inadmissible.
                #expect(throws: CPRSegmentReadPlanError.sourceRangeExceeded) {
                    try ProjectStore.attachCPRAudioMedia(from: source, to: events[0].id, in: baseline.project, at: package)
                }
                #expect(try mediaFiles(package).isEmpty)
                #expect(try Data(contentsOf: package.appendingPathComponent("Project.json")) == before)
            } else {
                let project = try attach(baseline.project, package: package, source: source)
                #expect(project.cprMediaAttachments.count == 1)
                #expect(project.attachedMedia(for: events[0]) == project.attachedMedia(for: events[1]))
                try ProjectStore.save(project, to: package)
                #expect(try ProjectStore.load(from: package) == project)
                var partial = project
                partial.tracks[0].unresolvedAudioEvents.removeFirst(); partial.removeUnusedCPRMediaAttachments()
                #expect(partial.cprMediaAttachments.count == 1)
                try ProjectStore.save(partial, to: package)
                #expect(try ProjectStore.load(from: package) == partial)
            }
            #expect(try Data(contentsOf: package.appendingPathComponent(CPRProject.originalRelativePath)) == archive)
        }
    }

    /// Two new events/clips/clusters/segments share one actual archive AudioFile
    /// identity. All lengths and references are written structurally, so import
    /// creates legitimate fresh report/source proof for the negative control.
    private func sharedSourceFixture(secondLength: UInt64) -> Data {
        let f = AttachmentArchiveFixture()
        func path() {
            f.object("path", "FNPath") {
                f.string("self-authored.wav"); f.u32(0)
                for _ in 0..<3 { f.string("") }
                f.u32(0); f.u16(0); f.string("/unresolved/self-authored/")
            }
        }
        func event(_ index: Int) {
            f.object("event\(index)", "MAudioEvent", version: 6) {
                f.zeros(2); f.u64(0); f.u64(Double(1_058_400).bitPattern); f.u64(0)
                f.object("clip\(index)", "PAudioClip", version: 4) {
                    f.string("Source \(index)"); f.u32(10); f.u64((1.0 / 44_100).bitPattern); f.u32(0)
                    if index == 0 { path() } else { f.reference("path") }
                    f.string(""); f.u16(0); f.u32(0); f.u64(0); f.u32(0)
                    f.object("cluster\(index)", "AudioCluster") {
                        f.u32(0); f.u16(2); f.u32(1)
                        if index == 0 {
                            f.object("file", "AudioFile", version: 1) {
                                f.u64(1_058_400); f.u16(24); f.u16(6); f.u16(2); f.u32(Float(44_100).bitPattern)
                                f.reference("path"); f.u32(0)
                            }
                        } else { f.reference("file") }
                        f.u16(1); f.u32(1)
                        f.object("segment\(index)", "AClusterSegment") {
                            f.reference("file"); f.u64(0); f.u64(index == 0 ? 1_058_400 : secondLength); f.u64(0)
                        }
                    }
                    f.u16(1); f.u32(0)
                }
                f.u32(0); f.u32(1); f.u32(0); f.u32(0); f.u64(0); f.string("")
                f.u32(0); f.u32(Float(1).bitPattern); f.u32(0); f.u16(0)
                f.object("curve\(index)", "VolumeCurveDataNode") {
                    f.string(""); f.u32(1); f.u64(Double(1).bitPattern); f.u32(0)
                }
            }
        }
        f.object("arrangement", "PArrangement", version: 4) {
            f.object("root", "MRoot", version: 6) {
                f.zeros(26)
                f.object("rootList", "MTrackList") {
                    f.string(""); f.u32(1); f.u64(Double(1).bitPattern); f.u16(0); f.u32(1)
                    f.object("audio", "MAudioTrackEvent", version: 1) {
                        f.zeros(26)
                        f.object("audioList", "MListNode") {
                            f.string("Shared Audio"); f.u32(1); f.u64(Double(1).bitPattern); f.u32(2)
                            event(0); event(1)
                        }
                    }
                }
            }
        }
        return f.container()
    }
}

private final class AttachmentArchiveFixture {
    private var data = Data()
    private var identities: [String: Int] = [:]
    private func integer<T: FixedWidthInteger>(_ value: T) {
        var value = value.bigEndian
        data.append(withUnsafeBytes(of: &value) { Data($0) })
    }
    func u16(_ value: UInt16) { integer(value) }
    func u32(_ value: UInt32) { integer(value) }
    func u64(_ value: UInt64) { integer(value) }
    func zeros(_ count: Int) { data.append(Data(repeating: 0, count: count)) }
    func string(_ value: String) { u32(UInt32(value.utf8.count + 1)); data.append(Data(value.utf8)); data.append(0) }
    func reference(_ name: String) { u32(UInt32(identities[name]!)) }
    func object(_ label: String, _ name: String, version: UInt16 = 0, body: () -> Void) {
        precondition(identities[label] == nil)
        u32(.max); string(name); u16(version)
        let identity = data.count; identities[label] = identity; u32(0)
        let start = data.count; body()
        var length = UInt32(data.count - start).bigEndian
        data.replaceSubrange(identity..<(identity + 4), with: withUnsafeBytes(of: &length) { Data($0) })
    }
    func container() -> Data {
        func u32(_ value: UInt32) -> Data { var value = value.bigEndian; return withUnsafeBytes(of: &value) { Data($0) } }
        func text(_ value: String) -> Data { u32(UInt32(value.utf8.count)) + Data(value.utf8) }
        func chunk(_ name: String, _ payload: Data) -> Data { Data(name.utf8) + u32(UInt32(payload.count)) + payload }
        let sections = chunk("ROOT", text("Arrangement1") + text("PArrangement")) + chunk("ARCH", data)
        return Data("RIFF".utf8) + u32(UInt32(sections.count)) + Data("NUND".utf8) + sections
    }
}
