import Foundation
import Darwin
import Testing
@testable import RebaseCore

/// Pinned source bytes and deliberate mutations test a bounded saved-coordinate
/// interpretation. No test executes Reference or asserts playable audio fidelity.
struct CPRRecoveryV4Tests {
    private let workspace = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    private func sourceURL(_ name: String) -> URL {
        workspace.appendingPathComponent("research/targets/full-reference/expanded/Reference 15.app.pkg/Payload/Reference 15.app/Contents/Project Templates/Reference Pro/" + name + ".cpr")
    }
    private func source(_ name: String = "LoFi Hip Hop") throws -> Data {
        let bytes = try Data(contentsOf: sourceURL(name))
        let pins = ["LoFi Hip Hop": "2795af70cbc6651fbd6aa4cfbcb546d606d25d5970722a6c553384f3d196e495",
                    "Classic House": "28db9a9e6aca3357e0758c4b985c4bbdfb4e1d9268502d53238f0ceb2733e892"]
        #expect(cprSHA256(bytes) == pins[name])
        return bytes
    }
    private func recover(_ bytes: Data) throws -> (recovery: CPRRecoveryResult, clock: NativeTempoClock?) {
        try CPRRecoveryV4(container: CPRProject.readContainer(bytes)).decode(sourceName: "Control.cpr")
    }
    private func archiveEvent(_ bytes: Data) throws -> CPRSourceAudioEvent {
        let events = try CPRAudioEventArchive.read(container: CPRProject.readContainer(bytes))
        #expect(events.count == 1)
        return try #require(events.first)
    }
    private func event(_ bytes: Data) throws -> UnresolvedCPRAudioEvent {
        let project = try #require(recover(bytes).recovery.project)
        #expect(project.unresolvedAudioEvents.count == 1)
        #expect(project.tracks.flatMap(\.clips).isEmpty)
        return try #require(project.unresolvedAudioEvents.first)
    }
    private func overwrite<T: FixedWidthInteger>(_ value: T, at offset: Int, in bytes: inout Data) {
        var big = value.bigEndian
        bytes.replaceSubrange(offset..<(offset + MemoryLayout<T>.size), with: withUnsafeBytes(of: &big) { Data($0) })
    }
    private func temporaryDirectory() throws -> URL {
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("CPRAudioV4-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }
    private func changedEvent(_ project: Project, _ change: (inout [String: Any]) throws -> Void) throws -> Project {
        var json = try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(project)) as? [String: Any])
        var tracks = try #require(json["tracks"] as? [[String: Any]])
        let index = try #require(tracks.firstIndex { ($0["unresolvedAudioEvents"] as? [Any])?.isEmpty == false })
        var events = try #require(tracks[index]["unresolvedAudioEvents"] as? [[String: Any]])
        try change(&events[0])
        tracks[index]["unresolvedAudioEvents"] = events
        json["tracks"] = tracks
        return try JSONDecoder().decode(Project.self, from: JSONSerialization.data(withJSONObject: json))
    }
    private func requireUnresolvedError(_ operation: () throws -> Void) {
        do { try operation(); Issue.record("Unresolved CPR audio unexpectedly passed the playback/export gate.") }
        catch RebaseCoreError.invalidProject(let message) {
            #expect(message.contains("unresolved Reference audio events"))
        } catch { Issue.record("Unexpected error instead of the explicit unresolved-audio gate: \(error)") }
    }

    @Test func pinnedLoFiHasExactTwentyFourSecondSourceExtentAndClassicStaysUnplaced() throws {
        for name in ["LoFi Hip Hop", "Classic House"] {
            let bytes = try source(name), result = try recover(bytes)
            let project = try #require(result.recovery.project)
            let decoded = try archiveEvent(bytes), unresolved = try event(bytes)
            #expect(unresolved.sourceSHA256 == cprSHA256(bytes))
            #expect(unresolved.event == decoded.event && unresolved.clip == decoded.clip)
            #expect(unresolved.cluster == decoded.cluster.object)
            #expect(unresolved.rawStartBits == 0 && unresolved.rawOffsetBits == 0)
            #expect(unresolved.files.count == 1 && unresolved.segments.count == 1)
            #expect(unresolved.files[0].directory.hasPrefix("vstsound://"))
            #expect(unresolved.segments[0].streamIdentity == unresolved.files[0].object.identityOffset)
            #expect(unresolved.segments[0].storedLength == unresolved.files[0].frameCount)
            #expect(project.duration == 0 && project.tracks.flatMap(\.clips).isEmpty)
            #expect(result.recovery.unsupported.contains { $0.category == "Unresolved audio playback" && $0.objectCount == 1 })
            #expect(try recover(bytes).recovery.project == project)
            if name == "LoFi Hip Hop" {
                let placement = try #require(unresolved.placement)
                #expect(placement.contract == CPRAudioSourcePlacement.contractName)
                #expect(placement.position.bitPattern == 0 && placement.offset.bitPattern == 0)
                #expect(placement.duration.bitPattern == 0x4038000000000000)
                #expect(unresolved.datumTag == 10 && unresolved.datumScalarBits == 0x3ef7c6f8c751f177)
                #expect(unresolved.rawLengthBits == Double(1_058_400).bitPattern)
                #expect(project.arrangementDuration == 24)
            } else {
                #expect(unresolved.datumTag == 0 && unresolved.datumScalarBits == nil)
                #expect(unresolved.placement == nil && project.arrangementDuration == 0)
                #expect(unresolved.placementStatus.contains("musical or unsupported duration datum"))
            }
            #expect(try Data(contentsOf: sourceURL(name)) == bytes)
        }
    }

