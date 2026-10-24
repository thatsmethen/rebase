import Foundation
import Testing
@testable import RebasePortable

struct PortableSourceAuditionTests {
    private final class Client {
        let session = PortableSession()
        var id = 0
        var revision = 0
        func send(_ command: String, _ fields: [String: Any] = [:], revision expected: Int? = nil) throws -> [String: Any] {
            id += 1
            var input: [String: Any] = ["protocol": 1, "id": id, "command": command, "expectedRevision": expected ?? revision]
            input.merge(fields) { _, new in new }
            let reply = try #require(JSONSerialization.jsonObject(with: session.process(JSONSerialization.data(withJSONObject: input))) as? [String: Any])
            revision = try #require((reply["state"] as? [String: Any])?["revision"] as? Int)
            return reply
        }
    }
    private func scratch() throws -> URL {
        let parent = ProcessInfo.processInfo.environment["REBASE_TEST_WORK_ROOT"].map { URL(fileURLWithPath: $0) }
            ?? FileManager.default.temporaryDirectory
        let root = parent.appendingPathComponent("portable-source-modes-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        return root
    }
    private func state(_ reply: [String: Any]) throws -> Data {
        try JSONSerialization.data(withJSONObject: #require(reply["state"] as? [String: Any]), options: [.sortedKeys])
    }
    private func error(_ reply: [String: Any]) -> String? { (reply["error"] as? [String: Any])?["code"] as? String }
    private func object(_ data: Data) throws -> [String: Any] { try #require(JSONSerialization.jsonObject(with: data) as? [String: Any]) }
    private func open(_ client: Client, _ fixture: CPRAuditionModesControl.Fixture) throws -> UUID {
        #expect(try client.send("open", ["path": fixture.root.path])["ok"] as? Bool == true)
        return try #require(fixture.project.unresolvedAudioEvents.first?.id)
    }
    private func render(_ client: Client, _ event: UUID, _ mode: CPRSourceEventPlaybackMode, _ output: URL,
                        seconds: Double = 0, rewind: Bool = false) throws -> [String: Any] {
        try client.send("renderSourceEvent", ["clipID": event.uuidString, "mode": mode.rawValue,
            "path": output.path, "startSeconds": seconds, "rewindAtEnd": rewind])
    }
    private func pcm(_ prepared: CPRSourceAudition.Prepared, from frame: Int64 = 0) throws -> Data {
        let cursor = try prepared.cursor(from: frame)
        var bytes = Data()
        while let block = try cursor.nextPlaybackBlock() {
            for sample in block.interleaved {
                var bits = sample.bitPattern.littleEndian
                withUnsafeBytes(of: &bits) { bytes.append(contentsOf: $0) }
            }
        }
        return bytes
    }
    private func verifiedProof(_ reply: [String: Any], output: URL) throws -> [String: Any] {
        #expect(reply["ok"] as? Bool == true)
        let receipt = try #require(reply["render"] as? [String: Any])
        let path = try #require(receipt["manifestPath"] as? String)
        #expect(URL(fileURLWithPath: path).standardizedFileURL == output.appendingPathExtension("source-audition.json"))
        let bytes = try Data(contentsOf: URL(fileURLWithPath: path)), wave = try Data(contentsOf: output)
        #expect(receipt["manifestSHA256"] as? String == PortableSHA256.hexDigest(bytes))
        #expect(receipt["manifestBytes"] as? Int == bytes.count)
        #expect(receipt["sha256"] as? String == PortableSHA256.hexDigest(wave))
        let proof = try object(bytes)
        #expect(proof["schema"] as? String == "rebase.source-audition-manifest.v1")
        #expect(proof["wavSHA256"] as? String == receipt["sha256"] as? String)
        #expect(proof["wavBytes"] as? Int == wave.count && proof["wavFileName"] as? String == output.lastPathComponent)
        for key in ["revision", "frames", "sampleRate", "startFrame", "totalFrames"] {
            #expect(proof[key] as? NSNumber == receipt[key] as? NSNumber)
        }
        for key in ["mode", "eventID", "sourceSHA256", "mediaSHA256"] {
            #expect(proof[key] as? String == receipt[key] as? String)
        }
        #expect(proof["maximumFrames"] as? Int == 32_000_000 && proof["channels"] as? Int == 2)
        return proof
    }

    @Test func everyModeInspectionAndRenderPreserveDirtyHistorySelectionAndSource() throws {
        let directory = try scratch(); defer { try? FileManager.default.removeItem(at: directory) }
        let fixture = try CPRAuditionModesControl.makePackage(in: directory), client = Client()
        let event = try open(client, fixture)
        let original = try Data(contentsOf: fixture.root.appendingPathComponent(ProjectStore.manifestName))
        _ = try client.send("selectClip", ["clipID": event.uuidString])
        _ = try client.send("setGain", ["trackID": fixture.project.tracks[0].id.uuidString, "value": -6])
        let stable = try state(client.send("state"))
        let inspection = try client.send("inspectSourceEvent", ["clipID": event.uuidString])
        let availability = try #require(inspection["sourceInspection"] as? [String: Any])
        let modes = try #require(availability["modes"] as? [[String: Any]])
        #expect(availability["availabilityScope"] as? String == "preparation-only")
        #expect(modes.compactMap { $0["mode"] as? String } == CPRSourceEventPlaybackMode.allCases.map(\.rawValue))
        #expect(modes.allSatisfy { $0["available"] as? Bool == true })
        #expect(try state(inspection) == stable)
        for mode in CPRSourceEventPlaybackMode.allCases {
            let output = directory.appendingPathComponent(mode.rawValue + ".wav")
            let reply = try render(client, event, mode, output)
            let proof = try verifiedProof(reply, output: output)
            let prepared = try CPRSourceAudition.prepare(eventID: event, in: fixture.project, at: fixture.root, mode: mode)
            #expect(try Data(contentsOf: output).dropFirst(58) == pcm(prepared))
            #expect(proof["frames"] as? Int64 == prepared.frameCount)
            #expect(proof["sampleRate"] as? Double == prepared.sampleRate)
            #expect(proof["projectSampleRate"] as? Double == 44_100)
            #expect(proof["projectManifestSHA256"] as? String == PortableSHA256.hexDigest(original))
            let reportBytes = try Data(contentsOf: fixture.root.appendingPathComponent(CPRProject.reportRelativePath))
            #expect(proof["importReportSHA256"] as? String == PortableSHA256.hexDigest(reportBytes))
            #expect(try state(reply) == stable)
            #expect(try Data(contentsOf: fixture.root.appendingPathComponent(ProjectStore.manifestName)) == original)
        }
        #expect(try client.send("undo")["ok"] as? Bool == true)
        #expect((try client.send("state")["state"] as? [String: Any])?["dirty"] as? Bool == false)
        #expect(try client.send("redo")["ok"] as? Bool == true)
    }

    @Test func missingModePreservesLegacySourceWaveAndManifestHasFullClockProof() throws {
        let directory = try scratch(); defer { try? FileManager.default.removeItem(at: directory) }
        let fixture = try CPRAuditionModesControl.makePackage(in: directory), client = Client()
        let event = try open(client, fixture), output = directory.appendingPathComponent("default.wav")
        let reply = try client.send("renderSourceEvent", ["clipID": event.uuidString, "path": output.path])
        let proof = try verifiedProof(reply, output: output)
        let old = directory.appendingPathComponent("old-writer.wav")
        _ = try CPRSourceEventRenderer.renderAudition(eventID: event, in: fixture.project, at: fixture.root, to: old)
        #expect(try Data(contentsOf: output) == Data(contentsOf: old))
        #expect(proof["mode"] as? String == "sourceRate" && proof["clockRole"] as? String == "source-rate")
        #expect(proof["sourceKind"] as? String == "event")
        let savedOutput = directory.appendingPathComponent("saved.wav")
        let saved = try verifiedProof(render(client, event, .nativeTimelineSavedProjectClock, savedOutput), output: savedOutput)
        #expect(saved["sampleRate"] as? Int == 32_000 && saved["sourceSampleRate"] as? Int == 48_000)
        #expect(saved["clockRole"] as? String == "saved-project-clock-unconverted")
        let setup = try #require(saved["savedProjectAudioSetup"] as? [String: Any])
        #expect(setup["baseRateBits"] as? UInt32 == Float(32_000).bitPattern)
        #expect(setup["factorBits"] as? UInt64 == Double(1).bitPattern)
        #expect(saved["timelineRange"] is [String: Any])
        let readReport = try CPRProject.compatibilityReport(from: fixture.root)
        let report = try #require(readReport)
        if let clock = report.nativeClock {
            let returned = try JSONDecoder().decode(NativeTempoClock.self, from: JSONSerialization.data(withJSONObject: #require(saved["preservedNativeClock"])))
            #expect(returned == clock)
        }
    }

    @Test func freshOddSeekEOFAndRoundedRewindUseSharedSchedulingAndCursor() throws {
        let directory = try scratch(); defer { try? FileManager.default.removeItem(at: directory) }
        let fixture = try CPRAuditionModesControl.makePackage(in: directory), client = Client()
        let event = try open(client, fixture), stable = try state(client.send("state"))
        for mode in CPRSourceEventPlaybackMode.allCases {
            let prepared = try CPRSourceAudition.prepare(eventID: event, in: fixture.project, at: fixture.root, mode: mode)
            let seconds = 1 / prepared.sampleRate, start = try prepared.startFrame(at: seconds)
            #expect(start == 1)
            let output = directory.appendingPathComponent(mode.rawValue + "-odd.wav")
            let proof = try verifiedProof(render(client, event, mode, output, seconds: seconds), output: output)
            #expect(proof["startFrame"] as? Int64 == start)
            #expect(proof["frames"] as? Int64 == prepared.frameCount - start)
            #expect(try Data(contentsOf: output).dropFirst(58) == pcm(prepared, from: start))
            let end = directory.appendingPathComponent(mode.rawValue + "-end.wav")
            let endProof = try verifiedProof(render(client, event, mode, end, seconds: 1e100), output: end)
            #expect(endProof["startFrame"] as? Int64 == prepared.frameCount && endProof["frames"] as? Int == 0)
            #expect(try Data(contentsOf: end).count == 58)
            let rewind = directory.appendingPathComponent(mode.rawValue + "-rewind.wav")
            let nearEnd = (Double(prepared.frameCount) - 0.25) / prepared.sampleRate
            let rewindProof = try verifiedProof(render(client, event, mode, rewind, seconds: nearEnd, rewind: true), output: rewind)
            #expect(rewindProof["startFrame"] as? Int == 0 && rewindProof["frames"] as? Int64 == prepared.frameCount)
            #expect(try Data(contentsOf: rewind).dropFirst(58) == pcm(prepared))
            #expect(try state(client.send("state")) == stable)
        }
    }

    @Test func completeTrackProofRetainsCoveredContributorsAndRefusesTheirChangedMedia() throws {
        let directory = try scratch(); defer { try? FileManager.default.removeItem(at: directory) }
        let settings = CPRAuditionModesControl.Options(events: [
            .init(frames: 4_803, priority: -7), .init(frames: 4_803, priority: 3), .init(frames: 4_803, priority: 9)
        ])
        let fixture = try CPRAuditionModesControl.makePackage(in: directory, options: settings), client = Client()
        let event = try open(client, fixture), output = directory.appendingPathComponent("track.wav")
        let proof = try verifiedProof(render(client, event, .nativeTrackSavedProjectClock, output), output: output)
        let track = try #require(proof["sourceTrack"] as? [String: Any])
        let contributors = try #require(track["events"] as? [[String: Any]])
        let fragments = try #require(track["fragments"] as? [[String: Any]])
        #expect(proof["sourceKind"] as? String == "track" && contributors.count == 3)
        #expect(contributors.compactMap { $0["sourceOrdinal"] as? Int } == [0, 1, 2])
        #expect(contributors.compactMap { $0["priority"] as? Int } == [-7, 3, 9])
        #expect(Set(contributors.compactMap { $0["eventID"] as? String }) == Set(fixture.project.unresolvedAudioEvents.map { $0.id.uuidString }))
        #expect(Set(contributors.compactMap { $0["mediaSHA256"] as? String }).count == 3)
        #expect(!fragments.isEmpty && fragments.count < contributors.count)
        let covered = try #require(fixture.project.unresolvedAudioEvents.first)
        let attachment = try #require(fixture.project.attachedMedia(for: covered))
        let attached = try CPRAudioMediaValidation.attachedURL(attachment.mediaPath, root: fixture.root)
        var data = try Data(contentsOf: attached); data[data.count - 1] ^= 1; try data.write(to: attached)
        let stable = try state(client.send("state")), refused = directory.appendingPathComponent("changed-covered.wav")
        let failure = try render(client, event, .nativeTrackSavedProjectClock, refused)
        #expect(failure["ok"] as? Bool == false && !FileManager.default.fileExists(atPath: refused.path))
        #expect(!FileManager.default.fileExists(atPath: refused.appendingPathExtension("source-audition.json").path))
        #expect(try state(failure) == stable)
    }

    @Test func unavailableSavedSetupAndMissingMediaAreExplicitInspectionOutcomes() throws {
        let directory = try scratch(); defer { try? FileManager.default.removeItem(at: directory) }
        let fixture = try CPRAuditionModesControl.makePackage(in: directory,
            options: .init(savedRate: nil), attachMedia: false), client = Client()
        let event = try open(client, fixture), stable = try state(client.send("state"))
        let reply = try client.send("inspectSourceEvent", ["clipID": event.uuidString])
        let inspection = try #require(reply["sourceInspection"] as? [String: Any])
        let modes = try #require(inspection["modes"] as? [[String: Any]])
        #expect(reply["ok"] as? Bool == true && modes.count == 8)
        #expect(modes.allSatisfy { $0["available"] as? Bool == false && ($0["reason"] as? String)?.isEmpty == false })
        #expect(try state(reply) == stable)
        let attached = try client.send("attachSourceMedia", ["clipID": event.uuidString, "path": fixture.media[0].path])
        #expect(attached["ok"] as? Bool == true)
        let after = try client.send("inspectSourceEvent", ["clipID": event.uuidString])
        let afterModes = try #require((after["sourceInspection"] as? [String: Any])?["modes"] as? [[String: Any]])
        for mode in afterModes {
            let isSaved = ["nativeTimelineSavedProjectClock", "nativeTrackSavedProjectClock"].contains(mode["mode"] as? String ?? "")
            #expect(mode["available"] as? Bool == !isSaved)
        }
    }

    @Test func staleUnknownInvalidAndExistingDestinationsPreserveStateAndFiles() throws {
        let directory = try scratch(); defer { try? FileManager.default.removeItem(at: directory) }
        let fixture = try CPRAuditionModesControl.makePackage(in: directory), client = Client()
        let event = try open(client, fixture), stable = try state(client.send("state"))
        let output = directory.appendingPathComponent("protected.wav")
        let base: [String: Any] = ["clipID": event.uuidString, "path": output.path]
        for command in ["inspectSourceEvent", "renderSourceEvent"] {
            let stale = try client.send(command, base, revision: 0)
            #expect(error(stale) == "staleRevision")
            #expect(try state(stale) == stable)
        }
        for fields: [String: Any] in [["mode": "guessed"], ["mode": ""], ["startSeconds": -1], ["rewindAtEnd": "yes"]] {
            let refused = try client.send("renderSourceEvent", base.merging(fields) { _, new in new })
            #expect(refused["ok"] as? Bool == false)
            #expect(try state(refused) == stable)
            #expect(!FileManager.default.fileExists(atPath: output.path))
        }
        let sentinel = Data("owned by another writer".utf8), sidecar = output.appendingPathExtension("source-audition.json")
        try sentinel.write(to: sidecar)
        #expect(try client.send("renderSourceEvent", base)["ok"] as? Bool == false)
        #expect(try Data(contentsOf: sidecar) == sentinel && !FileManager.default.fileExists(atPath: output.path))
        try FileManager.default.removeItem(at: sidecar)
        try sentinel.write(to: output)
        #expect(try client.send("renderSourceEvent", base)["ok"] as? Bool == false)
        #expect(try Data(contentsOf: output) == sentinel && !FileManager.default.fileExists(atPath: sidecar.path))
        let inPackage = fixture.root.appendingPathComponent("unwanted.wav")
        #expect(try render(client, event, .sourceRate, inPackage)["ok"] as? Bool == false)
        #expect(!FileManager.default.fileExists(atPath: inPackage.path))
        #expect(try state(client.send("state")) == stable)
    }

    @Test func oversizedPlacedTimelineRefusesBeforeOutputPublication() throws {
        let directory = try scratch(); defer { try? FileManager.default.removeItem(at: directory) }
        let fixture = try CPRAuditionModesControl.makePackage(in: directory,
            options: .init(events: [.init(frames: 64, startTicks: 960_000)])), client = Client()
        let event = try open(client, fixture), output = directory.appendingPathComponent("oversized.wav")
        let prepared = try CPRSourceAudition.prepare(eventID: event, in: fixture.project, at: fixture.root, mode: .nativeTimelineProjectClock)
        #expect(prepared.frameCount > PortableSession.maximumSourceAuditionFrames)
        let reply = try render(client, event, .nativeTimelineProjectClock, output)
        #expect(error(reply) == "sourceFrameLimit")
        #expect(!FileManager.default.fileExists(atPath: output.path))
        #expect(!FileManager.default.fileExists(atPath: output.appendingPathExtension("source-audition.json").path))
        let inspect = try client.send("inspectSourceEvent", ["clipID": event.uuidString])
        let modes = try #require((inspect["sourceInspection"] as? [String: Any])?["modes"] as? [[String: Any]])
        let timeline = try #require(modes.first { $0["mode"] as? String == "nativeTimelineProjectClock" })
        #expect(timeline["available"] as? Bool == false && timeline["frames"] as? Int64 == prepared.frameCount)
    }

    @Test func freshEOFRendersStillRejectChangedSourceReportManifestAndMedia() throws {
        for changed in ["source", "report", "manifest", "media"] {
            let directory = try scratch(); defer { try? FileManager.default.removeItem(at: directory) }
            let fixture = try CPRAuditionModesControl.makePackage(in: directory), client = Client()
            let event = try open(client, fixture), stable = try state(client.send("state"))
            #expect(try client.send("inspectSourceEvent", ["clipID": event.uuidString])["ok"] as? Bool == true)
            let file: URL
            switch changed {
            case "source": file = fixture.root.appendingPathComponent(CPRProject.originalRelativePath)
            case "report": file = fixture.root.appendingPathComponent(CPRProject.reportRelativePath)
            case "manifest": file = fixture.root.appendingPathComponent(ProjectStore.manifestName)
            default:
                let retained = try #require(fixture.project.unresolvedAudioEvents.first)
                let attachment = try #require(fixture.project.attachedMedia(for: retained))
                file = try CPRAudioMediaValidation.attachedURL(attachment.mediaPath, root: fixture.root)
            }
            var data = try Data(contentsOf: file); data[data.count - 1] ^= 1; try data.write(to: file)
            let output = directory.appendingPathComponent("end.wav")
            let reply = try render(client, event, .nativeMode2ProjectRate, output, seconds: 1e100)
            #expect(reply["ok"] as? Bool == false)
            #expect(try state(reply) == stable)
            #expect(!FileManager.default.fileExists(atPath: output.path))
            #expect(!FileManager.default.fileExists(atPath: output.appendingPathExtension("source-audition.json").path))
        }
    }
}
