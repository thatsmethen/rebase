import Testing
import Foundation
import RebaseCore

/// Analytic Rebase curve tests, not measurements of Reference automation behavior.
struct AutomationTests {
    @Test func mixedOutgoingSegmentsAndExactBoundaries() throws {
        let lane = AutomationLane(parameter: .pan, points: [
            AutomationPoint(time: 1, value: -1, interpolation: .step),
            AutomationPoint(time: 2, value: 0),
            AutomationPoint(time: 4, value: 1)
        ])
        try lane.validate()
        #expect(lane.value(at: 0, fallback: 0.2) == -1)
        #expect(lane.value(at: 1.999, fallback: 0.2) == -1)
        #expect(lane.value(at: 2, fallback: 0.2) == 0)
        #expect(lane.value(at: 3, fallback: 0.2) == 0.5)
        #expect(lane.value(at: 4, fallback: 0.2) == 1)
        #expect(lane.value(at: 100, fallback: 0.2) == 1)
    }

    @Test func gainInterpolatesInDecibelsAndReadGateUsesManualValue() throws {
        var lane = AutomationLane(parameter: .gainDB, points: [
            AutomationPoint(time: 0, value: -12), AutomationPoint(time: 2, value: 0)
        ])
        try lane.validate()
        #expect(lane.value(at: 1, fallback: -20) == -6)
        lane.isReadEnabled = false
        #expect(lane.value(at: 1, fallback: -20) == -20)
        lane.isReadEnabled = true
        for time in [-1, Double.nan, .infinity] {
            #expect(lane.value(at: time, fallback: -20) == -20)
        }
        lane.points = []
        #expect(lane.value(at: 1, fallback: -20) == -20)
    }

    @Test func pointEditingAndCodablePreserveIdentityAndSegments() throws {
        let first = AutomationPoint(time: 1, value: -1, interpolation: .step)
        var lane = AutomationLane(parameter: .pan, points: [first])
        let end = AutomationPoint(time: 3, value: 1)
        try lane.upsert(end)
        try lane.upsert(AutomationPoint(id: end.id, time: 2, value: 0.5))
        #expect(lane.points.map(\.time) == [1, 2])
        let replacement = AutomationPoint(time: 1, value: -0.5)
        try lane.upsert(replacement)
        #expect(lane.points[0] == replacement)
        #expect(lane.points.count == 2)
        let decoded = try JSONDecoder().decode(AutomationLane.self, from: JSONEncoder().encode(lane))
        #expect(decoded == lane)
        lane.removePoint(id: replacement.id)
        #expect(lane.value(at: 0, fallback: 0) == 0.5)
    }

    @Test func malformedPointsRejectWithoutChangingLane() throws {
        let start = AutomationPoint(time: 0, value: 0)
        var lane = AutomationLane(parameter: .pan, points: [start])
        let before = lane
        for point in [AutomationPoint(time: .nan, value: 0),
                      AutomationPoint(time: .infinity, value: 0),
                      AutomationPoint(time: -1, value: 0),
                      AutomationPoint(time: 86_401, value: 0),
                      AutomationPoint(time: 1, value: .infinity),
                      AutomationPoint(time: 1, value: 1.01)] {
            #expect(throws: RebaseCoreError.self) { try lane.upsert(point) }
            #expect(lane == before)
        }
        for points in [[start, AutomationPoint(time: 0, value: 1)],
                       [AutomationPoint(time: 1, value: 1), start],
                       [start, AutomationPoint(id: start.id, time: 1, value: 1)]] {
            #expect(throws: RebaseCoreError.self) {
                try AutomationLane(parameter: .pan, points: points).validate()
            }
        }
    }
}
