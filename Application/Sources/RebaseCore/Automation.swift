import Foundation

/// Rebase's explicit automation domains; these are not normalized VST parameters.
public enum AutomationParameter: String, Codable, CaseIterable {
    case gainDB
    case pan

    public var valueRange: ClosedRange<Double> {
        switch self {
        case .gainDB: return -96...24
        case .pan: return -1...1
        }
    }
}

public enum AutomationInterpolation: String, Codable, CaseIterable {
    case linear
    case step
}

/// Time is absolute project seconds. Interpolation belongs to the outgoing segment.
public struct AutomationPoint: Codable, Equatable, Identifiable {
    public var id: UUID
    public var time: Double
    public var value: Double
    public var interpolation: AutomationInterpolation

    public init(id: UUID = UUID(), time: Double, value: Double,
                interpolation: AutomationInterpolation = .linear) {
        self.id = id; self.time = time; self.value = value
        self.interpolation = interpolation
    }
}

/// This is Rebase's defined curve behavior, not a claim of Reference equivalence.
/// Gain interpolation occurs in dB; conversion to linear amplitude follows evaluation.
public struct AutomationLane: Codable, Equatable, Identifiable {
    public var id: UUID
    public var parameter: AutomationParameter
    public var isReadEnabled: Bool
    public var points: [AutomationPoint]

    public init(id: UUID = UUID(), parameter: AutomationParameter,
                isReadEnabled: Bool = true, points: [AutomationPoint] = []) {
        self.id = id; self.parameter = parameter
        self.isReadEnabled = isReadEnabled; self.points = points
    }

    public func validate() throws {
        guard Set(points.map(\.id)).count == points.count else {
            throw RebaseCoreError.invalidProject("Automation point identifiers must be unique within a lane.")
        }
        var previousTime: Double = -1
        for point in points {
            guard point.time.isFinite, point.time >= 0, point.time <= 86_400,
                  point.time > previousTime, point.value.isFinite,
                  parameter.valueRange.contains(point.value) else {
                throw RebaseCoreError.invalidProject(
                    "Automation points need unique increasing times within 24 hours and valid \(parameter.rawValue) values.")
            }
            previousTime = point.time
        }
    }

    /// Validate after loading/editing, before repeated per-sample evaluation.
    /// Disabled or empty lanes and invalid query times return the caller's manual value.
    /// Before/after the curve, hold its first/last value. At a point, use that point's value.
    public func value(at time: Double, fallback: Double) -> Double {
        guard isReadEnabled, time.isFinite, time >= 0,
              let first = points.first, let last = points.last else { return fallback }
        if time <= first.time { return first.value }
        if time >= last.time { return last.value }
        var lower = 0
        var upper = points.count - 1
        while upper - lower > 1 {
            let middle = lower + (upper - lower) / 2
            if points[middle].time <= time { lower = middle } else { upper = middle }
        }
        let left = points[lower], right = points[upper]
        if left.interpolation == .step { return left.value }
        let fraction = (time - left.time) / (right.time - left.time)
        return left.value + fraction * (right.value - left.value)
    }

    /// Exact-time insertion replaces the existing point; moving an ID replaces its old point.
    /// Validation completes before mutation, including when the new point is malformed.
    public mutating func upsert(_ point: AutomationPoint) throws {
        var candidate = self
        candidate.points.removeAll { $0.id == point.id || $0.time == point.time }
        candidate.points.append(point)
        candidate.points.sort { $0.time < $1.time }
        try candidate.validate()
        self = candidate
    }

    public mutating func removePoint(id: UUID) {
        points.removeAll { $0.id == id }
    }
}
