import Foundation
import Testing
@testable import RebasePortable

struct PortableSourceStreamTests {
    private final class Client {
        let session = PortableSession()
        var id = 0, revision = 0
        func send(_ command: String, _ fields: [String: Any] = [:], expected: Int? = nil) throws -> [String: Any] {
            id += 1
            var input: [String: Any] = ["protocol": 1, "id": id, "command": command, "expectedRevision": expected ?? revision]
            input.merge(fields) { _, new in new }
            let response = try #require(JSONSerialization.jsonObject(with: session.process(JSONSerialization.data(withJSONObject: input))) as? [String: Any])
            revision = try #require((response["state"] as? [String: Any])?["revision"] as? Int)
            return response
        }
    }
    private struct Record { let kind: Int; let metadata: [String: Any]; let payload: Data }
    private func scratch() throws -> URL {
        let parent = ProcessInfo.processInfo.environment["REBASE_TEST_WORK_ROOT"].map { URL(fileURLWithPath: $0) } ?? FileManager.default.temporaryDirectory
        let root = parent.appendingPathComponent("portable-source-stream-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        return root
    }
    private func state(_ response: [String: Any]) throws -> Data {
        try JSONSerialization.data(withJSONObject: #require(response["state"] as? [String: Any]), options: [.sortedKeys])
    }
    private func prepare(_ client: Client, fixture: CPRAuditionModesControl.Fixture, output: URL,
                         mode: CPRSourceEventPlaybackMode = .sourceRate, seconds: Double = 0,
                         rewind: Bool = false) throws -> [String: Any] {
        let response = try client.send("prepareSourceStream", ["clipID": fixture.project.unresolvedAudioEvents[0].id.uuidString,
            "path": output.path, "mode": mode.rawValue, "startSeconds": seconds, "rewindAtEnd": rewind])
        if response["ok"] as? Bool != true {
            // Retain the actual refusal in failed test output; a missing receipt
            // alone cannot distinguish producer, custody and filesystem errors.
            print("source-stream-prepare-refusal mode=\(mode.rawValue) seconds=\(seconds) error=\(String(describing: response["error"]))")
        }
        #expect(response["ok"] as? Bool == true)
        return try #require(response["sourceStream"] as? [String: Any])
    }
    private func startup(_ receipt: [String: Any], chunk: Int? = nil) throws -> Data {
        var result: [String: Any] = ["schema": "rebase.source-stream-start.v1"]
        for name in ["ticketPath", "ticketSHA256", "capability", "generation"] { result[name] = receipt[name] }
        if let chunk { result["maximumChunkFrames"] = chunk }
        return try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
    }
    private func decode(_ bytes: Data) throws -> Record {
        func number(_ first: Int, _ count: Int) -> Int { (0..<count).reduce(0) { $0 | Int(bytes[first + $1]) << (8 * $1) } }
        #expect(bytes.prefix(4) == Data("RBAS".utf8) && bytes.count >= 16)
        #expect(number(4, 2) == 1)
        let length = number(8, 4), payload = number(12, 4)
        #expect(length <= 8_388_608 && payload <= 65_536 * 8 && bytes.count == 16 + length + payload)
        let object = try #require(JSONSerialization.jsonObject(with: bytes.subdata(in: 16..<(16 + length))) as? [String: Any])
        return Record(kind: number(6, 2), metadata: object, payload: bytes.suffix(payload))
    }
    private func run(_ bytes: Data) throws -> (Int32, [Record]) {
        var records: [Record] = []
        let result = PortableSourceStream.produce(startup: bytes) { records.append(try decode($0)) }
        return (result, records)
    }
    private func expectedPCM(_ prepared: CPRSourceAudition.Prepared, start: Int64 = 0) throws -> Data {
        let cursor = try prepared.cursor(from: start); var data = Data()
        while let block = try cursor.nextPlaybackBlock() {
            for sample in block.interleaved { var bits = sample.bitPattern.littleEndian; withUnsafeBytes(of: &bits) { data.append(contentsOf: $0) } }
        }
        return data
    }

    @Test func internalProjectCopyStreamsEveryModeWithRealParentsAndUnchangedSource() throws {
        let root = try scratch(); defer { try? FileManager.default.removeItem(at: root) }
        let fixture = try CPRAuditionModesControl.makePackage(in: root), client = Client()
        let sourceBefore = try PortablePackageSnapshot.capture(in: fixture.root)
        let opened = try client.send("open", ["path": fixture.root.path, "asCopy": true])
        #expect(opened["ok"] as? Bool == true)
        let openedState = try #require(opened["state"] as? [String: Any])
        #expect(openedState["needsSaveAs"] as? Bool == true)
        let stable = try state(opened)
        for mode in CPRSourceEventPlaybackMode.allCases {
            let output = root.appendingPathComponent("copy-" + mode.rawValue + ".ticket")
            let receipt = try prepare(client, fixture: fixture, output: output, mode: mode)
            let ticket = try #require(JSONSerialization.jsonObject(with: Data(contentsOf: output)) as? [String: Any])
            let copyPath = try #require(ticket["rootPath"] as? String)
            let copiedRoot = URL(fileURLWithPath: copyPath)
            #expect(!ProjectFileIO.samePath(copiedRoot, fixture.root))
            var directory = copiedRoot
            while true {
                try ProjectFileIO.requireRealDirectory(directory)
                if directory.pathComponents.count <= 1 { break }
                let parent = directory.deletingLastPathComponent()
                if ProjectFileIO.samePath(directory, parent) { break }
                directory = parent
            }
            let (result, records) = try run(startup(receipt, chunk: 257))
            #expect(result == 0 && records.first?.kind == 1 && records.last?.kind == 3)
            let prepared = try CPRSourceAudition.prepare(eventID: fixture.project.unresolvedAudioEvents[0].id,
                in: fixture.project, at: fixture.root, mode: mode)
            let outputPCM = records.filter { $0.kind == 2 }.reduce(into: Data()) { $0.append($1.payload) }
            let expected = try expectedPCM(prepared)
            #expect(outputPCM == expected)
            #expect(try state(client.send("state")) == stable)
        }
        #expect(try PortablePackageSnapshot.capture(in: fixture.root) == sourceBefore)
    }

    @Test func everyModeStreamsExactSharedOutputAndPreservesDirtySession() throws {
        let root = try scratch(); defer { try? FileManager.default.removeItem(at: root) }
        let fixture = try CPRAuditionModesControl.makePackage(in: root), client = Client()
        _ = try client.send("open", ["path": fixture.root.path])
        _ = try client.send("selectClip", ["clipID": fixture.project.unresolvedAudioEvents[0].id.uuidString])
        _ = try client.send("setGain", ["trackID": fixture.project.tracks[0].id.uuidString, "value": -6])
        let stable = try state(client.send("state"))
        for mode in CPRSourceEventPlaybackMode.allCases {
            let receipt = try prepare(client, fixture: fixture, output: root.appendingPathComponent(mode.rawValue + ".ticket"), mode: mode)
            let (result, records) = try run(startup(receipt, chunk: 257))
            #expect(result == 0 && records.first?.kind == 1 && records.last?.kind == 3)
            let admission = try #require(records.first?.metadata), eof = try #require(records.last?.metadata)
            let proof = try #require(admission["proof"] as? [String: Any])
            #expect(proof["schema"] as? String == "rebase.source-stream-proof.v1")
            #expect(proof["wavSHA256"] == nil && proof["maximumFrames"] == nil)
            let prepared = try CPRSourceAudition.prepare(eventID: fixture.project.unresolvedAudioEvents[0].id, in: fixture.project, at: fixture.root, mode: mode)
            let expected = try expectedPCM(prepared)
            let output = records.filter { $0.kind == 2 }.reduce(into: Data()) { $0.append($1.payload) }
            #expect(output == expected && eof["pcmSHA256"] as? String == PortableSHA256.hexDigest(output))
            var frame: Int64 = 0, logical = 0, offset = 0
            for (sequence, record) in records.filter({ $0.kind == 2 }).enumerated() {
                let count = try #require(record.metadata["frames"] as? Int)
                let logicalFrames = try #require(record.metadata["logicalFrames"] as? Int)
                #expect(count <= 257 && record.payload.count == count * 8)
                #expect(record.metadata["sequence"] as? Int == sequence && record.metadata["absoluteFrame"] as? Int64 == frame)
                #expect(record.metadata["logicalBlock"] as? Int == logical && record.metadata["logicalOffset"] as? Int == offset)
                #expect(record.metadata["sha256"] as? String == PortableSHA256.hexDigest(record.payload))
                offset += count; frame += Int64(count)
                if offset == logicalFrames { logical += 1; offset = 0 }
            }
            #expect(offset == 0 && frame == prepared.frameCount)
            #expect(eof["peakPayloadFrames"] as? Int ?? Int.max <= 257)
            #expect(try state(client.send("state")) == stable)
        }
    }

    @Test func oddSeekEOFRoundedRewindAndTransportPartitionAreIndependent() throws {
        let root = try scratch(); defer { try? FileManager.default.removeItem(at: root) }
        let fixture = try CPRAuditionModesControl.makePackage(in: root), client = Client()
        _ = try client.send("open", ["path": fixture.root.path])
        for mode: CPRSourceEventPlaybackMode in [.nativeMode0ProjectRate, .nativeMode1ProjectRate, .nativeMode2ProjectRate] {
            let prepared = try CPRSourceAudition.prepare(eventID: fixture.project.unresolvedAudioEvents[0].id, in: fixture.project, at: fixture.root, mode: mode)
            for (tag, seconds, rewind, wanted) in [("odd", 1 / prepared.sampleRate, false, Int64(1)),
                ("eof", Double(prepared.frameCount) / prepared.sampleRate, false, prepared.frameCount),
                ("rewind", (Double(prepared.frameCount) - 0.1) / prepared.sampleRate, true, Int64(0))] {
                let receipt = try prepare(client, fixture: fixture, output: root.appendingPathComponent(mode.rawValue + tag), mode: mode, seconds: seconds, rewind: rewind)
                let (first, a) = try run(startup(receipt)), (second, b) = try run(startup(receipt, chunk: 257))
                #expect(first == 0 && second == 0 && a.first?.metadata["startFrame"] as? Int64 == wanted)
                let pcm = a.filter { $0.kind == 2 }.reduce(into: Data()) { $0.append($1.payload) }
                let other = b.filter { $0.kind == 2 }.reduce(into: Data()) { $0.append($1.payload) }
                let expected = try expectedPCM(prepared, start: wanted)
                #expect(pcm == expected && pcm == other)
                #expect(a.first?.metadata["proofSHA256"] as? String == b.first?.metadata["proofSHA256"] as? String)
                #expect(a.last?.metadata["pcmSHA256"] as? String == b.last?.metadata["pcmSHA256"] as? String)
            }
        }
    }

    @Test func longTimelineTailAndEOFHaveNoSnapshotDurationLimit() throws {
        let root = try scratch(); defer { try? FileManager.default.removeItem(at: root) }
        for name in ["boundary", "overlap", "near-day"] {
            let directory = root.appendingPathComponent(name)
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: false)
            let fixture = try CPRAuditionModesControl.makePackage(in: directory, name: name, options: CPRLongTimelineFixtureTests.options(name)), client = Client()
            _ = try client.send("open", ["path": fixture.root.path])
            let inspected = try client.send("inspectSourceEvent", ["clipID": fixture.project.unresolvedAudioEvents[0].id.uuidString])
            let inspection = try #require(inspected["sourceInspection"] as? [String: Any])
            let availability = try #require(inspection["modes"] as? [[String: Any]])
            for mode: CPRSourceEventPlaybackMode in [.nativeTimelineSourceRate, .nativeTimelineProjectClock, .nativeTimelineSavedProjectClock, .nativeTrackSavedProjectClock] {
                let availability = try #require(availability.first { $0["mode"] as? String == mode.rawValue })
                #expect(availability["available"] as? Bool == true && availability["liveAvailable"] as? Bool == true)
                #expect(availability["snapshotExportAvailable"] as? Bool == false && availability["snapshotExportReason"] as? String != nil)
                #expect(availability["reason"] == nil && availability["liveReason"] == nil)
                let prepared = try CPRSourceAudition.prepare(eventID: fixture.project.unresolvedAudioEvents[0].id, in: fixture.project, at: fixture.root, mode: mode)
                #expect(prepared.frameCount > 32_000_000)
                let receipt = try prepare(client, fixture: fixture, output: root.appendingPathComponent(name + mode.rawValue), mode: mode,
                    seconds: Double(prepared.frameCount - 1000) / prepared.sampleRate)
                let (result, records) = try run(startup(receipt, chunk: 257))
                #expect(result == 0 && records.last?.metadata["frames"] as? Int == 1000)
                #expect(records.last?.metadata["peakLogicalFrames"] as? Int == 1000)
                let pcm = records.filter { $0.kind == 2 }.reduce(into: Data()) { $0.append($1.payload) }
                let expected = try expectedPCM(prepared, start: prepared.frameCount - 1000)
                #expect(pcm == expected)
            }
        }
    }

    @Test func changedCoveredMediaSourceReportAndManifestFailBeforeAdmission() throws {
        let root = try scratch(); defer { try? FileManager.default.removeItem(at: root) }
        let fixture = try CPRAuditionModesControl.makePackage(in: root, options: CPRLongTimelineFixtureTests.options("overlap")), client = Client()
        _ = try client.send("open", ["path": fixture.root.path])
        let receipt = try prepare(client, fixture: fixture, output: root.appendingPathComponent("valid.ticket"), mode: .nativeTrackSavedProjectClock, seconds: 1000.13)
        let covered = fixture.project.unresolvedAudioEvents[0]
        let attachment = try #require(fixture.project.attachedMedia(for: covered))
        for path in [CPRProject.originalRelativePath, CPRProject.reportRelativePath, ProjectStore.manifestName, attachment.mediaPath] {
            let url = fixture.root.appendingPathComponent(path), original = try Data(contentsOf: url)
            var changed = original; changed[changed.count - 1] ^= 1; try changed.write(to: url)
            let (result, records) = try run(startup(receipt))
            #expect(result == 1 && records.count == 1 && records[0].kind == 4)
            #expect(!(records[0].metadata["message"] as? String ?? "").contains(root.path))
            try original.write(to: url)
        }
    }

    @Test func ticketsRejectTamperingExistingDestinationsAndRevokeOnStateChanges() throws {
        let root = try scratch(); defer { try? FileManager.default.removeItem(at: root) }
        let fixture = try CPRAuditionModesControl.makePackage(in: root, options: .init(events: [.init(), .init(startTicks: 480)])), client = Client()
        _ = try client.send("open", ["path": fixture.root.path])
        let path = root.appendingPathComponent("first.ticket")
        let receipt = try prepare(client, fixture: fixture, output: path), original = try Data(contentsOf: path)
        let fields: [String: Any] = ["clipID": fixture.project.unresolvedAudioEvents[0].id.uuidString, "path": path.path]
        #expect(try client.send("prepareSourceStream", fields)["ok"] as? Bool == false)
        #expect(try client.send("prepareSourceStream", fields, expected: client.revision - 1)["ok"] as? Bool == false)
        #expect(try Data(contentsOf: path) == original)
        var changed = original; changed[changed.count - 1] ^= 1; try changed.write(to: path)
        #expect(try run(startup(receipt)).0 == 1)
        try original.write(to: path)
        _ = try prepare(client, fixture: fixture, output: root.appendingPathComponent("second.ticket"))
        #expect(!FileManager.default.fileExists(atPath: path.path))
        _ = try client.send("setGain", ["trackID": fixture.project.tracks[0].id.uuidString, "value": -6])
        #expect(!FileManager.default.fileExists(atPath: root.appendingPathComponent("second.ticket").path))
        _ = try prepare(client, fixture: fixture, output: root.appendingPathComponent("third.ticket"))
        _ = try client.send("selectClip", ["clipID": fixture.project.unresolvedAudioEvents[1].id.uuidString])
        #expect(!FileManager.default.fileExists(atPath: root.appendingPathComponent("third.ticket").path))
        let inside = fixture.root.appendingPathComponent("forbidden.ticket")
        #expect(try client.send("prepareSourceStream", ["clipID": fixture.project.unresolvedAudioEvents[0].id.uuidString, "path": inside.path])["ok"] as? Bool == false)
        #expect(!FileManager.default.fileExists(atPath: inside.path))
    }

    @Test func malformedStartupAndOutputFailureAreTerminalAndPathFree() throws {
        let root = try scratch(); defer { try? FileManager.default.removeItem(at: root) }
        let fixture = try CPRAuditionModesControl.makePackage(in: root), client = Client()
        _ = try client.send("open", ["path": fixture.root.path])
        let receipt = try prepare(client, fixture: fixture, output: root.appendingPathComponent("valid.ticket"))
        var cases = [Data(), Data("null".utf8), Data("[]".utf8), Data(repeating: 65, count: 65_537)]
        let original = try #require(JSONSerialization.jsonObject(with: startup(receipt)) as? [String: Any])
        for (field, value): (String, Any) in [("maximumChunkFrames", 0), ("maximumChunkFrames", 65_537), ("maximumChunkFrames", true),
            ("capability", UUID().uuidString), ("generation", UUID().uuidString), ("ticketSHA256", String(repeating: "0", count: 64)), ("schema", "future")] {
            var input = original; input[field] = value; cases.append(try JSONSerialization.data(withJSONObject: input))
        }
        let text = String(decoding: try startup(receipt), as: UTF8.self)
        cases.append(Data(("{\"schema\":\"rebase.source-stream-start.v1\"," + text.dropFirst()).utf8))
        cases.append(Data((String(text.dropLast()) + ",\"maximumChunkFrames\":1.0}").utf8))
        cases.append(Data((String(text.dropLast()) + ",\"unknown\":1}").utf8))
        for input in cases {
            let (result, records) = try run(input)
            #expect(result == 1 && records.count == 1 && records[0].kind == 4)
            #expect(!(records[0].metadata["message"] as? String ?? "").contains(root.path))
        }
        struct Closed: Error {}
        var count = 0
        let result = PortableSourceStream.produce(startup: try startup(receipt)) { _ in count += 1; throw Closed() }
        #expect(result == 1 && count == 2) // Failed admission write, then one best-effort failure write.
        #expect(try client.send("state")["ok"] as? Bool == true)
    }

    #if !os(Windows)
    @Test func managedScratchParentsRejectLinksWithoutCreatingRedirectedContents() throws {
        let root = try scratch(); defer { try? FileManager.default.removeItem(at: root) }
        let target = root.appendingPathComponent("target"), link = root.appendingPathComponent("linked-cache")
        try FileManager.default.createDirectory(at: target, withIntermediateDirectories: false)
        let sentinel = target.appendingPathComponent("sentinel"), bytes = Data("unchanged".utf8)
        try bytes.write(to: sentinel)
        try FileManager.default.createSymbolicLink(at: link, withDestinationURL: target)
        do {
            try PortableSession.prepareScratchDirectories(link.appendingPathComponent("Rebase").appendingPathComponent("SessionCopies"))
            Issue.record("A linked internal scratch parent was accepted")
        } catch { }
        #expect(try Data(contentsOf: sentinel) == bytes)
        #expect(try FileManager.default.contentsOfDirectory(atPath: target.path) == ["sentinel"])
        let ordinary = root.appendingPathComponent("ordinary").appendingPathComponent("Rebase").appendingPathComponent("SessionCopies")
        try PortableSession.prepareScratchDirectories(ordinary)
        try PortableSession.prepareScratchDirectories(ordinary)
        try ProjectFileIO.requireRealDirectory(ordinary)
    }

    @Test func ticketAndParentSymlinksAreRejectedWithoutFollowingThem() throws {
        let root = try scratch(); defer { try? FileManager.default.removeItem(at: root) }
        let fixture = try CPRAuditionModesControl.makePackage(in: root), client = Client()
        _ = try client.send("open", ["path": fixture.root.path])
        let receipt = try prepare(client, fixture: fixture, output: root.appendingPathComponent("valid.ticket"))
        let link = root.appendingPathComponent("linked.ticket")
        try FileManager.default.createSymbolicLink(at: link, withDestinationURL: URL(fileURLWithPath: try #require(receipt["ticketPath"] as? String)))
        var altered = receipt; altered["ticketPath"] = link.path
        #expect(try run(startup(altered)).0 == 1)
        let parent = root.appendingPathComponent("parent-link")
        try FileManager.default.createSymbolicLink(at: parent, withDestinationURL: root)
        altered["ticketPath"] = parent.appendingPathComponent("valid.ticket").path
        #expect(try run(startup(altered)).0 == 1)
        let response = try client.send("prepareSourceStream", ["clipID": fixture.project.unresolvedAudioEvents[0].id.uuidString, "path": parent.appendingPathComponent("new.ticket").path])
        #expect(response["ok"] as? Bool == false && !FileManager.default.fileExists(atPath: root.appendingPathComponent("new.ticket").path))
    }
    #endif

    @Test func worstWidthCompleteProofFitsWithoutTruncatingContributors() throws {
        let range = CPRSourceEventTimelineRange(contract: CPRPlacedSourceEventPlan.savedProjectClockContract,
            position: -Double.greatestFiniteMagnitude, duration: Double.leastNormalMagnitude, offset: Double.greatestFiniteMagnitude)
        let id = UUID(), sha = String(repeating: "f", count: 64)
        let event = CPRSourceTrackPlaybackInfo.Event(eventID: id, eventIdentity: Int.min, sourceOrdinal: Int.min,
            priority: Int32.min, sourceSampleRate: Double.greatestFiniteMagnitude, mediaSHA256: sha,
            canonicalStart: -Double.greatestFiniteMagnitude, canonicalEnd: Double.greatestFiniteMagnitude, range: range)
        let fragment = CPRSourceTrackPlaybackInfo.Fragment(eventID: id, eventIdentity: Int.min, sourceOrdinal: Int.min, range: range)
        let track = CPRSourceTrackPlaybackInfo(contract: CPRSourceTrackPlaybackInfo.contractName, freshRootMode: UInt32.max,
            trackIdentity: Int.min, events: Array(repeating: event, count: 4096), fragments: Array(repeating: fragment, count: 16_384), snappedEmptyFragmentCount: Int.max)
        let proof = PortableSourceStream.Proof(revision: UInt64.max, eventID: id, name: String(repeating: "\u{1}", count: 50_000),
            mode: "nativeTimelineSavedProjectClock", sourceKind: "track", clockRole: "saved-project-clock-unconverted",
            projectSampleRate: Double.greatestFiniteMagnitude, currentNativeClock: nil, preservedNativeClock: nil,
            projectManifestSHA256: sha, currentProjectSHA256: sha, importReportSHA256: sha, sourceSHA256: sha,
            mediaSHA256: sha, sampleRate: Double.greatestFiniteMagnitude, sourceSampleRate: Double.greatestFiniteMagnitude,
            frames: Int64.max, startFrame: Int64.max, totalFrames: Int64.max, timelineRange: .init(range),
            savedProjectAudioSetup: nil, sourceTrack: .init(track))
        let data = try PortableSourceStream.encode(proof)
        // Reserve a further16KiB for two ≤2-record clocks, the three fixed-class
        // saved-setup identities, and the entire admission envelope. These are
        // far smaller than the margin. Every variable per-contributor field
        // above uses a representation at least as wide as admitted values.
        print("source-stream-worst-proof-bytes=\(data.count); reserved-envelope-clock-setup-bytes=16384")
        #expect(data.count + 16_384 < PortableSourceStream.maximumMetadataBytes)
        #expect(data.count > 4_000_000)
        let object = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let encodedTrack = try #require(object["sourceTrack"] as? [String: Any])
        #expect((encodedTrack["events"] as? [Any])?.count == 4096 && (encodedTrack["fragments"] as? [Any])?.count == 16_384)
    }
}