    @Test func frozenV3HasNoNewEventsOrChangedSerialization() throws {
        for name in ["LoFi Hip Hop", "Classic House"] {
            let bytes = try source(name), container = try CPRProject.readContainer(bytes)
            let old = try CPRRecoveryV3(container: container).decode(sourceName: name + ".cpr")
            let project = try #require(old.recovery.project)
            #expect(project.unresolvedAudioEvents.isEmpty && project.tracks.flatMap(\.clips).isEmpty)
            let encoded = try JSONEncoder().encode(project)
            #expect(!String(decoding: encoded, as: UTF8.self).contains("unresolvedAudioEvents"))
            let current = try CPRRecoveryV4(container: container).decode(sourceName: name + ".cpr")
            #expect(current.clock == old.clock)
            var stripped = try #require(current.recovery.project)
            for index in stripped.tracks.indices { stripped.tracks[index].unresolvedAudioEvents = [] }
            #expect(stripped == project)
        }
    }

    @Test func everyAncestorAndEventRequiresPositiveZeroOffsetsAndZeroPrefixWord() throws {
        let original = try source(), decoded = try archiveEvent(original)
        #expect(decoded.ancestorTracks.count == 1)
        let objects = [decoded.root] + decoded.ancestorTracks + [decoded.event]
        for object in objects {
            for relativeOffset in [2, 18] {
                for bits in [Double(1).bitPattern, UInt64(0x8000000000000000)] {
                    var bytes = original
                    overwrite(bits, at: object.payloadOffset + relativeOffset, in: &bytes)
                    let unresolved = try event(bytes)
                    #expect(unresolved.placement == nil)
                    #expect(unresolved.placementStatus.contains("ancestor/event offsets"))
                    if object == decoded.event {
                        #expect(relativeOffset == 2 ? unresolved.rawStartBits == bits : unresolved.rawOffsetBits == bits)
                    }
                }
            }
            var bytes = original
            overwrite(UInt16(1), at: object.payloadOffset, in: &bytes)
            #expect(try event(bytes).placement == nil)
        }
        // The finite ancestor length is not silently used as event duration.
        for object in [decoded.root] + decoded.ancestorTracks {
            var bytes = original
            overwrite(Double(123.25).bitPattern, at: object.payloadOffset + 10, in: &bytes)
            #expect(try event(bytes).placement?.duration == 24)
        }
    }

    @Test func minimumLengthReciprocalAndRateAreRealPlacementGates() throws {
        let original = try source(), decoded = try archiveEvent(original)
        var clipPrefix = CPRCursor(data: original, lower: decoded.clip.payloadOffset,
                                   upper: decoded.clip.payloadOffset + decoded.clip.payloadByteCount)
        _ = try clipPrefix.nativeString()
        let datumOffset = clipPrefix.position
        #expect(try clipPrefix.i32() == 10)
        #expect(try clipPrefix.u64() == 0x3ef7c6f8c751f177)
        for length in [0.0, 0.5, -1.0, 44_100.0 * 86_401.0] {
            var bytes = original
            overwrite(length.bitPattern, at: decoded.event.payloadOffset + 10, in: &bytes)
            #expect(try event(bytes).placement == nil)
        }
        var one = original
        overwrite(Double(1).bitPattern, at: decoded.event.payloadOffset + 10, in: &one)
        #expect(try event(one).placement?.duration.bitPattern == 0x3ef7c6f8c751f177)
        for scalar in [Double(bitPattern: 0x3ef7c6f8c751f177).nextUp, -1.0, 0.0] {
            var bytes = original
            overwrite(scalar.bitPattern, at: datumOffset + 4, in: &bytes)
            #expect(try event(bytes).placement == nil)
        }
        var otherTag = original
        overwrite(UInt32(1), at: datumOffset, in: &otherTag)
        #expect(try event(otherTag).placement == nil)
        var otherRate = original
        let file = try #require(decoded.cluster.files.first)
        overwrite(Float(48_000).bitPattern, at: file.object.payloadOffset + 14, in: &otherRate)
        #expect(try event(otherRate).placement == nil)
        // A paired, explicitly saved source rate and scalar can be projected;
        // this remains metadata reconstruction, not a backend-rate observation.
        overwrite((1.0 / 48_000).bitPattern, at: datumOffset + 4, in: &otherRate)
        #expect(try event(otherRate).placement?.duration == (1.0 / 48_000) * 1_058_400)
    }

