import Foundation
import Testing
@testable import RebasePortable

struct PortableAutomationSessionTests {
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
    private func fixture(_ project: Project) throws -> URL {
        let parent = ProcessInfo.processInfo.environment["REBASE_TEST_WORK_ROOT"].map { URL(fileURLWithPath: $0) }
            ?? FileManager.default.temporaryDirectory
        let root = parent.appendingPathComponent("automation-" + UUID().uuidString + ".rebaseproj")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        try ProjectStore.save(project, to: root)
        return root
    }
    private func original() -> Project {
        let commonID = UUID()
        return Project(name: "Authored automation control", tracks: [
            Track(name: "Edited", gainDB: -3, pan: 0.2, automation: [
                AutomationLane(parameter: .gainDB, isReadEnabled: false, points: [
                    AutomationPoint(id: commonID, time: 0, value: -18), AutomationPoint(time: 1, value: -6, interpolation: .step)
                ]),
                AutomationLane(parameter: .pan, points: [AutomationPoint(id: commonID, time: 0, value: -0.5)])
            ]),
            Track(name: "Unedited", automation: [AutomationLane(parameter: .gainDB, points: [AutomationPoint(id: commonID, time: 0, value: -9)])])
        ])
    }
    private func state(_ reply: [String: Any]) throws -> [String: Any] { try #require(reply["state"] as? [String: Any]) }
    private func stateBytes(_ reply: [String: Any]) throws -> Data { try JSONSerialization.data(withJSONObject: state(reply), options: [.sortedKeys]) }
    private func project(_ reply: [String: Any]) throws -> Project {
        try JSONDecoder().decode(Project.self, from: JSONSerialization.data(withJSONObject: #require(try state(reply)["project"])))
    }
    private func error(_ reply: [String: Any]) -> String? { (reply["error"] as? [String: Any])?["code"] as? String }
    private func fields(_ project: Project, parameter: String = "gainDB") -> [String: Any] {
        ["trackID": project.tracks[0].id.uuidString, "parameter": parameter]
    }
    private func merging(_ base: [String: Any], _ extra: [String: Any]) -> [String: Any] { base.merging(extra) { _, new in new } }

    @Test func automationIdentityAndTimestampCollisionsPreserveUneditedLanes() throws {
        let initial = original(), root = try fixture(initial)
        defer { try? FileManager.default.removeItem(at: root) }
        let client = Client(), base = fields(initial)
        _ = try client.send("open", ["path": root.path])
        let added = try client.send("upsertAutomationPoint", merging(base, ["time": 0.5, "value": -12, "interpolation": "step"]))
        let afterAdd = try project(added), addedPoint = afterAdd.tracks[0].automation[0].points[1]
        #expect(added["ok"] as? Bool == true && client.revision == 2)
        #expect(afterAdd.tracks[0].automation[0].id == initial.tracks[0].automation[0].id)
        #expect(!afterAdd.tracks[0].automation[0].isReadEnabled)
        #expect(afterAdd.tracks[0].automation[0].points.map(\.time) == [0, 0.5, 1])
        #expect(addedPoint.interpolation == .step && addedPoint.id != initial.tracks[0].automation[0].points[0].id)
        let collided = try client.send("upsertAutomationPoint", merging(base, ["pointID": addedPoint.id.uuidString, "time": 1, "value": -4]))
        let afterMove = try project(collided)
        #expect(afterMove.tracks[0].automation[0].points.map(\.time) == [0, 1])
        #expect(afterMove.tracks[0].automation[0].points[1] == AutomationPoint(id: addedPoint.id, time: 1, value: -4))
        let replaced = try client.send("upsertAutomationPoint", merging(base, ["time": 0, "value": -20]))
        let afterReplace = try project(replaced)
        #expect(afterReplace.tracks[0].automation[0].points[0].id != initial.tracks[0].automation[0].points[0].id)
        #expect(afterReplace.tracks[0].automation[1] == initial.tracks[0].automation[1])
        #expect(afterReplace.tracks[1] == initial.tracks[1])
        #expect(afterReplace.tracks[0].gainDB == initial.tracks[0].gainDB && afterReplace.tracks[0].pan == initial.tracks[0].pan)
        #expect(try state(added)["selection"] as? [String: String] == state(replaced)["selection"] as? [String: String])
    }

    @Test func invalidStaleAndNoopAutomationPreserveFullStateAndRedo() throws {
        let initial = original(), root = try fixture(initial)
        defer { try? FileManager.default.removeItem(at: root) }
        let client = Client(), base = fields(initial), point = initial.tracks[0].automation[0].points[0]
        _ = try client.send("open", ["path": root.path])
        let edited = try client.send("upsertAutomationPoint", merging(base, ["pointID": point.id.uuidString, "time": point.time, "value": -10]))
        let undone = try client.send("undo"), stable = try stateBytes(undone), revision = client.revision
        let cases: [(String, [String: Any], String)] = [
            ("upsertAutomationPoint", ["time": -1, "value": -10], "automationTime"),
            ("upsertAutomationPoint", ["time": 86400.01, "value": -10], "automationTime"),
            ("upsertAutomationPoint", ["value": -10], "automationTime"),
            ("upsertAutomationPoint", ["time": 1], "value"),
            ("upsertAutomationPoint", ["time": 1, "value": -96.1], "automationValue"),
            ("upsertAutomationPoint", ["time": 1, "value": 24.1], "automationValue"),
            ("upsertAutomationPoint", ["parameter": "pan", "time": 1, "value": -1.01], "automationValue"),
            ("upsertAutomationPoint", ["parameter": "pan", "time": 1, "value": 1.01], "automationValue"),
            ("upsertAutomationPoint", ["time": 1, "value": -10, "interpolation": "spline"], "automationInterpolation"),
            ("upsertAutomationPoint", ["time": 1, "value": -10, "pointID": UUID().uuidString], "selection"),
            ("upsertAutomationPoint", ["time": 1, "value": -10, "pointID": "malformed"], "operationFailed"),
            ("removeAutomationPoint", [:], "selection"),
            ("removeAutomationPoint", ["pointID": UUID().uuidString], "selection"),
            ("setAutomationRead", [:], "automationRead"),
            ("setAutomationRead", ["enabled": "true"], "operationFailed"),
            ("setAutomationRead", ["parameter": "volume", "enabled": true], "automationParameter"),
            ("removeAutomationPoint", ["parameter": "", "pointID": point.id.uuidString], "automationParameter"),
            ("setAutomationRead", ["trackID": UUID().uuidString, "enabled": true], "selection")
        ]
        for (command, extra, code) in cases {
            let reply = try client.send(command, merging(base, extra))
            #expect(error(reply) == code)
            #expect(try stateBytes(reply) == stable)
        }
        let missingParameter = try client.send("setAutomationRead", ["trackID": initial.tracks[0].id.uuidString, "enabled": true])
        #expect(error(missingParameter) == "automationParameter")
        #expect(try stateBytes(missingParameter) == stable)
        for command in ["upsertAutomationPoint", "removeAutomationPoint", "setAutomationRead"] {
            let stale = try client.send(command, merging(base, ["pointID": point.id.uuidString, "time": point.time, "value": point.value, "enabled": false]), revision: revision - 1)
            #expect(error(stale) == "staleRevision")
            #expect(try stateBytes(stale) == stable)
        }
        let same = try client.send("upsertAutomationPoint", merging(base, ["pointID": point.id.uuidString, "time": point.time, "value": point.value]))
        let read = try client.send("setAutomationRead", merging(base, ["enabled": false]))
        #expect(same["ok"] as? Bool == true && read["ok"] as? Bool == true)
        #expect(try stateBytes(same) == stable && stateBytes(read) == stable)
        // JSON's overflowing exponent must fail decoding, never publish NaN/Inf.
        client.id += 1
        let raw = Data("{\"protocol\":1,\"id\":\(client.id),\"command\":\"upsertAutomationPoint\",\"expectedRevision\":\(revision),\"trackID\":\"\(initial.tracks[0].id)\",\"parameter\":\"gainDB\",\"time\":1e999,\"value\":0}".utf8)
        let overflow = try #require(JSONSerialization.jsonObject(with: client.session.process(raw)) as? [String: Any])
        #expect(overflow["ok"] as? Bool == false)
        #expect(try stateBytes(overflow) == stable)
        #expect(try project(client.send("redo")) == project(edited))
    }

    @Test func automationHistorySaveAndReopenRetainExactGainPanAndPointIdentities() throws {
        let initial = original(), root = try fixture(initial)
        defer { try? FileManager.default.removeItem(at: root) }
        let client = Client(), gain = fields(initial), pan = fields(initial, parameter: "pan")
        _ = try client.send("open", ["path": root.path])
        let gained = try client.send("upsertAutomationPoint", merging(gain, ["pointID": initial.tracks[0].automation[0].points[0].id.uuidString, "time": 0.25, "value": -24, "interpolation": "step"]))
        let panned = try client.send("upsertAutomationPoint", merging(pan, ["time": 0.75, "value": 0.75]))
        let removed = try client.send("removeAutomationPoint", merging(gain, ["pointID": initial.tracks[0].automation[0].points[1].id.uuidString]))
        let read = try client.send("setAutomationRead", merging(pan, ["enabled": false]))
        let expected = try project(read)
        for prior in [removed, panned, gained] { #expect(try project(client.send("undo")) == project(prior)) }
        #expect(try project(client.send("undo")) == initial)
        #expect(try state(client.send("state"))["dirty"] as? Bool == false)
        for next in [gained, panned, removed, read] { #expect(try project(client.send("redo")) == project(next)) }
        let saved = try client.send("save")
        #expect(saved["ok"] as? Bool == true)
        #expect(try state(saved)["dirty"] as? Bool == false)
        #expect(try ProjectStore.load(from: root) == expected)
        let reopened = try Client().send("open", ["path": root.path])
        #expect(try project(reopened) == expected)
        #expect(try state(reopened)["canUndo"] as? Bool == false)
        #expect(expected.tracks[0].automation[0].id == initial.tracks[0].automation[0].id)
        #expect(expected.tracks[0].automation[1].id == initial.tracks[0].automation[1].id)
        #expect(expected.tracks[1] == initial.tracks[1])
    }

    @Test func newAndEmptyLanesKeepReadStateAndLaneIdentity() throws {
        let initial = Project(tracks: [Track(name: "Empty")]), root = try fixture(initial)
        defer { try? FileManager.default.removeItem(at: root) }
        let client = Client(), gain = fields(initial), pan = fields(initial, parameter: "pan")
        _ = try client.send("open", ["path": root.path])
        let absent = try client.send("removeAutomationPoint", merging(gain, ["pointID": UUID().uuidString]))
        #expect(error(absent) == "selection" && client.revision == 1)
        let inserted = try client.send("upsertAutomationPoint", merging(gain, ["time": 86400, "value": 24]))
        let lane = try project(inserted).tracks[0].automation[0]
        #expect(lane.isReadEnabled && lane.points[0].interpolation == .linear)
        let empty = try client.send("removeAutomationPoint", merging(gain, ["pointID": lane.points[0].id.uuidString]))
        #expect(try project(empty).tracks[0].automation == [AutomationLane(id: lane.id, parameter: .gainDB)])
        let read = try client.send("setAutomationRead", merging(pan, ["enabled": false]))
        let panLane = try project(read).tracks[0].automation[1]
        #expect(!panLane.isReadEnabled && panLane.points.isEmpty)
        let panned = try client.send("upsertAutomationPoint", merging(pan, ["time": 0, "value": -1, "interpolation": "step"]))
        #expect(try project(panned).tracks[0].automation[1].id == panLane.id)
        #expect(try project(panned).tracks[0].automation[1].isReadEnabled == false)
        #expect(try project(panned).tracks[0].automation[0].id == lane.id)
    }

    @Test func automationGrowthBoundPreservesLargerExistingLanesAndAllowsReduction() throws {
        let limit = PortableSession.maximumEditableAutomationPoints
        for count in [limit, limit + 1] {
            let points = (0..<count).map { AutomationPoint(time: Double($0), value: -12) }
            let initial = Project(tracks: [Track(name: "Bounded growth", automation: [AutomationLane(parameter: .gainDB, points: points)])])
            let root = try fixture(initial)
            defer { try? FileManager.default.removeItem(at: root) }
            let client = Client(), base = fields(initial)
            let opened = try client.send("open", ["path": root.path]), stable = try stateBytes(opened)
            #expect(try project(opened) == initial)
            let growth = try client.send("upsertAutomationPoint", merging(base, ["time": Double(count), "value": -6]))
            #expect(error(growth) == "automationLimit")
            #expect(try stateBytes(growth) == stable)
            let updated = try client.send("upsertAutomationPoint", merging(base, ["pointID": points[0].id.uuidString, "time": 0, "value": -24]))
            #expect(updated["ok"] as? Bool == true)
            #expect(try project(updated).tracks[0].automation[0].points.count == count)
            let replaced = try client.send("upsertAutomationPoint", merging(base, ["time": 0, "value": -18]))
            #expect(replaced["ok"] as? Bool == true)
            #expect(try project(replaced).tracks[0].automation[0].points.count == count)
            let read = try client.send("setAutomationRead", merging(base, ["enabled": false]))
            #expect(read["ok"] as? Bool == true)
            let removed = try client.send("removeAutomationPoint", merging(base, ["pointID": points[1].id.uuidString]))
            #expect(removed["ok"] as? Bool == true)
            #expect(try project(removed).tracks[0].automation[0].points.count == count - 1)
        }
        // The boundary itself is inclusive.
        let points = (0..<(limit - 1)).map { AutomationPoint(time: Double($0), value: -12) }
        let initial = Project(tracks: [Track(name: "At limit", automation: [AutomationLane(parameter: .gainDB, points: points)])])
        let root = try fixture(initial)
        defer { try? FileManager.default.removeItem(at: root) }
        let client = Client(); _ = try client.send("open", ["path": root.path])
        let atLimit = try client.send("upsertAutomationPoint", merging(fields(initial), ["time": Double(limit), "value": -12]))
        #expect(atLimit["ok"] as? Bool == true)
        #expect(try project(atLimit).tracks[0].automation[0].points.count == limit)
    }
}
