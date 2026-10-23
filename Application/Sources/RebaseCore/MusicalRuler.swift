import Foundation

public struct MusicalRulerTick: Codable, Equatable, Sendable {
    public let seconds: Double
    /// True at a bar boundary. The label is the one-based bar number.
    public let bar: Bool
    public let label: String
}

/// Shared display policy extracted from the macOS arrangement. Tick density and
/// bar labels are application policy, not recovered reference display behavior.
/// TempoMap retains its checked native clock arithmetic when one is present.
/// This projection neither changes timing domains nor resolves source events.
public enum MusicalRuler {
    public static let maximumDuration: Double = 86_400
    public static let maximumTicks = 8_192
    public static let pixelsPerSecondRange: ClosedRange<Double> = 4...420

    public static func defaultDuration(for project: Project) -> Double {
        min(maximumDuration, max(30, project.arrangementDuration + 8))
    }

    /// Returns the first 8,192 ticks at most. A host drawing an extent with more
    /// ticks must leave the remaining span unlabeled rather than invent timing.
    public static func ticks(project: Project, duration: Double, pixelsPerSecond: Double) throws -> [MusicalRulerTick] {
        guard duration.isFinite, (0...maximumDuration).contains(duration) else {
            throw MusicalTimeError.invalidPosition("Ruler duration must be finite and between 0 and 86,400 seconds.")
        }
        guard pixelsPerSecond.isFinite, pixelsPerSecondRange.contains(pixelsPerSecond) else {
            throw MusicalTimeError.invalidPosition("Ruler scale must be finite and between 4 and 420 pixels per second.")
        }
        try project.tempoMap.validate()
        try project.signatureMap.validate()
        let end = try project.tempoMap.beat(atSeconds: duration)
        let fastest = project.tempoMap.events.map(\.bpm).max()!
        let minimumSpacing = 12.0 / pixelsPerSecond
        var ticks: [MusicalRulerTick] = []
        for (index, signature) in project.signatureMap.events.enumerated() {
            guard signature.beat <= end else { break }
            let nextBoundary = index + 1 < project.signatureMap.events.count
                ? project.signatureMap.events[index + 1].beat : nil
            let limit = min(end, nextBoundary ?? end)
            let beatSize = 4.0 / Double(signature.denominator)
            let barSize = Double(signature.numerator) * beatSize
            // Zoom changes visual density only. Snap resolution is independent.
            let showBeats = beatSize * 60 / fastest >= minimumSpacing
            let barStride = max(1, ceil(minimumSpacing * fastest / 60 / barSize))
            let step = showBeats ? beatSize : barSize * barStride
            var beat = signature.beat
            while beat <= limit {
                // The next signature owns its boundary; an unrelated future
                // signature must not suppress a tick at the visible endpoint.
                if let nextBoundary, beat >= nextBoundary { break }
                let seconds = try project.tempoMap.seconds(atBeat: beat)
                if seconds > duration { break }
                let position = try project.signatureMap.position(atBeat: beat)
                guard seconds.isFinite, seconds >= 0,
                      ticks.last.map({ seconds > $0.seconds }) ?? true else {
                    throw MusicalTimeError.invalidPosition("Ruler tick positions must be finite and strictly increasing.")
                }
                ticks.append(MusicalRulerTick(seconds: seconds,
                    bar: position.beat == 1 && position.sixteenth == 1 && position.tick == 0,
                    label: "\(position.bar)"))
                if ticks.count == maximumTicks { return ticks }
                beat += step
            }
        }
        return ticks
    }
}
