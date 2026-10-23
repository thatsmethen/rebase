import Foundation
import Testing
@testable import RebasePortable

struct PortableRulerTests {
    private func workspace(_ body: (URL) throws -> Void) throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("PortableRuler-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false)
        defer { try? FileManager.default.removeItem(at: root) }
        try body(root)
    }
    private func request(_ session: PortableSession, id: Int, command: String, revision: Int = 1,
                         fields: [String: Any] = [:]) throws -> [String: Any] {
        var value: [String: Any] = ["protocol": 1, "id": id, "command": command, "expectedRevision": revision]
        value.merge(fields) { _, new in new }
        return try #require(JSONSerialization.jsonObject(with: session.process(JSONSerialization.data(withJSONObject: value))) as? [String: Any])
    }
    private func state(_ reply: [String: Any]) throws -> Data {
        try JSONSerialization.data(withJSONObject: #require(reply["state"]), options: .sortedKeys)
    }

    @Test func rulerIsReadOnlyAndReflectsTempoEditsUndoAndMeterChanges() throws {
        try workspace { directory in
            let root = directory.appendingPathComponent("Control.rebaseproj")
            try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false)
            let original = Project(tempoMap: TempoMap(events: [TempoEvent(beat: 0, bpm: 96)]),
                signatureMap: SignatureMap(events: [SignatureEvent(beat: 0, numerator: 4, denominator: 4),
                    SignatureEvent(beat: 8, numerator: 3, denominator: 4)]))
            try ProjectStore.save(original, to: root)
            let manifest = try Data(contentsOf: root.appendingPathComponent(ProjectStore.manifestName))
            let session = PortableSession()
            let opened = try request(session, id: 1, command: "open", revision: 0, fields: ["path": root.path])
            let reply = try request(session, id: 2, command: "ruler", fields: ["value": 100, "duration": 7.5])
            #expect(reply["ok"] as? Bool == true)
            #expect(try state(reply) == state(opened))
            let ruler = try #require(reply["ruler"] as? [String: Any])
            #expect(ruler["revision"] as? Int == 1 && ruler["duration"] as? Double == 7.5 && ruler["pixelsPerSecond"] as? Double == 100)
            let ticks = try JSONDecoder().decode([MusicalRulerTick].self, from: JSONSerialization.data(withJSONObject: #require(ruler["ticks"])))
            #expect(ticks.filter(\.bar).map(\.seconds) == [0, 2.5, 5, 6.875])
            #expect(ticks.filter(\.bar).map(\.label) == ["1", "2", "3", "4"])
            let edited = try request(session, id: 3, command: "setTempo", fields: ["value": 120])
            let stale = try request(session, id: 4, command: "ruler", fields: ["value": 100, "duration": 7.5])
            #expect(stale["ok"] as? Bool == false && stale["ruler"] == nil)
            #expect((stale["error"] as? [String: Any])?["code"] as? String == "staleRevision")
            #expect(try state(stale) == state(edited))
            let refreshed = try request(session, id: 5, command: "ruler", revision: 2, fields: ["value": 100])
            #expect(try state(refreshed) == state(edited))
            #expect((refreshed["ruler"] as? [String: Any])?["duration"] as? Double == 30)
            let undone = try request(session, id: 6, command: "undo", revision: 2)
            let restored = try request(session, id: 7, command: "ruler", revision: 3, fields: ["value": 100, "duration": 7.5])
            #expect(try state(restored) == state(undone))
            let restoredTicks = try #require((restored["ruler"] as? [String: Any])?["ticks"])
            #expect(try JSONSerialization.data(withJSONObject: restoredTicks, options: .sortedKeys) == JSONSerialization.data(withJSONObject: #require(ruler["ticks"]), options: .sortedKeys))
            #expect(try Data(contentsOf: root.appendingPathComponent(ProjectStore.manifestName)) == manifest)
        }
    }

    @Test func invalidRequestsAndExternalManifestChangesNeverMutateStateOrReturnTicks() throws {
        try workspace { directory in
            let session = PortableSession()
            let missing = try request(session, id: 1, command: "ruler", revision: 0, fields: ["value": 100])
            #expect((missing["error"] as? [String: Any])?["code"] as? String == "noProject")
            let root = directory.appendingPathComponent("Control.rebaseproj")
            try FileManager.default.createDirectory(at: root, withIntermediateDirectories: false)
            var project = Project()
            try ProjectStore.save(project, to: root)
            let opened = try request(session, id: 2, command: "open", revision: 0, fields: ["path": root.path])
            let invalid: [[String: Any]] = [[:], ["value": 0], ["value": 421], ["value": "NaN"],
                ["value": 100, "duration": -1], ["value": 100, "duration": 86_401], ["value": 100, "duration": "Infinity"]]
            for (index, fields) in invalid.enumerated() {
                let reply = try request(session, id: index + 3, command: "ruler", fields: fields)
                #expect(reply["ok"] as? Bool == false && reply["ruler"] == nil)
                #expect(try state(reply) == state(opened))
            }
            let zero = try request(session, id: 10, command: "ruler", fields: ["value": 4, "duration": 0])
            #expect(((zero["ruler"] as? [String: Any])?["ticks"] as? [Any])?.count == 1)
            #expect(try state(zero) == state(opened))
            let bounded = try request(session, id: 11, command: "ruler", fields: ["value": 420, "duration": 86_400])
            #expect(((bounded["ruler"] as? [String: Any])?["ticks"] as? [Any])?.count == 8_192)
            #expect(try state(bounded) == state(opened))
            project.name = "External change"; try ProjectStore.save(project, to: root)
            let changed = try request(session, id: 12, command: "ruler", fields: ["value": 100])
            #expect((changed["error"] as? [String: Any])?["code"] as? String == "externalChange")
            #expect(changed["ruler"] == nil)
            #expect(try state(changed) == state(opened))
        }
    }

    @Test func retainedNativeClockRulerDoesNotConvertOrResolveTheProject() throws {
        try workspace { directory in
            let control = try CPRAudioControl.makePackage(in: directory)
            #expect(control.project.tempoMap.nativeClock != nil)
            let session = PortableSession()
            let opened = try request(session, id: 1, command: "open", revision: 0, fields: ["path": control.root.path])
            let reply = try request(session, id: 2, command: "ruler", fields: ["value": 100, "duration": 4])
            #expect(reply["ok"] as? Bool == true)
            #expect(try state(reply) == state(opened))
            let payload = try #require((reply["ruler"] as? [String: Any])?["ticks"])
            let ticks = try JSONDecoder().decode([MusicalRulerTick].self, from: JSONSerialization.data(withJSONObject: payload))
            #expect(ticks == (try MusicalRuler.ticks(project: control.project, duration: 4, pixelsPerSecond: 100)))
            #expect(try ProjectStore.load(from: control.root) == control.project)
            #expect(control.project.unresolvedAudioEvents.count == 1 && control.project.cprMediaAttachments.isEmpty)
        }
    }
}