    @Test func invalidNativeClockAndWrongTrackDatumKeepSourceEventsUnplaced() throws {
        let original = try source(), container = try CPRProject.readContainer(original)
        let roles = try CPRClockRoles.resolve(container: container)
        let tempo = try #require(roles.tempo)
        var badClock = original
        // Source second anchor is exactly 600; nextUp is noncanonical even
        // though the period/tick records still form an otherwise valid map.
        overwrite(Double(600).nextUp.bitPattern, at: tempo.descriptor.payloadOffset + 4 + 22 + 4, in: &badClock)
        let result = try recover(badClock)
        #expect(result.clock == nil && result.recovery.project?.tempoMap.nativeClock == nil)
        #expect(try event(badClock).placement == nil)
        #expect(result.recovery.unsupported.contains { $0.category == "Native jump-tempo map" })
        let decoded = try archiveEvent(original)
        var cursor = CPRCursor(data: original, lower: decoded.containingNode.payloadOffset,
                               upper: decoded.containingNode.payloadOffset + decoded.containingNode.payloadByteCount)
        _ = try cursor.nativeString()
        var alternateTag = original
        overwrite(UInt32(17), at: cursor.position, in: &alternateTag)
        // Both interface roles still resolve, but tag17 is not the accepted
        // containing-track coordinate contract for this profile.
        #expect(try recover(alternateTag).clock != nil)
        #expect(try event(alternateTag).placement == nil)
    }

    @Test func nonNearestFloatingPointModesCannotPublishSourceProjection() throws {
        let bytes = try source(), saved = fegetround()
        defer { _ = fesetround(saved) }
        for mode in [FE_UPWARD, FE_DOWNWARD, FE_TOWARDZERO] {
            #expect(fesetround(mode) == 0)
            #expect(throws: NativeTempoClockError.self) { try recover(bytes) }
            #expect(fegetround() == mode)
        }
        #expect(fesetround(FE_TONEAREST) == 0)
        #expect(try event(bytes).placement?.duration.bitPattern == 0x4038000000000000)
    }

    @Test func packageRoundTripPreservesOriginalReportAndExactUnresolvedEvents() throws {
        let root = try temporaryDirectory(); defer { try? FileManager.default.removeItem(at: root) }
        for name in ["LoFi Hip Hop", "Classic House"] {
            let bytes = try source(name), package = root.appendingPathComponent(name + ".rebaseproj")
            let imported = try CPRProject.importProject(from: sourceURL(name), to: package,
                                                        allowPartial: true, expectedSHA256: cprSHA256(bytes))
            #expect(imported.report.interpretationProfile == CPRProject.currentInterpretationProfile)
            #expect(imported.project.unresolvedAudioEvents.count == 1)
            let originalURL = package.appendingPathComponent(CPRProject.originalRelativePath)
            let reportURL = package.appendingPathComponent(CPRProject.reportRelativePath)
            let reportBytes = try Data(contentsOf: reportURL)
            try ProjectStore.save(imported.project, to: package)
            #expect(try ProjectStore.load(from: package) == imported.project)
            #expect(try CPRProject.compatibilityReport(from: package) == imported.report)
            let copied = root.appendingPathComponent(name + " Copy.rebaseproj")
            try FileManager.default.copyItem(at: package, to: copied)
            #expect(try ProjectStore.load(from: copied) == imported.project)
            #expect(try Data(contentsOf: originalURL) == bytes)
            #expect(try Data(contentsOf: reportURL) == reportBytes)
        }
    }

    @Test func alteredRawProjectionMediaAndTrackIdentityFailSourceProofBeforeSave() throws {
        let root = try temporaryDirectory(); defer { try? FileManager.default.removeItem(at: root) }
        let package = root.appendingPathComponent("Source.rebaseproj")
        let imported = try CPRProject.importProject(from: sourceURL("LoFi Hip Hop"), to: package, allowPartial: true)
        let manifest = package.appendingPathComponent("Project.json"), originalManifest = try Data(contentsOf: manifest)
        let reportURL = package.appendingPathComponent(CPRProject.reportRelativePath)
        let reportBytes = try Data(contentsOf: reportURL)
        let originalURL = package.appendingPathComponent(CPRProject.originalRelativePath)
        let originalBytes = try Data(contentsOf: originalURL)
        var mutations: [Project] = []
        mutations.append(try changedEvent(imported.project) { $0["rawLengthBits"] = Double(1_058_401).bitPattern })
        mutations.append(try changedEvent(imported.project) {
            var placement = try #require($0["placement"] as? [String: Any]); placement["duration"] = 25.0; $0["placement"] = placement
        })
        mutations.append(try changedEvent(imported.project) { $0["sourceSHA256"] = String(repeating: "a", count: 64) })
        mutations.append(try changedEvent(imported.project) {
            var files = try #require($0["files"] as? [[String: Any]])
            files[0]["filename"] = "Substituted.wav"; $0["files"] = files
        })
        mutations.append(try changedEvent(imported.project) {
            var object = try #require($0["event"] as? [String: Any])
            object["payloadSHA256"] = String(repeating: "b", count: 64); $0["event"] = object
        })
        var moved = imported.project
        let index = try #require(moved.tracks.firstIndex { !$0.unresolvedAudioEvents.isEmpty })
        let events = moved.tracks[index].unresolvedAudioEvents
        moved.tracks[index].unresolvedAudioEvents = []
        moved.tracks.append(Track(name: "Unrelated track", unresolvedAudioEvents: events))
        mutations.append(moved)
        for changed in mutations {
            try changed.validate() // The persistence check, not syntax, must reject these.
            #expect(throws: RebaseCoreError.self) { try ProjectStore.save(changed, to: package) }
            #expect(try Data(contentsOf: manifest) == originalManifest)
            try JSONEncoder().encode(changed).write(to: manifest, options: .atomic)
            #expect(throws: RebaseCoreError.self) { try ProjectStore.load(from: package) }
            try originalManifest.write(to: manifest, options: .atomic)
        }
        #expect(try ProjectStore.load(from: package) == imported.project)
        #expect(try Data(contentsOf: reportURL) == reportBytes)
        #expect(try Data(contentsOf: originalURL) == originalBytes)
        var standalone = imported.project
        try standalone.convertToApplicationTiming()
        let missingProof = root.appendingPathComponent("MissingProof.rebaseproj")
        #expect(throws: RebaseCoreError.self) { try ProjectStore.save(standalone, to: missingProof) }
        #expect(!FileManager.default.fileExists(atPath: missingProof.path))
    }

    @Test func unresolvedAudioBlocksRenderingAndExchangeUntilExplicitRemoval() throws {
        let root = try temporaryDirectory(); defer { try? FileManager.default.removeItem(at: root) }
        let package = root.appendingPathComponent("Source.rebaseproj")
        let imported = try CPRProject.importProject(from: sourceURL("LoFi Hip Hop"), to: package, allowPartial: true)
        var project = imported.project
        let reportURL = package.appendingPathComponent(CPRProject.reportRelativePath)
        let reportBytes = try Data(contentsOf: reportURL)
        let originalURL = package.appendingPathComponent(CPRProject.originalRelativePath)
        let sourceBytes = try Data(contentsOf: originalURL)
        try project.convertToApplicationTiming() // Isolate the audio gate from native timing export policy.
        try ProjectStore.save(project, to: package)
        #expect(try ProjectStore.load(from: package) == project)
        let wav = root.appendingPathComponent("Existing.wav"), sentinel = Data("existing destination".utf8)
        try sentinel.write(to: wav)
        let exchange = root.appendingPathComponent("Blocked.dawproject")
        requireUnresolvedError { _ = try OfflineRenderer.render(project: project, projectRoot: package) }
        requireUnresolvedError { _ = try OfflineRenderer.export(project: project, projectRoot: package, to: wav) }
        requireUnresolvedError { try DAWProject.export(project: project, projectRoot: package, to: exchange) }
        #expect(try Data(contentsOf: wav) == sentinel)
        #expect(!FileManager.default.fileExists(atPath: exchange.path))
        for index in project.tracks.indices { project.tracks[index].unresolvedAudioEvents = [] }
        try ProjectStore.save(project, to: package)
        #expect(try ProjectStore.load(from: package).unresolvedAudioEvents.isEmpty)
        try DAWProject.export(project: project, projectRoot: package, to: exchange)
        #expect(FileManager.default.fileExists(atPath: exchange.path))
        #expect(try Data(contentsOf: reportURL) == reportBytes)
        #expect(try Data(contentsOf: originalURL) == sourceBytes)
        #expect(try CPRProject.compatibilityReport(from: package)?.recoveredProject?.unresolvedAudioEvents.count == 1)
    }
}
